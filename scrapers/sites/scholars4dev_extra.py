"""Scraper for globalsouthopportunities.com — WordPress."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "Global South Opportunities"
BASE_URL = "https://www.globalsouthopportunities.com"
WP_API = f"{BASE_URL}/wp-json/wp/v2/posts"


class GlobalSouthScraper(BaseScraper):
    name = "globalsouthopportunities"
    base_url = BASE_URL
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            data = self.get_json(WP_API, params={"per_page": 50, "page": page, "categories": "scholarships", "_fields": "id,title,link,excerpt,content,date"})
            if not data or not isinstance(data, list):
                return self._scrape_html()
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
        amount_m = re.search(r"(\$[\d,]+|€[\d,]+|fully funded)", excerpt, re.I)
        return make_scholarship(
            title=title, source_url=url, source_site=SITE_NAME,
            description=excerpt[:800], degree_levels_raw=title + " " + excerpt,
            deadline_raw=deadline_raw,
            amount=amount_m.group(0) if amount_m else None,
            tags=["Global South"],
        )

    def _scrape_html(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            url = f"{BASE_URL}/category/scholarships/" if page == 1 else f"{BASE_URL}/category/scholarships/page/{page}/"
            soup = self.get_soup(url)
            if not soup:
                break
            articles = soup.find_all("article") or soup.find_all("div", class_=re.compile(r"post", re.I))
            found = 0
            for art in articles:
                title_tag = art.find(["h2", "h3"])
                link = title_tag.find("a") if title_tag else art.find("a")
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                text = art.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text)
                if not deadline_raw:
                    deadline_raw = self._fetch_deadline(href if href.startswith("http") else BASE_URL + href)
                results.append(make_scholarship(
                    title=title,
                    source_url=href if href.startswith("http") else BASE_URL + href,
                    source_site=SITE_NAME, degree_levels_raw=title,
                    deadline_raw=deadline_raw,
                    tags=["Global South"],
                ))
                found += 1
            if found == 0:
                break
            page += 1
        return results
