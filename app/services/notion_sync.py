import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic
from notion_client import AsyncClient

from app.config import settings
from app.models.chunk import Chunk

logger = logging.getLogger(__name__)

_anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
_notion_client = AsyncClient(auth=settings.notion_api_key) if settings.notion_api_key else None

MODEL = "claude-sonnet-4-6"

UNCATEGORIZED_TITLE = "Uncategorized"

CATEGORIES = [
    "Policy & Regulation",
    "Market & Sector Trend",
    "Ecosystem Move",
    "Founder Insight",
    "New Fund Launched",
]

INDUSTRIES = [
    "Fintech",
    "Proptech",
    "Healthtech",
    "Edtech",
    "AI & Enterprise Software",
    "E-commerce & Retail",
    "Logistics & Mobility",
    "Climate & Energy",
    "Consumer & Media",
    "Cybersecurity",
    "Other",
]

# Canonical geography names — the model is free-texting this field, so
# near-duplicate variants (e.g. "UAE" vs "United Arab Emirates") drift in
# over time unless normalized before writing to Notion.
GEOGRAPHY_ALIASES = {
    "uae": "UAE",
    "united arab emirates": "UAE",
    "ksa": "Saudi Arabia",
    "saudi": "Saudi Arabia",
    "kingdom of saudi arabia": "Saudi Arabia",
    "egypt": "Egypt",
    "arab republic of egypt": "Egypt",
}


def normalize_geography(geography: str) -> str:
    """Map free-text geography strings to a single canonical name so the
    Theme database's Geography select doesn't accumulate near-duplicates
    (e.g. "UAE" and "United Arab Emirates" as separate values)."""
    if not geography:
        return "Global"
    return GEOGRAPHY_ALIASES.get(geography.strip().lower(), geography.strip())


EXTRACT_SIGNALS_TOOL = {
    "name": "extract_signals",
    "description": (
        "Record notable signals found in the source excerpts: policy/regulatory "
        "announcements, market or sector trends, ecosystem moves (accelerator "
        "launches, key people moves, M&A), founder insights, and new VC/PE fund "
        "launches (a fund manager closing or announcing a new fund to invest FROM — "
        "not a startup raising a round). Do not record plain startup funding-round "
        "announcements with no broader signal attached — those are tracked elsewhere."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": CATEGORIES},
                        "industry": {
                            "type": "string",
                            "enum": INDUSTRIES,
                            "description": "The specific startup/market industry this signal is about.",
                        },
                        "geography": {
                            "type": "string",
                            "description": "Country, or 'Global' if not region-specific.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Short label for this specific observation.",
                        },
                        "excerpt": {
                            "type": "string",
                            "description": "A concise paraphrase of the observation, 1-2 sentences.",
                        },
                    },
                    "required": ["category", "industry", "geography", "title", "excerpt"],
                },
            }
        },
        "required": ["signals"],
    },
}

CLASSIFY_EVIDENCE_TOOL = {
    "name": "classify_evidence",
    "description": (
        "For each candidate signal, decide whether it matches an existing open theme, "
        "belongs in the Uncategorized bucket because it doesn't yet clearly fit any theme "
        "and doesn't warrant a brand-new one on its own, or is significant/distinctive "
        "enough to become a new theme."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "signal_index": {
                            "type": "integer",
                            "description": "Index of the candidate signal in the input list.",
                        },
                        "decision": {
                            "type": "string",
                            "enum": ["existing_theme", "uncategorized", "new_theme"],
                        },
                        "theme_id": {
                            "type": "string",
                            "description": "Notion page ID of the matched theme. Required when decision is 'existing_theme'.",
                        },
                        "new_theme_title": {
                            "type": "string",
                            "description": "Title for the new theme. Required when decision is 'new_theme'.",
                        },
                    },
                    "required": ["signal_index", "decision"],
                },
            }
        },
        "required": ["classifications"],
    },
}

REVIEW_UNCATEGORIZED_TOOL = {
    "name": "review_clusters",
    "description": (
        "Identify clusters among the Uncategorized evidence items that now form a coherent "
        "theme (e.g. three or more items pointing at the same underlying pattern). Only "
        "propose a cluster when the pattern is genuinely clear — most items should remain "
        "unclustered."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "clusters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "theme_title": {"type": "string"},
                        "category": {"type": "string", "enum": CATEGORIES},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Notion page IDs of the Evidence rows that belong to this new theme.",
                        },
                    },
                    "required": ["theme_title", "category", "evidence_ids"],
                },
            }
        },
        "required": ["clusters"],
    },
}


SUMMARIZE_SOURCE_TOOL = {
    "name": "summarize_source",
    "description": (
        "Write a Smart Brevity-style summary of a source excerpt: a short bold "
        "lede sentence stating the news, then a 'Why it matters' line, then 2-4 "
        "terse bullet points with the key facts. No filler, no throat-clearing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "lede": {
                "type": "string",
                "description": "One short, punchy sentence stating what happened. No more than ~20 words.",
            },
            "why_it_matters": {
                "type": "string",
                "description": "One sentence: why this is relevant to an early-stage MENA investor.",
            },
            "bullets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 short bullet points with the key supporting facts/numbers.",
            },
        },
        "required": ["lede", "why_it_matters", "bullets"],
    },
}


def _rich_text(value: str) -> List[Dict[str, Any]]:
    return [{"type": "text", "text": {"content": value[:2000]}}]


def _format_smart_brevity(summary: Dict[str, Any]) -> str:
    lede = summary.get("lede", "").strip()
    why = summary.get("why_it_matters", "").strip()
    bullets = summary.get("bullets") or []

    lines = [lede]
    if why:
        lines.append(f"Why it matters: {why}")
    for bullet in bullets:
        lines.append(f"• {bullet}")
    return "\n".join(line for line in lines if line)


async def summarize_source(excerpt_text: str) -> str:
    """Summarize a source excerpt in Axios Smart Brevity style (bold lede,
    'Why it matters', terse bullets) for the Evidence row's Source Summary
    field. Returns "" on failure or empty input; never raises."""
    if not excerpt_text:
        return ""

    try:
        message = await _anthropic_client.messages.create(
            model=MODEL,
            max_tokens=512,
            tools=[SUMMARIZE_SOURCE_TOOL],
            tool_choice={"type": "tool", "name": "summarize_source"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize this source excerpt per the tool's description "
                        "(Axios Smart Brevity style):\n\n---\n" + excerpt_text
                    ),
                }
            ],
        )
    except Exception:
        logger.exception("summarize_source: Claude call failed")
        return ""

    for block in message.content:
        if block.type == "tool_use" and block.name == "summarize_source":
            return _format_smart_brevity(block.input)
    return ""


async def extract_signals(chunks: List[Chunk]) -> List[Dict[str, Any]]:
    """Ask Claude to identify non-funding-round signals (policy, trend, ecosystem,
    founder insight) in the chunks. Returns a list of candidate signal dicts;
    never raises — extraction failures should not block the digest."""
    if not chunks:
        return []

    context_blocks = "\n\n".join(
        f"[{i + 1}] (source: {c.source_name or 'unknown'} | url: {c.source_url or 'unavailable'})\n{c.text}"
        for i, c in enumerate(chunks)
    )

    try:
        message = await _anthropic_client.messages.create(
            model=MODEL,
            max_tokens=2048,
            tools=[EXTRACT_SIGNALS_TOOL],
            tool_choice={"type": "tool", "name": "extract_signals"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Identify notable signals in these excerpts, per the tool's "
                        "description. Attach the source url/name of the excerpt each "
                        "signal came from.\n\n---\n" + context_blocks
                    ),
                }
            ],
        )
    except Exception:
        logger.exception("extract_signals: Claude call failed")
        return []

    for block in message.content:
        if block.type == "tool_use" and block.name == "extract_signals":
            signals = block.input.get("signals", [])
            for i, signal in enumerate(signals):
                chunk = chunks[min(i, len(chunks) - 1)]
                signal.setdefault("source_url", chunk.source_url)
                signal.setdefault("source_name", chunk.source_name)
                signal.setdefault("topic_id", chunk.topic_id)
                signal.setdefault("source_excerpt_text", chunk.text)
            return signals
    return []


async def get_open_themes(topic_id: str) -> List[Dict[str, str]]:
    """Query the Notion Themes database for Status = Active rows for this topic,
    including the standing Uncategorized theme. Returns [] if Notion isn't
    configured or the query fails."""
    if not _notion_client or not settings.notion_themes_database_id:
        return []

    try:
        response = await _notion_client.databases.query(
            database_id=settings.notion_themes_database_id,
            filter={
                "and": [
                    {"property": "Status", "select": {"equals": "Active"}},
                    {"property": "Topic", "select": {"equals": topic_id}},
                ]
            },
        )
    except Exception:
        logger.exception("get_open_themes: Notion query failed for topic_id=%r", topic_id)
        return []

    themes = []
    for page in response.get("results", []):
        title_prop = page["properties"].get("Title", {}).get("title", [])
        title = title_prop[0]["plain_text"] if title_prop else ""
        category_prop = page["properties"].get("Category", {}).get("select") or {}
        themes.append({"id": page["id"], "title": title, "category": category_prop.get("name", "")})
    return themes


async def _ensure_uncategorized_theme(topic_id: str) -> Optional[str]:
    """Return the page ID of the standing Uncategorized theme for this topic,
    creating it if it doesn't exist yet."""
    if not _notion_client or not settings.notion_themes_database_id:
        return None

    themes = await get_open_themes(topic_id)
    for theme in themes:
        if theme["title"] == UNCATEGORIZED_TITLE:
            return theme["id"]

    return await _create_theme(
        title=UNCATEGORIZED_TITLE,
        category=UNCATEGORIZED_TITLE,
        geography="Global",
        topic_id=topic_id,
    )


async def _create_theme(title: str, category: str, geography: str, topic_id: str) -> Optional[str]:
    if not _notion_client or not settings.notion_themes_database_id:
        return None

    now = datetime.now(timezone.utc).date().isoformat()
    try:
        page = await _notion_client.pages.create(
            parent={"database_id": settings.notion_themes_database_id},
            properties={
                "Title": {"title": _rich_text(title)},
                "Category": {"select": {"name": category}},
                "Geography": {"select": {"name": normalize_geography(geography)}},
                "Topic": {"select": {"name": topic_id}},
                "Status": {"select": {"name": "Active"}},
                "First Seen": {"date": {"start": now}},
                "Last Updated": {"date": {"start": now}},
            },
        )
        return page["id"]
    except Exception:
        logger.exception("_create_theme: failed to create theme title=%r", title)
        return None


async def _touch_theme(theme_id: str) -> None:
    if not _notion_client:
        return
    now = datetime.now(timezone.utc).date().isoformat()
    try:
        await _notion_client.pages.update(
            page_id=theme_id,
            properties={"Last Updated": {"date": {"start": now}}},
        )
    except Exception:
        logger.exception("_touch_theme: failed to update theme_id=%r", theme_id)


async def _create_evidence(signal: Dict[str, Any], theme_id: str) -> Optional[str]:
    if not _notion_client or not settings.notion_evidence_database_id:
        return None

    source_summary = await summarize_source(signal.get("source_excerpt_text") or signal.get("excerpt") or "")

    try:
        page = await _notion_client.pages.create(
            parent={"database_id": settings.notion_evidence_database_id},
            properties={
                "Title": {"title": _rich_text(signal.get("title", ""))},
                "Theme": {"relation": [{"id": theme_id}]},
                "Industry": {"select": {"name": signal.get("industry") or "Other"}},
                "Source Name": {"rich_text": _rich_text(signal.get("source_name") or "")},
                "Source URL": {"url": signal.get("source_url") or None},
                "Source Summary": {"rich_text": _rich_text(source_summary)},
                "Date": {"date": {"start": datetime.now(timezone.utc).date().isoformat()}},
                "Topic": {"select": {"name": signal.get("topic_id", "")}},
            },
        )
        return page["id"]
    except Exception:
        logger.exception("_create_evidence: failed to create evidence for signal=%r", signal.get("title"))
        return None


async def classify_evidence(
    candidates: List[Dict[str, Any]], open_themes: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Ask Claude to classify each candidate signal against currently-open themes.
    Never raises; returns [] on failure so the caller can skip syncing this batch."""
    if not candidates:
        return []

    themes_block = "\n".join(f"- id={t['id']} | {t['title']} ({t['category']})" for t in open_themes) or "(none yet)"
    signals_block = "\n".join(
        f"[{i}] {s['category']} | {s['geography']} | {s['title']}: {s['excerpt']}"
        for i, s in enumerate(candidates)
    )

    try:
        message = await _anthropic_client.messages.create(
            model=MODEL,
            max_tokens=2048,
            tools=[CLASSIFY_EVIDENCE_TOOL],
            tool_choice={"type": "tool", "name": "classify_evidence"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Currently open themes:\n{themes_block}\n\n"
                        f"Candidate signals:\n{signals_block}\n\n"
                        "Classify each candidate signal per the tool's description. Prefer "
                        "'uncategorized' over forcing a weak match into an existing theme or "
                        "spawning a new theme for a one-off observation."
                    ),
                }
            ],
        )
    except Exception:
        logger.exception("classify_evidence: Claude call failed")
        return []

    for block in message.content:
        if block.type == "tool_use" and block.name == "classify_evidence":
            return block.input.get("classifications", [])
    return []


async def review_uncategorized(topic_id: str) -> None:
    """Look for clusters among evidence currently sitting under the Uncategorized
    theme for this topic; promote clusters into new themes. Never raises."""
    if not _notion_client or not settings.notion_evidence_database_id:
        return

    uncategorized_id = await _ensure_uncategorized_theme(topic_id)
    if not uncategorized_id:
        return

    try:
        response = await _notion_client.databases.query(
            database_id=settings.notion_evidence_database_id,
            filter={
                "and": [
                    {"property": "Theme", "relation": {"contains": uncategorized_id}},
                    {"property": "Topic", "select": {"equals": topic_id}},
                ]
            },
        )
    except Exception:
        logger.exception("review_uncategorized: Notion query failed for topic_id=%r", topic_id)
        return

    items = []
    for page in response.get("results", []):
        title_prop = page["properties"].get("Title", {}).get("title", [])
        title = title_prop[0]["plain_text"] if title_prop else ""
        items.append({"id": page["id"], "title": title})

    if len(items) < 3:
        return

    items_block = "\n".join(f"- id={it['id']} | {it['title']}" for it in items)
    try:
        message = await _anthropic_client.messages.create(
            model=MODEL,
            max_tokens=2048,
            tools=[REVIEW_UNCATEGORIZED_TOOL],
            tool_choice={"type": "tool", "name": "review_clusters"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Uncategorized evidence items:\n{items_block}\n\n"
                        "Identify any clusters per the tool's description."
                    ),
                }
            ],
        )
    except Exception:
        logger.exception("review_uncategorized: Claude call failed")
        return

    clusters = []
    for block in message.content:
        if block.type == "tool_use" and block.name == "review_clusters":
            clusters = block.input.get("clusters", [])
            break

    for cluster in clusters:
        evidence_ids = cluster.get("evidence_ids", [])
        if not evidence_ids:
            continue
        new_theme_id = await _create_theme(
            title=cluster["theme_title"],
            category=cluster.get("category", "Market & Sector Trend"),
            geography="Global",
            topic_id=topic_id,
        )
        if not new_theme_id:
            continue
        for evidence_id in evidence_ids:
            try:
                await _notion_client.pages.update(
                    page_id=evidence_id,
                    properties={"Theme": {"relation": [{"id": new_theme_id}]}},
                )
            except Exception:
                logger.exception(
                    "review_uncategorized: failed to relink evidence_id=%r to theme_id=%r",
                    evidence_id,
                    new_theme_id,
                )


async def sync_to_notion(topic_id: str, chunks: List[Chunk]) -> None:
    """Extract signals from chunks, classify each against open Notion themes
    (falling back to Uncategorized rather than forcing a match), and write
    Theme/Evidence rows. Never raises — a Notion failure must not block
    Slack/email digest delivery."""
    if not _notion_client or not settings.notion_themes_database_id or not settings.notion_evidence_database_id:
        logger.info("sync_to_notion: Notion not configured, skipping topic_id=%r", topic_id)
        return

    try:
        await review_uncategorized(topic_id)

        candidates = await extract_signals(chunks)
        if not candidates:
            return

        open_themes = await get_open_themes(topic_id)
        uncategorized_id = await _ensure_uncategorized_theme(topic_id)
        classifications = await classify_evidence(candidates, open_themes)
        theme_by_id = {t["id"]: t for t in open_themes}

        for classification in classifications:
            idx = classification.get("signal_index")
            if idx is None or idx >= len(candidates):
                continue
            signal = candidates[idx]
            decision = classification.get("decision")

            if decision == "existing_theme":
                theme_id = classification.get("theme_id")
                if not theme_id or theme_id not in theme_by_id:
                    theme_id = uncategorized_id
                else:
                    await _touch_theme(theme_id)
            elif decision == "new_theme":
                theme_id = await _create_theme(
                    title=classification.get("new_theme_title", signal["title"]),
                    category=signal["category"],
                    geography=signal["geography"],
                    topic_id=topic_id,
                )
                if not theme_id:
                    theme_id = uncategorized_id
            else:
                theme_id = uncategorized_id

            if theme_id:
                await _create_evidence(signal, theme_id)

        logger.info(
            "sync_to_notion: processed %d candidate signals for topic_id=%r",
            len(candidates),
            topic_id,
        )
    except Exception:
        logger.exception("sync_to_notion: failed for topic_id=%r", topic_id)
