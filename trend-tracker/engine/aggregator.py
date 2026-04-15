"""
Trend Aggregator
Orchestrates all data sources, merges their signals, and returns
a unified ranked list of trends + Reels URLs.

Usage:
    aggregator = TrendAggregator(config)
    results = aggregator.run()
    # results["trending_now"] — list of TrendResult
    # results["upcoming"]     — list of TrendResult
    # results["reels"]        — list of Reel dicts with URLs
"""

import concurrent.futures
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from engine.scorer import (
    TrendScorer,
    TrendSignal,
    build_signals_from_exploding,
    build_signals_from_google,
    build_signals_from_meta,
    build_signals_from_social_blade,
)


@dataclass
class AggregatorConfig:
    # Google Trends — always enabled (no key needed)
    enable_google: bool = True
    google_country: str = "US"

    # Meta Ads Library — needs access token
    enable_meta: bool = False
    meta_access_token: str = ""

    # Exploding Topics — always enabled (scraping)
    enable_exploding: bool = True

    # Social Blade — always enabled (scraping); set api_key for paid API
    enable_social_blade: bool = True
    social_blade_api_key: str = ""

    # Instagram Graph API — needs token + business account ID
    enable_instagram: bool = False
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""

    # Content niches to focus on (used for IG hashtag discovery)
    niches: list[str] = field(default_factory=lambda: ["fashion", "beauty", "fitness"])

    # Result limits
    max_trending_now: int = 15
    max_upcoming: int = 15
    max_reels: int = 20


@dataclass
class TrendResult:
    keyword: str
    score: float
    trend_type: str
    sources: list[str]
    velocity: float
    instagram_relevance: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "score": round(self.score, 1),
            "trend_type": self.trend_type,
            "sources": self.sources,
            "source_count": len(self.sources),
            "velocity": round(self.velocity, 2),
            "instagram_relevance": round(self.instagram_relevance, 2),
            "metadata": self.metadata,
        }


class TrendAggregator:
    def __init__(self, config: AggregatorConfig):
        self.config = config
        self.scorer = TrendScorer()
        self._source_errors: dict[str, str] = {}
        self._source_data: dict[str, dict] = {}

    # ── Source Fetchers ────────────────────────────────────────────────────

    def _fetch_google(self) -> dict:
        from sources.google_trends import GoogleTrendsSource
        src = GoogleTrendsSource()
        return src.fetch_all()

    def _fetch_meta(self) -> dict:
        from sources.meta_ads import MetaAdsSource
        src = MetaAdsSource(self.config.meta_access_token)
        return src.fetch_all()

    def _fetch_exploding(self) -> dict:
        from sources.exploding_topics import ExplodingTopicsSource
        src = ExplodingTopicsSource()
        return src.fetch_all()

    def _fetch_social_blade(self) -> dict:
        from sources.social_blade import SocialBladeSource
        src = SocialBladeSource(api_key=self.config.social_blade_api_key or None)
        return src.fetch_all()

    def _fetch_instagram(self) -> dict:
        from sources.instagram_graph import InstagramGraphSource
        src = InstagramGraphSource(
            access_token=self.config.instagram_access_token,
            business_account_id=self.config.instagram_business_account_id,
        )
        return src.fetch_all(niches=self.config.niches)

    # ── Orchestration ──────────────────────────────────────────────────────

    def _run_sources_parallel(self) -> dict[str, dict]:
        """Run all enabled source fetchers in parallel threads."""
        tasks = {}
        if self.config.enable_google:
            tasks["google"] = self._fetch_google
        if self.config.enable_meta and self.config.meta_access_token:
            tasks["meta"] = self._fetch_meta
        if self.config.enable_exploding:
            tasks["exploding"] = self._fetch_exploding
        if self.config.enable_social_blade:
            tasks["social_blade"] = self._fetch_social_blade
        if self.config.enable_instagram and self.config.instagram_access_token:
            tasks["instagram"] = self._fetch_instagram

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fn): name for name, fn in tasks.items()}
            for future in concurrent.futures.as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=30)
                except Exception as e:
                    self._source_errors[name] = str(e)
                    results[name] = {}

        return results

    def _build_all_signals(self, source_data: dict[str, dict]) -> list[TrendSignal]:
        """Convert raw source data into unified TrendSignal objects."""
        signals = []

        if "google" in source_data:
            signals.extend(build_signals_from_google(source_data["google"]))
        if "meta" in source_data:
            signals.extend(build_signals_from_meta(source_data["meta"]))
        if "exploding" in source_data:
            signals.extend(build_signals_from_exploding(source_data["exploding"]))
        if "social_blade" in source_data:
            signals.extend(build_signals_from_social_blade(source_data["social_blade"]))

        return signals

    def _signals_to_results(self, signals: list[TrendSignal]) -> list[TrendResult]:
        """Convert scored+merged TrendSignals into TrendResult objects."""
        results = []
        for sig in signals:
            sources = sig.metadata.get("sources", [sig.source])
            results.append(TrendResult(
                keyword=sig.keyword,
                score=sig.final_score,
                trend_type=sig.trend_type,
                sources=sources,
                velocity=sig.velocity,
                instagram_relevance=sig.instagram_relevance,
                metadata={k: v for k, v in sig.metadata.items() if k != "sources"},
            ))
        return results

    def run(self) -> dict:
        """
        Main entry point. Fetches all sources, scores signals, and returns
        a dict with trending_now, upcoming, and reels lists.
        """
        # 1. Fetch all sources in parallel
        source_data = self._run_sources_parallel()
        self._source_data = source_data

        # 2. Build signals from keyword-based sources
        raw_signals = self._build_all_signals(source_data)

        # 3. Merge cross-platform signals + score them
        merged = self.scorer.merge_cross_platform(raw_signals)

        # 4. Rank separately by type
        trending_signals = self.scorer.rank(merged, trend_type="trending_now", limit=self.config.max_trending_now)
        upcoming_signals = self.scorer.rank(merged, trend_type="upcoming", limit=self.config.max_upcoming)

        # 5. Convert to TrendResult objects
        trending_results = self._signals_to_results(trending_signals)
        upcoming_results = self._signals_to_results(upcoming_signals)

        # 6. Get Instagram Reels (if available)
        ig_data = source_data.get("instagram", {})
        trending_reels = ig_data.get("trending_reels", [])
        upcoming_reels = ig_data.get("upcoming_reels", [])

        # Score each reel
        for reel in trending_reels + upcoming_reels:
            reel["trend_score"] = self.scorer.score_reel(reel)

        trending_reels.sort(key=lambda r: r["trend_score"], reverse=True)
        upcoming_reels.sort(key=lambda r: r["trend_score"], reverse=True)

        # 7. Build sources status summary
        sources_status = self._build_sources_status(source_data)

        return {
            "trending_now": [r.to_dict() for r in trending_results],
            "upcoming": [r.to_dict() for r in upcoming_results],
            "trending_reels": trending_reels[:self.config.max_reels],
            "upcoming_reels": upcoming_reels[:self.config.max_reels],
            "sources_status": sources_status,
            "errors": self._source_errors,
            "total_signals_processed": len(raw_signals),
            "fetched_at": datetime.utcnow().isoformat(),
        }

    def _build_sources_status(self, source_data: dict) -> list[dict]:
        """Build a status card for each data source."""
        source_map = {
            "google": {"name": "Google Trends", "icon": "📈", "required_key": None},
            "meta": {"name": "Meta Ads Library", "icon": "📱", "required_key": "META_ACCESS_TOKEN"},
            "exploding": {"name": "Exploding Topics", "icon": "🚀", "required_key": None},
            "social_blade": {"name": "Social Blade", "icon": "⚔️", "required_key": None},
            "instagram": {"name": "Instagram Graph API", "icon": "📸", "required_key": "INSTAGRAM_ACCESS_TOKEN"},
        }
        statuses = []
        for key, meta in source_map.items():
            has_data = bool(source_data.get(key))
            has_error = key in self._source_errors
            enabled = bool(source_data.get(key) is not None)

            if has_error:
                status = "error"
                message = self._source_errors.get(key, "Unknown error")[:80]
            elif has_data:
                status = "ok"
                message = f"{len(source_data[key])} signals fetched"
            elif not enabled:
                status = "disabled"
                message = f"Add {meta['required_key']} to .env to enable" if meta["required_key"] else "Disabled"
            else:
                status = "no_data"
                message = "Connected but no data returned"

            statuses.append({
                "source": key,
                "name": meta["name"],
                "icon": meta["icon"],
                "status": status,
                "message": message,
            })
        return statuses
