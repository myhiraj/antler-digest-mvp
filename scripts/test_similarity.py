"""
Manual integration test: embeds a few newsletter sentences, stores them in MongoDB,
runs an Atlas vector search query, and prints ranked results so you can eyeball relevance.

Run after create_vector_index.py and once the index is ACTIVE in Atlas:
    python scripts/test_similarity.py

Requires real MONGODB_URI and VOYAGE_API_KEY in .env.
"""
import os
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import voyageai
import motor.motor_asyncio

MONGODB_URI = os.environ["MONGODB_URI"]
VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]
INDEX_NAME = "chunks_embedding_vector_index"

SAMPLE_DOCS = [
    {"text": "Antler MENAP closed its second fund at $50 million targeting pre-seed startups in the Gulf.", "topic_id": "menap_general"},
    {"text": "Tabby raised a $200M Series D to expand its BNPL platform across Saudi Arabia and the UAE.", "topic_id": "menap_general"},
    {"text": "Andreessen Horowitz led a $500M fund focused on AI infrastructure and foundation models.", "topic_id": "global_vc"},
    {"text": "NutriPlan, a Cairo-based AI nutrition app, has onboarded over 50,000 users in six months.", "topic_id": "menap_general"},
    {"text": "Sequoia Capital announced a new early-stage fund targeting Southeast Asia and India.", "topic_id": "global_vc"},
]

QUERY = "Which MENA startups raised funding recently?"


async def main():
    voyage = voyageai.Client(api_key=VOYAGE_API_KEY)
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    col = client["vc_digest"]["similarity_test"]

    await col.delete_many({})  # clean up from previous runs

    print("Embedding sample documents...")
    texts = [d["text"] for d in SAMPLE_DOCS]
    result = voyage.embed(texts, model="voyage-3", input_type="document")
    docs_to_insert = [
        {"text": d["text"], "topic_id": d["topic_id"], "embedding": emb}
        for d, emb in zip(SAMPLE_DOCS, result.embeddings)
    ]
    await col.insert_many(docs_to_insert)
    print(f"Inserted {len(docs_to_insert)} documents.\n")

    print(f"Query: '{QUERY}'")
    q_result = voyage.embed([QUERY], model="voyage-3", input_type="query")
    query_vector = q_result.embeddings[0]

    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 10,
                "limit": 5,
            }
        },
        {"$project": {"_id": 0, "text": 1, "topic_id": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    print("\nTop results by cosine similarity:")
    print("-" * 60)
    async for doc in col.aggregate(pipeline):
        print(f"[{doc['score']:.4f}] ({doc['topic_id']}) {doc['text']}")

    await col.drop()
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
