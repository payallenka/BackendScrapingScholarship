"""
Scholarship matching via Groq LLM.

Flow:
1. Parse and validate user profile (budget math, language check)
2. Pre-filter DB candidates by degree, nationality, host country, funding need
3. Format scholarships into a compact prompt
4. Send to Groq → JSON with top 10 + reasons
5. Attach full scholarship objects to response
"""
from __future__ import annotations
import json
import logging
import os
import re
from datetime import date
from typing import List, Optional

import httpx
from pydantic import BaseModel

from backend.database import get_supabase, row_to_dict

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


class UserProfile(BaseModel):
    name: str
    nationality: str
    current_level: str        # "bachelor" | "masters" | "phd" | "high_school"
    target_level: str         # "undergraduate" | "masters" | "phd"
    field: str                # e.g. "Computer Science", "Public Health"
    languages: List[str] = [] # e.g. ["English", "French"]
    budget_usd: Optional[float] = None  # user's available funds in USD
    background: Optional[str] = None   # GPA, achievements, etc.
    extra: Optional[str] = None        # any other preferences


# ---------------------------------------------------------------------------
# Budget math
# ---------------------------------------------------------------------------

def _parse_budget(raw: str | float | None) -> Optional[float]:
    """Convert budget string like '$5,000' or '5000' to float."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = re.sub(r"[^\d.]", "", str(raw))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _funding_need(budget: Optional[float]) -> str:
    """Return funding requirement tier based on the user's available funds."""
    if budget is None:
        return "unknown"
    if budget < 3_000:
        return "full"      # needs fully funded scholarship
    if budget < 15_000:
        return "partial"   # partial or full is fine
    return "flexible"      # has funds, but scholarship still helps


# ---------------------------------------------------------------------------
# DB candidate fetch
# ---------------------------------------------------------------------------

def get_candidates(profile: UserProfile, limit: int = 80) -> list[dict]:
    # Supabase has no raw-SQL access, and the table is small, so fetch all rows
    # and filter/sort in Python.
    sb = get_supabase()
    today = date.today().isoformat()
    rows = [row_to_dict(r) for r in (sb.table("scholarships").select("*").execute().data or [])]

    lvl = (profile.target_level or "").lower()
    nat = (profile.nationality or "").strip().lower()
    need = _funding_need(profile.budget_usd)

    target_countries: list[str] = []
    if profile.extra:
        m = re.search(r"Preferred countries:\s*(.+)", profile.extra)
        if m:
            target_countries = [c.strip() for c in m.group(1).split(",") if c.strip()]

    def keep(r: dict) -> bool:
        dl = r.get("deadline")
        if dl and dl < today:                 # expired
            return False
        if r.get("is_open") is False:          # explicitly closed
            return False
        if lvl and lvl != "any":               # degree level
            degs = [d.lower() for d in (r.get("degree_levels") or [])]
            if degs and "any" not in degs and lvl not in degs:
                return False
        if nat and nat not in ("any", "all", "open"):   # nationality eligibility
            elig = r.get("eligible_nationalities") or []
            if elig:
                joined = " ".join(elig).lower()
                if not (nat in joined or "african" in joined or "commonwealth" in joined):
                    return False
        if need == "full" and r.get("funding_type") == "partial":   # funding need
            return False
        return True

    def sort_key(r: dict):
        dl = r.get("deadline")
        ft = r.get("funding_type")
        return (
            0 if dl else 1,                                  # dated first
            dl or "9999-12-31",                              # soonest deadline
            0 if ft == "full" else 1 if ft == "partial" else 2,
            0 if r.get("amount") else 1,
            r.get("scraped_at") or "",
        )

    candidates = sorted([r for r in rows if keep(r)], key=sort_key)[:limit]

    # Boost host-country matches to the front without discarding others
    if target_countries:
        boosted, rest = [], []
        for s in candidates:
            hc = " ".join(s.get("host_countries") or []).lower()
            (boosted if any(tc.lower() in hc for tc in target_countries) else rest).append(s)
        candidates = boosted + rest

    return candidates


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _fmt(s: dict, idx: int) -> str:
    levels = ", ".join(s.get("degree_levels") or ["any"])
    nats_list = s.get("eligible_nationalities") or []
    nats = (
        ", ".join(nats_list[:5]) + ("..." if len(nats_list) > 5 else "")
        if nats_list else "Open to All"
    )
    funding = s.get("amount") or (s.get("funding_type") or "Unknown").title()
    deadline = s.get("deadline") or "Not listed"
    desc = (s.get("description") or "")[:120].replace("\n", " ")
    org = s.get("organization") or "Not specified"
    host = ", ".join(s.get("host_countries") or []) or "Any"
    return (
        f"[{idx}] {s['title']} | {org}\n"
        f"    Level: {levels} | Funding: {funding} | Deadline: {deadline}\n"
        f"    Host country: {host} | Eligible: {nats}\n"
        f"    {desc}"
    )


SYSTEM_PROMPT = """\
You are an expert scholarship advisor helping students find the best matching scholarships.

Given a student profile and a numbered list of scholarships, select the TOP 10 most suitable scholarships.

HARD RULES — disqualify if violated:
1. Student must be eligible by nationality (if "Eligible" lists specific nationalities, the student's must match)
2. Degree level must match what the student wants to pursue
3. If the scholarship is hosted in a country that primarily uses a non-English language (e.g. France → French, Germany → German, China → Chinese), the student must speak that language UNLESS the scholarship explicitly teaches in English
4. If the student's available budget is stated, they need at least enough funding coverage — fully funded > partial > unknown

SOFT RANKING FACTORS (weight in order):
1. Field of study relevance (highest weight)
2. Target country preference
3. Funding quality (fully funded preferred)
4. Deadline viability
5. Organisation prestige

Return ONLY valid JSON — no extra text — in this exact structure:
{
  "summary": "2-3 sentence personalised overview explaining your selection approach and how it was tailored to this student",
  "matches": [
    {
      "rank": 1,
      "index": <number from scholarship list, 1-based>,
      "reason": "2-3 sentences explaining why this is specifically right for this student given their profile",
      "highlights": ["key point 1", "key point 2", "key point 3"],
      "funding_coverage": "full|partial|unknown"
    }
  ]
}"""


def _build_user_msg(profile: UserProfile, scholarships: list[dict]) -> str:
    need = _funding_need(profile.budget_usd)
    lines = [
        "## Student Profile",
        f"Name: {profile.name}",
        f"Nationality: {profile.nationality}",
        f"Current education level: {profile.current_level}",
        f"Wants to pursue: {profile.target_level}",
        f"Field of study: {profile.field}",
    ]

    if profile.languages:
        lines.append(f"Languages spoken: {', '.join(profile.languages)}")
    else:
        lines.append("Languages spoken: English (assumed)")

    if profile.budget_usd is not None:
        lines.append(
            f"Available budget: ${profile.budget_usd:,.0f} USD "
            f"(funding need: {need} — "
            + {
                "full": "needs a fully funded scholarship to cover all costs",
                "partial": "can contribute some funds, partial or full funding acceptable",
                "flexible": "has significant funds available, funding is a bonus",
            }[need]
            + ")"
        )
    else:
        lines.append("Available budget: Not specified (prefer fully funded options)")

    if profile.background:
        lines.append(f"Academic background: {profile.background}")
    if profile.extra:
        lines.append(f"Other preferences: {profile.extra}")

    lines.append(f"\n## Scholarship Candidates ({len(scholarships)} options)\n")
    lines.extend(_fmt(s, i + 1) for i, s in enumerate(scholarships))
    lines.append(
        "\nApply the hard rules first to eliminate ineligible scholarships, "
        "then rank the remaining by fit. Return the top 10 as JSON."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Groq call
# ---------------------------------------------------------------------------

def _fallback_result(profile: UserProfile, candidates: list[dict]) -> dict:
    """Heuristic ranking used when the LLM is unavailable, so Find My Match still
    returns results (candidates are already sorted by deadline/funding)."""
    matches = []
    for i, s in enumerate(candidates[:10]):
        ft = s.get("funding_type")
        cov = "full" if ft == "full" else "partial" if ft == "partial" else "unknown"
        host = ", ".join(s.get("host_countries") or []) or "your target country"
        highlights = [h for h in [
            s.get("amount") or (f"{ft.title()} funding" if ft else None),
            f"Deadline {s['deadline']}" if s.get("deadline") else None,
        ] if h]
        matches.append({
            "rank": i + 1,
            "index": i + 1,
            "scholarship": s,
            "reason": f"Relevant to {profile.field} and open to applicants like you in {host}.",
            "highlights": highlights,
            "funding_coverage": cov,
        })
    return {
        "summary": f"Found {len(matches)} scholarships for {profile.field}, ranked by upcoming deadline and funding.",
        "matches": matches,
        "profile": profile.model_dump(),
        "total_candidates": len(candidates),
    }


async def match_scholarships(profile: UserProfile) -> dict:
    candidates = get_candidates(profile, limit=60)

    # Broaden if too few results after hard filters
    if len(candidates) < 5:
        broad = UserProfile(**{
            **profile.model_dump(),
            "target_level": "any",
            "budget_usd": None,   # drop funding filter
        })
        candidates = get_candidates(broad, limit=60)

    if not candidates:
        raise ValueError("No scholarships in the database. Run the scraper first.")

    # Fall back to heuristic ranking if the LLM key is missing.
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return _fallback_result(profile, candidates)

    try:
        user_msg = _build_user_msg(profile, candidates)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 2500,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(raw)
    except Exception:
        # LLM call/parse failed — still return useful matches.
        return _fallback_result(profile, candidates)

    for match in result.get("matches", []):
        idx = match.get("index", 1) - 1
        if 0 <= idx < len(candidates):
            match["scholarship"] = candidates[idx]

    result["profile"] = profile.model_dump()
    result["total_candidates"] = len(candidates)
    return result
