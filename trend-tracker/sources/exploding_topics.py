"""
Exploding Topics Source
Scrapes the public Exploding Topics trending page.
No API key required — uses their free public web data.
Falls back to their unofficial JSON endpoint when available.
"""

import requests
import re
import json
from datetime import datetime
from bs4 import BeautifulSoup


ET_BASE_URL = "https://explodingtopics.com"
ET_HOME_URL = ET_BASE_URL  # NEXT_DATA lives on the homepage
ET_TRENDING_URL = f"{ET_BASE_URL}/trending"
ET_API_URL = f"{ET_BASE_URL}/api/topics/top"  # unofficial, may change

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://explodingtopics.com",
}

# Social/content-relevant categories to prioritize
RELEVANT_CATEGORIES = {
    "social media", "creator economy", "content", "beauty", "fashion",
    "fitness", "food", "travel", "entertainment", "music", "lifestyle",
    "wellness", "technology", "marketing",
}


class ExplodingTopicsSource:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _extract_json_from_page(self, html: str) -> dict:
        """Extract __NEXT_DATA__ from the page HTML using brace-matching."""
        import re
        idx = html.find("__NEXT_DATA__ = ")
        if idx == -1:
            return {}
        start = idx + len("__NEXT_DATA__ = ")
        brace_count, end = 0, start
        for i, c in enumerate(html[start:], start):
            if c == "{":
                brace_count += 1
            elif c == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        try:
            return json.loads(html[start:end])
        except (json.JSONDecodeError, ValueError):
            return {}

    def _fetch_via_json_endpoint(self) -> list[dict]:
        """Try the internal JSON API endpoint first (faster)."""
        try:
            resp = self.session.get(ET_API_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                topics = data if isinstance(data, list) else data.get("topics", data.get("data", []))
                return self._normalize_json_topics(topics)
        except Exception:
            pass
        return []

    def _normalize_json_topics(self, topics: list) -> list[dict]:
        results = []
        for t in topics[:30]:
            if not isinstance(t, dict):
                continue
            name = t.get("topic") or t.get("name") or t.get("title", "")
            if not name:
                continue
            growth = t.get("growth") or t.get("percent_growth") or t.get("volume_growth", 0)
            try:
                growth = float(str(growth).replace("%", "").replace(",", ""))
            except (ValueError, TypeError):
                growth = 0

            category = str(t.get("category") or t.get("type") or "").lower()
            results.append({
                "keyword": name,
                "growth_pct": growth,
                "category": category,
                "url": t.get("url") or f"{ET_BASE_URL}/topic/{name.lower().replace(' ', '-')}",
                "status": t.get("status") or ("Exploding" if growth > 200 else "Regular"),
                "source": "Exploding Topics",
                "type": "upcoming" if growth > 100 else "trending_now",
                "score": min(int(growth / 10), 100) if growth > 0 else 50,
            })
        return results

    def _fetch_via_scraping(self) -> list[dict]:
        """Scrape the Exploding Topics homepage which contains trendingDesktopData."""
        try:
            resp = self.session.get(ET_HOME_URL, timeout=15)
            # 404 status is normal on their homepage for some regions — check content
            if len(resp.text) < 1000:
                return []

            data = self._extract_json_from_page(resp.text)
            if data:
                topics = self._extract_from_next_data(data)
                if topics:
                    return topics

            # Fallback: parse HTML cards
            soup = BeautifulSoup(resp.text, "html.parser")
            return self._parse_html_cards(soup)
        except Exception:
            return []

    def _extract_from_next_data(self, data: dict) -> list[dict]:
        """Extract topics from Next.js __NEXT_DATA__ blob."""
        try:
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            # Primary path: trendingDesktopData (confirmed structure)
            trending_desktop = page_props.get("trendingDesktopData", {})
            if isinstance(trending_desktop, dict):
                all_topics = []
                for category in ["trends", "startups", "websites"]:
                    items = trending_desktop.get(category, [])
                    if isinstance(items, list):
                        all_topics.extend(items)
                if all_topics:
                    return self._normalize_desktop_topics(all_topics)

            # Fallback: try other common keys
            for key in ["topics", "trendingTopics", "data", "items"]:
                topics_raw = page_props.get(key)
                if topics_raw and isinstance(topics_raw, list):
                    return self._normalize_json_topics(topics_raw)

            return []
        except Exception:
            return []

    def _normalize_desktop_topics(self, topics: list) -> list[dict]:
        """Normalize the trendingDesktopData.trends structure."""
        results = []
        for t in topics:
            if not isinstance(t, dict):
                continue
            keyword = t.get("keyword", "")
            if not keyword:
                continue
            path = t.get("path", "")
            url = f"{ET_BASE_URL}/topics/{path}" if path else ET_BASE_URL

            # Extract search history for growth calculation
            history = t.get("searchHistory", [])
            growth = 0
            if isinstance(history, list) and len(history) >= 2:
                recent = history[-1].get("value", 0) if isinstance(history[-1], dict) else history[-1]
                older = history[0].get("value", 1) if isinstance(history[0], dict) else history[0]
                try:
                    growth = int(((float(recent) - float(older)) / max(float(older), 1)) * 100)
                except (TypeError, ValueError, ZeroDivisionError):
                    growth = 0

            # Volume from keywordDataGlobal
            kd = t.get("keywordDataGlobal", {})
            volume = kd.get("vol", 0) if isinstance(kd, dict) else 0

            score = min(max(int(growth / 5), 0) + min(int(volume / 1000), 50), 100)
            results.append({
                "keyword": keyword,
                "growth_pct": growth,
                "volume": volume,
                "category": "trending",
                "url": url,
                "status": "Exploding" if growth > 200 else "Trending",
                "source": "Exploding Topics",
                "type": "upcoming" if growth > 50 else "trending_now",
                "score": score,
            })
        return results

    def _deep_find_topics(self, obj, depth=0) -> list:
        """Recursively find topic arrays in nested dicts."""
        if depth > 4:
            return []
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            if any(k in obj[0] for k in ["topic", "name", "title", "growth"]):
                return obj
        if isinstance(obj, dict):
            for v in obj.values():
                result = self._deep_find_topics(v, depth + 1)
                if result:
                    return result
        return []

    def _parse_html_cards(self, soup: BeautifulSoup) -> list[dict]:
        """Parse topic cards from HTML as a last resort."""
        results = []
        # Common class patterns on Exploding Topics
        cards = (
            soup.find_all("div", class_=re.compile(r"topic|card|trend", re.I))
            or soup.find_all("article")
        )
        for card in cards[:20]:
            name_el = card.find(["h2", "h3", "h4", "strong", "span"])
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) > 60:
                continue

            growth_text = ""
            growth_el = card.find(text=re.compile(r"\d+%"))
            if growth_el:
                growth_text = growth_el.strip()
            growth = 0
            m = re.search(r"(\d+)%", growth_text)
            if m:
                growth = int(m.group(1))

            results.append({
                "keyword": name,
                "growth_pct": growth,
                "category": "unknown",
                "url": ET_TRENDING_URL,
                "status": "Exploding" if growth > 200 else "Regular",
                "source": "Exploding Topics",
                "type": "upcoming" if growth > 100 else "trending_now",
                "score": min(int(growth / 10), 100) if growth > 0 else 40,
            })
        return results

    def filter_social_relevant(self, topics: list[dict]) -> list[dict]:
        """Prioritize topics relevant to social/content creation."""
        relevant = []
        other = []
        for t in topics:
            cat = t.get("category", "").lower()
            name = t.get("keyword", "").lower()
            if any(rc in cat for rc in RELEVANT_CATEGORIES) or \
               any(rc in name for rc in RELEVANT_CATEGORIES):
                t["relevance_boost"] = True
                t["score"] = min(t.get("score", 50) + 15, 100)
                relevant.append(t)
            else:
                other.append(t)
        return relevant + other

    def fetch_all(self) -> dict:
        """Fetch all Exploding Topics data."""
        # Try JSON endpoint first, then scraping
        topics = self._fetch_via_json_endpoint()
        if not topics:
            topics = self._fetch_via_scraping()

        topics = self.filter_social_relevant(topics)

        return {
            "trending_now": [t for t in topics if t["type"] == "trending_now"][:15],
            "upcoming": [t for t in topics if t["type"] == "upcoming"][:15],
            "source": "exploding_topics",
            "total_found": len(topics),
            "fetched_at": datetime.utcnow().isoformat(),
        }
