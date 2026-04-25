"""
Normalized scholarship schema and normalization utilities.
All scrapers output NormalizedScholarship instances.
"""
from __future__ import annotations
import html as html_lib
import re
import uuid
import warnings
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, field_validator
from dateutil import parser as dateparser
from dateutil.parser._parser import UnknownTimezoneWarning


# ---------------------------------------------------------------------------
# Deadline label detection — used by scrapers and extract_deadline_from_soup
# ---------------------------------------------------------------------------

# Matches any common deadline label variant followed by the date value.
DEADLINE_LABEL_RE = re.compile(
    r"(?:"
    r"(?:application(?:\s+submission)?\s+)?deadline"
    r"|closing\s+dates?"
    r"|due\s+dates?"
    r"|apply\s+(?:by|before|on\s+or\s+before)"
    r"|last\s+(?:date|day)(?:\s+to\s+(?:apply|submit))?"
    r"|applications?\s+(?:close|due|are\s+due|accepted\s+until|close\s+on)"
    r"|submission\s+(?:date|deadline)"
    r")"
    r"[:\s]+([^\n|<]{3,80})",
    re.I,
)

# Simpler keyword check — used to identify whether an HTML element IS a label.
_DEADLINE_KEYWORD_RE = re.compile(
    r"(?:application(?:\s+submission)?\s+)?(?:deadline|closing\s+dates?|due\s+dates?)"
    r"|apply\s+(?:by|before)"
    r"|last\s+(?:date|day)"
    r"|submission\s+(?:date|deadline)",
    re.I,
)


def find_deadline_in_text(text: str) -> Optional[str]:
    """Return the raw date string captured after a deadline label, or None."""
    if not text:
        return None
    m = DEADLINE_LABEL_RE.search(text)
    return m.group(1).strip() if m else None


class NormalizedScholarship(BaseModel):
    id: str
    title: str
    organization: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[str] = None        # "Fully Funded" | "$10,000" | "Partial" | None
    amount_usd: Optional[float] = None
    funding_type: Optional[str] = None  # "full" | "partial" | "unknown"
    deadline: Optional[str] = None      # ISO date YYYY-MM-DD
    deadline_raw: Optional[str] = None
    degree_levels: List[str] = []       # undergraduate | masters | phd | postdoctoral | any
    fields_of_study: List[str] = []
    eligible_nationalities: List[str] = []
    host_countries: List[str] = []
    source_url: str
    source_site: str
    tags: List[str] = []
    scraped_at: str
    is_open: Optional[bool] = None
    image_url: Optional[str] = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        v = html_lib.unescape(v).strip()
        v = re.sub(r"(?i)\s+for\s+(?:young|emerging|african|nigerian|international|students|women|graduates|researchers|changemakers|scientists|journalists|entrepreneurs|south africans|kenyans|ghanaians|leaders).*?$", "", v)
        v = re.sub(r"(?i)\s*\((?:fully funded|usd|eur|gbp|\d+-year|partially funded|partial).*?\)", "", v)
        return v.strip().strip('.')


# ---------------------------------------------------------------------------
# Degree level normalizer
# ---------------------------------------------------------------------------

_DEGREE_MAP = {
    "undergraduate": [
        "undergraduate", "bachelor", "bachelors", "b.sc", "b.a.", " bsc ", " bs ", " ba ",
        "first degree", " ug ", "associate degree",
    ],
    "masters": [
        "master's", "masters", " msc", "m.sc", " ma ", " mba", "m.eng", "m.phil",
        "graduate degree", "taught postgraduate",
    ],
    "phd": ["ph.d", " phd", "doctorate", "doctoral", "dphil", "research degree"],
    "postdoctoral": ["postdoc", "post-doc", "postdoctoral"],
}

_ROUNDUP_PATTERN = re.compile(
    r"^\d+\+?\s|^top\s+\d|^best\s+\d|^list\s+of|scholarships?\s+for\s+\d{4}|multiple scholarships",
    re.I,
)

# Keywords that indicate a post is about an actual scholarship / funding opportunity
_SCHOLARSHIP_KW_RE = re.compile(
    r"\b(?:scholarship|fellowship|grant|bursary|award|prize|fund(?:ing|ed)?|"
    r"programme|internship|exchange|residency|competition|"
    r"call\s+for|fully\s+funded|stipend|application|opportunity|opportunities|"
    r"tuition|endowment|assistantship|vacancy|position)\b",
    re.I,
)

# Patterns that strongly indicate a non-scholarship post
_JUNK_POST_RE = re.compile(
    r"\b(?:person\s+of\s+the\s+(?:month|year)|volunteer\s+of\s+the\s+(?:month|year)|"
    r"employee\s+of\s+the|in\s+memoriam|obituary|"
    r"(?:is|was|named)\s+(?:\w+\s+)?(?:young\s+person|leader\s+of))\b"
    # WordPress default post
    r"|^hello\s+world\b"
    # Social media follow links (e.g. "Erasmus+ on X", "Erasmus+ on Facebook")
    r"|\bon\s+(?:x|facebook|twitter|instagram|linkedin|youtube|tiktok)\s*$"
    # Tip/advice articles, not scholarships
    r"|\b\d+\s+\w+\s+(?:scholarship|funding|application)\s+tips?\b"
    r"|\bscholarship\s+(?:application\s+)?tips?\b"
    # Generic navigation or category pages
    r"|^find\s+scholarships?\s+to\b"
    r"|^scholarships?\s+and\s+funding\s*$"
    r"|^scholarships?\s+(?:and\s+)?(?:grants?)?\s*$"
    r"|^funding\s+(?:opportunities?)?\s*$"
    # Numbered tip/list articles (Scholarship Tip #6, Top 10+ Scholarships...)
    r"|\bscholarships?\s+tip\s*#?\d*\b"
    r"|^top\s+\d+\+?\s+"
    r"|^list\s+of\s+"
    # Story / profile posts about a person who won a scholarship
    r"|\d+-year-old\b.{0,40}\b(?:wins?|won|bags?|earn|graduate)\b"
    r"|\b(?:wins?|won|bags?|earned|secured)\b.{0,50}\b(?:scholarship|fellowship)\b(?!.*program)"
    r"|\b(?:how|why)\s+\w[\w\s]{2,30}\b(?:won|got|earned|secured|bags?)\b"
    # Correction / update notices
    r"|^correction\s*:"
    # Generic guide / listicle pages
    r"|^top\s+countries\s+offer"
    r"|post.?study\s+work\s+visas?\b"
    # Catch-all ad/placeholder slugs (e.g. "GSO Plug 2")
    r"|^\w{2,5}\s+plug\s*\d*$",
    re.I,
)


def is_valid_scholarship_title(title: str, description: str = "") -> bool:
    """Return True when title+description look like an actual scholarship post.

    Rejects person-profile posts (Person of the Month, etc.) and posts
    that contain no scholarship-related keywords at all.
    """
    if _JUNK_POST_RE.search(title):
        return False
    combined = title + " " + description[:400]
    return bool(_SCHOLARSHIP_KW_RE.search(combined))


def normalize_degree_levels(raw: str | List[str], title: str = "") -> List[str]:
    if isinstance(raw, list):
        raw = " ".join(raw)
    # Roundup posts like "35+ scholarships" → any
    if _ROUNDUP_PATTERN.search(title or raw):
        return ["any"]

    # Pad with spaces so word-boundary checks work
    padded = f" {raw.lower()} "
    levels = set()
    for level, keywords in _DEGREE_MAP.items():
        if any(k in padded for k in keywords):
            levels.add(level)

    # "doctoral" alone should not also produce "masters" via "graduate"
    if "phd" in levels and "graduate degree" not in padded and "masters" not in padded:
        levels.discard("masters")

    return sorted(levels) if levels else ["any"]


# ---------------------------------------------------------------------------
# Amount / funding type
# ---------------------------------------------------------------------------

_CURRENCY_RATES = {"€": 1.08, "£": 1.27, "CHF": 1.12, "CAD": 0.74, "AUD": 0.65}

_FULL_KEYWORDS = [
    "fully funded", "full scholarship", "full tuition", "full funding",
    "100% funded", "covers all", "all expenses", "full award", "full stipend",
    "covers tuition", "tuition and living", "all costs covered",
]
_PARTIAL_KEYWORDS = [
    "partial", "partially funded", "partial scholarship",
    "tuition waiver", "tuition only", "living allowance only",
    "up to", "varies",
]


def parse_amount(text: str) -> tuple[str | None, Optional[float], str | None]:
    """Return (display string | None, USD float | None, funding_type)."""
    if not text:
        return (None, None, None)
    text = html_lib.unescape(text.strip())
    lower = text.lower()

    if any(k in lower for k in _FULL_KEYWORDS):
        return ("Fully Funded", None, "full")

    if any(k in lower for k in _PARTIAL_KEYWORDS):
        # Try to extract a number
        numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
        if numbers:
            val = float(numbers[-1].replace(",", ""))
            usd = val
            for sym, rate in _CURRENCY_RATES.items():
                if sym in text:
                    usd = val * rate
                    break
            return (text, round(usd, 2), "partial")
        return (text, None, "partial")

    # Explicit currency amounts
    numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    if numbers:
        val = float(numbers[-1].replace(",", ""))
        usd = val
        for sym, rate in _CURRENCY_RATES.items():
            if sym in text:
                usd = val * rate
                break
        ftype = "full" if usd > 20000 else "partial"
        return (text, round(usd, 2), ftype)

    return (None, None, None)


def infer_funding_from_description(desc: str) -> tuple[str | None, str | None]:
    """Try to detect funding type from a description when no explicit amount is given."""
    if not desc:
        return (None, None)
    lower = desc.lower()
    if any(k in lower for k in _FULL_KEYWORDS):
        return ("Fully Funded", "full")
    if any(k in lower for k in _PARTIAL_KEYWORDS):
        return (None, "partial")
    # Currency amounts in description
    m = re.search(r"(\$|€|£)([\d,]+)", desc)
    if m:
        return (f"{m.group(1)}{m.group(2)}", "partial")
    return (None, None)


# ---------------------------------------------------------------------------
# Eligibility / nationality inference
# ---------------------------------------------------------------------------

_AFRICAN_KEYWORDS = [
    "african students", "students from africa", "africa only", "sub-saharan",
    "for africans", "open to africans",
]
_DEVELOPING_KEYWORDS = [
    "developing countries", "low.*income countr", "lmic", "low and middle income",
    "low- and middle-income", "emerging economies", "global south",
]
_SPECIFIC_COUNTRY = re.compile(
    r"\bfor students from ([A-Z][a-zA-Z\s,]+(?:and [A-Z][a-zA-Z]+)?)\b"
)


def infer_eligibility(description: str, tags: List[str] = []) -> List[str]:
    if not description:
        return []
    lower = description.lower()
    combined = lower + " " + " ".join(t.lower() for t in tags)

    if any(k in combined for k in _AFRICAN_KEYWORDS):
        return ["African"]
    if any(re.search(k, combined) for k in _DEVELOPING_KEYWORDS):
        return ["Developing Countries"]
    return []


# ---------------------------------------------------------------------------
# Deadline parser
# ---------------------------------------------------------------------------

def parse_deadline(text: str) -> Optional[str]:
    if not text:
        return None
    text = html_lib.unescape(text.strip())

    text = re.sub(r"(?i)\s+Applications?\b.*$", "", text).strip()
    text = re.sub(r"(?i)\(midnight\)", "", text)

    # Strip leading label prefixes
    text = re.sub(
        r"(?i)^(?:application(?:\s+submission)?\s+)?(?:deadline|closing\s+dates?|due\s+dates?|apply\s+(?:by|before))[:\s]+",
        "", text,
    ).strip()

    # Strip leading filler words ("is", "are", "was", "will be", "coincides with...")
    text = re.sub(r"(?i)^(?:is|are|was|will\s+be|falls?\s+on|set\s+for)\s+", "", text).strip()

    # If still complex (contains "coincides", "varies", multiple dates) → extract first real date
    if re.search(r"coincides|varies|depending|around", text, re.I):
        # Pull out first clear date pattern
        m = re.search(
            r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+(\d{4})\b",
            text, re.I,
        )
        if m:
            text = m.group(0)
        else:
            return None

    # Strip trailing context after the date (". Course starts...", "for graduate...")
    text = re.split(r"\.\s+[A-Z]|for\s+(?:courses?|graduate|undergraduate|the\s)", text)[0].strip()
    text = re.split(r"\s{2,}", text)[0].strip()

    # Remove day names
    text = re.sub(r"(?i)\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*", "", text).strip()

    # Limit length to avoid feeding a paragraph to dateparser
    text = text[:60]

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UnknownTimezoneWarning)
            dt = dateparser.parse(text, dayfirst=True)
        if dt and dt.year >= 2020:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Regex date extraction
    patterns = [
        r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+(\d{4})\b",
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+(\d{1,2}),?\s+(\d{4})\b",
        r"\b(\d{4})[/-](\d{2})[/-](\d{2})\b",
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                dt = dateparser.parse(m.group(0), dayfirst=True)
                if dt and dt.year >= 2020:
                    return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
    return None


def extract_deadline_from_soup(soup) -> Optional[str]:
    """Parse a BeautifulSoup object and return an ISO deadline date, or None.

    Tries structured HTML elements first (dt/dd, table cells, bold labels),
    then falls back to a full-page text search with DEADLINE_LABEL_RE.
    """
    # 1. Definition lists: <dt>Deadline</dt><dd>March 15</dd>
    for dt in soup.find_all("dt"):
        if _DEADLINE_KEYWORD_RE.search(dt.get_text()):
            dd = dt.find_next_sibling("dd")
            if dd:
                result = parse_deadline(dd.get_text(strip=True))
                if result:
                    return result

    # 2. Table label/value pairs: <th>Deadline</th><td>March 15</td>
    for label_cell in soup.find_all(["th", "td"]):
        cell_text = label_cell.get_text(strip=True).rstrip(": ")
        if len(cell_text) < 50 and _DEADLINE_KEYWORD_RE.fullmatch(cell_text):
            val_cell = label_cell.find_next_sibling(["td", "th"])
            if val_cell:
                result = parse_deadline(val_cell.get_text(strip=True))
                if result:
                    return result

    # 3. Elements whose class name signals a deadline
    for el in soup.find_all(class_=re.compile(r"deadline|due.?date|closing.?date", re.I)):
        text = el.get_text(" ", strip=True)
        raw = find_deadline_in_text(text) or text
        result = parse_deadline(raw[:80])
        if result:
            return result

    # 4. Bold/strong labels followed by date text in the same parent element
    for bold in soup.find_all(["strong", "b"]):
        if not _DEADLINE_KEYWORD_RE.search(bold.get_text()):
            continue
        parent = bold.parent
        if parent:
            raw = find_deadline_in_text(parent.get_text(" ", strip=True))
            if raw:
                result = parse_deadline(raw)
                if result:
                    return result

    # 5. Full-page text fallback
    raw = find_deadline_in_text(soup.get_text(" ", strip=True))
    if raw:
        return parse_deadline(raw)

    return None


# ---------------------------------------------------------------------------
# Organization extractor
# ---------------------------------------------------------------------------

_ORG_SUFFIXES = (
    "university", "université", "universität", "instituto", "institute",
    "college", "school", "academy", "foundation", "fund", "programme",
    "program", "center", "centre", "council", "agency", "commission",
    "bank", "trust", "society", "association", "fellowship", "endowment",
)

_BAD_ORG_PREFIX = re.compile(
    r"^\d|^top\s|^best\s|^list\s|^\d+\+|^multiple|^various|^several",
    re.I,
)


def extract_org_from_title(title: str) -> Optional[str]:
    """Best-effort org extraction — returns None if not confident."""
    # "Scholarship at Tsinghua University" → "Tsinghua University"
    at_match = re.search(
        r"\bat\s+([A-Z][A-Za-z\s\-\'\.]{2,50}?(?:"
        + "|".join(_ORG_SUFFIXES) + r"))\b",
        title, re.I,
    )
    if at_match:
        candidate = at_match.group(1).strip()
        if not _BAD_ORG_PREFIX.match(candidate):
            return candidate

    # "UNICAF Scholarship" / "DAAD Fellowship" — leading ACRONYM (all-caps word)
    acronym_match = re.match(
        r"^([A-Z]{2,8}(?:-[A-Z]{1,4})?)\s+(?:Scholarship|Fellowship|Award|Grant|Prize|Bursary|Program|Fund)\b",
        title,
    )
    if acronym_match:
        return acronym_match.group(1)

    return None


# ---------------------------------------------------------------------------
# Scholarship factory
# ---------------------------------------------------------------------------

def make_scholarship(
    title: str,
    source_url: str,
    source_site: str,
    **kwargs,
) -> NormalizedScholarship:
    # Decode HTML entities everywhere
    title = html_lib.unescape(title).strip()
    description = html_lib.unescape(kwargs.pop("description", None) or "").strip() or None

    # Organization — validate scraper-supplied value, then fall back to title extraction
    organization = kwargs.pop("organization", None)
    if organization:
        organization = html_lib.unescape(organization).strip()
        words = organization.split()
        # Reject multi-word fragments that are just the start of the title
        # (single-word orgs like "UNICAF" or "DAAD" are fine even if title starts with them)
        is_title_fragment = (
            len(words) >= 3
            and title.lower().startswith(organization.lower()[:min(20, len(organization))])
        )
        if _BAD_ORG_PREFIX.match(organization) or len(organization) < 3 or is_title_fragment:
            organization = None
    if not organization:
        organization = extract_org_from_title(title)

    # Amount — check explicit kwarg, then title, then description
    amount_raw = kwargs.pop("amount", None)
    amount_str, amount_usd, funding_type = parse_amount(amount_raw or "")
    if not amount_str:
        # Try extracting from title (e.g. "up to $5,000" or "Fully Funded")
        _, _, funding_type = parse_amount(title)
        m = re.search(r"(\$|€|£)([\d,]+)", title)
        if m:
            amount_str = f"{m.group(1)}{m.group(2)}"
    if not amount_str and description:
        amount_str, funding_type = infer_funding_from_description(description)

    # Deadline
    deadline_raw = kwargs.pop("deadline_raw", None) or kwargs.pop("deadline", None)
    deadline_iso = parse_deadline(deadline_raw or "")
    # Clean deadline_raw to just the date text (strip "is", filler, trailing context)
    if deadline_raw:
        cleaned = html_lib.unescape(deadline_raw).strip()
        cleaned = re.sub(r"(?i)^(?:is|are|was|will\s+be|falls?\s+on|set\s+for)\s+", "", cleaned)
        cleaned = re.sub(r"(?i)\s+Applications?\b.*$", "", cleaned).strip()
        cleaned = re.split(r"\.\s+[A-Z]|Read more|&raquo|»|\s{2,}", cleaned)[0].strip()
        cleaned = re.sub(r"(?i)\(midnight\)", "", cleaned).strip()
        deadline_raw = cleaned or deadline_raw

    # Degree levels
    degree_raw = kwargs.pop("degree_levels_raw", kwargs.pop("degree_levels", []))
    if isinstance(degree_raw, str):
        degree_levels = normalize_degree_levels(degree_raw, title=title)
    elif degree_raw:
        degree_levels = normalize_degree_levels(" ".join(degree_raw), title=title)
    else:
        degree_levels = ["any"]

    # Eligibility — use provided, or infer from description + tags
    tags = kwargs.get("tags", [])
    eligible_nationalities = kwargs.pop("eligible_nationalities", [])
    if not eligible_nationalities and description:
        eligible_nationalities = infer_eligibility(description, tags)

    return NormalizedScholarship(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, source_url)),
        title=title,
        organization=organization,
        description=description,
        amount=amount_str or None,
        amount_usd=amount_usd,
        funding_type=funding_type,
        deadline=deadline_iso,
        deadline_raw=deadline_raw,
        degree_levels=degree_levels,
        eligible_nationalities=eligible_nationalities,
        source_url=source_url,
        source_site=source_site,
        scraped_at=datetime.utcnow().isoformat(),
        **kwargs,
    )
