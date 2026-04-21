"""
ScholarshipOwl Business API client.
Docs: https://docs.business.scholarshipowl.com/api/scholarships.html

Set OWL_API_KEY and optionally OWL_API_BASE_URL in environment.
"""
from __future__ import annotations
import os
import logging
from typing import List, Optional
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

logger = logging.getLogger(__name__)

SITE_NAME = "ScholarshipOwl"
DEFAULT_BASE_URL = "https://api.scholarshipowl.com"


class ScholarshipOwlAPI(BaseScraper):
    name = "scholarshipowl"
    delay = 0.5

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("OWL_API_KEY", "")
        self.base_url = base_url or os.getenv("OWL_API_BASE_URL", DEFAULT_BASE_URL)
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def scrape(self) -> List[NormalizedScholarship]:
        if not self.api_key:
            logger.warning("[scholarshipowl] OWL_API_KEY not set — skipping.")
            return []

        results = []
        page = 1
        per_page = 50
        while page <= self.max_pages:
            data = self.get_json(
                f"{self.base_url}/api/scholarship",
                params={"page": page, "per_page": per_page},
            )
            if not data:
                break

            # JSON:API format: {"data": [...], "meta": {...}, "links": {...}}
            items = data.get("data") or (data if isinstance(data, list) else [])
            if not items:
                break

            for item in items:
                results.append(self._parse_item(item))

            # Check pagination via JSON:API links
            links = data.get("links", {})
            if not links.get("next"):
                break
            page += 1

        return results

    def _parse_item(self, item: dict) -> NormalizedScholarship:
        attrs = item.get("attributes") or item  # JSON:API nests under attributes
        sid = item.get("id") or attrs.get("id") or ""

        title = attrs.get("title") or attrs.get("name") or "Scholarship"
        description = attrs.get("description") or attrs.get("body") or ""
        deadline = str(attrs.get("deadline") or attrs.get("deadline_date") or "")
        amount_val = attrs.get("award_amount") or attrs.get("amount") or 0
        amount = f"${amount_val:,.0f}" if isinstance(amount_val, (int, float)) and amount_val else str(amount_val)
        org = attrs.get("sponsor") or attrs.get("organization") or ""
        is_open = not bool(attrs.get("expired") or attrs.get("is_expired"))
        url = attrs.get("url") or f"https://scholarshipowl.com/scholarships/{sid}"

        return make_scholarship(
            title=title,
            source_url=url,
            source_site=SITE_NAME,
            organization=org,
            description=str(description)[:800] if description else None,
            amount=amount,
            deadline_raw=deadline,
            degree_levels_raw=str(attrs.get("eligible_grades") or attrs.get("study_level") or "any"),
            is_open=is_open,
        )

    def get_scholarship_fields(self, scholarship_id: str) -> Optional[dict]:
        """Fetch required application fields for a scholarship."""
        return self.get_json(f"{self.base_url}/api/scholarship/{scholarship_id}/fields")

    def get_scholarship_requirements(self, scholarship_id: str) -> Optional[dict]:
        """Fetch eligibility requirements for a scholarship."""
        return self.get_json(f"{self.base_url}/api/scholarship/{scholarship_id}/requirements")
