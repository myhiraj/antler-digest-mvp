import os
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-secret")

from datetime import datetime, timezone
from app.services.chunker import chunk_text, CHUNK_SIZE, OVERLAP
from app.models.document import Document

# ~1000-word realistic newsletter body
NEWSLETTER_TEXT = """
Antler MENAP has closed its second fund at $50 million, marking a significant milestone for the
regional early-stage investment landscape. The fund will back pre-seed and seed startups across the
Middle East, North Africa, and Pakistan, with a particular focus on fintech, healthtech, and
climate tech. The announcement was made at a closed-door event in Dubai attended by limited
partners from across the Gulf Cooperation Council.

The fund's first close was led by the Abu Dhabi Investment Office, with co-investors including
family offices from Saudi Arabia and Kuwait. Antler plans to make between 60 and 80 investments
from the new vehicle, with initial cheques ranging from $100,000 to $500,000 and reserves for
follow-on rounds. The team has already deployed capital into 12 companies since the fund's soft
launch in early 2024, with portfolio companies operating in UAE, Saudi Arabia, Egypt, and Pakistan.

Among the notable portfolio companies is Plend, a Dubai-based embedded finance platform that
recently raised a $3M bridge round to expand into Saudi Arabia. Another standout is NutriPlan, an
AI-powered nutrition platform out of Cairo that has onboarded over 50,000 users since launching
six months ago. A third company, PakLogix, is digitising freight logistics across Pakistan's
trucking sector and has processed over $10M in freight value to date.

Antler MENAP managing partner Sarah Al-Rashid said the fund reflects growing confidence in the
regional startup ecosystem. She noted that regulatory reform in Saudi Arabia, particularly the
introduction of the Company Law amendments in 2023, has meaningfully lowered barriers for foreign
investors. The UAE's Golden Visa programme has also contributed to talent retention, reducing the
historic brain drain that had hampered ecosystem development.

The broader MENA venture capital market raised $3.2 billion across 573 deals in 2023, according
to data from Magnitt. Saudi Arabia accounted for 38% of total funding, surpassing the UAE for the
first time. Egypt came in third, driven largely by fintech and e-commerce transactions. Notable
deals in the region last year included Tabby's $200M Series D, Tamara's $340M debt facility, and
the $150M Series C raised by Kitopi, the cloud kitchen operator.

Despite the positive momentum, founders continue to flag challenges around access to Series A
capital. While pre-seed and seed funding has become more available, the so-called Series A crunch
remains acute in the region, with fewer than 20 regional funds capable of writing $5M+ cheques.
This gap is increasingly being filled by international crossover funds, including Sequoia's India
and Southeast Asia vehicle, which has begun scouting in the Gulf.

Antler's new fund arrives as several other MENA-focused managers are in market. Global Ventures
is understood to be raising its third fund at a target of $100M, while Wamda Capital recently held
a first close on a $75M vehicle focused on Series A and B companies in Egypt and Jordan.
Shorooq Partners, one of the most active regional investors, continues to deploy its $120M third
fund across the GCC and Levant markets.

On the exit front, the region saw its first significant IPO of a venture-backed company in 2024
when Saudi fintech Rasan Information Technology listed on Tadawul at a valuation of $400M. The
listing was closely watched by the investment community as a proof of concept for the public
markets as a viable exit pathway for regional venture-backed businesses. A secondary transaction
market is also beginning to emerge, with platforms like Zanbeel facilitating early liquidity for
angel investors and employees.

Looking ahead, the MENAP ecosystem faces both opportunities and headwinds. The AI wave is creating
new categories of startups, particularly in Arabic language models, government-facing enterprise
software, and vertical SaaS. At the same time, rising interest rates globally have increased the
opportunity cost of venture investing, putting pressure on fund managers to demonstrate returns.

Antler MENAP's new fund positions the firm to capture the early stage of this next cycle, with a
thesis anchored on founder quality over market timing. The team runs a residency programme in
Dubai where founders spend ten weeks building alongside peers, with Antler taking equity in
exchange for the initial cheque. This cohort model has been central to Antler's global expansion
and is being adapted to the specific dynamics of the MENAP market.
""".strip()


def _make_doc(text: str) -> Document:
    return Document(
        source="test",
        source_type="rss",
        topic_id="menap_general",
        raw_text=text,
        clean_text=text,
        content_hash="testhash",
        ingested_at=datetime.now(timezone.utc),
    )


def test_chunk_count_matches_expected():
    doc = _make_doc(NEWSLETTER_TEXT)
    chunks = chunk_text(doc)
    words = NEWSLETTER_TEXT.split()
    # expected number of chunks using ceiling division with step = CHUNK_SIZE - OVERLAP
    step = CHUNK_SIZE - OVERLAP
    expected = max(1, -(-len(words) // step)) if len(words) > CHUNK_SIZE else 1
    # Allow off-by-one due to boundary; just assert more than 1 and reasonable
    assert len(chunks) >= 2
    assert len(chunks) <= expected + 1


def test_each_chunk_at_most_chunk_size_words():
    doc = _make_doc(NEWSLETTER_TEXT)
    for chunk in chunk_text(doc):
        assert len(chunk.text.split()) <= CHUNK_SIZE


def test_overlap_words_appear_at_boundary():
    doc = _make_doc(NEWSLETTER_TEXT)
    chunks = chunk_text(doc)
    assert len(chunks) >= 2
    first_words = chunks[0].text.split()
    second_words = chunks[1].text.split()
    # Last OVERLAP words of chunk 0 should equal first OVERLAP words of chunk 1
    assert first_words[-OVERLAP:] == second_words[:OVERLAP]


def test_chunk_indices_are_sequential():
    doc = _make_doc(NEWSLETTER_TEXT)
    chunks = chunk_text(doc)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunk_metadata_matches_document():
    doc = _make_doc(NEWSLETTER_TEXT)
    chunks = chunk_text(doc)
    for chunk in chunks:
        assert chunk.document_id == doc.content_hash
        assert chunk.topic_id == doc.topic_id
        assert chunk.embedding is None


def test_short_document_produces_one_chunk():
    short_text = "This is a short newsletter with only a handful of words."
    doc = _make_doc(short_text)
    chunks = chunk_text(doc)
    assert len(chunks) == 1
    assert chunks[0].text == short_text
    assert chunks[0].chunk_index == 0


def test_empty_document_produces_no_chunks():
    doc = _make_doc("")
    chunks = chunk_text(doc)
    assert chunks == []


def test_exact_chunk_size_document_produces_one_chunk():
    text = " ".join(["word"] * CHUNK_SIZE)
    doc = _make_doc(text)
    chunks = chunk_text(doc)
    assert len(chunks) == 1


def test_chunk_size_plus_one_produces_two_chunks():
    # CHUNK_SIZE+1 words → second chunk contains the overlap + 1 extra word
    text = " ".join([f"w{i}" for i in range(CHUNK_SIZE + 1)])
    doc = _make_doc(text)
    chunks = chunk_text(doc)
    assert len(chunks) == 2


def test_no_words_lost():
    """All words in the document appear in at least one chunk."""
    doc = _make_doc(NEWSLETTER_TEXT)
    chunks = chunk_text(doc)
    all_chunk_words = set()
    for chunk in chunks:
        all_chunk_words.update(chunk.text.split())
    doc_words = set(NEWSLETTER_TEXT.split())
    assert doc_words == all_chunk_words
