"""
Google Trends Source
Uses pytrends (unofficial Google Trends API) — no API key required.
Fetches real-time trending searches + Instagram-specific trend velocity.
"""

import time
import pandas as pd
from datetime import datetime, timedelta

try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False


INSTAGRAM_SEED_KEYWORDS = [
    "instagram reels",
    "viral reel",
    "instagram trend",
    "instagram audio trend",
    "reel template",
]

CONTENT_CATEGORIES = [
    "fashion trend",
    "beauty trend",
    "fitness trend",
    "food trend",
    "travel trend",
    "dance trend",
    "lifestyle trend",
]


class GoogleTrendsSource:
    def __init__(self):
        if not PYTRENDS_AVAILABLE:
            raise ImportError("pytrends is not installed. Run: pip install pytrends")
        self.client = TrendReq(hl="en-US", tz=0, timeout=(10, 25), retries=2, backoff_factor=0.5)
        self.last_request_time = 0
        self.request_delay = 1.5  # seconds between requests to avoid rate limiting

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    def get_realtime_trending(self, country: str = "US") -> list[dict]:
        """
        Get trending topic signals via interest_over_time on seed keywords.
        Google's trending_searches endpoint is unreliable — this is more stable.
        """
        self._rate_limit()
        results = []

        # Use interest_over_time on broad content seed terms as a trending signal
        seed_terms = ["trending", "viral", "new song", "new movie", "breaking news"]
        try:
            self.client.build_payload(seed_terms, timeframe="now 1-d", geo=country)
            df = self.client.interest_over_time()
            if not df.empty:
                for col in df.columns:
                    if col == "isPartial":
                        continue
                    recent = df[col].iloc[-3:].mean()
                    if recent > 20:
                        results.append({
                            "keyword": col,
                            "source": "Google Trends (Realtime)",
                            "type": "trending_now",
                            "score": int(min(recent, 100)),
                        })
        except Exception:
            pass

        # Try suggestions API as supplementary trending signal
        self._rate_limit()
        try:
            for kw in ["instagram reel", "viral video", "trending audio"]:
                suggestions = self.client.suggestions(kw)
                for s in suggestions[:3]:
                    title = s.get("title", "")
                    if title and len(title) > 2:
                        results.append({
                            "keyword": title,
                            "source": "Google Trends (Suggestions)",
                            "type": "trending_now",
                            "score": 65,
                        })
        except Exception:
            pass

        return results

    def get_instagram_trend_keywords(self) -> list[dict]:
        """Get rising queries related to Instagram content."""
        self._rate_limit()
        try:
            self.client.build_payload(INSTAGRAM_SEED_KEYWORDS[:5], timeframe="now 7-d")
            related = self.client.related_queries()
            results = []
            for kw in INSTAGRAM_SEED_KEYWORDS[:5]:
                data = related.get(kw, {})
                rising = data.get("rising")
                if rising is not None and not rising.empty:
                    for _, row in rising.head(5).iterrows():
                        results.append({
                            "keyword": row["query"],
                            "source": "Google Trends (Rising)",
                            "type": "upcoming",
                            "score": min(int(row.get("value", 50)), 100),
                            "related_to": kw,
                        })
            return results
        except Exception:
            return []

    def get_trend_velocity(self, keywords: list[str]) -> dict[str, float]:
        """
        Calculate velocity score for keywords by comparing last 7 days vs prior 7 days.
        Returns a dict of keyword -> velocity (1.0 = flat, >1 = growing, <1 = declining).
        """
        if not keywords:
            return {}
        self._rate_limit()
        try:
            kw_batch = keywords[:5]
            self.client.build_payload(kw_batch, timeframe="now 30-d")
            df = self.client.interest_over_time()
            if df.empty:
                return {kw: 1.0 for kw in kw_batch}

            velocities = {}
            for kw in kw_batch:
                if kw not in df.columns:
                    velocities[kw] = 1.0
                    continue
                series = df[kw].dropna()
                if len(series) < 14:
                    velocities[kw] = 1.0
                    continue
                recent = series.iloc[-7:].mean()
                prior = series.iloc[-14:-7].mean()
                velocities[kw] = (recent / prior) if prior > 0 else 1.0
            return velocities
        except Exception:
            return {kw: 1.0 for kw in keywords}

    def get_content_category_trends(self) -> list[dict]:
        """Get which content categories are surging."""
        self._rate_limit()
        try:
            self.client.build_payload(CONTENT_CATEGORIES[:5], timeframe="now 7-d")
            df = self.client.interest_over_time()
            if df.empty:
                return []

            results = []
            for col in df.columns:
                if col == "isPartial":
                    continue
                series = df[col].dropna()
                if len(series) >= 7:
                    recent_avg = series.iloc[-3:].mean()
                    overall_avg = series.mean()
                    velocity = (recent_avg / overall_avg) if overall_avg > 0 else 1.0
                    results.append({
                        "keyword": col,
                        "source": "Google Trends (Category)",
                        "type": "upcoming" if velocity > 1.2 else "trending_now",
                        "score": int(min(recent_avg, 100)),
                        "velocity": round(velocity, 2),
                    })
            return sorted(results, key=lambda x: x["score"], reverse=True)
        except Exception:
            return []

    def fetch_all(self) -> dict:
        """Fetch all Google Trends data."""
        trending = self.get_realtime_trending()
        ig_keywords = self.get_instagram_trend_keywords()
        category_trends = self.get_content_category_trends()

        all_keywords = [item["keyword"] for item in trending[:5]]
        velocities = self.get_trend_velocity(all_keywords) if all_keywords else {}

        # Enrich trending items with velocity
        for item in trending:
            kw = item["keyword"]
            v = velocities.get(kw, 1.0)
            item["velocity"] = round(v, 2)
            if v > 1.5:
                item["type"] = "upcoming"

        return {
            "trending_now": [i for i in trending + category_trends if i["type"] == "trending_now"],
            "upcoming": [i for i in trending + ig_keywords + category_trends if i["type"] == "upcoming"],
            "raw_keywords": [i["keyword"] for i in trending + ig_keywords],
            "source": "google_trends",
            "fetched_at": datetime.utcnow().isoformat(),
        }
