from app.models.document import Document
from app.models.chunk import Chunk
from typing import List

CHUNK_SIZE = 400   # words
OVERLAP = 80       # words


def chunk_text(doc: Document) -> List[Chunk]:
    words = doc.clean_text.split()
    chunks = []
    index = 0
    start = 0

    while start < len(words):
        end = start + CHUNK_SIZE
        chunk_words = words[start:end]
        chunks.append(Chunk(
            document_id=doc.content_hash,
            topic_id=doc.topic_id,
            text=" ".join(chunk_words),
            chunk_index=index,
        ))
        index += 1
        if end >= len(words):
            break
        start += CHUNK_SIZE - OVERLAP

    return chunks
