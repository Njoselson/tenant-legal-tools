"""
Tests for text chunking utilities.
"""

import pytest

from tenant_legal_guidance.utils.chunking import (
    build_chunk_docs,
    make_super_chunks,
    naive_token_estimate,
    recursive_char_chunks,
    split_headings,
)


class TestNaiveTokenEstimate:
    def test_empty_text(self):
        assert naive_token_estimate("") == 0
        assert naive_token_estimate(None) == 0

    def test_short_text(self):
        text = "Hello world"  # 11 chars
        assert naive_token_estimate(text) == 2  # 11 / 4 = 2.75 → 2

    def test_long_text(self):
        text = "a" * 1000
        assert naive_token_estimate(text) == 250  # 1000 / 4


class TestRecursiveCharChunks:
    def test_empty_text(self):
        chunks = recursive_char_chunks("", 1000, 0)
        assert chunks == []

    def test_text_smaller_than_target(self):
        text = "Short text"
        chunks = recursive_char_chunks(text, 1000, 0)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_simple_split_no_overlap(self):
        # 2000 chars should split into 2 chunks of ~1000 each
        text = "a" * 2000
        chunks = recursive_char_chunks(text, 1000, 0)
        assert len(chunks) == 2
        assert 900 <= len(chunks[0]) <= 1100  # Approximately 1000
        assert 900 <= len(chunks[1]) <= 1100

    def test_split_with_overlap(self):
        text = "a" * 3000
        chunks = recursive_char_chunks(text, 1000, 200)
        # Should create 3 chunks with 200 char overlap
        assert len(chunks) >= 3
        # Each chunk should be around target size
        for chunk in chunks:
            assert 800 <= len(chunk) <= 1200

    def test_sentence_boundary_breaking(self):
        # Create text with clear sentence boundaries
        text = ". ".join([f"Sentence number {i}" for i in range(200)])
        chunks = recursive_char_chunks(text, 1000, 0)

        # Should create multiple chunks
        assert len(chunks) > 1

        # Each chunk should end with a period (sentence boundary)
        for chunk in chunks[:-1]:  # All except last
            assert chunk.rstrip().endswith(".")

    @pytest.mark.slow
    def test_large_document(self):
        # Simulate a 120k char document (like NYC Admin Code)
        text = "This is a sentence. " * 6000  # ~120k chars
        chunks = recursive_char_chunks(text, 3000, 200)

        # Should create ~40 chunks
        assert 35 <= len(chunks) <= 50

        # Each chunk should be approximately target size
        for chunk in chunks:
            assert len(chunk) <= 3200  # Allow some overage for sentence breaking

    def test_medium_document_fast(self):
        # Faster version for CI
        text = "This is a sentence. " * 600  # ~12k chars
        chunks = recursive_char_chunks(text, 3000, 200)

        # Should create ~4 chunks
        assert 3 <= len(chunks) <= 6

        # Each chunk should be approximately target size
        for chunk in chunks:
            assert len(chunk) <= 3200

    def test_no_sentence_boundaries(self):
        # Edge case: no punctuation
        text = "word " * 1000  # 5000 chars, no sentences
        chunks = recursive_char_chunks(text, 1000, 0)

        # Should still split by words
        assert len(chunks) > 1


class TestSplitHeadings:
    def test_empty_text(self):
        sections = split_headings("")
        assert sections == []

    def test_no_headings(self):
        text = "Just regular text without headings"
        sections = split_headings(text)
        assert len(sections) == 1
        assert sections[0]["title"] is None
        assert sections[0]["body"] == text

    def test_all_caps_headings(self):
        text = """
SECTION ONE
This is the first section.

SECTION TWO
This is the second section.
"""
        sections = split_headings(text)
        assert len(sections) == 2
        assert "SECTION ONE" in sections[0]["title"]
        assert "first section" in sections[0]["body"]
        assert "SECTION TWO" in sections[1]["title"]
        assert "second section" in sections[1]["body"]

    def test_numbered_headings(self):
        text = """
1. First Section
Content of first section.

2. Second Section
Content of second section.
"""
        sections = split_headings(text)
        assert len(sections) >= 2


class TestMakeSuperChunks:
    def test_small_document(self):
        text = "Short document"
        supers = make_super_chunks(text, 10000)
        assert len(supers) == 1

    def test_large_document_with_headings(self):
        text = "\n\n".join(
            [f"SECTION {i}\n" + ("Content. " * 500) for i in range(10)]
        )  # ~30k chars

        supers = make_super_chunks(text, 10000)
        # Should aggregate sections into ~10k chunks
        assert len(supers) >= 2

        # Each super should be around target
        for s in supers:
            body = s.get("body", "")
            assert len(body) <= 15000  # Allow some overage


class TestBuildChunkDocs:
    def test_basic_chunking(self):
        text = "This is a test document. " * 200  # ~5000 chars
        chunks = build_chunk_docs(
            text=text,
            source="https://example.com/doc",
            title="Test Document",
            target_chars=1000,
            overlap_chars=100,
        )

        # Should create multiple chunks
        assert len(chunks) >= 4

        # Each chunk should have required fields
        for chunk in chunks:
            assert "chunk_index" in chunk
            assert "text" in chunk
            assert "token_count" in chunk
            assert "title" in chunk
            assert chunk["title"] == "Test Document"
            assert len(chunk["text"]) > 0
            assert chunk["token_count"] > 0

    def test_chunk_index_sequential(self):
        text = "a" * 10000
        chunks = build_chunk_docs(text, "test", "Test", 1000, 100)

        # Indices should be sequential
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

    def test_realistic_legal_document(self):
        # Simulate NYC Admin Code structure
        text = (
            """
Chapter 4 - RENT STABILIZATION

§ 26-504 Prohibition against harassment.
No landlord shall engage in harassment of tenants...

§ 26-505 Civil penalties.
The commissioner may impose civil penalties...
"""
            * 100
        )  # Repeat to make it substantial

        chunks = build_chunk_docs(text, "nyc_admin_code", "NYC Admin Code", 3000, 200)

        # Should create multiple chunks
        assert len(chunks) > 1

        # Verify metadata
        for chunk in chunks:
            assert chunk["title"] in ["NYC Admin Code", "Chapter 4 - RENT STABILIZATION"]
            assert 1000 <= len(chunk["text"]) <= 4000  # Reasonable size

    def test_token_estimation(self):
        text = "word " * 1000  # 5000 chars
        chunks = build_chunk_docs(text, "test", "Test", 1000, 0)

        for chunk in chunks:
            # Token count should be approximately chars / 4
            estimated = chunk["token_count"]
            actual_chars = len(chunk["text"])
            assert 200 <= estimated <= 350  # ~1000 chars / 4 = 250 tokens


class TestChunkingEdgeCases:
    def test_very_long_single_sentence(self):
        # Edge case: 5000 char sentence with no periods
        text = "word " * 1000
        chunks = recursive_char_chunks(text, 1000, 0)

        # Should still split (by words)
        assert len(chunks) >= 4

    def test_unicode_handling(self):
        text = "Legal text with émojis 🏛️ and spëcial çharacters. " * 100
        chunks = recursive_char_chunks(text, 1000, 100)

        # Should handle unicode without errors
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) > 0

    def test_extreme_overlap(self):
        text = "sentence. " * 50  # Reduced from 500 for speed
        # Overlap larger than chunk size
        chunks = recursive_char_chunks(text, 100, 150)

        # Should still work (overlap capped at chunk size)
        assert len(chunks) >= 1

    def test_whitespace_handling(self):
        text = "   \n\n   Text with lots of    whitespace   \n\n   "
        chunks = build_chunk_docs(text, "test", "Test", 1000, 0)

        # Should strip whitespace
        for chunk in chunks:
            assert chunk["text"] == chunk["text"].strip()


@pytest.fixture
def sample_legal_text():
    return """
NYC Housing Maintenance Code § 27-2029 Heat requirement.

During the period from October first through May thirty-first, centrally-supplied heat, 
in any dwelling in which such heat is required to be provided, shall be furnished so as 
to maintain, in every portion of such dwelling used or occupied for living purposes:

(a) Between the hours of 6:00 A.M. and 10:00 P.M., a temperature of at least 
sixty-eight degrees Fahrenheit whenever the outside temperature falls below fifty-five degrees.

(b) Between the hours of 10:00 P.M. and 6:00 A.M., a temperature of at least 
sixty-two degrees Fahrenheit.

§ 27-2030 Hot water requirement.

The owner of any multiple dwelling shall provide hot water at a constant minimum 
temperature of one hundred twenty degrees Fahrenheit at the tap.
"""


class TestRealWorldScenarios:
    def test_nyc_admin_code_chunking(self, sample_legal_text):
        chunks = build_chunk_docs(
            sample_legal_text, "https://nycadmincode.readthedocs.io/", "NYC HMC", 1000, 100
        )

        # Should create 1-2 chunks from this moderate text
        assert 1 <= len(chunks) <= 3

        # Verify structure
        for chunk in chunks:
            assert "§" in chunk["text"] or "27-" in chunk["text"]  # Contains legal citations

    def test_met_council_guide_chunking(self):
        text = """
Getting Repairs

The laws and regulations of New York require that your landlord maintain 
essential services in your building and apartment.

If your landlord fails to make repairs:
1. Document everything
2. Send written requests
3. File a complaint with HPD
4. Consider rent withholding
5. File an HP Action in Housing Court

For help, contact Met Council at (212) 979-0611.
"""
        chunks = build_chunk_docs(text, "metcouncil.org", "Getting Repairs", 500, 50)

        # Should create multiple chunks
        assert len(chunks) >= 1

        # Each chunk should have content
        for chunk in chunks:
            assert len(chunk["text"]) > 0
            assert chunk["token_count"] > 0
