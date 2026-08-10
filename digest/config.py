from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


@dataclass
class GNewsConfig:
    max_daily_queries: int = 15
    rate_limit_seconds: float = 1.1


@dataclass
class WeightsConfig:
    relevance: float = 0.50
    reputation: float = 0.30
    corroboration: float = 0.20


@dataclass
class DomainReputation:
    trusted: list[str] = field(default_factory=list)
    trusted_score: float = 0.85
    neutral_score: float = 0.40
    blocked: list[str] = field(default_factory=list)


@dataclass
class RetentionConfig:
    """Article text is only needed while it can still be re-rendered; dedup
    only ever reads url_hash. See db.prune."""
    keep_full_days: int = 30
    delete_after_days: int = 365


@dataclass
class Config:
    trusted_feeds: list[str]
    search_topics: list[str]
    search_topics_pt: list[str]
    interest_paragraph: str
    domain_reputation: DomainReputation
    weights: WeightsConfig
    top_n: int
    gnews: GNewsConfig
    browser: str = "default"
    # Embedded separately and scored by best match, so a story only has to hit
    # one interest rather than the average of all of them.
    interest_topics: list[str] = field(default_factory=list)
    # How far to pull relevance toward the centroid of clicked articles.
    click_weight: float = 0.30
    # Cosine above which two articles count as the same story.
    corroboration_similarity: float = 0.72
    retention: RetentionConfig = field(default_factory=RetentionConfig)


def load_config(path: Path = CONFIG_PATH) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    rep_raw = raw.get("domain_reputation", {})
    rep = DomainReputation(
        trusted=rep_raw.get("trusted", []),
        trusted_score=rep_raw.get("trusted_score", 0.85),
        neutral_score=rep_raw.get("neutral_score", 0.40),
        blocked=rep_raw.get("blocked", []),
    )

    gnews_raw = raw.get("gnews", {})
    gnews = GNewsConfig(
        max_daily_queries=gnews_raw.get("max_daily_queries", 15),
        rate_limit_seconds=gnews_raw.get("rate_limit_seconds", 1.1),
    )

    weights_raw = raw.get("weights", {})
    weights = WeightsConfig(
        relevance=weights_raw.get("relevance", 0.50),
        reputation=weights_raw.get("reputation", 0.30),
        corroboration=weights_raw.get("corroboration", 0.20),
    )

    ret_raw = raw.get("retention", {})
    retention = RetentionConfig(
        keep_full_days=ret_raw.get("keep_full_days", 30),
        delete_after_days=ret_raw.get("delete_after_days", 365),
    )

    return Config(
        trusted_feeds=raw.get("trusted_feeds", []),
        search_topics=raw.get("search_topics", []),
        search_topics_pt=raw.get("search_topics_pt", []),
        interest_paragraph=raw.get("interest_paragraph", ""),
        domain_reputation=rep,
        weights=weights,
        top_n=raw.get("top_n", 20),
        gnews=gnews,
        browser=raw.get("browser", "default"),
        interest_topics=raw.get("interest_topics", []),
        click_weight=raw.get("click_weight", 0.30),
        corroboration_similarity=raw.get("corroboration_similarity", 0.72),
        retention=retention,
    )
