"""Stage 2-3: Embed articles, score on relevance + reputation + corroboration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import Config, DomainReputation

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MODEL: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        logger.info("Loading sentence-transformer (all-MiniLM-L6-v2) — first run downloads ~80 MB…")
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    if denom < 1e-9:
        return 0.0
    return float(np.dot(a, b) / denom)


def _is_blocked(domain: str, rep: DomainReputation) -> bool:
    return any(
        domain == d or domain.endswith("." + d) for d in rep.blocked
    )


def _reputation_score(domain: str, rep: DomainReputation) -> float:
    if any(domain == d or domain.endswith("." + d) for d in rep.trusted):
        return rep.trusted_score
    return rep.neutral_score


def _corroboration_score(count: int, max_count: int) -> float:
    if max_count <= 1:
        return 0.0
    return min((count - 1) / (max_count - 1), 1.0)


def score_articles(articles: list[dict], cfg: Config) -> list[dict]:
    if not articles:
        return []

    # Drop blocked domains before any expensive work
    blocked_set = set(cfg.domain_reputation.blocked)
    articles = [
        a for a in articles
        if not _is_blocked(a["source_domain"], cfg.domain_reputation)
    ]
    if not articles:
        logger.warning("All articles were blocked; nothing to score.")
        return []

    model = _get_model()

    interest_emb: np.ndarray = model.encode(
        cfg.interest_paragraph, normalize_embeddings=True
    )

    texts = [
        (f"{a['title']} {a['summary']}")[:512] for a in articles
    ]
    article_embs: np.ndarray = model.encode(
        texts, normalize_embeddings=True, show_progress_bar=False, batch_size=64
    )

    max_corr = max((a.get("corroboration", 1) for a in articles), default=1)
    w = cfg.weights

    scored: list[dict] = []
    for art, emb in zip(articles, article_embs):
        relevance = _cosine(emb, interest_emb)
        reputation = _reputation_score(art["source_domain"], cfg.domain_reputation)
        corroboration = _corroboration_score(art.get("corroboration", 1), max_corr)

        final = (
            w.relevance * relevance
            + w.reputation * reputation
            + w.corroboration * corroboration
        )

        scored.append(
            {
                **art,
                "relevance_score": round(relevance, 4),
                "reputation_score": round(reputation, 4),
                "corroboration_score": round(corroboration, 4),
                "final_score": round(final, 4),
            }
        )

    scored.sort(key=lambda a: a["final_score"], reverse=True)

    logger.info(
        "Scored %d articles (top score %.3f, bottom %.3f)",
        len(scored),
        scored[0]["final_score"] if scored else 0,
        scored[-1]["final_score"] if scored else 0,
    )
    # Return ALL scored articles sorted by final_score.
    # Caller selects top_n for synthesis; all are persisted to DB to prevent
    # lower-ranked articles from reappearing in future runs.
    return scored


def print_stage2_report(articles: list[dict], show: int = 20) -> None:
    top = articles[:show]
    print(f"\n{'='*70}")
    print(f"  Stage 2 results: {len(articles)} scored  |  showing top {len(top)}")
    print(f"{'='*70}")
    print(f"{'#':>3}  {'Score':>6}  {'Rel':>5}  {'Rep':>5}  {'Corr':>4}  {'Domain':<28}  Title")
    print("-" * 120)
    for i, a in enumerate(top, 1):
        print(
            f"{i:>3}  {a['final_score']:>6.3f}  "
            f"{a['relevance_score']:>5.3f}  "
            f"{a['reputation_score']:>5.2f}  "
            f"{a.get('corroboration', 1):>4}  "
            f"{a['source_domain']:<28}  "
            f"{a['title'][:55]}"
        )
    print()
