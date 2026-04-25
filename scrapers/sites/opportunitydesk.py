"""Scraper for opportunitydesk.org — WordPress REST API + HTML parsing for roundup posts."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text, is_valid_scholarship_title

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
                params={"per_page": 50, "page": page, "search": "scholarship", "_fields": "id,title,link,excerpt,content,date"},
            )
            if not data or not isinstance(data, list):
                break
            for post in data:
                parsed = self._parse_post(post)
                if parsed is not None:
                    results.append(parsed)
            if len(data) < 50:
                break
            page += 1
        return results

    def _parse_post(self, post: dict):
        title = re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", "")).strip()
        url = post.get("link", "")
        excerpt = re.sub(r"<[^>]+>", " ", post.get("excerpt", {}).get("rendered", "")).strip()
        content_text = re.sub(r"<[^>]+>", " ", post.get("content", {}).get("rendered", "")).strip()

        # Skip person-profile posts and posts with no scholarship-related keywords
        if not is_valid_scholarship_title(title, excerpt or content_text[:400]):
            return None

        deadline_raw = find_deadline_in_text(excerpt) or find_deadline_in_text(content_text)

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
