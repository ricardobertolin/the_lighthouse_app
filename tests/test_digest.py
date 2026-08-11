"""
Unit tests for the parts of the pipeline that don't need network or an API key.

Run with:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from digest import db
from digest.fetch import dedup, _domain, _make_article
from digest.score import (
    _normalize,
    _standardize_columns,
    _corroboration_counts,
    _interest_topics,
    _reputation_score,
    _is_blocked,
)
from digest.config import Config, DomainReputation, WeightsConfig, GNewsConfig


def _tmp_conn() -> tuple[sqlite3.Connection, Path]:
    path = Path(tempfile.mkdtemp()) / "test.db"
    return db.get_conn(path), path


class NormalizeTests(unittest.TestCase):
    def test_maps_to_unit_range(self):
        out = _normalize(np.array([1.0, 3.0, 5.0]))
        self.assertAlmostEqual(out.min(), 0.0)
        self.assertAlmostEqual(out.max(), 1.0)
        self.assertAlmostEqual(out[1], 0.5)

    def test_constant_input_does_not_divide_by_zero(self):
        out = _normalize(np.array([2.0, 2.0, 2.0]))
        self.assertTrue(np.allclose(out, 0.5))

    def test_handles_negative_values(self):
        # Raw cosine against short headlines does go negative.
        out = _normalize(np.array([-0.2, 0.0, 0.4]))
        self.assertAlmostEqual(out.min(), 0.0)
        self.assertAlmostEqual(out.max(), 1.0)


class StandardizeTests(unittest.TestCase):
    def test_columns_become_zero_mean_unit_variance(self):
        m = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
        out = _standardize_columns(m)
        self.assertTrue(np.allclose(out.mean(axis=0), 0.0, atol=1e-9))
        self.assertTrue(np.allclose(out.std(axis=0), 1.0, atol=1e-9))

    def test_removes_between_column_scale_bias(self):
        """
        The bug this exists to prevent: one topic column sitting at a much
        higher baseline than another purely because of language clustering,
        so a raw argmax always picks the same column.
        """
        # Column 0 is uniformly high, column 1 uniformly low, but column 1's
        # last row is its own standout.
        m = np.array([[0.30, 0.00], [0.31, 0.01], [0.29, 0.10]])
        self.assertTrue(np.all(m.argmax(axis=1) == 0))  # raw: col 0 always wins
        out = _standardize_columns(m)
        self.assertEqual(out[2].argmax(), 1)  # standardized: the standout wins

    def test_zero_variance_column_does_not_produce_nan(self):
        m = np.array([[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]])
        out = _standardize_columns(m)
        self.assertFalse(np.isnan(out).any())


class CorroborationTests(unittest.TestCase):
    @staticmethod
    def _unit(vec):
        v = np.array(vec, dtype=float)
        return v / np.linalg.norm(v)

    def test_similar_articles_from_different_domains_corroborate(self):
        a = self._unit([1.0, 0.0, 0.0])
        near = self._unit([0.99, 0.14, 0.0])  # cosine ~0.99 with `a`
        far = self._unit([0.0, 0.0, 1.0])
        embs = np.vstack([a, near, far])
        counts = _corroboration_counts(embs, ["bbc.com", "nytimes.com", "wired.com"], 0.72)
        self.assertEqual(counts, [2, 2, 1])

    def test_same_domain_does_not_self_corroborate(self):
        a = self._unit([1.0, 0.0, 0.0])
        near = self._unit([0.99, 0.14, 0.0])
        embs = np.vstack([a, near])
        counts = _corroboration_counts(embs, ["bbc.com", "bbc.com"], 0.72)
        self.assertEqual(counts, [1, 1])

    def test_threshold_is_respected(self):
        a = self._unit([1.0, 0.0])
        b = self._unit([0.6, 0.8])  # cosine 0.6 with `a`
        embs = np.vstack([a, b])
        self.assertEqual(_corroboration_counts(embs, ["x.com", "y.com"], 0.72), [1, 1])
        self.assertEqual(_corroboration_counts(embs, ["x.com", "y.com"], 0.55), [2, 2])


class InterestTopicTests(unittest.TestCase):
    def _cfg(self, topics, paragraph):
        return Config(
            trusted_feeds=[], search_topics=[], search_topics_pt=[],
            interest_paragraph=paragraph,
            domain_reputation=DomainReputation(), weights=WeightsConfig(),
            top_n=20, gnews=GNewsConfig(), interest_topics=topics,
        )

    def test_explicit_topics_win(self):
        cfg = self._cfg(["ai", "space"], "some paragraph here that is long enough.")
        self.assertEqual(_interest_topics(cfg), ["ai", "space"])

    def test_falls_back_to_sentence_split(self):
        cfg = self._cfg([], "I care about artificial intelligence a lot. I also follow geopolitics closely.")
        topics = _interest_topics(cfg)
        self.assertEqual(len(topics), 2)
        self.assertIn("artificial intelligence", topics[0])

    def test_never_returns_empty(self):
        cfg = self._cfg([], "short.")
        self.assertEqual(_interest_topics(cfg), ["short."])


class ReputationTests(unittest.TestCase):
    def setUp(self):
        self.rep = DomainReputation(trusted=["bbc.com"], blocked=["spam.example"])

    def test_subdomain_of_trusted_is_trusted(self):
        self.assertEqual(_reputation_score("news.bbc.com", self.rep), 0.85)

    def test_unknown_domain_is_neutral(self):
        self.assertEqual(_reputation_score("random.io", self.rep), 0.40)

    def test_lookalike_domain_is_not_trusted(self):
        # endswith("." + d) must not match "notbbc.com"
        self.assertEqual(_reputation_score("notbbc.com", self.rep), 0.40)

    def test_blocked_matches_subdomains(self):
        self.assertTrue(_is_blocked("a.spam.example", "https://a.spam.example/x", self.rep))
        self.assertFalse(_is_blocked("notspam.example", "https://notspam.example/x", self.rep))


class BlockedUrlPatternTests(unittest.TestCase):
    """BBC ships podcast episodes through the technology news feed."""

    def setUp(self):
        self.rep = DomainReputation(
            trusted=["bbc.co.uk"], blocked_url_patterns=["bbc.co.uk/sounds/"]
        )

    def test_blocks_matching_path_on_an_otherwise_trusted_domain(self):
        self.assertTrue(
            _is_blocked("bbc.co.uk", "https://www.bbc.co.uk/sounds/play/w3ct8jy7", self.rep)
        )

    def test_leaves_news_on_the_same_domain_alone(self):
        self.assertFalse(
            _is_blocked("bbc.co.uk", "https://www.bbc.co.uk/news/technology-123", self.rep)
        )

    def test_missing_url_does_not_raise(self):
        self.assertFalse(_is_blocked("bbc.co.uk", "", self.rep))


class DedupTests(unittest.TestCase):
    def setUp(self):
        self.conn, _ = _tmp_conn()

    def tearDown(self):
        self.conn.close()

    def _art(self, url, title="t"):
        return _make_article(title, "summary", url, "2026-08-10T00:00:00", "feed")

    def test_removes_within_batch_duplicates(self):
        arts = [self._art("https://a.com/1"), self._art("https://a.com/1")]
        self.assertEqual(len(dedup(arts, self.conn)), 1)

    def test_url_matching_is_case_insensitive(self):
        arts = [self._art("https://a.com/One"), self._art("https://A.com/one")]
        self.assertEqual(len(dedup(arts, self.conn)), 1)

    def test_removes_articles_already_in_db(self):
        art = self._art("https://a.com/1")
        db.upsert_article(self.conn, art)
        self.assertEqual(dedup([art], self.conn), [])

    def test_does_not_mutate_input(self):
        art = self._art("https://a.com/1")
        out = dedup([art], self.conn)
        out[0]["title"] = "changed"
        self.assertEqual(art["title"], "t")


class DomainTests(unittest.TestCase):
    def test_strips_www(self):
        self.assertEqual(_domain("https://www.bbc.com/news"), "bbc.com")

    def test_keeps_other_subdomains(self):
        self.assertEqual(_domain("https://feeds.bbci.co.uk/x"), "feeds.bbci.co.uk")


class RecurringTitleTests(unittest.TestCase):
    """
    A title repeating verbatim across days is a strand, not a story. Each
    episode gets a fresh URL, so url_hash dedup never catches it.
    """

    def setUp(self):
        self.conn, _ = _tmp_conn()

    def tearDown(self):
        self.conn.close()

    def _seen(self, title, url, day):
        art = _make_article(title, "summary", url, "2026-08-10T00:00:00", "feed")
        art["seen_date"] = day
        db.upsert_article(self.conn, art)
        self.conn.execute(
            "UPDATE articles SET seen_date = ? WHERE url_hash = ?",
            (day, art["url_hash"]),
        )
        self.conn.commit()
        return art

    def test_flags_a_title_repeating_across_days(self):
        for n, day in enumerate(["2026-08-01", "2026-08-08", "2026-08-15"]):
            self._seen("Tech Life", f"https://bbc.co.uk/sounds/play/w{n}", day)
        art = self._seen("Tech Life", "https://bbc.co.uk/sounds/play/w9", "2026-08-22")
        self.assertIn(art["title_hash"], db.get_recurring_title_hashes(self.conn, 3))

    def test_ignores_a_title_below_the_threshold(self):
        for n, day in enumerate(["2026-08-01", "2026-08-08"]):
            art = self._seen("Weekly Roundup", f"https://x.com/{n}", day)
        self.assertNotIn(art["title_hash"], db.get_recurring_title_hashes(self.conn, 3))

    def test_same_day_repeats_do_not_accumulate(self):
        # Three URLs, one day: a syndication burst, not a recurring strand.
        for n in range(3):
            art = self._seen("Breaking", f"https://x.com/{n}", "2026-08-01")
        self.assertNotIn(art["title_hash"], db.get_recurring_title_hashes(self.conn, 3))

    def test_pruned_rows_are_excluded(self):
        # prune() blanks title but keeps the hash; those rows must not count.
        for n, day in enumerate(["2026-08-01", "2026-08-08", "2026-08-15"]):
            art = self._seen("Tech Life", f"https://bbc.co.uk/sounds/{n}", day)
        self.conn.execute("UPDATE articles SET title = ''")
        self.conn.commit()
        self.assertEqual(db.get_recurring_title_hashes(self.conn, 3), set())


class SynthesisPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.conn, _ = _tmp_conn()
        self.articles = [
            _make_article(f"title {i}", "s", f"https://a.com/{i}", "2026-08-10", "feed")
            for i in range(3)
        ]
        for a in self.articles:
            db.upsert_article(self.conn, a)

    def tearDown(self):
        self.conn.close()

    def test_roundtrip_preserves_payload_and_order(self):
        payload = {"intro_en": "hi", "articles": [{"index": 0}]}
        db.save_synthesis(self.conn, payload, self.articles, model="test")
        got, hashes = db.get_synthesis(self.conn)
        self.assertEqual(got, payload)
        self.assertEqual(hashes, [a["url_hash"] for a in self.articles])

    def test_get_articles_by_hash_preserves_given_order(self):
        hashes = [self.articles[2]["url_hash"], self.articles[0]["url_hash"]]
        got = db.get_articles_by_hash(self.conn, hashes)
        self.assertEqual([a["url_hash"] for a in got], hashes)
        self.assertEqual(got[0]["title"], "title 2")

    def test_missing_hashes_are_skipped_not_fatal(self):
        got = db.get_articles_by_hash(self.conn, ["deadbeef", self.articles[0]["url_hash"]])
        self.assertEqual(len(got), 1)

    def test_second_save_for_same_day_overwrites(self):
        db.save_synthesis(self.conn, {"v": 1}, self.articles)
        db.save_synthesis(self.conn, {"v": 2}, self.articles)
        payload, _ = db.get_synthesis(self.conn)
        self.assertEqual(payload["v"], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM synthesis").fetchone()[0], 1)

    def test_missing_day_returns_none(self):
        self.assertIsNone(db.get_synthesis(self.conn, "1999-01-01"))


class ImageWritebackTests(unittest.TestCase):
    def setUp(self):
        self.conn, _ = _tmp_conn()

    def tearDown(self):
        self.conn.close()

    def test_fills_empty_image_only(self):
        art = _make_article("t", "s", "https://a.com/1", "2026-08-10", "feed")
        db.upsert_article(self.conn, art)
        n = db.update_images(self.conn, [dict(art, image_url="https://img/1.png")])
        self.assertEqual(n, 1)
        row = self.conn.execute("SELECT image_url FROM articles").fetchone()
        self.assertEqual(row["image_url"], "https://img/1.png")

    def test_does_not_overwrite_existing_image(self):
        art = _make_article("t", "s", "https://a.com/1", "2026-08-10", "feed", image_url="https://orig.png")
        db.upsert_article(self.conn, art)
        db.update_images(self.conn, [dict(art, image_url="https://new.png")])
        row = self.conn.execute("SELECT image_url FROM articles").fetchone()
        self.assertEqual(row["image_url"], "https://orig.png")


class ClickTests(unittest.TestCase):
    def setUp(self):
        self.conn, _ = _tmp_conn()

    def tearDown(self):
        self.conn.close()

    def test_reimport_of_same_click_is_idempotent(self):
        self.assertTrue(db.log_click(self.conn, "https://a.com/1", "a.com", "2026-08-10T10:00:00"))
        self.assertFalse(db.log_click(self.conn, "https://a.com/1", "a.com", "2026-08-10T10:00:00"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0], 1)

    def test_same_url_at_different_times_counts_twice(self):
        db.log_click(self.conn, "https://a.com/1", "a.com", "2026-08-10T10:00:00")
        db.log_click(self.conn, "https://a.com/1", "a.com", "2026-08-11T10:00:00")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0], 2)

    def test_clicked_texts_joins_to_articles(self):
        art = _make_article("Clicked headline", "body", "https://a.com/1", "2026-08-10", "feed")
        db.upsert_article(self.conn, art)
        db.log_click(self.conn, "https://a.com/1", "a.com")
        texts = db.get_clicked_texts(self.conn)
        self.assertEqual(len(texts), 1)
        self.assertIn("Clicked headline", texts[0])

    def test_clicked_texts_skips_pruned_rows(self):
        art = _make_article("Old", "body", "https://a.com/1", "2026-08-10", "feed")
        db.upsert_article(self.conn, art)
        db.log_click(self.conn, "https://a.com/1", "a.com")
        self.conn.execute("UPDATE articles SET title='', summary=''")
        self.conn.commit()
        self.assertEqual(db.get_clicked_texts(self.conn), [])

    def test_domain_counts(self):
        db.log_click(self.conn, "https://a.com/1", "a.com", "2026-01-01T00:00:00")
        db.log_click(self.conn, "https://a.com/2", "a.com", "2026-01-02T00:00:00")
        db.log_click(self.conn, "https://b.com/1", "b.com", "2026-01-03T00:00:00")
        self.assertEqual(db.get_click_domain_counts(self.conn), {"a.com": 2, "b.com": 1})


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.conn, _ = _tmp_conn()

    def tearDown(self):
        self.conn.close()

    def _insert(self, url, days_ago):
        art = _make_article("title", "summary", url, "2026-01-01", "feed")
        db.upsert_article(self.conn, art)
        self.conn.execute(
            "UPDATE articles SET seen_date = ? WHERE url_hash = ?",
            ((date.today() - timedelta(days=days_ago)).isoformat(), art["url_hash"]),
        )
        self.conn.commit()
        return art["url_hash"]

    def test_recent_rows_keep_their_text(self):
        self._insert("https://a.com/recent", days_ago=5)
        db.prune(self.conn, keep_full_days=30, delete_after_days=365)
        row = self.conn.execute("SELECT title, summary FROM articles").fetchone()
        self.assertEqual(row["title"], "title")
        self.assertEqual(row["summary"], "summary")

    def test_old_rows_lose_text_but_keep_hash(self):
        uh = self._insert("https://a.com/old", days_ago=60)
        db.prune(self.conn, keep_full_days=30, delete_after_days=365)
        row = self.conn.execute("SELECT url_hash, title, summary, url FROM articles").fetchone()
        self.assertEqual(row["url_hash"], uh)
        self.assertEqual(row["title"], "")
        self.assertEqual(row["summary"], "")
        self.assertEqual(row["url"], "")

    def test_stripped_rows_still_dedup(self):
        """The whole point of keeping the hash: pruning must not resurrect articles."""
        art = _make_article("t", "s", "https://a.com/old", "2026-01-01", "feed")
        db.upsert_article(self.conn, art)
        self.conn.execute(
            "UPDATE articles SET seen_date = ?",
            ((date.today() - timedelta(days=60)).isoformat(),),
        )
        self.conn.commit()
        db.prune(self.conn, keep_full_days=30, delete_after_days=365)
        self.assertTrue(db.is_seen(self.conn, art["url_hash"]))
        self.assertEqual(dedup([art], self.conn), [])

    def test_very_old_rows_are_deleted(self):
        self._insert("https://a.com/ancient", days_ago=400)
        db.prune(self.conn, keep_full_days=30, delete_after_days=365)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 0)

    def test_prune_is_idempotent(self):
        self._insert("https://a.com/old", days_ago=60)
        first = db.prune(self.conn, keep_full_days=30, delete_after_days=365)
        second = db.prune(self.conn, keep_full_days=30, delete_after_days=365)
        self.assertEqual(first["stripped"], 1)
        self.assertEqual(second["stripped"], 0)


class SchemaMigrationTests(unittest.TestCase):
    def test_upgrades_a_pre_existing_legacy_database(self):
        """The shipped DB predates image_url, clicks.url_hash and synthesis."""
        path = Path(tempfile.mkdtemp()) / "legacy.db"
        legacy = sqlite3.connect(str(path))
        legacy.executescript("""
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT NOT NULL, title_hash TEXT NOT NULL,
                url TEXT NOT NULL, title TEXT, summary TEXT,
                source_domain TEXT, published_at TEXT, origin TEXT,
                corroboration INTEGER DEFAULT 1,
                relevance_score REAL, reputation_score REAL,
                corroboration_score REAL, final_score REAL,
                seen_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL, source_domain TEXT,
                clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        legacy.commit()
        legacy.close()

        conn = db.get_conn(path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)")}
        self.assertIn("image_url", cols)
        click_cols = {r[1] for r in conn.execute("PRAGMA table_info(clicks)")}
        self.assertIn("url_hash", click_cols)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("synthesis", tables)
        # Re-opening must be a no-op, not an error.
        conn.close()
        db.get_conn(path).close()


class SynthesizeTests(unittest.TestCase):
    """
    Exercises request shaping and every degradation path at the HTTP layer,
    so none of these cost an API call.
    """

    ARTICLES = [{"title": "T", "summary": "S", "source_domain": "bbc.com"}]

    def _run(self, handler):
        import os
        import anthropic
        import httpx
        from digest import synthesize as syn

        captured = {}

        def transport(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["beta"] = request.headers.get("anthropic-beta")
            captured["path"] = request.url.path
            return handler(request, captured)

        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        real_init = anthropic.Anthropic.__init__

        def patched(self, *a, **kw):
            kw["http_client"] = httpx.Client(transport=httpx.MockTransport(transport))
            real_init(self, *a, **kw)

        anthropic.Anthropic.__init__ = patched
        try:
            result = syn.synthesize(self.ARTICLES)
        finally:
            anthropic.Anthropic.__init__ = real_init
        return result, captured

    @staticmethod
    def _ok_body(stop_reason="end_turn", text=None):
        payload = {
            "intro_en": "a", "intro_pt": "b",
            "articles": [{
                "index": 0, "headline_en": "h", "headline_pt": "p",
                "one_liner_en": "o", "one_liner_pt": "r", "category": "AI",
                "region": "world", "rationale": "x", "low_signal": False,
            }],
        }
        return {
            "id": "msg_1", "type": "message", "role": "assistant",
            "model": "claude-opus-5",
            "content": [{"type": "text", "text": text if text is not None else json.dumps(payload)}],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }

    def test_sends_structured_output_schema_and_fallbacks(self):
        import httpx
        result, cap = self._run(lambda r, c: httpx.Response(200, json=self._ok_body()))
        self.assertEqual(cap["body"]["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(cap["body"]["fallbacks"], "default")
        self.assertEqual(cap["beta"], "server-side-fallback-2026-07-01")
        self.assertEqual(result["articles"][0]["headline_pt"], "p")

    def test_refusal_falls_back_instead_of_indexing_empty_content(self):
        """A refusal is HTTP 200 with content that doesn't match the schema."""
        import httpx

        def handler(r, c):
            body = self._ok_body(stop_reason="refusal")
            body["content"] = []
            return httpx.Response(200, json=body)

        result, _ = self._run(handler)
        self.assertIn("unavailable", result["intro_en"])
        self.assertEqual(result["articles"][0]["headline_en"], "T")

    def test_truncated_response_falls_back(self):
        import httpx
        result, _ = self._run(
            lambda r, c: httpx.Response(200, json=self._ok_body(stop_reason="max_tokens"))
        )
        self.assertIn("unavailable", result["intro_en"])

    def test_retries_without_beta_when_fallbacks_unsupported(self):
        """An account without the beta must still get its digest."""
        import httpx
        calls = []

        def handler(r, c):
            calls.append(c["body"].get("fallbacks"))
            if len(calls) == 1:
                return httpx.Response(
                    400, json={"type": "error", "error": {
                        "type": "invalid_request_error", "message": "unknown beta"}})
            return httpx.Response(200, json=self._ok_body())

        result, _ = self._run(handler)
        self.assertEqual(calls, ["default", None])  # retried without fallbacks
        self.assertEqual(result["articles"][0]["category"], "AI")

    def test_server_error_falls_back_rather_than_raising(self):
        import httpx
        result, _ = self._run(
            lambda r, c: httpx.Response(500, json={"type": "error", "error": {
                "type": "api_error", "message": "boom"}})
        )
        self.assertIn("unavailable", result["intro_en"])

    def test_missing_api_key_uses_fallback_without_network(self):
        import os
        from digest import synthesize as syn
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result = syn.synthesize(self.ARTICLES)
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["articles"][0]["region"], "world")


if __name__ == "__main__":
    unittest.main()
