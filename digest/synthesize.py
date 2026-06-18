"""Stage 5: Send top-N articles to Claude for synthesis."""
from __future__ import annotations

import json
import logging
import os
import re

import anthropic

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a personal news editor for a reader based in Curitiba, Brazil who reads "
    "both Portuguese and English. The user will send you a JSON list of articles — each "
    "has only a title and a short description (no full article body is available). "
    "Return ONLY a valid JSON object with this exact structure:\n\n"
    "{\n"
    '  "intro_en": "<2-3 sentence English overview of today\'s most important themes>",\n'
    '  "intro_pt": "<2-3 sentence Portuguese overview of today\'s most important themes>",\n'
    '  "articles": [\n'
    "    {\n"
    '      "index": <integer matching the input index>,\n'
    '      "headline_en": "<English headline: translate if the original is not in English, under 15 words>",\n'
    '      "headline_pt": "<Portuguese headline: translate if the original is not in Portuguese, under 15 words>",\n'
    '      "one_liner_en": "<one crisp English sentence summary, under 25 words>",\n'
    '      "one_liner_pt": "<one crisp Portuguese sentence summary, under 25 words>",\n'
    '      "category": "<exactly one of: AI, Tech, Science, Geopolitics, Economy, Brazil, Climate, Culture, Other>",\n'
    '      "region": "<exactly one of: world, brazil, curitiba>",\n'
    '      "rationale": "<one English sentence: why is this newsworthy today>",\n'
    '      "low_signal": <true if clickbait / press release / near-duplicate / opinion without news hook, else false>\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Base all summaries ONLY on the provided title and description. Do not hallucinate content.\n"
    "- headline_en / headline_pt: translate the source title into the target language when needed. Keep under 15 words.\n"
    "- Keep one_liner_en and one_liner_pt each under 25 words and prefer active voice.\n"
    "- region rules (apply in order, stop at first match):\n"
    "    1. 'curitiba' if the article is specifically about Curitiba city, its metropolitan area, "
    "or Paraná state events/politics/culture/infrastructure/sports — OR if the source domain is "
    "one of: gazetadopovo.com.br, bemparana.com.br, bandab.com.br, tribunapr.com.br, curitibacult.com.br "
    "(these are Curitiba/Paraná-local outlets; default to 'curitiba' unless the article clearly "
    "covers a national or international topic with no local angle).\n"
    "    2. 'brazil' if it is a Brazil-national story not specific to Curitiba/Paraná.\n"
    "    3. 'world' for everything else.\n"
    "- low_signal=true for: press releases, opinion pieces without a factual hook, "
    "obvious clickbait, or near-identical stories already summarized.\n"
    "- Return the raw JSON object only — no markdown fences, no extra commentary."
)


def synthesize(
    articles: list[dict],
    model: str = "claude-sonnet-4-6",
) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — using fallback synthesis")
        return _fallback(articles)

    client = anthropic.Anthropic(api_key=api_key)

    payload = [
        {
            "index": i,
            "title": art["title"],
            "description": (art["summary"] or "")[:400],
            "source": art["source_domain"],
        }
        for i, art in enumerate(articles)
    ]

    user_msg = (
        f"Here are today's top {len(payload)} articles. "
        f"Synthesize them per the instructions.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    logger.info("Calling Claude (%s) with %d articles…", model, len(articles))
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=8192,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = msg.content[0].text.strip()
        usage = msg.usage if hasattr(msg, "usage") else None
        logger.info(
            "Claude response: %d chars | in=%s out=%s tokens | stop=%s",
            len(raw),
            usage.input_tokens if usage else "?",
            usage.output_tokens if usage else "?",
            msg.stop_reason if hasattr(msg, "stop_reason") else "?",
        )
        if getattr(msg, "stop_reason", None) == "max_tokens":
            logger.error(
                "Response was TRUNCATED (hit max_tokens) — JSON will be invalid. "
                "Consider reducing top_n in config.yaml or the synthesis will fall back."
            )
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return _fallback(articles)

    # Strip code fences defensively
    raw = re.sub(r"^```[a-z]*\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(
            "JSON parse failed (%s) — using fallback.\n"
            "  Snippet (first 400): %r\n"
            "  Snippet (last  200): %r",
            exc, raw[:400], raw[-200:],
        )
        return _fallback(articles)

    # Validate minimal shape
    if "articles" not in result:
        logger.error("Claude response missing 'articles' key — using fallback")
        return _fallback(articles)

    return result


def _fallback(articles: list[dict]) -> dict:
    return {
        "intro_en": "Today's digest (LLM synthesis unavailable — check ANTHROPIC_API_KEY).",
        "intro_pt": "Resumo do dia (síntese LLM indisponível — verifique ANTHROPIC_API_KEY).",
        "articles": [
            {
                "index": i,
                "headline_en": art["title"],
                "headline_pt": art["title"],
                "one_liner_en": art["title"],
                "one_liner_pt": art["title"],
                "category": "Other",
                "region": "world",
                "rationale": "Included based on relevance score.",
                "low_signal": False,
            }
            for i, art in enumerate(articles)
        ],
    }
