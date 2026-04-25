"""Scraper for opportunitiesforafricans.com — WordPress REST API."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "Opportunities for Africans"
CATEGORIES = {
    "undergraduate": "https://www.opportunitiesforafricans.com/wp-json/wp/v2/posts?categories=undergraduate&per_page=50",
    "masters": "https://www.opportunitiesforafricans.com/wp-json/wp/v2/posts?per_page=50",
    "postgraduate": "https://www.opportunitiesforafricans.com/wp-json/wp/v2/posts?per_page=50",
}
WP_API = "https://www.opportunitiesforafricans.com/wp-json/wp/v2/posts"


class OpportunitiesForAfricansScraper(BaseScraper):
    name = "opportunitiesforafricans"
    base_url = "https://www.opportunitiesforafricans.com"
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        seen = set()
        for category_slug in ["scholarships"]:
            page = 1
            while page <= self.max_pages:
                data = self.get_json(
                    WP_API,
                    params={"per_page": 50, "page": page, "_fields": "id,title,link,excerpt,content,date"},
                )
                if not data or not isinstance(data, list):
                    break
                for post in data:
                    url = post.get("link", "")
                    if url in seen:
                        continue
                    seen.add(url)
                    results.append(self._parse_post(post))
                if len(data) < 50:
                    break
                page += 1
        return results

    def _parse_post(self, post: dict) -> NormalizedScholarship:
        title = re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", "")).strip()
        url = post.get("link", "")
        excerpt = re.sub(r"<[^>]+>", " ", post.get("excerpt", {}).get("rendered", "")).strip()
        content_text = re.sub(r"<[^>]+>", " ", post.get("content", {}).get("rendered", "")).strip()

        deadline_raw = find_deadline_in_text(excerpt) or find_deadline_in_text(content_text)

        amount_match = re.search(r"(\$[\d,]+|€[\d,]+|£[\d,]+|fully funded|full scholarship)", excerpt, re.I)
        amount = amount_match.group(0) if amount_match else None

        degree_raw = title + " " + excerpt

        return make_scholarship(
            title=title,
            source_url=url,
            source_site=SITE_NAME,
            description=excerpt[:800] if excerpt else None,
            amount=amount,
            degree_levels_raw=degree_raw,
            deadline_raw=deadline_raw,
            eligible_nationalities=["African"],
            tags=["Africa"],
        )
