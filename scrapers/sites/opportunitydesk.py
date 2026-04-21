"""Scraper for opportunitydesk.org — WordPress REST API + HTML parsing for roundup posts."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

SITE_NAME = "Opportunity Desk"
WP_API = "https://opportunitydesk.org/wp-json/wp/v2/posts"


class OpportunityDeskScraper(BaseScraper):
    name = "opportunitydesk"
    base_url = "https://opportunitydesk.org"
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            data = self.get_json(
                WP_API,
                params={"per_page": 50, "page": page, "search": "scholarship", "_fields": "id,title,link,excerpt,date"},
            )
            if not data or not isinstance(data, list):
                break
            for post in data:
                results.append(self._parse_post(post))
            if len(data) < 50:
                break
            page += 1
        return results

    def _parse_post(self, post: dict) -> NormalizedScholarship:
        title = re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", "")).strip()
        url = post.get("link", "")
        excerpt = re.sub(r"<[^>]+>", " ", post.get("excerpt", {}).get("rendered", "")).strip()

        deadline_match = re.search(r"[Dd]eadline[:\s]+([^\n|<.]+)", excerpt)
        deadline_raw = deadline_match.group(1).strip() if deadline_match else None

        amount_match = re.search(r"(\$[\d,]+|€[\d,]+|£[\d,]+|fully funded|full scholarship)", excerpt, re.I)
        amount = amount_match.group(0) if amount_match else None

        return make_scholarship(
            title=title,
            source_url=url,
            source_site=SITE_NAME,
            description=excerpt[:800] if excerpt else None,
            amount=amount,
            degree_levels_raw=title + " " + excerpt,
            deadline_raw=deadline_raw,
        )
