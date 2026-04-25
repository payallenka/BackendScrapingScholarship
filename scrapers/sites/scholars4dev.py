"""Scraper for scholars4dev.com — uses WordPress REST API for reliability."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

WP_API = "https://www.scholars4dev.com/wp-json/wp/v2/posts"
SITE_NAME = "Scholars4Dev"


class Scholars4DevScraper(BaseScraper):
    name = "scholars4dev"
    base_url = "https://www.scholars4dev.com"
    delay = 1.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            data = self.get_json(WP_API, params={"per_page": 50, "page": page, "_fields": "id,title,link,excerpt,content,date,tags,categories"})
            if not data or not isinstance(data, list) or len(data) == 0:
                break
            for post in data:
                results.append(self._parse_post(post))
            if len(data) < 50:
                break
            page += 1
        return results

    def _parse_post(self, post: dict) -> NormalizedScholarship:
        title = post.get("title", {}).get("rendered", "").strip()
        title = re.sub(r"<[^>]+>", "", title)
        url = post.get("link", "")
        excerpt_html = post.get("excerpt", {}).get("rendered", "")
        content_html = post.get("content", {}).get("rendered", "")
        description = re.sub(r"<[^>]+>", " ", excerpt_html).strip()
        content_text = re.sub(r"<[^>]+>", " ", content_html).strip()

        deadline_raw = find_deadline_in_text(description) or find_deadline_in_text(content_text)

        # Infer degree level from title/description
        degree_raw = title + " " + description

        # Extract amount
        amount_match = re.search(r"(\$[\d,]+|€[\d,]+|£[\d,]+|fully funded|full scholarship|full tuition)", description, re.I)
        amount = amount_match.group(0) if amount_match else None

        return make_scholarship(
            title=title,
            source_url=url,
            source_site=SITE_NAME,
            description=description[:800] if description else None,
            amount=amount,
            degree_levels_raw=degree_raw,
            deadline_raw=deadline_raw,
        )
