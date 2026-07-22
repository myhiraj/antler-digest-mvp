import logging
from datetime import datetime, date, timezone
from typing import Any, Dict, List

from anthropic import AsyncAnthropic

from app.config import settings
from app.models.chunk import Chunk
from app.models.topic_output import TopicOutput
from app.services import document_store

logger = logging.getLogger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

EXTRACT_COMPANIES_TOOL = {
    "name": "extract_companies",
    "description": "Record the startups/companies mentioned in the source excerpts, with their website domain if known.",
    "input_schema": {
        "type": "object",
        "properties": {
            "companies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "domain": {
                            "type": "string",
                            "description": "Website domain, e.g. 'leantech.me'. Omit if not stated or not confidently known.",
                        },
                    },
                    "required": ["name"],
                },
            }
        },
        "required": ["companies"],
    },
}


async def extract_companies(chunks: List[Chunk]) -> List[Dict[str, str]]:
    """Ask Claude to identify companies mentioned in the chunks and their
    website domains, so they can be looked up in Harmonic. Returns a list
    of {"name": ..., "domain": ...} dicts; domain is omitted when unknown."""
    if not chunks:
        return []

    context_blocks = "\n\n".join(f"[{i + 1}] {c.text}" for i, c in enumerate(chunks))
    message = await _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[EXTRACT_COMPANIES_TOOL],
        tool_choice={"type": "tool", "name": "extract_companies"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Identify every distinct startup/company mentioned in these excerpts, "
                    "with its website domain if stated or confidently known. Do not guess "
                    "domains.\n\n---\n" + context_blocks
                ),
            }
        ],
    )

    for block in message.content:
        if block.type == "tool_use" and block.name == "extract_companies":
            return block.input.get("companies", [])
    return []

SYSTEM_PROMPT = """\
You are a senior analyst at Antler MENAP, the leading early-stage VC fund in the \
Middle East, North Africa, and Pakistan. Your job is to produce a concise daily \
intelligence digest for the investment team.

You write with precision and authority. You highlight signal over noise. You flag \
emerging patterns, notable deals, and founder insights that matter to early-stage \
investors operating in the MENA startup ecosystem.

When given a set of numbered source excerpts, you synthesise them into a structured \
digest formatted in Slack's mrkdwn syntax (not standard markdown). You do not quote \
sources verbatim — you paraphrase and surface insight. If a section has no relevant \
information in the provided context, write "Nothing notable today." for that section \
rather than hallucinating content."""

TOPIC_LABELS = {
    "menap_general": "MENA & Pakistan Startup Ecosystem",
    "global_vc": "Global VC & Venture Markets",
}


def _build_enrichment_block(enrichment: Dict[str, Dict[str, Any]]) -> str:
    if not enrichment:
        return ""

    lines = []
    for domain, payload in enrichment.items():
        name = payload.get("name", domain)
        headcount = payload.get("headcount")
        funding = payload.get("funding", {}) or {}
        funding_total = funding.get("funding_total")
        funding_stage = funding.get("funding_stage")
        location = (payload.get("location") or {}).get("address_formatted")

        facts = [f"name={name}"]
        if headcount is not None:
            facts.append(f"headcount={headcount}")
        if funding_total is not None:
            facts.append(f"total_funding_usd={funding_total}")
        if funding_stage:
            facts.append(f"funding_stage={funding_stage}")
        if location:
            facts.append(f"location={location}")
        lines.append(f"- {domain}: " + ", ".join(facts))

    return (
        "\n\nCompany data (from Harmonic, for the companies mentioned above). "
        "Weave the relevant facts into your prose naturally where they add "
        "context — do not list this data separately or refer to it as a "
        "'dataset' or 'Harmonic'. Only use a fact if it's relevant to the point "
        "being made:\n" + "\n".join(lines)
    )


def _build_user_prompt(
    topic_id: str,
    chunks: List[Chunk],
    digest_date: date,
    enrichment: Dict[str, Dict[str, Any]] = None,
) -> str:
    label = TOPIC_LABELS.get(topic_id, topic_id)
    context_blocks = "\n\n".join(
        f"[{i + 1}] {chunk.text}" for i, chunk in enumerate(chunks)
    )
    enrichment_block = _build_enrichment_block(enrichment or {})

    menap_section = ""
    if topic_id == "menap_general":
        menap_section = """
*MENA-Specific Highlights*
Regulatory changes, government initiatives, cross-border activity, and anything unique to the MENA operating environment.

*So What?* (one sentence: why does this matter to an early-stage MENA investor?)
"""

    return f"""Today's date: {digest_date.isoformat()}
Topic: {label}

Below are {len(chunks)} excerpts from newsletters and news sources ingested today. Each excerpt is numbered.

---
{context_blocks}
---
{enrichment_block}

Using only the information in the excerpts above (plus the company data, if provided), write the daily digest with the following sections, formatted for Slack (mrkdwn), NOT standard markdown:
- Use *text* for bold (single asterisks), never **text**.
- Use _text_ for italics.
- Do not use markdown headers (#, ##, ###). Use a bold line as the section title instead, e.g. *Key Deals & Funding*.
- Use "- " for bullet points, not other bullet characters.
- For links, use Slack's format <https://example.com|label>, never [label](https://example.com).

Sections:

*Key Deals & Funding*
Rounds closed, tranches announced, notable investors involved.

*So What?* (one sentence takeaway)

*Emerging Trends*
Patterns across multiple excerpts — sectors heating up, new geographies, shifting investor thesis.

*So What?* (one sentence takeaway)

*Founder Insights*
Quotes, strategies, or lessons attributed to founders in the excerpts.

*So What?* (one sentence takeaway)

*Notable Exits & IPOs*
Acquisitions, secondary sales, public listings — only if present in the context. Otherwise write "Nothing notable today."

*So What?* (one sentence takeaway, or omit if nothing notable)
{menap_section}
---
Keep each section tight. Use bullet points. No filler. No hallucination."""


async def summarize_topic(
    topic_id: str,
    chunks: List[Chunk],
    enrichment: Dict[str, Dict[str, Any]] = None,
) -> TopicOutput:
    digest_date = date.today()

    if not chunks:
        output = TopicOutput(
            topic_id=topic_id,
            date=digest_date,
            summary_text="_No new content was ingested for this topic today._",
            sources_used=[],
            generated_at=datetime.now(timezone.utc),
            chunk_count=0,
        )
        await document_store.save_topic_output(output)
        return output

    user_prompt = _build_user_prompt(topic_id, chunks, digest_date, enrichment)

    message = await _client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    summary_text = message.content[0].text

    sources_used = list({c.document_id for c in chunks})

    output = TopicOutput(
        topic_id=topic_id,
        date=digest_date,
        summary_text=summary_text,
        sources_used=sources_used,
        generated_at=datetime.now(timezone.utc),
        model_used=MODEL,
        chunk_count=len(chunks),
        companies_enriched=list((enrichment or {}).keys()),
    )
    await document_store.save_topic_output(output)
    return output
