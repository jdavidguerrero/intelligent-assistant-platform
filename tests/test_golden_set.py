"""
Golden set for RAG quality assurance.

15 music production queries + 10 non-musical queries to measure:
- Citation accuracy
- Hallucination rate (should refuse non-musical queries)
- Genre term disambiguation
- Source diversity

Run with: pytest tests/test_golden_set.py -v --tb=short
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app

# Golden Set: 15 Music Production Q&A Pairs
# Covers: arrangement, synthesis, mixing, genre-specific, live performance
GOLDEN_MUSICAL_QUERIES = [
    # Arrangement
    {
        "query": "What's the recommended arrangement structure for a progressive house track?",
        "expected_topics": ["intro", "breakdown", "build", "drop", "arrangement"],
        "expected_sources": [
            "pete-tong",
            "production",
        ],  # Should cite Pete Tong or production books
    },
    # Synthesis
    {
        "query": "What is an ADSR envelope and how does it work?",
        "expected_topics": ["attack", "decay", "sustain", "release", "envelope"],
        "expected_sources": ["synthesis", "power-tools", "welsh"],
    },
    # Mixing - Kick/Bass
    {
        "query": "How should I mix kick and bass together in house music?",
        "expected_topics": ["sidechain", "eq", "frequency", "phase"],
        "expected_sources": ["pete-tong", "mixing"],
    },
    # Genre-specific
    {
        "query": "What makes organic house different from progressive house?",
        "expected_topics": ["organic", "house", "texture", "atmosphere"],
        "expected_sources": ["youtube", "pete-tong"],
    },
    # Mastering
    {
        "query": "What loudness target should I aim for when mastering for Spotify?",
        "expected_topics": ["lufs", "loudness", "mastering", "streaming"],
        "expected_sources": ["pete-tong", "mastering", "fabfilter"],
    },
    # EQ Fundamentals
    {
        "query": "When should I use a high-pass filter on vocals?",
        "expected_topics": ["high-pass", "filter", "eq", "vocals", "frequency"],
        "expected_sources": ["mixing", "pete-tong"],
    },
    # Compression
    {
        "query": "What's the difference between ratio and threshold in a compressor?",
        "expected_topics": ["compressor", "ratio", "threshold", "dynamics"],
        "expected_sources": ["mixing", "production"],
    },
    # Synthesis Advanced
    {
        "query": "How does FM synthesis differ from subtractive synthesis?",
        "expected_topics": ["fm", "subtractive", "synthesis", "modulation"],
        "expected_sources": ["synthesis", "power-tools", "creating-sounds"],
    },
    # Genre: Kick Design
    {
        "query": "How to design a punchy kick for techno?",
        "expected_topics": ["kick", "techno", "punch", "transient"],
        "expected_sources": ["pete-tong", "kick"],
    },
    # Live Performance
    {
        "query": "What's the best way to prepare stems for a DJ set?",
        "expected_topics": ["stems", "dj", "export", "preparation"],
        "expected_sources": ["pete-tong", "production"],
    },
    # Music Theory
    {
        "query": "What chord progressions work well for melodic techno?",
        "expected_topics": ["chord", "progression", "melodic", "techno", "harmony"],
        "expected_sources": ["pete-tong", "music-theory", "youtube"],
    },
    # Mixing: Stereo
    {
        "query": "How wide should I make my bass in the mix?",
        "expected_topics": ["bass", "stereo", "mono", "width", "low"],
        "expected_sources": ["pete-tong", "mixing"],
    },
    # Synthesis: Wavetable
    {
        "query": "What is Serum and what makes it different from other synths?",
        "expected_topics": ["serum", "wavetable", "synthesis"],
        "expected_sources": ["serum", "synthesis"],
    },
    # DAW Workflow
    {
        "query": "How do I set up sidechain compression in Ableton Live?",
        "expected_topics": ["sidechain", "compression", "ableton", "routing"],
        "expected_sources": ["ableton", "live", "pete-tong"],
    },
    # Advanced Mixing
    {
        "query": "When should I use parallel compression on drums?",
        "expected_topics": ["parallel", "compression", "drums", "new york"],
        "expected_sources": ["mixing", "pete-tong"],
    },
]

# Hallucination Test: 10 Non-Musical Queries
# System should refuse with "insufficient_knowledge"
HALLUCINATION_QUERIES = [
    "What is the capital of France?",
    "How do I install React Router?",
    "What's the recipe for chocolate chip cookies?",
    "Who won the 2022 World Cup?",
    "How to fix a flat tire?",
    "What are the symptoms of the flu?",
    "How do I learn Python programming?",
    "What is quantum computing?",
    "How to grow tomatoes in a garden?",
    "What is the plot of Game of Thrones season 8?",
]

# Disambiguation Test: Terms with multiple meanings
DISAMBIGUATION_QUERIES = [
    {
        "query": "What is acid in electronic music?",
        "expected_disambiguation": "genre/sound",  # Should clarify acid house vs acid bass line
        "expected_topics": ["acid", "303", "bass", "house"],
    },
    {
        "query": "How do I use a house compressor?",
        "expected_disambiguation": "genre vs building",  # Should understand "house music" not "house"
        "expected_topics": ["house", "compressor", "compression"],
    },
    {
        "query": "What frequency range does bass occupy?",
        "expected_disambiguation": "instrument vs frequency",  # Should understand both bass instrument and bass frequencies
        "expected_topics": ["bass", "frequency", "low", "hz"],
    },
]


class TestGoldenSet:
    """Golden set tests for RAG quality assurance."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        """Clear dependency overrides (use real providers for golden set)."""
        app.dependency_overrides.clear()
        yield
        app.dependency_overrides.clear()

    @pytest.mark.parametrize("golden_query", GOLDEN_MUSICAL_QUERIES)
    def test_golden_musical_query(self, golden_query: dict) -> None:
        """Test that musical queries return cited answers with expected topics."""
        client = TestClient(app)
        response = client.post(
            "/ask", json={"query": golden_query["query"], "top_k": 5, "confidence_threshold": 0.58}
        )

        # Should succeed
        assert response.status_code == 200
        data = response.json()

        # Should have answer
        assert len(data["answer"]) > 50, "Answer too short"

        # Should have citations
        assert len(data["citations"]) > 0, "No citations found"

        # Should have sources
        assert len(data["sources"]) > 0, "No sources found"

        # Check if expected topics appear in answer (case-insensitive)
        answer_lower = data["answer"].lower()
        topic_found = any(topic in answer_lower for topic in golden_query["expected_topics"])
        assert topic_found, f"Expected topics {golden_query['expected_topics']} not found in answer"

        # Optional: Check source diversity (should cite expected source types)
        # This is informational — not a hard assertion
        print(f"\nQuery: {golden_query['query'][:60]}...")
        print(f"Sources: {[src['source_name'][:30] for src in data['sources']]}")

    @pytest.mark.parametrize("query", HALLUCINATION_QUERIES)
    def test_hallucination_refusal(self, query: str) -> None:
        """Test that non-musical queries are rejected with insufficient_knowledge."""
        client = TestClient(app)
        response = client.post("/ask", json={"query": query})

        # Should reject with 422
        assert response.status_code == 422, f"Should reject non-musical query: {query}"
        data = response.json()

        # Should contain "insufficient_knowledge" in reason
        assert "insufficient_knowledge" in data["detail"]["reason"]

    @pytest.mark.parametrize("disamb_query", DISAMBIGUATION_QUERIES)
    def test_disambiguation(self, disamb_query: dict) -> None:
        """Test that ambiguous musical terms are disambiguated correctly."""
        client = TestClient(app)
        response = client.post(
            "/ask", json={"query": disamb_query["query"], "confidence_threshold": 0.65, "top_k": 5}
        )

        # May succeed or reject depending on content
        if response.status_code == 200:
            data = response.json()
            answer_lower = data["answer"].lower()

            # Should mention at least one expected topic
            topic_found = any(topic in answer_lower for topic in disamb_query["expected_topics"])
            assert (
                topic_found
            ), f"Expected topics {disamb_query['expected_topics']} not found in answer"

            print(f"\nDisambiguation: {disamb_query['query']}")
            print(
                f"Topics found: {[t for t in disamb_query['expected_topics'] if t in answer_lower]}"
            )
        else:
            # If rejected, note it
            print(f"\nDisambiguation query rejected: {disamb_query['query']}")
            print(f"Reason: {response.json()['detail']}")


@pytest.mark.skip(reason="Manual validation — run with --runxfail to execute")
def test_citation_accuracy_manual():
    """Manual test to validate citation accuracy on golden set.

    Run this test manually and check:
    1. Are citations [1], [2] valid (pointing to real sources)?
    2. Do cited sources actually support the claim?
    3. Hallucination rate: % of non-musical queries correctly refused

    Expected:
    - Citation accuracy: 100% (no invalid [5] when only 3 sources)
    - Hallucination refusal rate: >= 90% (9+ out of 10 non-musical queries rejected)
    """
    client = TestClient(app)

    print("\n" + "=" * 80)
    print("CITATION ACCURACY VALIDATION")
    print("=" * 80)

    valid_citations = 0
    total_musical = len(GOLDEN_MUSICAL_QUERIES)

    for i, golden_query in enumerate(GOLDEN_MUSICAL_QUERIES, 1):
        response = client.post("/ask", json={"query": golden_query["query"]})
        if response.status_code == 200:
            data = response.json()
            # Check if any invalid_citations warning
            if "invalid_citations" not in data.get("warnings", []):
                valid_citations += 1
            print(
                f"{i}/{total_musical}: {'✅' if 'invalid_citations' not in data.get('warnings', []) else '❌'} {golden_query['query'][:60]}"
            )
        else:
            print(f"{i}/{total_musical}: ⚠️ REJECTED - {golden_query['query'][:60]}")

    print(
        f"\nCitation Accuracy: {valid_citations}/{total_musical} ({valid_citations/total_musical*100:.1f}%)"
    )

    # Hallucination test
    print("\n" + "=" * 80)
    print("HALLUCINATION REFUSAL TEST")
    print("=" * 80)

    refused = 0
    total_hallucination = len(HALLUCINATION_QUERIES)

    for i, query in enumerate(HALLUCINATION_QUERIES, 1):
        response = client.post("/ask", json={"query": query})
        if response.status_code == 422:
            refused += 1
            print(f"{i}/{total_hallucination}: ✅ REFUSED - {query[:50]}")
        else:
            print(f"{i}/{total_hallucination}: ❌ ANSWERED - {query[:50]}")

    print(
        f"\nHallucination Refusal Rate: {refused}/{total_hallucination} ({refused/total_hallucination*100:.1f}%)"
    )
    print("\nTarget: Citation Accuracy >= 95%, Refusal Rate >= 90%")
