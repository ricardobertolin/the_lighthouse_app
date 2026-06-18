"""
The Lighthouse — daily personal news digest.

Usage:
  python -m digest                  Full pipeline, opens browser.
  python -m digest --no-browser     Full pipeline, no browser.
  python -m digest --fetch-only     Stage 1: fetch + print (no scoring/LLM).
  python -m digest --config PATH    Use an alternate config.yaml.
"""
from __future__ import annotations

import argparse
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
        help="Skip fetch/score/LLM; re-render today's DB articles + fresh weather.",
    )
    parser.add_argument(
        "--weather",
        choices=["sunny", "cloudy", "rainy", "foggy", "snow", "thunderstorm"],
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
        help="Generate digest.html but do not open it in the browser.",
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
    from .db import get_conn, upsert_article, get_today_articles
    from .fetch import fetch_all, print_stage1_report, enrich_missing_images
    from .score import score_articles, print_stage2_report
    from .synthesize import synthesize
    from .weather import fetch_weather
    from .render import render, open_browser, OUTPUT_PATH

    cfg_path = Path(args.config) if args.config else CONFIG_PATH
    if not cfg_path.exists():
        log.error("Config file not found: %s", cfg_path)
        sys.exit(1)

    cfg = load_config(cfg_path)
    gnews_key = os.environ.get("GNEWS_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if not gnews_key:
        log.warning("GNEWS_API_KEY not set — discovery queries will be skipped.")
    if not anthropic_key and not args.fetch_only:
        log.warning("ANTHROPIC_API_KEY not set — synthesis will use fallback text.")

    conn = get_conn()
    log.info("Database ready.")

    # ── Weather override ──────────────────────────────────────────
    _FAKE_WEATHER = {
        "sunny":       {"wmo_code": 0,  "temp_max": 26, "temp_min": 16, "wind_max_kmh": 10, "precipitation_mm": 0,   "description": "Clear sky"},
        "cloudy":      {"wmo_code": 3,  "temp_max": 20, "temp_min": 14, "wind_max_kmh": 18, "precipitation_mm": 0,   "description": "Overcast"},
        "rainy":       {"wmo_code": 61, "temp_max": 17, "temp_min": 13, "wind_max_kmh": 28, "precipitation_mm": 8.0, "description": "Rain"},
        "foggy":       {"wmo_code": 45, "temp_max": 15, "temp_min": 11, "wind_max_kmh": 6,  "precipitation_mm": 0,   "description": "Fog"},
        "snow":        {"wmo_code": 71, "temp_max": 3,  "temp_min": -1, "wind_max_kmh": 20, "precipitation_mm": 4.0, "description": "Snow"},
        "thunderstorm":{"wmo_code": 95, "temp_max": 19, "temp_min": 15, "wind_max_kmh": 55, "precipitation_mm": 15., "description": "Thunderstorm"},
    }
    if args.weather or args.all_weathers:
        args.render_only = True

    # ── Render-only shortcut ──────────────────────────────────────
    if args.render_only:
        top = get_today_articles(conn)
        if not top:
            log.warning("No articles for today in the DB — run without --render-only first.")
            conn.close()
            return
        top = top[: cfg.top_n]
        log.info("Render-only: %d articles from DB.", len(top))
        from .synthesize import _fallback
        synthesis = _fallback(top)
        if args.all_weathers:
            for condition, fake_wx in _FAKE_WEATHER.items():
                out_path = OUTPUT_PATH.parent / f"digest_{condition}.html"
                render(top, synthesis, fake_wx, output_path=out_path)
                log.info("Rendered %-12s → %s", condition, out_path.name)
                if not args.no_browser:
                    open_browser(out_path, cfg.browser)
            conn.close()
            log.info("Done — %d weather previews opened.", len(_FAKE_WEATHER))
            return

        if args.weather:
            weather = _FAKE_WEATHER[args.weather]
            log.info("Weather override: %s", args.weather)
        else:
            log.info("Fetching weather…")
            weather = fetch_weather()
        log.info("Rendering…")
        output = render(top, synthesis, weather)
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
    scored = score_articles(articles, cfg)  # returns ALL scored, sorted by final_score
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

    # ── Stage 5: Synthesize ───────────────────────────────────────
    log.info("Stage 5 — synthesizing with Claude…")
    synthesis = synthesize(top)

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
    log.info("Stage 7 — rendering digest.html…")
    output = render(top, synthesis, weather)
    log.info("Digest written → %s", output)

    # ── Stage 8: Open browser ─────────────────────────────────────
    if not args.no_browser:
        log.info("Opening digest in browser (%s)…", cfg.browser)
        open_browser(output, cfg.browser)

    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
