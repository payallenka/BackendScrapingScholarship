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
PER_PAGE = 30


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


class AfterSchoolAfricaScraper(BaseScraper):
    name = "afterschoolafrica"
    base_url = BASE_URL
    delay = 1.0

    def _category_id(self) -> int:
        cats = self.get_json(f"{API}/categories", params={"slug": CATEGORY_SLUG})
        if isinstance(cats, list) and cats:
            return cats[0].get("id", CATEGORY_ID_FALLBACK)
        return CATEGORY_ID_FALLBACK

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        cid = self._category_id()

        for page in range(1, self.max_pages + 1):
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
            if not isinstance(posts, list) or not posts:
                break

            for p in posts:
                title = _strip_html(p.get("title", {}).get("rendered", ""))
                if not title:
                    continue
                content = _strip_html(p.get("content", {}).get("rendered", ""))
                excerpt = _strip_html(p.get("excerpt", {}).get("rendered", "")) or content[:400]
                deadline_raw = find_deadline_in_text(content)

                amount = None
                m = re.search(r"fully funded|full scholarship|\$[\d,]+|€[\d,]+|£[\d,]+", content, re.I)
                if m:
                    amount = m.group(0)

                results.append(make_scholarship(
                    title=title,
                    source_url=p.get("link") or BASE_URL,
                    source_site=SITE_NAME,
                    description=excerpt[:600],
                    degree_levels_raw=f"{title} {content[:300]}",
                    deadline_raw=deadline_raw,
                    amount=amount,
                    tags=["After School Africa", "Africa"],
                ))

        return results
