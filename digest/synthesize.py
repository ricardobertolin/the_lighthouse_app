"""Stage 5: Send top-N articles to Claude for synthesis."""
from __future__ import annotations

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"

CATEGORIES = ["AI", "Tech", "Science", "Geopolitics", "Economy", "Brazil", "Climate", "Culture", "Other"]
REGIONS = ["world", "brazil", "curitiba"]

# Structured outputs guarantee this shape, which is why there is no
# fence-stripping or JSON-repair code below any more. Note that JSON Schema
# length constraints are not supported — word limits stay in the prompt.
_SCHEMA = {
    "type": "object",
    "properties": {
        "intro_en": {"type": "string"},
        "intro_pt": {"type": "string"},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "headline_en": {"type": "string"},
                    "headline_pt": {"type": "string"},
                    "one_liner_en": {"type": "string"},
                    "one_liner_pt": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "region": {"type": "string", "enum": REGIONS},
                    "rationale": {"type": "string"},
                    "low_signal": {"type": "boolean"},
                },
                "required": [
                    "index", "headline_en", "headline_pt", "one_liner_en",
                    "one_liner_pt", "category", "region", "rationale", "low_signal",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intro_en", "intro_pt", "articles"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a personal news editor for a reader based in Curitiba, Brazil who reads "
    "both Portuguese and English. The user will send you a JSON list of articles — each "
    "has only a title and a short description (no full article body is available).\n\n"
    "Rules:\n"
    "- Base all summaries ONLY on the provided title and description. Do not hallucinate content.\n"
    "- Return one entry per input article, with `index` matching the input index.\n"
    "- headline_en / headline_pt: translate the source title into the target language when needed. Keep under 15 words.\n"
    "- Keep one_liner_en and one_liner_pt each under 25 words and prefer active voice.\n"
    "- rationale: one English sentence on why this is newsworthy today.\n"
    "- region rules — classify by CONTENT first, use source domain only as a weak tiebreaker:\n"
    "    Step 1 — read the title and description carefully. Ask: what place or scope is this story ABOUT?\n"
    "    Step 2 — assign the region:\n"
    "      'curitiba'  → the story is specifically about Curitiba city, its metropolitan area, or "
    "Paraná state (local politics, infrastructure, culture, crime, sports, economy). "
    "A Curitiba outlet publishing a story about federal government, national GDP, or international "
    "affairs is NOT 'curitiba' — classify by topic.\n"
    "      'brazil'    → the story is about Brazil as a nation (federal policy, nationwide economy, "
    "national politics, major Brazilian cities outside Paraná) but not specific to Curitiba/Paraná.\n"
    "      'world'     → everything else (foreign countries, international organizations, global trends).\n"
    "    Step 3 — if the content is genuinely ambiguous (could fit two regions), use the source domain "
    "as a tiebreaker: gazetadopovo.com.br, bemparana.com.br, bandab.com.br, tribunapr.com.br, "
    "curitibacult.com.br lean 'curitiba'; g1.globo.com, bbc.com/portuguese lean 'brazil'.\n"
    "- low_signal=true for: press releases, opinion pieces without a factual hook, "
    "obvious clickbait, or near-identical stories already summarized.\n"
    "- intro_en / intro_pt: 2-3 sentences each, overviewing today's most important themes."
)


def synthesize(articles: list[dict], model: str = DEFAULT_MODEL) -> dict:
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

    kwargs = dict(
        model=model,
        # Opus 5 thinks by default and max_tokens caps thinking + output
        # together, so this is well above the ~4.5k of JSON we actually want.
        max_tokens=16000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": _SCHEMA},
        },
    )

    logger.info("Calling Claude (%s) with %d articles…", model, len(articles))
    try:
        msg = _create_with_fallback(client, kwargs)
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return _fallback(articles)

    usage = getattr(msg, "usage", None)
    logger.info(
        "Claude response: in=%s out=%s tokens | stop=%s | served by %s",
        usage.input_tokens if usage else "?",
        usage.output_tokens if usage else "?",
        msg.stop_reason,
        getattr(msg, "model", model),
    )

    # Check stop_reason before touching content: a refusal returns HTTP 200
    # with empty or partial content that does not match the schema.
    if msg.stop_reason == "refusal":
        details = getattr(msg, "stop_details", None)
        logger.error(
            "Claude declined the request (category=%s) — using fallback.",
            getattr(details, "category", None),
        )
        return _fallback(articles)
    if msg.stop_reason == "max_tokens":
        logger.error("Response hit max_tokens — JSON is truncated, using fallback.")
        return _fallback(articles)

    text = next((b.text for b in msg.content if b.type == "text"), "")
    if not text:
        logger.error("No text block in response — using fallback.")
        return _fallback(articles)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Should be unreachable with structured outputs; kept so a schema
        # regression degrades instead of crashing the daily run.
        logger.error("JSON parse failed despite structured outputs (%s) — using fallback.", exc)
        return _fallback(articles)


def _create_with_fallback(client: anthropic.Anthropic, kwargs: dict):
    """
    Request server-side refusal fallbacks, degrading to a plain call.

    Opus 5 ships elevated cybersecurity safeguards and news copy occasionally
    trips them; `fallbacks="default"` re-runs a declined request on Anthropic's
    recommended substitute inside the same call.

    `fallbacks` is passed via extra_body because the SDK has no typed parameter
    for it yet (0.96 raises TypeError on the keyword); extra_body goes straight
    into the request JSON. If the beta isn't enabled for this account, we fall
    back to a plain call rather than losing the day's digest.
    """
    try:
        return client.beta.messages.create(
            **kwargs,
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
    except (anthropic.BadRequestError, anthropic.NotFoundError, TypeError) as exc:
        logger.warning(
            "Server-side refusal fallbacks unavailable (%s: %s) — retrying without.",
            type(exc).__name__, str(exc)[:200],
        )
        return client.messages.create(**kwargs)


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
