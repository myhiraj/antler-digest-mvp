import voyageai
from app.models.chunk import Chunk
from app.config import settings
from typing import List

_client = voyageai.Client(api_key=settings.voyage_api_key)


def embed_chunks(chunks: List[Chunk]) -> List[Chunk]:
    if not chunks:
        return chunks

    texts = [c.text for c in chunks]
    result = _client.embed(texts, model="voyage-3")

    for chunk, embedding in zip(chunks, result.embeddings):
        chunk.embedding = embedding

    return chunks
