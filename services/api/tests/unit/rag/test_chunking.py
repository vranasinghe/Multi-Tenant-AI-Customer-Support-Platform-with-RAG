from __future__ import annotations

import itertools

import pytest

from app.rag.chunking import CHARS_PER_TOKEN, ChunkingConfig, chunk_blocks, estimate_tokens
from app.rag.extract import Block

CONFIG = ChunkingConfig(size_tokens=50, overlap_tokens=10)  # 200 chars, 40 chars overlap


def para(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_config_validates_overlap_against_size() -> None:
    with pytest.raises(ValueError, match="overlap"):
        ChunkingConfig(size_tokens=100, overlap_tokens=100)
    with pytest.raises(ValueError, match="size_tokens"):
        ChunkingConfig(size_tokens=4, overlap_tokens=0)


def test_small_document_is_one_chunk_and_keeps_page_metadata() -> None:
    chunks = chunk_blocks(
        [Block("Hello there.", page=3), Block("Second paragraph.", page=4)], CONFIG
    )

    assert len(chunks) == 1
    assert chunks[0].content == "Hello there.\n\nSecond paragraph."
    assert (chunks[0].page_start, chunks[0].page_end) == (3, 4)
    assert chunks[0].ordinal == 0


def test_chunks_respect_the_size_budget() -> None:
    text = " ".join(f"Sentence number {i} is here." for i in range(60))

    chunks = chunk_blocks([Block(text)], CONFIG)

    assert len(chunks) > 3
    max_chars = CONFIG.size_tokens * CHARS_PER_TOKEN
    # a chunk may exceed the budget only by the carried-over overlap
    assert all(
        len(c.content) <= max_chars + CONFIG.overlap_tokens * CHARS_PER_TOKEN + 2 for c in chunks
    )
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_consecutive_chunks_overlap() -> None:
    text = " ".join(f"Sentence number {i} is here." for i in range(60))

    chunks = chunk_blocks([Block(text)], CONFIG)

    for previous, current in itertools.pairwise(chunks):
        tail = previous.content[-30:]
        assert tail.split()[-1] in current.content[: 4 * CONFIG.overlap_tokens + 10]


def test_zero_overlap_means_no_repeated_text() -> None:
    config = ChunkingConfig(size_tokens=50, overlap_tokens=0)
    text = " ".join(f"unique{i}" for i in range(200))

    chunks = chunk_blocks([Block(text)], config)

    words = [w for c in chunks for w in c.content.split()]
    assert words == text.split()


def test_chunks_never_cross_a_heading_boundary() -> None:
    blocks = [
        Block("Intro", heading_path=("A",), is_heading=True),
        Block(para(10, "a"), heading_path=("A",)),
        Block("Next", heading_path=("A", "B"), is_heading=True),
        Block(para(10, "b"), heading_path=("A", "B")),
    ]

    chunks = chunk_blocks(blocks, CONFIG)

    assert [c.heading_path for c in chunks] == [("A",), ("A", "B")]
    assert "b0" not in chunks[0].content and "a0" not in chunks[1].content


def test_embedded_text_carries_title_and_heading_path() -> None:
    blocks = [Block("Body text.", heading_path=("Returns", "International"))]

    [chunk] = chunk_blocks(blocks, CONFIG, title="Policy")

    assert chunk.embedded_text == "Policy\nReturns > International\nBody text."
    assert chunk.content == "Body text."


def test_no_context_header_means_no_embedded_text() -> None:
    [chunk] = chunk_blocks([Block("Body text.")], CONFIG)
    assert chunk.embedded_text is None


def test_a_single_unbreakable_token_is_hard_split() -> None:
    chunks = chunk_blocks([Block("x" * 1000)], CONFIG)

    assert len(chunks) > 1
    assert "".join(c.content for c in chunks).count("x") >= 1000


def test_long_sentenceless_paragraph_is_split_on_words() -> None:
    chunks = chunk_blocks([Block(para(300))], ChunkingConfig(50, 0))

    assert all(len(c.content) <= 200 for c in chunks)


def test_only_headings_yield_no_chunks() -> None:
    assert chunk_blocks([Block("Title", is_heading=True)], CONFIG) == []


def test_chunking_is_deterministic() -> None:
    blocks = [Block(para(120), page=1), Block(para(80, "z"), page=2)]
    assert chunk_blocks(blocks, CONFIG) == chunk_blocks(blocks, CONFIG)


def test_token_estimate() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
