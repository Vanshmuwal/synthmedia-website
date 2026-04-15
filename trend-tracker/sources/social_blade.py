"""
Social Blade Source
Scrapes Social Blade's public-facing pages to identify:
  - Fastest-growing Instagram accounts (signal of emerging trends)
  - Creator categories gaining traction

Social Blade has a paid API (socialblade.com/business/api).
This module uses their public web data. For production, swap in
SOCIALBLADE_API_KEY from .env for the official API.
"""

import requests
import re
import json
from datetime import datetime
from bs4 import BeautifulSoup

SB_BASE = "https://socialblade.com"
SB_TOP_INSTAGRAM = f"{SB_BASE}/instagram/top/50/followers"
SB_FASTEST_GROWING = f"{SB_BASE}/instagram/top/50/followersweekly"

# Official API endpoint (requires paid key)
SB_API_BASE = "https://matrix.sbapis.com/b"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://socialblade.com",
}

# Map follower categories to content niches
NICHE_KEYWORDS = {
    "beauty": ["makeup", "beauty", "skincare", "cosmetics", "glam"],
    "fashion": ["fashion", "style", "ootd", "outfit", "wear"],
    "fitness": ["fitness", "gym", "workout", "health", "sport", "yoga"],
    "food": ["food", "recipe", "cook", "chef", "eat", "bake"],
    "travel": ["travel", "explore", "wanderlust", "trip", "adventure"],
    "comedy": ["comedy", "funny", "humor", "laugh", "meme"],
    "music": ["music", "song", "artist", "dj", "producer", "singer"],
    "gaming": ["gaming", "gamer", "game", "stream", "esport"],
    "lifestyle": ["lifestyle", "life", "daily", "vlog", "day"],
}


class SocialBladeSource:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ── Official API (paid) ─────────────────────────────────────────────────

    def _api_get_fastest_growing(self, limit: int = 20) -> list[dict]:
        """Use official Social Blade API if key is present."""
        if not self.api_key:
            return []
        try:
            url = f"{SB_API_BASE}/instagram/statistics"
            resp = self.session.get(
                url,
                headers={"clientid": self.api_key, "token": self.api_key},
                params={"sort": "weekly_followers", "order": "desc", "limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            accounts = data.get("data", [])
            return self._normalize_api_accounts(accounts)
        except Exception:
            return []

    def _normalize_api_accounts(self, accounts: list) -> list[dict]:
        results = []
        for acc in accounts:
            username = acc.get("username") or acc.get("id", "")
            weekly_gain = acc.get("weekly_followers") or acc.get("followers_weekly", 0)
            total_followers = acc.get("followers") or acc.get("followers_count", 0)
            try:
                weekly_gain = int(str(weekly_gain).replace(",", ""))
                total_followers = int(str(total_followers).replace(",", ""))
            except (ValueError, TypeError):
                weekly_gain = 0
                total_followers = 0

            growth_rate = (weekly_gain / total_followers * 100) if total_followers > 0 else 0
            results.append({
                "username": username,
                "profile_url": f"https://www.instagram.com/{username}/",
                "weekly_follower_gain": weekly_gain,
                "total_followers": total_followers,
                "weekly_growth_rate": round(growth_rate, 2),
                "niche": self._detect_niche(username, acc.get("description", "")),
                "source": "Social Blade (API)",
                "type": "upcoming" if growth_rate > 5 else "trending_now",
                "score": min(int(growth_rate * 10), 100),
            })
        return results

    # ── Public Web Scraping ──────────────────────────────────────────────────

    def _scrape_fastest_growing(self) -> list[dict]:
        """
        Scrape Social Blade's fastest-growing Instagram accounts page.
        Note: Social Blade returns 403 for automated scrapers.
        Use the official paid API key for reliable data.
        """
        try:
            resp = self.session.get(SB_FASTEST_GROWING, timeout=15)
            if resp.status_code == 403:
                raise PermissionError(
                    "Social Blade blocks automated scraping (403). "
                    "Add your SOCIAL_BLADE_API_KEY in .env for live data."
                )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            return self._parse_sb_table(soup)
        except PermissionError:
            raise
        except Exception:
            return []

    def _parse_sb_table(self, soup: BeautifulSoup) -> list[dict]:
        """Parse the ranking table from Social Blade HTML."""
        results = []

        # Social Blade renders data in a specific div structure
        rows = soup.find_all("div", id=re.compile(r"^YouTubeUserTopStats")) or \
               soup.find_all("div", class_=re.compile(r"top.*row|row.*top", re.I)) or \
               soup.find_all("tr")

        for row in rows[:30]:
            cells = row.find_all(["td", "span", "div"])
            if len(cells) < 3:
                continue

            username = ""
            weekly_gain = 0
            total_followers = 0

            for cell in cells:
                text = cell.get_text(strip=True)
                link = cell.find("a")

                if link and "/instagram/user/" in str(link.get("href", "")):
                    username = text.lstrip("@")
                elif re.match(r"^\+[\d,]+$", text):
                    try:
                        weekly_gain = int(text.replace("+", "").replace(",", ""))
                    except ValueError:
                        pass
                elif re.match(r"^[\d,.]+[KMB]?$", text) and not username:
                    try:
                        total_followers = self._parse_number(text)
                    except ValueError:
                        pass

            if not username:
                # Try to find username from anchor tags
                link = row.find("a", href=re.compile(r"/instagram/user/"))
                if link:
                    username = link.get_text(strip=True).lstrip("@")

            if username and len(username) > 0:
                growth_rate = (weekly_gain / total_followers * 100) if total_followers > 0 else 0
                results.append({
                    "username": username,
                    "profile_url": f"https://www.instagram.com/{username}/",
                    "weekly_follower_gain": weekly_gain,
                    "total_followers": total_followers,
                    "weekly_growth_rate": round(growth_rate, 2),
                    "niche": self._detect_niche(username, ""),
                    "source": "Social Blade (Web)",
                    "type": "upcoming" if growth_rate > 3 else "trending_now",
                    "score": min(int(growth_rate * 10) + 20, 100),
                })

        return results

    def _parse_number(self, text: str) -> int:
        """Parse numbers like '1.2M', '450K', '1,234,567'."""
        text = text.strip().replace(",", "")
        if text.endswith("B"):
            return int(float(text[:-1]) * 1_000_000_000)
        if text.endswith("M"):
            return int(float(text[:-1]) * 1_000_000)
        if text.endswith("K"):
            return int(float(text[:-1]) * 1_000)
        return int(float(text))

    def _detect_niche(self, username: str, bio: str) -> str:
        """Detect content niche from username and bio."""
        combined = (username + " " + bio).lower()
        for niche, keywords in NICHE_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                return niche
        return "general"

    def get_niche_velocity(self, accounts: list[dict]) -> dict[str, float]:
        """Compute which niches have the highest combined growth rate."""
        from collections import defaultdict
        niche_growth = defaultdict(list)
        for acc in accounts:
            niche = acc.get("niche", "general")
            growth = acc.get("weekly_growth_rate", 0)
            niche_growth[niche].append(growth)

        return {
            niche: round(sum(rates) / len(rates), 2)
            for niche, rates in niche_growth.items()
        }

    def fetch_all(self) -> dict:
        """Fetch all Social Blade data."""
        # Prefer official API if key exists, fall back to scraping
        accounts = self._api_get_fastest_growing() if self.api_key else []
        if not accounts:
            accounts = self._scrape_fastest_growing()

        niche_velocity = self.get_niche_velocity(accounts)
        top_niches = sorted(niche_velocity.items(), key=lambda x: x[1], reverse=True)

        return {
            "fastest_growing_accounts": accounts[:20],
            "trending_niches": [
                {"niche": n, "avg_weekly_growth_pct": v, "type": "upcoming" if v > 3 else "trending_now"}
                for n, v in top_niches[:8]
            ],
            "source": "social_blade",
            "total_accounts_analyzed": len(accounts),
            "fetched_at": datetime.utcnow().isoformat(),
        }
