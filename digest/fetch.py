"""Stage 1: Fetch from RSS feeds and GNews, then dedup + corroborate."""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

import feedparser
import httpx

from .config import Config
from .db import is_seen, url_hash, title_hash

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers

def _domain(url: str) -> str:
    host = urlparse(url).netloc
    return host.removeprefix("www.")


def _parse_dt(dt_struct) -> str:
    if dt_struct:
        try:
            return datetime(*dt_struct[:6], tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def _make_article(
    title: str, summary: str, url: str, published: str, origin: str,
    image_url: str = "",
) -> dict:
    t = (title or "").strip()
    s = (summary or "").strip()
    u = (url or "").strip()
    return {
        "title": t,
        "summary": s,
        "url": u,
        "source_domain": _domain(u),
        "published_at": published,
        "origin": origin,
        "image_url": (image_url or "").strip(),
        "url_hash": url_hash(u),
        "title_hash": title_hash(t),
    }


def _extract_rss_image(entry) -> str:
    """Pull the first usable image URL from a feedparser entry."""
    # <media:thumbnail url="...">
    for thumb in entry.get("media_thumbnail", []):
        url = thumb.get("url", "")
        if url:
            return url
    # <media:content url="..." medium="image"> or type="image/..."
    for mc in entry.get("media_content", []):
        if mc.get("medium") == "image" or mc.get("type", "").startswith("image/"):
            url = mc.get("url", "")
            if url:
                return url
    # <enclosure type="image/...">
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image/"):
            url = enc.get("href", "")
            if url:
                return url
    return ""


# ---------------------------------------------------------------------------
# RSS fetch

def fetch_rss(feeds: list[str]) -> list[dict]:
    articles: list[dict] = []
    for feed_url in feeds:
        try:
            parsed = feedparser.parse(feed_url)
            if parsed.bozo and not parsed.entries:
                logger.warning("RSS bozo error for %s: %s", feed_url, parsed.bozo_exception)
                continue
            count = 0
            for entry in parsed.entries:
                url = entry.get("link", "")
                if not url:
                    continue
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                published = _parse_dt(entry.get("published_parsed"))
                image_url = _extract_rss_image(entry)
                articles.append(_make_article(title, summary, url, published, "feed", image_url))
                count += 1
            logger.info("RSS %-55s -> %d articles", feed_url[:55], count)
        except Exception as exc:
            logger.warning("RSS fetch failed for %s: %s", feed_url, exc)
    return articles


# ---------------------------------------------------------------------------
# Search provider interface (swappable)

@runtime_checkable
class SearchProvider(Protocol):
    def search(self, query: str) -> list[dict]:
        ...


class GNewsProvider:
    """GNews free tier: 100 req/day, 1 req/sec, title + description only."""

    BASE_URL = "https://gnews.io/api/v4/search"

    def __init__(
        self,
        api_key: str,
        rate_limit_s: float = 1.1,
        max_queries: int = 15,
    ) -> None:
        self._key = api_key
        self._rate_limit = rate_limit_s
        self._max_queries = max_queries
        self._query_count = 0
        self._last_request: float = 0.0

    @property
    def queries_remaining(self) -> int:
        return self._max_queries - self._query_count

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        wait = self._rate_limit - elapsed
        if wait > 0:
            time.sleep(wait)

    def search(self, query: str, lang: str = "en") -> list[dict]:
        if self._query_count >= self._max_queries:
            logger.warning(
                "GNews daily cap (%d) reached — skipping: %r", self._max_queries, query
            )
            return []

        self._throttle()
        try:
            resp = httpx.get(
                self.BASE_URL,
                params={
                    "q": query,
                    "lang": lang,
                    "max": 10,
                    "token": self._key,
                },
                timeout=15,
            )
            self._last_request = time.monotonic()
            self._query_count += 1
            resp.raise_for_status()
            raw = resp.json()

            articles: list[dict] = []
            for item in raw.get("articles", []):
                url = item.get("url", "")
                if not url:
                    continue
                title = item.get("title", "")
                # GNews free tier: only title + description are reliable;
                # `content` is truncated and not used for scoring or synthesis.
                summary = item.get("description", "")
                published = item.get("publishedAt", datetime.now(timezone.utc).isoformat())
                image_data = item.get("image", "")
                image_url = (
                    image_data.get("url", "") if isinstance(image_data, dict) else str(image_data or "")
                )
                articles.append(_make_article(title, summary, url, published, "search", image_url))

            logger.info(
                "GNews %r → %d articles (query %d/%d)",
                query,
                len(articles),
                self._query_count,
                self._max_queries,
            )
            return articles

        except Exception as exc:
            self._last_request = time.monotonic()
            logger.warning("GNews query %r failed: %s", query, exc)
            return []


# ---------------------------------------------------------------------------
# Dedup + corroboration

def dedup_and_corroborate(articles: list[dict], conn) -> list[dict]:
    """
    1. Remove URL-exact duplicates within today's batch.
    2. Count distinct source_domains per title_hash (corroboration signal).
    3. Remove articles whose url_hash is already in the DB (yesterday+ dedup).
    Returns the fresh, annotated list.
    """
    # Pass 1: build title → {domains} map across the whole raw batch
    title_domains: dict[str, set[str]] = {}
    seen_url_hashes: set[str] = set()

    for art in articles:
        th = art["title_hash"]
        title_domains.setdefault(th, set()).add(art["source_domain"])

    # Pass 2: deduplicate and filter
    fresh: list[dict] = []
    for art in articles:
        uh = art["url_hash"]

        if uh in seen_url_hashes:
            continue  # within-batch URL duplicate
        seen_url_hashes.add(uh)

        if is_seen(conn, uh):
            continue  # already in DB (any previous day or earlier today)

        art = dict(art)  # don't mutate original
        art["corroboration"] = len(title_domains.get(art["title_hash"], {art["source_domain"]}))
        fresh.append(art)

    return fresh


# ---------------------------------------------------------------------------
# Main entry point for this stage

def fetch_all(cfg: Config, gnews_key: str | None, conn) -> list[dict]:
    articles: list[dict] = []

    # 1a — RSS
    rss = fetch_rss(cfg.trusted_feeds)
    articles.extend(rss)

    # 1b — GNews discovery
    if gnews_key:
        provider = GNewsProvider(
            api_key=gnews_key,
            rate_limit_s=cfg.gnews.rate_limit_seconds,
            max_queries=cfg.gnews.max_daily_queries,
        )
        en_topics = cfg.search_topics
        pt_topics = cfg.search_topics_pt
        # Allocate budget: pt topics get up to 1/3 of the cap, rest goes to en
        pt_budget = min(len(pt_topics), cfg.gnews.max_daily_queries // 3)
        en_budget = cfg.gnews.max_daily_queries - pt_budget
        for topic in en_topics[:en_budget]:
            if provider.queries_remaining <= 0:
                break
            articles.extend(provider.search(topic, lang="en"))
        for topic in pt_topics[:pt_budget]:
            if provider.queries_remaining <= 0:
                break
            articles.extend(provider.search(topic, lang="pt"))
    else:
        logger.warning("GNEWS_API_KEY not set — skipping discovery queries")

    # Dedup + corroboration
    fresh = dedup_and_corroborate(articles, conn)

    logger.info(
        "Fetch complete: %d raw articles -> %d fresh after dedup", len(articles), len(fresh)
    )
    return fresh


_OG_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*name=["\']twitter:image["\']', re.I),
]
_OG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def _fetch_og_image(url: str, timeout: float) -> str:
    try:
        with httpx.Client(timeout=timeout, headers=_OG_HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            text = resp.text[:40000]
        base = urlparse(url)
        for pat in _OG_PATTERNS:
            m = pat.search(text)
            if m:
                img = m.group(1).strip()
                if img.startswith("http"):
                    return img
                if img.startswith("//"):
                    return "https:" + img
                if img.startswith("/"):
                    return f"{base.scheme}://{base.netloc}{img}"
    except Exception:
        pass
    return ""


def enrich_missing_images(
    articles: list[dict],
    max_workers: int = 8,
    timeout: float = 5.0,
) -> list[dict]:
    """Fill image_url for articles that have none by fetching og:image from the article page."""
    missing = [a for a in articles if not a.get("image_url")]
    if not missing:
        return articles

    logger.info("Fetching OG images for %d articles without thumbnails...", len(missing))
    url_to_img: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(_fetch_og_image, a["url"], timeout): a["url"] for a in missing}
        for fut in as_completed(futs):
            url = futs[fut]
            img = fut.result()
            if img:
                url_to_img[url] = img

    found = len(url_to_img)
    logger.info("OG image enrichment: %d/%d found", found, len(missing))

    return [
        dict(a, image_url=url_to_img.get(a["url"], "")) if not a.get("image_url") else a
        for a in articles
    ]


def print_stage1_report(articles: list[dict]) -> None:
    """Pretty-print stage-1 results for standalone testing."""
    print(f"\n{'='*70}")
    print(f"  Stage 1 results: {len(articles)} fresh articles")
    print(f"{'='*70}")
    for i, a in enumerate(articles[:40], 1):
        corr = a.get("corroboration", 1)
        corr_str = f"[{corr} src]" if corr > 1 else ""
        print(
            f"{i:>3}. [{a['origin'][:4].upper()}] "
            f"({a['source_domain']:<30}) {corr_str}\n"
            f"     {a['title'][:90]}"
        )
    if len(articles) > 40:
        print(f"     … and {len(articles) - 40} more")
    print()
