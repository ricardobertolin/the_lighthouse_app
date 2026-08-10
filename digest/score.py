"""Stage 2-3: Embed articles, score on relevance + reputation + corroboration."""
from __future__ import annotations

import logging
import re

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import Config, DomainReputation

logger = logging.getLogger(__name__)

_MODEL: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        logger.info("Loading sentence-transformer (all-MiniLM-L6-v2) — first run downloads ~80 MB…")
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _is_blocked(domain: str, rep: DomainReputation) -> bool:
    return any(
        domain == d or domain.endswith("." + d) for d in rep.blocked
    )


def _reputation_score(domain: str, rep: DomainReputation) -> float:
    if any(domain == d or domain.endswith("." + d) for d in rep.trusted):
        return rep.trusted_score
    return rep.neutral_score


def _normalize(values: np.ndarray) -> np.ndarray:
    """
    Min-max a signal into [0, 1] across the batch.

    Raw MiniLM cosine against a headline lands in a narrow band (empirically
    -0.19..0.44, sd 0.077), while reputation is effectively binary at 0.40/0.85.
    Scoring them together unnormalized meant the 0.30 reputation weight
    swamped the 0.50 relevance weight and every top slot went to a trusted
    domain regardless of topic. Normalizing first makes the configured weights
    mean what they say.
    """
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-9:
        return np.full_like(values, 0.5)
    return (values - lo) / (hi - lo)


def _standardize_columns(matrix: np.ndarray) -> np.ndarray:
    """
    Z-score each topic's similarity column across the batch.

    Topic columns are not comparable raw: on a corpus that is ~60% Brazilian
    news, the Portuguese-flavoured topics average 0.21-0.25 cosine while the
    English tech topics average 0.00-0.03. That gap is the multilingual model
    clustering by language, not a statement about relevance — taking a raw max
    across columns therefore just selects whichever topic matches the corpus's
    dominant language, and every top slot went local.

    Standardizing per column asks "how well does this article match topic X
    relative to the rest of today's batch", which is language-neutral and lets
    the single best space story out-rank the 156th competent politics story.
    """
    mean = matrix.mean(axis=0, keepdims=True)
    std = matrix.std(axis=0, keepdims=True)
    std = np.where(std < 1e-9, 1.0, std)
    return (matrix - mean) / std


def _interest_topics(cfg: Config) -> list[str]:
    """Explicit topics if configured, else one per sentence of the paragraph."""
    if cfg.interest_topics:
        return cfg.interest_topics
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", cfg.interest_paragraph)]
    return [s for s in sentences if len(s) > 20] or [cfg.interest_paragraph]


def build_interest_vectors(
    cfg: Config, model: SentenceTransformer, clicked_texts: list[str] | None = None
) -> tuple[np.ndarray, np.ndarray | None]:
    """
    Return (topic_embeddings, click_centroid).

    A single vector averaged over "AI + geopolitics + climate + Curitiba" sits
    in the middle of all of them and is close to none, so topics are embedded
    separately and relevance takes the best match. The click centroid is the
    learned half: it is the mean of what actually got read.
    """
    topics = _interest_topics(cfg)
    topic_embs = model.encode(topics, normalize_embeddings=True)
    topic_embs = np.atleast_2d(topic_embs)
    logger.info("Interest profile: %d topic vector(s).", len(topic_embs))

    centroid = None
    if clicked_texts:
        click_embs = model.encode(
            [t[:512] for t in clicked_texts],
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )
        centroid = np.atleast_2d(click_embs).mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        if norm > 1e-9:
            centroid = centroid / norm
            logger.info("Click centroid built from %d clicked articles.", len(clicked_texts))
        else:
            centroid = None
    return topic_embs, centroid


def _corroboration_counts(
    embeddings: np.ndarray, domains: list[str], threshold: float
) -> list[int]:
    """
    Distinct source domains covering each story.

    The original exact-title match found corroboration for 141 of 18,893
    articles (0.7%) — two outlets essentially never write byte-identical
    headlines, so the signal was dead. Clustering on the embeddings that were
    computed anyway catches the same story told in different words, and across
    languages.
    """
    # Embeddings are L2-normalized, so the Gram matrix is pairwise cosine.
    sim = embeddings @ embeddings.T
    neighbours = sim >= threshold

    domain_ids = {}
    idx = np.array([domain_ids.setdefault(d, len(domain_ids)) for d in domains])

    counts = []
    for row in neighbours:
        counts.append(int(np.unique(idx[row]).size))
    return counts


def score_articles(
    articles: list[dict],
    cfg: Config,
    clicked_texts: list[str] | None = None,
) -> list[dict]:
    if not articles:
        return []

    articles = [
        a for a in articles
        if not _is_blocked(a["source_domain"], cfg.domain_reputation)
    ]
    if not articles:
        logger.warning("All articles were blocked; nothing to score.")
        return []

    model = _get_model()
    topic_embs, click_centroid = build_interest_vectors(cfg, model, clicked_texts)

    texts = [(f"{a['title']} {a['summary']}")[:512] for a in articles]
    article_embs: np.ndarray = model.encode(
        texts, normalize_embeddings=True, show_progress_bar=False, batch_size=64
    )

    # Relevance — best-matching topic, optionally pulled toward what gets read.
    topic_sim = _standardize_columns(article_embs @ topic_embs.T)
    relevance_raw = topic_sim.max(axis=1)
    if click_centroid is not None and cfg.click_weight > 0:
        # Standardized on the same scale so the blend weight is meaningful.
        click_sim = _standardize_columns(
            (article_embs @ click_centroid).reshape(-1, 1)
        ).ravel()
        w = cfg.click_weight
        relevance_raw = (1.0 - w) * relevance_raw + w * click_sim

    # Corroboration — recomputed here rather than trusting fetch's title match.
    corr_counts = _corroboration_counts(
        article_embs, [a["source_domain"] for a in articles], cfg.corroboration_similarity
    )
    max_corr = max(corr_counts)

    reputation_raw = np.array(
        [_reputation_score(a["source_domain"], cfg.domain_reputation) for a in articles]
    )
    corroboration_raw = np.array(corr_counts, dtype=float)

    rel_n = _normalize(relevance_raw)
    rep_n = _normalize(reputation_raw)
    corr_n = _normalize(corroboration_raw)

    w = cfg.weights
    final = w.relevance * rel_n + w.reputation * rep_n + w.corroboration * corr_n

    scored: list[dict] = []
    for i, art in enumerate(articles):
        scored.append(
            {
                **art,
                "corroboration": corr_counts[i],
                # Raw cosine is kept for display; the normalized value is what
                # actually drives final_score.
                "relevance_score": round(float(relevance_raw[i]), 4),
                "reputation_score": round(float(reputation_raw[i]), 4),
                "corroboration_score": round(float(corr_n[i]), 4),
                "final_score": round(float(final[i]), 4),
            }
        )

    scored.sort(key=lambda a: a["final_score"], reverse=True)

    logger.info(
        "Scored %d articles (top %.3f, bottom %.3f) | corroborated>1: %d | max sources: %d",
        len(scored),
        scored[0]["final_score"],
        scored[-1]["final_score"],
        sum(1 for c in corr_counts if c > 1),
        max_corr,
    )
    # All scored articles are returned sorted by final_score. The caller takes
    # top_n for synthesis but persists everything, so lower-ranked articles
    # don't reappear in future runs.
    return scored


def print_stage2_report(articles: list[dict], show: int = 20) -> None:
    top = articles[:show]
    print(f"\n{'='*70}")
    print(f"  Stage 2 results: {len(articles)} scored  |  showing top {len(top)}")
    print(f"{'='*70}")
    print(f"{'#':>3}  {'Score':>6}  {'Rel':>6}  {'Rep':>5}  {'Corr':>4}  {'Domain':<28}  Title")
    print("-" * 120)
    for i, a in enumerate(top, 1):
        print(
            f"{i:>3}  {a['final_score']:>6.3f}  "
            f"{a['relevance_score']:>6.3f}  "
            f"{a['reputation_score']:>5.2f}  "
            f"{a.get('corroboration', 1):>4}  "
            f"{a['source_domain']:<28}  "
            f"{a['title'][:55]}"
        )
    print()
