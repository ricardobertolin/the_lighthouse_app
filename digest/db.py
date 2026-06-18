from __future__ import annotations

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "digest.db"


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
        CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url_hash
            ON articles(url_hash);
        CREATE INDEX IF NOT EXISTS idx_articles_title_hash
            ON articles(title_hash);
        CREATE INDEX IF NOT EXISTS idx_articles_seen_date
            ON articles(seen_date);

        CREATE TABLE IF NOT EXISTS clicks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            url             TEXT NOT NULL,
            source_domain   TEXT,
            clicked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            -- TODO: feedback loop — auto-promote frequently-clicked domains
            --       into the trusted tier and demote consistently ignored ones.
            --       Suggested query:
            --         SELECT source_domain, COUNT(*) as clicks
            --         FROM clicks GROUP BY source_domain ORDER BY clicks DESC
        );
        CREATE INDEX IF NOT EXISTS idx_clicks_domain ON clicks(source_domain);
        CREATE INDEX IF NOT EXISTS idx_clicks_at    ON clicks(clicked_at);
    """)
    # Migrate existing DB: add image_url if it was created before this column existed
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")
        conn.commit()
    except Exception:
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


def log_click(conn: sqlite3.Connection, url: str, source_domain: str) -> None:
    conn.execute(
        "INSERT INTO clicks (url, source_domain) VALUES (?, ?)",
        (url, source_domain),
    )
    conn.commit()
