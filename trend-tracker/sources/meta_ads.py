"""
Meta Ads Library Source
Official Meta Ad Library API — free, requires a Facebook access token.
Surfaces trending creative formats, topics, and ad themes on Instagram.

Setup:
  1. Go to developers.facebook.com → My Apps → create app
  2. Add "Marketing API" product
  3. Generate a User Access Token with ads_read permission
  4. Paste into .env as META_ACCESS_TOKEN
"""

import requests
from datetime import datetime, timedelta
from typing import Optional

META_AD_LIBRARY_URL = "https://graph.facebook.com/v19.0/ads_archive"

# Instagram-relevant ad categories
SEARCH_TERMS = [
    "instagram reels",
    "viral",
    "trending",
    "new launch",
    "limited time",
    "challenge",
    "tutorial",
]


class MetaAdsSource:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "TrendTracker/1.0"})

    def _search_ads(
        self,
        search_term: str,
        limit: int = 25,
        publisher_platform: str = "instagram",
        ad_type: str = "ALL",
    ) -> list[dict]:
        """Query the Meta Ad Library API for a search term."""
        params = {
            "access_token": self.access_token,
            "ad_reached_countries": '["US"]',
            "search_terms": search_term,
            "ad_type": ad_type,
            "publisher_platforms": f'["{publisher_platform}"]',
            "fields": (
                "id,ad_creation_time,ad_creative_bodies,ad_creative_link_captions,"
                "ad_creative_link_descriptions,ad_creative_link_titles,"
                "page_name,impressions,spend,ad_snapshot_url,languages"
            ),
            "limit": limit,
        }
        try:
            resp = self.session.get(META_AD_LIBRARY_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 401:
                raise ValueError("Invalid Meta access token. Please check your META_ACCESS_TOKEN.") from e
            return []
        except Exception:
            return []

    def _parse_ad(self, ad: dict, search_term: str) -> dict:
        """Normalize a raw ad record into a trend signal."""
        bodies = ad.get("ad_creative_bodies") or []
        captions = ad.get("ad_creative_link_captions") or []
        titles = ad.get("ad_creative_link_titles") or []

        copy_text = " | ".join(filter(None, bodies[:1] + captions[:1] + titles[:1]))
        copy_text = copy_text[:200] if copy_text else "No preview available"

        impressions = ad.get("impressions", {})
        imp_lower = impressions.get("lower_bound", 0) if isinstance(impressions, dict) else 0
        imp_upper = impressions.get("upper_bound", 0) if isinstance(impressions, dict) else 0
        imp_mid = (int(imp_lower) + int(imp_upper)) // 2 if imp_lower and imp_upper else 0

        spend = ad.get("spend", {})
        spend_lower = spend.get("lower_bound", 0) if isinstance(spend, dict) else 0

        return {
            "keyword": search_term,
            "page_name": ad.get("page_name", "Unknown Brand"),
            "copy_preview": copy_text,
            "snapshot_url": ad.get("ad_snapshot_url", ""),
            "impressions_mid": imp_mid,
            "spend_lower": int(spend_lower) if spend_lower else 0,
            "created_at": ad.get("ad_creation_time", ""),
            "ad_id": ad.get("id", ""),
            "source": "Meta Ads Library",
            "type": "trending_now",
        }

    def _score_ad(self, ad: dict) -> int:
        """Score an ad based on impressions and spend signal."""
        imp = ad.get("impressions_mid", 0)
        spend = ad.get("spend_lower", 0)
        # Base score of 25 for any valid ad that appears in search results
        score = 25
        if imp > 1_000_000:
            score += 50
        elif imp > 100_000:
            score += 30
        elif imp > 10_000:
            score += 15
        if spend > 10_000:
            score += 30
        elif spend > 1_000:
            score += 20
        elif spend > 100:
            score += 10
        return min(score, 100)

    def get_trending_ad_themes(self) -> list[dict]:
        """Search multiple terms and return trending ad themes."""
        all_ads = []
        for term in SEARCH_TERMS:
            raw = self._search_ads(term, limit=10)
            for ad in raw:
                parsed = self._parse_ad(ad, term)
                parsed["score"] = self._score_ad(parsed)
                all_ads.append(parsed)

        # Deduplicate by ad_id
        seen = set()
        unique = []
        for ad in all_ads:
            if ad["ad_id"] not in seen:
                seen.add(ad["ad_id"])
                unique.append(ad)

        return sorted(unique, key=lambda x: x["score"], reverse=True)

    def get_top_spending_instagram_ads(self, country: str = "US") -> list[dict]:
        """Get highest-spend Instagram ads — these indicate what formats are working."""
        params = {
            "access_token": self.access_token,
            "ad_reached_countries": f'["{country}"]',
            "ad_type": "ALL",
            "publisher_platforms": '["instagram"]',
            "fields": (
                "id,ad_creation_time,ad_creative_bodies,page_name,"
                "impressions,spend,ad_snapshot_url"
            ),
            "limit": 30,
            "search_type": "KEYWORD_UNORDERED",
            "search_terms": "reel",
        }
        try:
            resp = self.session.get(META_AD_LIBRARY_URL, params=params, timeout=15)
            resp.raise_for_status()
            ads = resp.json().get("data", [])
            results = []
            for ad in ads:
                parsed = self._parse_ad(ad, "reel")
                parsed["score"] = self._score_ad(parsed)
                parsed["type"] = "trending_now"
                results.append(parsed)
            return sorted(results, key=lambda x: x["score"], reverse=True)[:15]
        except Exception:
            return []

    def extract_trending_themes(self, ads: list[dict]) -> list[str]:
        """Extract common themes/words from ad copy."""
        from collections import Counter
        import re

        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
                      "for", "of", "with", "by", "from", "is", "are", "was", "be",
                      "this", "that", "it", "we", "you", "your", "our", "get", "now"}
        words = []
        for ad in ads:
            text = ad.get("copy_preview", "").lower()
            tokens = re.findall(r"\b[a-z]{3,}\b", text)
            words.extend([t for t in tokens if t not in stop_words])

        counter = Counter(words)
        return [word for word, _ in counter.most_common(10)]

    def fetch_all(self) -> dict:
        """Fetch all Meta Ads data."""
        themed_ads = self.get_trending_ad_themes()
        top_ads = self.get_top_spending_instagram_ads()

        all_ads = themed_ads + [a for a in top_ads if a["ad_id"] not in {x["ad_id"] for x in themed_ads}]
        themes = self.extract_trending_themes(all_ads)

        return {
            "trending_now": [a for a in all_ads if a["score"] >= 25],
            "upcoming": [a for a in all_ads if a["score"] < 25],
            "trending_themes": themes,
            "total_ads_analyzed": len(all_ads),
            "source": "meta_ads_library",
            "fetched_at": datetime.utcnow().isoformat(),
        }
