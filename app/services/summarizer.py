import logging
from datetime import datetime, date, timezone
from typing import List

from anthropic import AsyncAnthropic

from app.config import settings
from app.models.chunk import Chunk
from app.models.topic_output import TopicOutput
from app.services import document_store

logger = logging.getLogger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

SYSTEM_PROMPT = """\
You are a senior analyst at Antler MENAP, the leading early-stage VC fund in the \
Middle East, North Africa, and Pakistan. Your job is to produce a concise daily \
intelligence digest for the investment team.

You write with precision and authority. You highlight signal over noise. You flag \
emerging patterns, notable deals, and founder insights that matter to early-stage \
investors operating in the MENA startup ecosystem.

When given a set of numbered source excerpts, you synthesise them into a structured \
markdown digest. You do not quote sources verbatim — you paraphrase and surface insight. \
If a section has no relevant information in the provided context, write \
"Nothing notable today." for that section rather than hallucinating content."""

TOPIC_LABELS = {
    "menap_general": "MENA & Pakistan Startup Ecosystem",
    "global_vc": "Global VC & Venture Markets",
}


def _build_user_prompt(topic_id: str, chunks: List[Chunk], digest_date: date) -> str:
    label = TOPIC_LABELS.get(topic_id, topic_id)
    context_blocks = "\n\n".join(
        f"[{i + 1}] {chunk.text}" for i, chunk in enumerate(chunks)
    )

    menap_section = ""
    if topic_id == "menap_general":
        menap_section = """
### MENA-Specific Highlights
Regulatory changes, government initiatives, cross-border activity, and anything unique to the MENA operating environment.

**So What?** (one sentence: why does this matter to an early-stage MENA investor?)
"""

    return f"""Today's date: {digest_date.isoformat()}
Topic: {label}

Below are {len(chunks)} excerpts from newsletters and news sources ingested today. Each excerpt is numbered.

---
{context_blocks}
---

Using only the information in the excerpts above, write the daily digest with the following sections in markdown:

### Key Deals & Funding
Rounds closed, tranches announced, notable investors involved.

**So What?** (one sentence takeaway)

### Emerging Trends
Patterns across multiple excerpts — sectors heating up, new geographies, shifting investor thesis.

**So What?** (one sentence takeaway)

### Founder Insights
Quotes, strategies, or lessons attributed to founders in the excerpts.

**So What?** (one sentence takeaway)

### Notable Exits & IPOs
Acquisitions, secondary sales, public listings — only if present in the context. Otherwise write "Nothing notable today."

**So What?** (one sentence takeaway, or omit if nothing notable)
{menap_section}
---
Keep each section tight. Use bullet points. No filler. No hallucination."""


async def summarize_topic(topic_id: str, chunks: List[Chunk]) -> TopicOutput:
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

    user_prompt = _build_user_prompt(topic_id, chunks, digest_date)

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
    )
    await document_store.save_topic_output(output)
    return output
