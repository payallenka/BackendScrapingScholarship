"""
Scholarship matching via Groq LLM.

Flow:
1. Filter DB for candidates matching user's target degree + open deadlines
2. Format scholarships into a compact prompt
3. Send to Groq → JSON with top 10 + reasons
4. Attach full scholarship objects to response
"""
from __future__ import annotations
import json
import logging
import os
from datetime import date
from typing import Optional

import httpx
from pydantic import BaseModel

from backend.database import get_conn, row_to_dict

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


class UserProfile(BaseModel):
    name: str
    nationality: str
    current_level: str       # "bachelor" | "masters" | "phd" | "high_school"
    target_level: str        # "undergraduate" | "masters" | "phd"
    field: str               # e.g. "Computer Science", "Public Health"
    background: Optional[str] = None   # GPA, achievements, etc.
    extra: Optional[str] = None        # any other preferences


# ---------------------------------------------------------------------------
# DB candidate fetch
# ---------------------------------------------------------------------------

def get_candidates(profile: UserProfile, limit: int = 100) -> list[dict]:
    conn = get_conn()
    today = date.today().isoformat()

    conditions = ["(deadline IS NULL OR deadline >= ?)"]
    params: list = [today]

    # Match target degree level
    lvl = profile.target_level.lower()
    if lvl and lvl != "any":
        conditions.append('(degree_levels LIKE ? OR degree_levels LIKE \'%"any"%\')')
        params.append(f'%"{lvl}"%')

    where = "WHERE " + " AND ".join(conditions)

    # Prioritise: future deadlines first, then has amount, then recency
    order = """ORDER BY
        CASE WHEN deadline IS NULL THEN 1 ELSE 0 END,
        deadline ASC,
        CASE WHEN amount IS NOT NULL THEN 0 ELSE 1 END,
        scraped_at DESC"""

    rows = conn.execute(
        f"SELECT * FROM scholarships {where} {order} LIMIT ?",
        params + [limit],
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _fmt(s: dict, idx: int) -> str:
    levels = ", ".join(s.get("degree_levels") or ["any"])
    nats = ", ".join(s.get("eligible_nationalities") or []) or "Open to All"
    funding = s.get("amount") or (s.get("funding_type") or "Unknown").title()
    deadline = s.get("deadline") or "Not listed"
    desc = (s.get("description") or "")[:180].replace("\n", " ")
    org = s.get("organization") or ""
    return (
        f"[{idx}] {s['title']}\n"
        f"    Provider: {org or 'Not specified'}\n"
        f"    Level: {levels} | Funding: {funding} | Eligibility: {nats}\n"
        f"    Deadline: {deadline}\n"
        f"    Info: {desc}"
    )


SYSTEM_PROMPT = """\
You are an expert scholarship advisor helping students find the best scholarships.

Given a student profile and a numbered list of scholarships, select the TOP 10 most suitable scholarships.

Prioritise based on:
- Nationality eligibility (student must be eligible)
- Degree level match (must match what they want to study)
- Field of study relevance
- Funding quality (fully funded > partial > unknown)
- Deadline viability (sooner open deadlines are better)

Return ONLY valid JSON — no extra text — in this exact structure:
{
  "summary": "2-3 sentence personalised overview for the student explaining your selection approach",
  "matches": [
    {
      "rank": 1,
      "index": <number from list, 1-based>,
      "reason": "2-3 sentences explaining why this scholarship is specifically right for this student",
      "highlights": ["key point 1", "key point 2", "key point 3"]
    }
  ]
}"""


def _build_user_msg(profile: UserProfile, scholarships: list[dict]) -> str:
    lines = [
        "## Student Profile",
        f"Name: {profile.name}",
        f"Nationality: {profile.nationality}",
        f"Current education: {profile.current_level}",
        f"Wants to pursue: {profile.target_level}",
        f"Field of study: {profile.field}",
    ]
    if profile.background:
        lines.append(f"Background / achievements: {profile.background}")
    if profile.extra:
        lines.append(f"Other preferences: {profile.extra}")

    lines.append(f"\n## Available Scholarships ({len(scholarships)} candidates)\n")
    lines.extend(_fmt(s, i + 1) for i, s in enumerate(scholarships))
    lines.append("\nSelect the top 10 most suitable scholarships for this student and return JSON.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Groq call
# ---------------------------------------------------------------------------

async def match_scholarships(profile: UserProfile) -> dict:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set. Add it to your .env file.")

    candidates = get_candidates(profile, limit=100)
    if len(candidates) < 5:
        # Broaden search if too few results
        candidates = get_candidates(
            UserProfile(**{**profile.model_dump(), "target_level": "any"}), limit=100
        )

    if not candidates:
        raise ValueError("No scholarships in the database. Run the scraper first.")

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

    # Attach full scholarship data for each match
    for match in result.get("matches", []):
        idx = match.get("index", 1) - 1  # 1-based → 0-based
        if 0 <= idx < len(candidates):
            match["scholarship"] = candidates[idx]

    result["profile"] = profile.model_dump()
    result["total_candidates"] = len(candidates)
    return result
