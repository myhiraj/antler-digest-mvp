"""
Creates the MongoDB Atlas Vector Search index on the chunks collection.

Run once after the collection exists:
    python scripts/create_vector_index.py

Requires MONGODB_URI in .env pointing at an Atlas cluster (not localhost).
Atlas Vector Search is not available on local/Community MongoDB.
"""
import os
import sys
from pathlib import Path

# allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import pymongo

MONGODB_URI = os.environ["MONGODB_URI"]
DB = "vc_digest"
COLLECTION = "chunks"
INDEX_NAME = "chunks_embedding_vector_index"

client = pymongo.MongoClient(MONGODB_URI)
db = client[DB]

index_definition = {
    "name": INDEX_NAME,
    "type": "vectorSearch",
    "definition": {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": 1024,  # voyage-3 output dimension
                "similarity": "cosine",
            },
            {
                "type": "filter",
                "path": "topic_id",
            },
        ]
    },
}

try:
    result = db[COLLECTION].create_search_index(index_definition)
    print(f"Index creation initiated: {result}")
    print("Atlas builds the index asynchronously — check the Atlas UI for status.")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
