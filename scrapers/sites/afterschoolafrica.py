"""
After School Africa — scraped via its WordPress REST API.

The public site is fully JS-rendered (plain HTML has no content), but the
WordPress REST API (/wp-json/wp/v2) returns posts as JSON, so we read the
"scholarship" category directly — no headless browser needed.
"""
from __future__ import annotations
import html as html_lib
import re
from typing import List

from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "After School Africa"
BASE_URL = "https://www.afterschoolafrica.com"
API = f"{BASE_URL}/wp-json/wp/v2"
CATEGORY_SLUG = "scholarship"
CATEGORY_ID_FALLBACK = 13
PER_PAGE = 100          # WordPress REST API max
# Keep the recent/current slice (~400 newest), not the entire multi-year archive
# — the site's own "Scholarships" filter shows only the current ones (~400), and
# the deep archive is years of closed cycles.
MAX_API_PAGES = 4

# Only keep scholarships hosted in these four countries.
TARGET_COUNTRIES = {
    "United States": re.compile(
        r"\bunited states\b|\bu\.s\.a?\.?\b|\busa\b|\bamericas?\b|\bamerican\b", re.I),
    "United Kingdom": re.compile(
        r"\bunited kingdom\b|\bu\.k\.?\b|\bbritain\b|\bbritish\b|\bengland\b"
        r"|\bscotland\b|\bwales\b|\bchevening\b", re.I),
    "Canada": re.compile(r"\bcanada\b|\bcanadian\b|\bquebec\b|\bontario\b", re.I),
    "France": re.compile(r"\bfrance\b|\bfrench\b|\beiffel\b|\bsorbonne\b|\bparis\b", re.I),
}


def _detect_countries(text: str) -> list[str]:
    return [c for c, pat in TARGET_COUNTRIES.items() if pat.search(text)]


# Posts embed a "Related:" / "You may also like" block of links to OTHER
# scholarships (with their own amounts/deadlines). Cut it so we don't extract a
# neighbouring scholarship's "$50 stipend" or deadline as if it were this one's.
_NOISE_CUT_RE = re.compile(
    r"\b(?:related|you may also like|see also|recommended|read also|don'?t miss)\s*:",
    re.I,
)


def _clean_content(content: str) -> str:
    return _NOISE_CUT_RE.split(content, 1)[0]


_MONEY = r"(?:US\$|\$|€|£|USD|EUR|GBP)\s?\d[\d,]*(?:\.\d+)?\s*(?:million|billion)?"
_MONEY_RE = re.compile(_MONEY, re.I)

# High-confidence funding-type wording (always preferred).
_FUNDING_RE = re.compile(
    r"fully funded|full tuition|tuition (?:waiver|coverage)"
    r"|\d{1,3}%\s*(?:tuition|funding|coverage|scholarship)"
    r"|partial(?:ly)?\s*fund\w*|full scholarship",
    re.I,
)
# A currency figure with award context next to it — so market sizes / salaries /
# fees ("$7.32 billion market", "$50 fee") aren't picked up.
_CTX_MONEY_RE = re.compile(
    rf"(?:worth|valued at|award(?:ed)?\s+of|grant of|stipend of|prize of|"
    rf"bursary of|scholarship of|up to|receives?|covers?|provides?)\s+{_MONEY}"
    rf"|{_MONEY}\s*(?:per\s+(?:year|annum|month|semester)|annually|scholarship|"
    rf"grant|award|stipend|bursary|prize|in\s+(?:funding|scholarships?|prizes?)|towards)",
    re.I,
)


def _extract_amount(content: str):
    fm = _FUNDING_RE.search(content)
    if fm:
        return fm.group(0).strip()
    cm = _CTX_MONEY_RE.search(content)
    if not cm:
        return None
    money = _MONEY_RE.search(cm.group(0))
    if not money:
        return None
    mstr = money.group(0).strip()
    if re.search(r"million|billion", mstr, re.I):
        return mstr
    # Plain figures must be >= 1,000 — real awards are; travel/licence/fee
    # components ("up to £850 travel", "licences valued at $150") are not.
    num = re.sub(r"[^\d.]", "", mstr) or "0"
    try:
        return mstr if float(num) >= 1000 else None
    except ValueError:
        return None


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


class AfterSchoolAfricaScraper(BaseScraper):
    name = "afterschoolafrica"
    base_url = BASE_URL
    delay = 0.4  # it's a JSON API, so we can poll faster than HTML scraping
    check_links = False  # URLs come from the WP API and are known-valid

    def _category_id(self) -> int:
        cats = self.get_json(f"{API}/categories", params={"slug": CATEGORY_SLUG})
        if isinstance(cats, list) and cats:
            return cats[0].get("id", CATEGORY_ID_FALLBACK)
        return CATEGORY_ID_FALLBACK

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        cid = self._category_id()

        # Fetch the full scholarship archive (the cheap JSON API lets us paginate
        # deep), not just the most recent page — independent of the small global
        # max_pages used for slow HTML scrapers. A transient failure (rate limit /
        # timeout) on one page must not truncate the whole archive, so retry a
        # page a few times before giving up.
        page = 1
        page_fails = 0
        while page <= MAX_API_PAGES:
            posts = self.get_json(
                f"{API}/posts",
                params={
                    "categories": cid,
                    "per_page": PER_PAGE,
                    "page": page,
                    "orderby": "date",
                    "order": "desc",
                    "_fields": "id,link,title,excerpt,content,date",
                },
            )
            if not isinstance(posts, list):
                # transient error — retry the same page up to 3 times
                page_fails += 1
                if page_fails >= 3:
                    break
                continue
            page_fails = 0
            if not posts:
                break  # genuine end of the archive
            page += 1

            for p in posts:
                title = _strip_html(p.get("title", {}).get("rendered", ""))
                if not title:
                    continue
                content = _clean_content(_strip_html(p.get("content", {}).get("rendered", "")))
                excerpt = _strip_html(p.get("excerpt", {}).get("rendered", "")) or content[:400]

                # Only keep scholarships hosted in the US / UK / Canada / France.
                countries = _detect_countries(f"{title} {content}")
                if not countries:
                    continue

                deadline_raw = find_deadline_in_text(content)
                amount = _extract_amount(content)

                results.append(make_scholarship(
                    title=title,
                    source_url=p.get("link") or BASE_URL,
                    source_site=SITE_NAME,
                    description=excerpt[:600],
                    degree_levels_raw=f"{title} {content[:300]}",
                    deadline_raw=deadline_raw,
                    amount=amount,
                    host_countries=countries,
                    tags=["After School Africa", "Africa"],
                ))

        return results
