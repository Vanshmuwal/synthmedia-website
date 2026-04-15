"""
Trend Scoring Engine
Combines signals from all sources into unified trend scores.

Scoring philosophy:
  - Trending NOW  = high cross-platform agreement + high volume
  - Upcoming      = high velocity (acceleration) + low-to-medium current volume
  - Viral Reels   = high engagement relative to account size + trend signal keywords

Weights are tunable via the WEIGHTS dict.
"""

from dataclasses import dataclass, field
from typing import Literal

TrendType = Literal["trending_now", "upcoming"]

WEIGHTS = {
    "google_trends": 0.25,
    "meta_ads_library": 0.20,
    "exploding_topics": 0.25,
    "social_blade": 0.15,
    "instagram_graph_api": 0.15,
}

# Keywords that boost a trend's relevance to Instagram content creation
INSTAGRAM_RELEVANCE_BOOST_TERMS = [
    "reel", "reels", "instagram", "viral", "trend", "challenge", "template",
    "audio", "sound", "filter", "transition", "pov", "storytime", "aesthetic",
    "tutorial", "hack", "tip", "routine", "haul", "vlog", "grwm",
]


@dataclass
class TrendSignal:
    keyword: str
    source: str
    raw_score: float          # 0–100 from the source
    trend_type: TrendType
    velocity: float = 1.0     # growth acceleration (>1 = speeding up)
    cross_platform_count: int = 1
    instagram_relevance: float = 1.0  # multiplier
    metadata: dict = field(default_factory=dict)

    @property
    def final_score(self) -> float:
        source_weight = WEIGHTS.get(self.source, 0.2)
        base = self.raw_score * source_weight * 5  # scale to 0–100 range
        velocity_bonus = max(0, (self.velocity - 1.0) * 20)
        cross_platform_bonus = (self.cross_platform_count - 1) * 10
        relevance_adj = base * self.instagram_relevance
        return min(relevance_adj + velocity_bonus + cross_platform_bonus, 100)


class TrendScorer:
    def __init__(self):
        self._signals: list[TrendSignal] = []

    def add_signals(self, signals: list[TrendSignal]):
        self._signals.extend(signals)

    def clear(self):
        self._signals = []

    @staticmethod
    def compute_instagram_relevance(keyword: str) -> float:
        """Score how relevant a keyword is to Instagram content creation."""
        kw_lower = keyword.lower()
        matches = sum(1 for term in INSTAGRAM_RELEVANCE_BOOST_TERMS if term in kw_lower)
        if matches >= 3:
            return 1.5
        if matches == 2:
            return 1.3
        if matches == 1:
            return 1.15
        return 1.0

    @staticmethod
    def normalize_keyword(keyword: str) -> str:
        """Lowercase and strip for deduplication."""
        return keyword.lower().strip().rstrip("s")  # naive stemming

    def merge_cross_platform(self, signals: list[TrendSignal]) -> list[TrendSignal]:
        """
        Merge signals about the same keyword from different sources.
        Cross-platform agreement is a strong trend signal.
        """
        from collections import defaultdict

        groups: dict[str, list[TrendSignal]] = defaultdict(list)
        for sig in signals:
            key = self.normalize_keyword(sig.keyword)
            groups[key].append(sig)

        merged = []
        for key, group in groups.items():
            if len(group) == 1:
                group[0].cross_platform_count = 1
                merged.append(group[0])
                continue

            # Create a merged signal from the group
            best = max(group, key=lambda s: s.raw_score)
            best.cross_platform_count = len(group)
            best.velocity = max(s.velocity for s in group)
            best.raw_score = sum(s.raw_score for s in group) / len(group)

            # Inherit metadata from all sources
            combined_metadata = {}
            for s in group:
                combined_metadata[s.source] = s.metadata
            best.metadata["sources"] = [s.source for s in group]
            best.metadata.update(combined_metadata)
            merged.append(best)

        return merged

    def rank(
        self,
        signals: list[TrendSignal] = None,
        trend_type: TrendType = None,
        limit: int = 20,
    ) -> list[TrendSignal]:
        """Return ranked trend signals, optionally filtered by type."""
        src = signals or self._signals
        if trend_type:
            src = [s for s in src if s.trend_type == trend_type]
        return sorted(src, key=lambda s: s.final_score, reverse=True)[:limit]

    def score_reel(self, reel: dict) -> float:
        """
        Score an individual Reel for trend potential.
        High score = currently viral or likely to go viral.
        """
        engagement = reel.get("engagement_score", 0)
        likes = reel.get("like_count", 0)
        comments = reel.get("comments_count", 0)
        has_signals = reel.get("has_trend_signals", False)
        discovery = reel.get("discovery_type", "top")

        score = 0.0

        # Engagement tiers
        if engagement > 500_000:
            score += 60
        elif engagement > 100_000:
            score += 45
        elif engagement > 50_000:
            score += 35
        elif engagement > 10_000:
            score += 25
        elif engagement > 1_000:
            score += 15
        else:
            score += 5

        # Comment ratio (high comments = viral conversation)
        if likes > 0 and comments / max(likes, 1) > 0.05:
            score += 10

        # Trend signal keywords in caption
        if has_signals:
            score += 15

        # Recent discovery = potential upcoming
        if discovery == "recent":
            score += 10

        return min(score, 100)


def build_signals_from_google(data: dict) -> list[TrendSignal]:
    signals = []
    for item in data.get("trending_now", []) + data.get("upcoming", []):
        kw = item.get("keyword", "")
        if not kw:
            continue
        signals.append(TrendSignal(
            keyword=kw,
            source="google_trends",
            raw_score=float(item.get("score", 50)),
            trend_type=item.get("type", "trending_now"),
            velocity=float(item.get("velocity", 1.0)),
            instagram_relevance=TrendScorer.compute_instagram_relevance(kw),
            metadata={"google_category": item.get("category", "")},
        ))
    return signals


def build_signals_from_meta(data: dict) -> list[TrendSignal]:
    signals = []
    for item in data.get("trending_now", []) + data.get("upcoming", []):
        kw = item.get("keyword", "")
        if not kw:
            continue
        signals.append(TrendSignal(
            keyword=kw,
            source="meta_ads_library",
            raw_score=float(item.get("score", 40)),
            trend_type=item.get("type", "trending_now"),
            instagram_relevance=TrendScorer.compute_instagram_relevance(kw),
            metadata={
                "page_name": item.get("page_name", ""),
                "copy_preview": item.get("copy_preview", ""),
                "snapshot_url": item.get("snapshot_url", ""),
            },
        ))
    # Add theme keywords as signals
    for theme in data.get("trending_themes", []):
        signals.append(TrendSignal(
            keyword=theme,
            source="meta_ads_library",
            raw_score=35.0,
            trend_type="trending_now",
            instagram_relevance=TrendScorer.compute_instagram_relevance(theme),
        ))
    return signals


def build_signals_from_exploding(data: dict) -> list[TrendSignal]:
    signals = []
    for item in data.get("trending_now", []) + data.get("upcoming", []):
        kw = item.get("keyword", "")
        if not kw:
            continue
        growth = item.get("growth_pct", 0)
        velocity = max(1.0, growth / 100) if growth > 0 else 1.0
        signals.append(TrendSignal(
            keyword=kw,
            source="exploding_topics",
            raw_score=float(item.get("score", 50)),
            trend_type=item.get("type", "upcoming"),
            velocity=velocity,
            instagram_relevance=TrendScorer.compute_instagram_relevance(kw),
            metadata={
                "growth_pct": growth,
                "category": item.get("category", ""),
                "et_url": item.get("url", ""),
            },
        ))
    return signals


def build_signals_from_social_blade(data: dict) -> list[TrendSignal]:
    signals = []
    for niche in data.get("trending_niches", []):
        niche_name = niche.get("niche", "")
        if not niche_name:
            continue
        growth = niche.get("avg_weekly_growth_pct", 0)
        signals.append(TrendSignal(
            keyword=f"{niche_name} content",
            source="social_blade",
            raw_score=min(float(growth) * 10, 100),
            trend_type=niche.get("type", "trending_now"),
            velocity=max(1.0, growth / 3),
            instagram_relevance=1.2,  # Social Blade data is inherently Instagram-relevant
            metadata={"avg_weekly_growth": growth},
        ))
    return signals
