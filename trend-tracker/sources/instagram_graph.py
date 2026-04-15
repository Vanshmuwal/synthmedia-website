"""
Instagram Graph API Source
Fetches actual Reels URLs using the official Instagram Graph API.

What this does:
  1. Searches trending hashtags → gets top & recent Reels
  2. Returns permalink URLs for each Reel (these are the shareable Instagram links)
  3. Identifies audio/music trends from Reel metadata

Setup (required for Reels URLs):
  1. You need a Facebook Developer account → create an App
  2. Add Instagram Graph API product
  3. Connect an Instagram Business or Creator account
  4. Get a long-lived User Access Token with:
       instagram_basic, instagram_manage_insights, pages_read_engagement
  5. Paste token into .env as INSTAGRAM_ACCESS_TOKEN
  6. Add your Instagram Business Account ID as INSTAGRAM_BUSINESS_ACCOUNT_ID

Without a token: the app still runs but Reels URLs won't be fetched.
"""

import requests
import time
from datetime import datetime
from typing import Optional

IG_GRAPH_BASE = "https://graph.facebook.com/v19.0"

# Seed hashtags for trend discovery
TRENDING_HASHTAGS = [
    "reels",
    "reelsinstagram",
    "viralreels",
    "trendingreels",
    "reelsvideo",
    "explore",
    "fyp",
    "viral",
    "trending",
    "instagramreels",
]

# Niche hashtags — surface category-specific trends
NICHE_HASHTAGS = {
    "fashion": ["fashionreels", "ootd", "styleinspo", "fashiontiktok"],
    "beauty": ["makeuptutorial", "beautyreels", "skincareroutine", "glowup"],
    "fitness": ["fitnessreels", "workoutvideo", "gymreels", "fitnessmotivation"],
    "food": ["foodreels", "recipevideo", "cookingreels", "foodtok"],
    "travel": ["travelreels", "wanderlust", "travelvideo", "travelgram"],
    "comedy": ["funnyreels", "comedyreels", "funnyvideo", "comedytok"],
    "dance": ["dancereels", "dancevideo", "choreography", "dancetrend"],
    "music": ["musicreels", "newmusic", "musicvideo", "singersongwriter"],
}


class InstagramGraphSource:
    def __init__(self, access_token: str, business_account_id: str):
        self.access_token = access_token
        self.business_account_id = business_account_id
        self.session = requests.Session()
        self._hashtag_id_cache: dict[str, str] = {}

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make an authenticated GET request to the Graph API."""
        base_params = {"access_token": self.access_token}
        if params:
            base_params.update(params)
        try:
            resp = self.session.get(
                f"{IG_GRAPH_BASE}/{endpoint}",
                params=base_params,
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 400:
                error = resp.json().get("error", {})
                if error.get("code") == 190:
                    raise ValueError("Instagram access token is expired or invalid.") from e
            return {}
        except Exception:
            return {}

    def get_hashtag_id(self, hashtag: str) -> Optional[str]:
        """Resolve a hashtag name to an Instagram hashtag ID."""
        if hashtag in self._hashtag_id_cache:
            return self._hashtag_id_cache[hashtag]

        data = self._get(
            "ig_hashtag_search",
            {
                "user_id": self.business_account_id,
                "q": hashtag,
            },
        )
        hashtag_id = None
        ids = data.get("data", [])
        if ids:
            hashtag_id = ids[0].get("id")
            self._hashtag_id_cache[hashtag] = hashtag_id
        return hashtag_id

    def get_top_reels(self, hashtag: str, limit: int = 10) -> list[dict]:
        """
        Get top media for a hashtag — these are the highest-engagement Reels.
        Returns list of Reel dicts with permalink URLs.
        """
        hashtag_id = self.get_hashtag_id(hashtag)
        if not hashtag_id:
            return []

        data = self._get(
            f"{hashtag_id}/top_media",
            {
                "user_id": self.business_account_id,
                "fields": "id,media_type,permalink,timestamp,like_count,comments_count,caption",
                "limit": limit,
            },
        )
        media = data.get("data", [])
        return [self._normalize_reel(m, hashtag, "top") for m in media if m.get("media_type") in ("VIDEO", "REEL")]

    def get_recent_reels(self, hashtag: str, limit: int = 10) -> list[dict]:
        """
        Get recent media for a hashtag — these catch emerging trends early.
        Recent high-engagement posts = potential upcoming trend.
        """
        hashtag_id = self.get_hashtag_id(hashtag)
        if not hashtag_id:
            return []

        data = self._get(
            f"{hashtag_id}/recent_media",
            {
                "user_id": self.business_account_id,
                "fields": "id,media_type,permalink,timestamp,like_count,comments_count,caption",
                "limit": limit,
            },
        )
        media = data.get("data", [])
        return [self._normalize_reel(m, hashtag, "recent") for m in media if m.get("media_type") in ("VIDEO", "REEL")]

    def _normalize_reel(self, media: dict, hashtag: str, discovery_type: str) -> dict:
        """Normalize a Graph API media object into a Reel signal."""
        like_count = media.get("like_count", 0) or 0
        comments_count = media.get("comments_count", 0) or 0
        engagement = like_count + (comments_count * 3)  # weighted engagement

        caption = media.get("caption", "") or ""
        caption_preview = caption[:150] + "..." if len(caption) > 150 else caption

        # Detect if this Reel is using a trending audio/template format
        has_trend_signals = any(
            sig in caption.lower()
            for sig in ["trend", "viral", "template", "pov", "storytime", "duet", "stitch", "challenge"]
        )

        return {
            "reel_id": media.get("id", ""),
            "permalink": media.get("permalink", ""),
            "url": media.get("permalink", ""),  # this IS the shareable Reels URL
            "hashtag": hashtag,
            "like_count": like_count,
            "comments_count": comments_count,
            "engagement_score": engagement,
            "caption_preview": caption_preview,
            "posted_at": media.get("timestamp", ""),
            "discovery_type": discovery_type,
            "has_trend_signals": has_trend_signals,
            "source": "Instagram Graph API",
            "type": "upcoming" if discovery_type == "recent" and has_trend_signals else "trending_now",
            "score": min(int(engagement / 1000), 100),
        }

    def get_trending_reels_batch(self, hashtags: list[str], top_per_tag: int = 5) -> list[dict]:
        """Fetch trending Reels across multiple hashtags with rate limiting."""
        all_reels = []
        seen_ids = set()

        for i, tag in enumerate(hashtags):
            if i > 0:
                time.sleep(0.5)  # respect rate limits

            top = self.get_top_reels(tag, limit=top_per_tag)
            recent = self.get_recent_reels(tag, limit=top_per_tag)

            for reel in top + recent:
                rid = reel.get("reel_id")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_reels.append(reel)

        return all_reels

    def get_niche_reels(self, niche: str, top_per_tag: int = 3) -> list[dict]:
        """Get trending Reels for a specific content niche."""
        hashtags = NICHE_HASHTAGS.get(niche, [])
        if not hashtags:
            return []
        return self.get_trending_reels_batch(hashtags, top_per_tag=top_per_tag)

    def get_account_insights(self) -> dict:
        """Get your own account's top-performing Reels for context."""
        data = self._get(
            f"{self.business_account_id}/media",
            {
                "fields": "id,media_type,permalink,timestamp,like_count,comments_count,caption",
                "limit": 20,
            },
        )
        media = data.get("data", [])
        reels = [m for m in media if m.get("media_type") in ("VIDEO", "REEL")]
        return {
            "your_top_reels": sorted(
                [self._normalize_reel(r, "your_account", "own") for r in reels],
                key=lambda x: x["engagement_score"],
                reverse=True,
            )[:5]
        }

    def fetch_all(self, niches: list[str] = None) -> dict:
        """Fetch all Instagram Reels trend data."""
        # Core trending hashtags
        trending_reels = self.get_trending_reels_batch(TRENDING_HASHTAGS[:6], top_per_tag=5)

        # Niche-specific if requested
        niche_reels = []
        if niches:
            for niche in niches[:3]:
                niche_reels.extend(self.get_niche_reels(niche, top_per_tag=3))

        all_reels = trending_reels + niche_reels
        all_reels.sort(key=lambda x: x["engagement_score"], reverse=True)

        # Deduplicate
        seen = set()
        unique_reels = []
        for r in all_reels:
            if r["reel_id"] not in seen:
                seen.add(r["reel_id"])
                unique_reels.append(r)

        trending_now = [r for r in unique_reels if r["type"] == "trending_now" and r["permalink"]]
        upcoming = [r for r in unique_reels if r["type"] == "upcoming" and r["permalink"]]

        return {
            "trending_reels": trending_now[:20],
            "upcoming_reels": upcoming[:20],
            "total_reels_found": len(unique_reels),
            "source": "instagram_graph_api",
            "fetched_at": datetime.utcnow().isoformat(),
        }
