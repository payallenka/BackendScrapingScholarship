"""Scraper for Stipendium Hungaricum scholarship finder (stipendiumhungaricum.hu)."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "Stipendium Hungaricum"
BASE_URL = "https://stipendiumhungaricum.hu"
STUDY_FINDER = f"{BASE_URL}/study-finder/"
API_URL = f"{BASE_URL}/wp-json/wp/v2/posts"


class StipendiumHungaricumScraper(BaseScraper):
    name = "stipendiumhungaricum"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        # Try WP REST API first
        results = self._scrape_wp_api()
        if results:
            return results
        return self._scrape_html()

    def _scrape_wp_api(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            data = self.get_json(API_URL, params={
                "per_page": 50, "page": page,
                "_fields": "id,title,link,excerpt,content,date"
            })
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
        content_text = re.sub(r"<[^>]+>", " ", post.get("content", {}).get("rendered", "")).strip()
        deadline_raw = find_deadline_in_text(excerpt) or find_deadline_in_text(content_text)
        return make_scholarship(
            title=title,
            source_url=url,
            source_site=SITE_NAME,
            description=excerpt[:800],
            degree_levels_raw=title + " " + excerpt,
            deadline_raw=deadline_raw,
            host_countries=["Hungary"],
            tags=["Hungary", "Government Scholarship"],
        )

    def _scrape_html(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            url = STUDY_FINDER if page == 1 else f"{STUDY_FINDER}?paged={page}"
            soup = self.get_soup(url)
            if not soup:
                break

            items = (
                soup.find_all("div", class_=re.compile(r"course|programme|scholarship|item|card|result", re.I))
                or soup.find_all("article")
                or soup.find_all("tr", class_=re.compile(r"course|programme", re.I))
            )

            found = 0
            for item in items:
                title_tag = item.find(["h2", "h3", "h4"])
                if not title_tag:
                    continue
                link = title_tag.find("a") or item.find("a", href=True)
                title = (title_tag or link).get_text(strip=True) if (title_tag or link) else None
                if not title or len(title) < 5:
                    continue
                href = (link.get("href", "") if link else "") or STUDY_FINDER
                if not href.startswith("http"):
                    href = BASE_URL + href
                text = item.get_text(" ", strip=True)
                degree_m = re.search(r"(undergraduate|bachelor|master|ph\.?d|doctoral)", text, re.I)
                uni_m = re.search(r"(?:at|university)[:\s]+([A-Z][^\n|]+)", text, re.I)
                results.append(make_scholarship(
                    title=title,
                    source_url=href,
                    source_site=SITE_NAME,
                    organization=uni_m.group(1).strip()[:80] if uni_m else None,
                    degree_levels_raw=degree_m.group(0) if degree_m else "any",
                    host_countries=["Hungary"],
                    tags=["Hungary", "Government Scholarship"],
                    amount="Fully Funded",
                ))
                found += 1

            if found == 0:
                break
            page += 1
        return results
