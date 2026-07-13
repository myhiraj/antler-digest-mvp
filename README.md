# Antler Digest MVP

An AI-powered daily newsletter digest for Antler MENAP. Ingests startup and VC content from RSS feeds and email newsletters, runs a RAG pipeline to summarise them, and stores a daily briefing in MongoDB.

## What it does

1. **Polls RSS feeds** every day at 12:05 PM PKT (5 sources: Wamda, MENAbytes, MENA Startup Digest, Not Boring, Crunchbase)
2. **Receives email newsletters** via Postmark inbound webhook (Digital Digest, Strictly VC, Term Sheet, Crunchbase Daily)
3. **Processes each article**: clean HTML → chunk (400 words, 80-word overlap) → embed with Voyage AI → store in MongoDB
4. **Generates a daily digest** at 1:10 PM PKT using Atlas Vector Search + Claude — one digest per topic namespace, enriched with company data (headcount, funding, traction) from Harmonic for startups mentioned in that day's sources

## Tech stack

- **Python** — FastAPI, Motor (async MongoDB), APScheduler
- **MongoDB Atlas** — document store + vector search
- **Voyage AI** — embeddings (`voyage-3`, 1024 dimensions)
- **Anthropic Claude** — digest summarisation + company extraction (`claude-sonnet-4-6`)
- **Harmonic** — company enrichment (headcount, funding, traction) for startups mentioned in digests
- **Postmark** — inbound email webhook
- **Railway** — deployment (web + scheduler in one process)

## Project structure

```
app/
├── main.py              # FastAPI init, APScheduler startup
├── config.py            # pydantic-settings, reads .env
├── routes/
│   └── inbound.py       # POST /inbound — Postmark webhook
├── services/
│   ├── cleaner.py       # strips HTML, footers, tracking pixels
│   ├── chunker.py       # 400-word chunks, 80-word overlap
│   ├── embedder.py      # Voyage AI embeddings
│   ├── retriever.py     # Atlas Vector Search
│   ├── summarizer.py    # Claude summarisation + company extraction
│   ├── harmonic.py      # Harmonic company lookups
│   └── document_store.py# Motor read/write
├── jobs/
│   ├── rss_poller.py    # APScheduler job, polls RSS feeds daily
│   └── digest_job.py    # APScheduler job, generates daily digest
└── models/
    ├── document.py            # source, topic_id, raw_text, clean_text, content_hash
    ├── chunk.py               # document_id, topic_id, text, embedding, chunk_index
    ├── topic_output.py        # topic_id, date, summary_text, sources_used, companies_enriched
    └── company_enrichment.py  # domain, payload (full Harmonic response), fetched_at
```

## Topic namespaces

| Source | Method | topic_id |
|---|---|---|
| Wamda | RSS | `menap_general` |
| MENAbytes | RSS | `menap_general` |
| MENA Startup Digest | RSS | `menap_general` |
| Digital Digest | Email | `menap_general` |
| Not Boring | RSS | `global_vc` |
| Crunchbase Daily | RSS | `global_vc` |
| Strictly VC | Email | `global_vc` |
| Term Sheet (Fortune) | Email | `global_vc` |

## Local setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# create .env with the variables listed below
uvicorn app.main:app --reload
```

## Environment variables

| Variable | Description |
|---|---|
| `MONGODB_URI` | MongoDB Atlas connection string |
| `VOYAGE_API_KEY` | Voyage AI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `POSTMARK_WEBHOOK_TOKEN` | Postmark inbound webhook token (optional — auth disabled if unset) |
| `HARMONIC_API_KEY` | Harmonic API key for company enrichment (optional — enrichment is skipped if unset) |

## MongoDB Atlas setup

The app requires a **Vector Search index** on the `chunks` collection named `chunks_embedding_vector_index`:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1024,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "topic_id"
    },
    {
      "type": "filter",
      "path": "ingested_at"
    },
    {
      "type": "filter",
      "path": "used_in_digest"
    }
  ]
}
```

Create this in Atlas → your cluster → **Atlas Search** → **Create Search Index** → **Vector Search** tab.

## Running jobs manually

```bash
# Trigger RSS poll
python3 -c "import asyncio; from app.jobs.rss_poller import poll_rss_feeds; asyncio.run(poll_rss_feeds())"

# Trigger digest generation
python3 -c "import asyncio; from app.jobs.digest_job import generate_daily_digest; asyncio.run(generate_daily_digest())"
```

## Running tests

```bash
pytest
```

## Schedule (PKT)

| Job | Time |
|---|---|
| RSS poll | 12:05 PM |
| Digest generation | 1:10 PM |
