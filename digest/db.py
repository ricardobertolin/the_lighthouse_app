from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "digest.db"

logger = logging.getLogger(__name__)


def get_conn(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash        TEXT NOT NULL,
            title_hash      TEXT NOT NULL,
            url             TEXT NOT NULL,
            title           TEXT,
            summary         TEXT,
            source_domain   TEXT,
            published_at    TEXT,
            origin          TEXT,
            image_url       TEXT,
            corroboration   INTEGER DEFAULT 1,
            relevance_score REAL,
            reputation_score REAL,
            corroboration_score REAL,
            final_score     REAL,
            seen_date       TEXT NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Clicks recorded in the browser (localStorage) and imported via
        -- `python -m digest --ingest-clicks`. Feeds the interest centroid in
        -- score.py, so what actually gets read steers future ranking.
        CREATE TABLE IF NOT EXISTS clicks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            url             TEXT NOT NULL,
            url_hash        TEXT,
            source_domain   TEXT,
            clicked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- One row per published digest. `url_hashes` pins the exact article
        -- order the LLM saw, so --render-only reproduces the real page instead
        -- of falling back to untranslated titles.
        CREATE TABLE IF NOT EXISTS synthesis (
            seen_date   TEXT PRIMARY KEY,
            payload     TEXT NOT NULL,
            url_hashes  TEXT NOT NULL,
            model       TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Indexes come after the column migration: some of them (clicks.url_hash)
    # reference columns that older databases don't have yet.
    _migrate(conn)
    conn.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url_hash
            ON articles(url_hash);
        CREATE INDEX IF NOT EXISTS idx_articles_title_hash
            ON articles(title_hash);
        CREATE INDEX IF NOT EXISTS idx_articles_seen_date
            ON articles(seen_date);
        CREATE INDEX IF NOT EXISTS idx_clicks_domain ON clicks(source_domain);
        CREATE INDEX IF NOT EXISTS idx_clicks_at    ON clicks(clicked_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clicks_unique
            ON clicks(url_hash, clicked_at);
    """)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the original schema. Safe to re-run."""
    for table, column, decl in (
        ("articles", "image_url", "TEXT"),
        ("clicks", "url_hash", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()[:32]


def title_hash(title: str) -> str:
    normalized = " ".join(title.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def is_seen(conn: sqlite3.Connection, uh: str) -> bool:
    """True if this URL has ever appeared in the DB (any date)."""
    row = conn.execute(
        "SELECT 1 FROM articles WHERE url_hash = ?", (uh,)
    ).fetchone()
    return row is not None


def upsert_article(conn: sqlite3.Connection, article: dict) -> None:
    today = date.today().isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO articles
            (url_hash, title_hash, url, title, summary, source_domain,
             published_at, origin, image_url, corroboration,
             relevance_score, reputation_score, corroboration_score,
             final_score, seen_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article["url_hash"],
            article["title_hash"],
            article["url"],
            article.get("title", ""),
            article.get("summary", ""),
            article.get("source_domain", ""),
            article.get("published_at", ""),
            article.get("origin", "feed"),
            article.get("image_url", ""),
            article.get("corroboration", 1),
            article.get("relevance_score"),
            article.get("reputation_score"),
            article.get("corroboration_score"),
            article.get("final_score"),
            today,
        ),
    )
    conn.commit()


def update_images(conn: sqlite3.Connection, articles: list[dict]) -> int:
    """
    Write OG-enriched image URLs back to the DB.

    upsert_article runs before image enrichment and uses INSERT OR IGNORE, so
    without this the enriched thumbnails only ever existed in the rendered HTML
    and were lost on any re-render.
    """
    updated = 0
    for art in articles:
        img = art.get("image_url") or ""
        if not img:
            continue
        cur = conn.execute(
            "UPDATE articles SET image_url = ? "
            "WHERE url_hash = ? AND (image_url IS NULL OR image_url = '')",
            (img, art["url_hash"]),
        )
        updated += cur.rowcount
    conn.commit()
    return updated


def get_today_articles(conn: sqlite3.Connection) -> list[dict]:
    """Return all articles already persisted for today, best-first."""
    today = date.today().isoformat()
    rows = conn.execute(
        """
        SELECT url_hash, title_hash, url, title, summary, source_domain,
               published_at, origin, image_url, corroboration,
               relevance_score, reputation_score, corroboration_score,
               final_score, seen_date
        FROM articles
        WHERE seen_date = ?
        ORDER BY final_score DESC NULLS LAST
        """,
        (today,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_articles_by_hash(conn: sqlite3.Connection, hashes: list[str]) -> list[dict]:
    """
    Fetch articles by url_hash, returned in the order the hashes were given.

    Order matters: the synthesis payload addresses articles by index, so the
    list handed to render() must match the one the LLM was shown.
    """
    if not hashes:
        return []
    placeholders = ",".join("?" * len(hashes))
    rows = conn.execute(
        f"""
        SELECT url_hash, title_hash, url, title, summary, source_domain,
               published_at, origin, image_url, corroboration,
               relevance_score, reputation_score, corroboration_score,
               final_score, seen_date
        FROM articles
        WHERE url_hash IN ({placeholders})
        """,
        hashes,
    ).fetchall()
    by_hash = {row["url_hash"]: dict(row) for row in rows}
    return [by_hash[h] for h in hashes if h in by_hash]


# ---------------------------------------------------------------------------
# Synthesis persistence


def save_synthesis(
    conn: sqlite3.Connection,
    synthesis: dict,
    articles: list[dict],
    model: str = "",
    day: str | None = None,
) -> None:
    day = day or date.today().isoformat()
    conn.execute(
        """
        INSERT INTO synthesis (seen_date, payload, url_hashes, model)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(seen_date) DO UPDATE SET
            payload    = excluded.payload,
            url_hashes = excluded.url_hashes,
            model      = excluded.model,
            created_at = CURRENT_TIMESTAMP
        """,
        (
            day,
            json.dumps(synthesis, ensure_ascii=False),
            json.dumps([a["url_hash"] for a in articles]),
            model,
        ),
    )
    conn.commit()


def get_synthesis(
    conn: sqlite3.Connection, day: str | None = None
) -> tuple[dict, list[str]] | None:
    """Return (synthesis_payload, ordered_url_hashes) for a day, or None."""
    day = day or date.today().isoformat()
    row = conn.execute(
        "SELECT payload, url_hashes FROM synthesis WHERE seen_date = ?", (day,)
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["payload"]), json.loads(row["url_hashes"])
    except (json.JSONDecodeError, TypeError):
        logger.warning("Stored synthesis for %s is corrupt — ignoring.", day)
        return None


# ---------------------------------------------------------------------------
# Clicks


def log_click(
    conn: sqlite3.Connection,
    url: str,
    source_domain: str = "",
    clicked_at: str | None = None,
) -> bool:
    """Record a click. Returns True if it was new (idempotent on re-import)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO clicks (url, url_hash, source_domain, clicked_at) "
        "VALUES (?, ?, ?, ?)",
        (
            url,
            url_hash(url),
            source_domain,
            clicked_at or datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def get_clicked_texts(conn: sqlite3.Connection, limit: int = 300) -> list[str]:
    """
    Title + summary for recently clicked articles, newest first.

    Used to build the interest centroid. Rows whose text has been pruned come
    back empty and are filtered out by the caller.
    """
    rows = conn.execute(
        """
        SELECT a.title, a.summary
        FROM clicks c
        JOIN articles a ON a.url_hash = c.url_hash
        ORDER BY c.clicked_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    texts = []
    for row in rows:
        text = f"{row['title'] or ''} {row['summary'] or ''}".strip()
        if text:
            texts.append(text)
    return texts


def get_recurring_title_hashes(
    conn: sqlite3.Connection, min_days: int = 3
) -> set[str]:
    """
    Titles that have appeared on `min_days` or more distinct days.

    A headline that repeats verbatim across weeks is a strand, not a story:
    a podcast episode ("Tech Life"), a live-blog stub ("Here's the latest."),
    a recurring column. Each gets a fresh URL every time, so url_hash dedup
    never catches them, and their generic wording sits closer to an abstract
    interest topic than any specific news article does — on 2026-08-11 "Tech
    Life" scored 6.07 standard deviations above the batch mean and took the
    top slot.

    Across 18,893 rows only four titles reach three days, and all four are
    this kind of filler, so the threshold discriminates cleanly.
    """
    rows = conn.execute(
        """
        SELECT title_hash
        FROM articles
        WHERE title != ''
        GROUP BY title_hash
        HAVING COUNT(DISTINCT seen_date) >= ?
        """,
        (min_days,),
    ).fetchall()
    return {row["title_hash"] for row in rows}


def get_click_domain_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT source_domain, COUNT(*) n FROM clicks "
        "WHERE source_domain != '' GROUP BY source_domain ORDER BY n DESC"
    ).fetchall()
    return {row["source_domain"]: row["n"] for row in rows}


# ---------------------------------------------------------------------------
# Retention
#
# is_seen() only ever reads url_hash, so the article text is dead weight once
# the digest that used it has been published. Keeping full rows for a month
# covers re-renders and click ingestion; after that only the hash needs to
# survive to keep dedup working.


def prune(
    conn: sqlite3.Connection,
    keep_full_days: int = 30,
    delete_after_days: int = 365,
    vacuum: bool = False,
) -> dict[str, int]:
    today = date.today()
    strip_before = (today - timedelta(days=keep_full_days)).isoformat()
    delete_before = (today - timedelta(days=delete_after_days)).isoformat()

    deleted = conn.execute(
        "DELETE FROM articles WHERE seen_date < ?", (delete_before,)
    ).rowcount

    # Keep url_hash/seen_date/source_domain; drop everything else. Empty string
    # rather than NULL so existing readers keep working unchanged.
    # `url` goes too: is_seen() reads url_hash, and clicks join on url_hash, so
    # the full URL is dead weight. Dropping it takes a stripped row from
    # 432 to 289 bytes, and stripped rows are ~92% of the table at steady state.
    stripped = conn.execute(
        """
        UPDATE articles
        SET summary = '', title = '', image_url = '', url = ''
        WHERE seen_date < ? AND (summary != '' OR title != '' OR url != '')
        """,
        (strip_before,),
    ).rowcount
    conn.commit()

    if vacuum:
        conn.execute("VACUUM")

    logger.info(
        "Retention: stripped text from %d rows (older than %s), deleted %d rows "
        "(older than %s).",
        stripped, strip_before, deleted, delete_before,
    )
    return {"stripped": stripped, "deleted": deleted}
