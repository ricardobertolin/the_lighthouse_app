"""
The Lighthouse — daily personal news digest.

Usage:
  python -m digest                    Full pipeline, opens browser.
  python -m digest --no-browser       Full pipeline, no browser.
  python -m digest --fetch-only       Stage 1: fetch + print (no scoring/LLM).
  python -m digest --render-only      Re-render today's digest from the DB.
  python -m digest --ingest-clicks F  Import clicks exported from the page.
  python -m digest --config PATH      Use an alternate config.yaml.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Suppress HuggingFace symlinks warning on Windows (Developer Mode not required)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    # Force UTF-8 on Windows where the default console encoding (cp1252) rejects
    # characters like em-dash used in feed titles and log messages.
    if hasattr(handler.stream, "reconfigure"):
        try:
            handler.stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)


_FAKE_WEATHER = {
    "sunny":       {"location": "Curitiba, PR", "wmo_code": 0,  "temp_max": 26, "temp_min": 16, "wind_max_kmh": 10, "precipitation_mm": 0,   "description": "Clear sky"},
    "cloudy":      {"location": "Curitiba, PR", "wmo_code": 3,  "temp_max": 20, "temp_min": 14, "wind_max_kmh": 18, "precipitation_mm": 0,   "description": "Overcast"},
    "rainy":       {"location": "Curitiba, PR", "wmo_code": 61, "temp_max": 17, "temp_min": 13, "wind_max_kmh": 28, "precipitation_mm": 8.0, "description": "Rain"},
    "foggy":       {"location": "Curitiba, PR", "wmo_code": 45, "temp_max": 15, "temp_min": 11, "wind_max_kmh": 6,  "precipitation_mm": 0,   "description": "Fog"},
    "snow":        {"location": "Curitiba, PR", "wmo_code": 71, "temp_max": 3,  "temp_min": -1, "wind_max_kmh": 20, "precipitation_mm": 4.0, "description": "Snow"},
    "thunderstorm":{"location": "Curitiba, PR", "wmo_code": 95, "temp_max": 19, "temp_min": 15, "wind_max_kmh": 55, "precipitation_mm": 15., "description": "Thunderstorm"},
}


def _ingest_clicks(conn, path: Path, log) -> int:
    """
    Import the click log exported from the digest page.

    Accepts the raw localStorage array (list of {url, domain, at}) or an object
    wrapping it under "clicks".
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Could not read clicks file %s: %s", path, exc)
        return 0

    entries = raw.get("clicks", []) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        log.error("Unexpected clicks format in %s — expected a list.", path)
        return 0

    from .db import log_click, get_click_domain_counts

    new = 0
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("url"):
            continue
        if log_click(
            conn,
            url=entry["url"],
            source_domain=entry.get("domain", ""),
            # "ts" is the key older builds of the page wrote.
            clicked_at=entry.get("at") or entry.get("ts"),
        ):
            new += 1

    total = conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0]
    log.info("Imported %d new clicks (%d total in DB).", new, total)
    top = list(get_click_domain_counts(conn).items())[:5]
    if top:
        log.info("Most-clicked domains: %s", ", ".join(f"{d} ({n})" for d, n in top))
    return new


def main() -> None:
    _setup_logging()
    log = logging.getLogger("digest")

    parser = argparse.ArgumentParser(
        prog="python -m digest",
        description="The Lighthouse — personal daily news digest",
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Run only stage 1 (fetch + dedup) and print results.",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Skip fetch/score/LLM; re-render today's digest from the stored synthesis.",
    )
    parser.add_argument(
        "--weather",
        choices=sorted(_FAKE_WEATHER),
        default=None,
        metavar="CONDITION",
        help="Override weather for testing: sunny|cloudy|rainy|foggy|snow|thunderstorm. Implies --render-only.",
    )
    parser.add_argument(
        "--all-weathers",
        action="store_true",
        help="Render all weather conditions to separate files and open each in the browser.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Generate index.html but do not open it in the browser.",
    )
    parser.add_argument(
        "--ingest-clicks",
        metavar="PATH",
        default=None,
        help="Import a clicks JSON exported from the digest page, then exit.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Apply the retention policy (with VACUUM) and exit.",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to an alternate config.yaml (default: config.yaml in project root).",
    )
    args = parser.parse_args()

    # Lazy imports — keep startup fast for --help
    from .config import load_config, CONFIG_PATH
    from .db import (
        get_conn, upsert_article, get_today_articles, get_articles_by_hash,
        update_images, save_synthesis, get_synthesis, get_clicked_texts,
        get_recurring_title_hashes, prune,
    )
    from .fetch import fetch_all, print_stage1_report, enrich_missing_images
    from .score import score_articles, print_stage2_report
    from .synthesize import synthesize, DEFAULT_MODEL
    from .weather import fetch_weather
    from .render import render, open_browser, OUTPUT_PATH

    cfg_path = Path(args.config) if args.config else CONFIG_PATH
    if not cfg_path.exists():
        log.error("Config file not found: %s", cfg_path)
        sys.exit(1)

    cfg = load_config(cfg_path)
    conn = get_conn()
    log.info("Database ready.")

    # ── Standalone maintenance modes ──────────────────────────────
    if args.ingest_clicks:
        _ingest_clicks(conn, Path(args.ingest_clicks), log)
        conn.close()
        return

    if args.prune:
        prune(
            conn,
            keep_full_days=cfg.retention.keep_full_days,
            delete_after_days=cfg.retention.delete_after_days,
            vacuum=True,
        )
        conn.close()
        return

    gnews_key = os.environ.get("GNEWS_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if not gnews_key:
        log.warning("GNEWS_API_KEY not set — discovery queries will be skipped.")
    if not anthropic_key and not args.fetch_only:
        log.warning("ANTHROPIC_API_KEY not set — synthesis will use fallback text.")

    if args.weather or args.all_weathers:
        args.render_only = True

    # ── Render-only shortcut ──────────────────────────────────────
    if args.render_only:
        stored = get_synthesis(conn)
        previewing = bool(args.weather or args.all_weathers)

        if stored:
            synthesis, hashes = stored
            top = get_articles_by_hash(conn, hashes)
            log.info("Render-only: %d articles from today's stored synthesis.", len(top))
        else:
            # Without the stored synthesis we can only produce untranslated
            # titles, no categories and no regions. That is fine for a weather
            # preview (separate file) but would silently replace the live page
            # with a degraded one.
            if not previewing:
                log.error(
                    "No stored synthesis for today — re-rendering would overwrite %s "
                    "with untranslated titles and no categories. Run the full "
                    "pipeline instead, or use --weather to preview to a separate file.",
                    OUTPUT_PATH.name,
                )
                conn.close()
                sys.exit(1)
            from .synthesize import _fallback
            top = get_today_articles(conn)[: cfg.top_n]
            if not top:
                log.warning("No articles for today in the DB — run without --render-only first.")
                conn.close()
                return
            synthesis = _fallback(top)
            log.warning("No stored synthesis — preview will show untranslated titles.")

        if args.all_weathers:
            for condition, fake_wx in _FAKE_WEATHER.items():
                out_path = OUTPUT_PATH.parent / f"digest_{condition}.html"
                render(top, synthesis, fake_wx, output_path=out_path, live_weather=False)
                log.info("Rendered %-12s → %s", condition, out_path.name)
                if not args.no_browser:
                    open_browser(out_path, cfg.browser)
            conn.close()
            log.info("Done — %d weather previews opened.", len(_FAKE_WEATHER))
            return

        if args.weather:
            weather = _FAKE_WEATHER[args.weather]
            out_path = OUTPUT_PATH.parent / f"digest_{args.weather}.html"
            log.info("Weather override: %s → %s", args.weather, out_path.name)
        else:
            log.info("Fetching weather…")
            weather = fetch_weather()
            out_path = OUTPUT_PATH

        log.info("Rendering…")
        output = render(
            top, synthesis, weather,
            output_path=out_path,
            live_weather=not args.weather,
        )
        log.info("Digest written → %s", output)
        if not args.no_browser:
            open_browser(output, cfg.browser)
        conn.close()
        log.info("Done.")
        return

    # ── Stage 1: Fetch ────────────────────────────────────────────
    log.info("Stage 1 — fetching RSS feeds and GNews…")
    articles = fetch_all(cfg, gnews_key, conn)

    if args.fetch_only:
        print_stage1_report(articles)
        conn.close()
        return

    if not articles:
        log.warning("No new articles found — digest may be empty.")

    # ── Stage 2-3: Score ──────────────────────────────────────────
    log.info("Stage 2-3 — scoring articles…")
    clicked_texts = get_clicked_texts(conn)
    if clicked_texts:
        log.info("Personalizing with %d clicked articles.", len(clicked_texts))
    else:
        log.info(
            "No clicks recorded yet — using configured topics only. "
            "Export clicks from the page and run --ingest-clicks to personalize."
        )
    recurring = (
        get_recurring_title_hashes(conn, cfg.recurring_title_days)
        if cfg.recurring_title_days
        else set()
    )
    scored = score_articles(articles, cfg, clicked_texts, recurring)  # ALL scored, sorted
    print_stage2_report(scored, show=cfg.top_n)

    # Persist ALL scored articles to DB so none reappear in future runs,
    # regardless of whether they made the top_n cut.
    for art in scored:
        upsert_article(conn, art)

    # Stage 4: merge today's new articles with whatever was already in the
    # DB from earlier runs today, then re-rank and take top_n.
    # This ensures a same-day re-run never shrinks the digest.
    existing_today = get_today_articles(conn)
    by_hash = {a["url_hash"]: a for a in existing_today}
    for a in scored:
        by_hash[a["url_hash"]] = a  # freshly scored takes precedence
    all_today = sorted(by_hash.values(), key=lambda a: a.get("final_score") or 0, reverse=True)
    top = all_today[: cfg.top_n]
    log.info(
        "Today's pool: %d articles (%d new + %d from earlier today) → top %d selected.",
        len(all_today), len(scored), max(0, len(existing_today) - len(scored)), len(top),
    )

    # Stage 4b: enrich missing images for the top articles
    log.info("Stage 4b — fetching OG images for articles missing thumbnails…")
    top = enrich_missing_images(top)
    written = update_images(conn, top)
    log.info("Persisted %d enriched thumbnails.", written)

    # ── Stage 5: Synthesize ───────────────────────────────────────
    log.info("Stage 5 — synthesizing with Claude…")
    synthesis = synthesize(top)
    save_synthesis(conn, synthesis, top, model=DEFAULT_MODEL)

    # ── Stage 6: Weather ──────────────────────────────────────────
    log.info("Stage 6 — fetching weather…")
    weather = fetch_weather()
    log.info(
        "Weather: %s, %s°C / %s°C",
        weather.get("description"),
        weather.get("temp_max"),
        weather.get("temp_min"),
    )

    # ── Stage 7: Render ───────────────────────────────────────────
    log.info("Stage 7 — rendering index.html…")
    output = render(top, synthesis, weather)
    log.info("Digest written → %s", output)

    # ── Stage 8: Retention ────────────────────────────────────────
    prune(
        conn,
        keep_full_days=cfg.retention.keep_full_days,
        delete_after_days=cfg.retention.delete_after_days,
    )

    # ── Stage 9: Open browser ─────────────────────────────────────
    if not args.no_browser:
        log.info("Opening digest in browser (%s)…", cfg.browser)
        open_browser(output, cfg.browser)

    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
