"""
Production search evaluation harness.

Runs 20 labeled music queries against local /search endpoint and measures:
- Hit@5 accuracy (category-based matching)
- Latency percentiles (p50, p95, max)
- Per-query breakdown

Usage:
    # Start API server first
    uvicorn api.main:app --reload

    # Run evaluation
    python scripts/eval_search.py

Output:
    - scripts/eval_results.json (machine-readable)
    - scripts/eval_results.md (human-readable report)
"""

import json
import statistics
from pathlib import Path

import requests

from core.categories import extract_category

# Configuration
API_BASE = "http://localhost:8000"
SCRIPT_DIR = Path(__file__).parent

# 20 labeled queries with graded relevance (strict + acceptable categories)
QUERIES = [
    {
        "query": "how to make a punchy kick drum",
        "expected_category": "the-kick",
        "acceptable_categories": ["youtube-tutorials"],  # YouTube kick tutorials are OK
    },
    {
        "query": "layering kick samples",
        "expected_category": "the-kick",
        "acceptable_categories": [],
    },
    {
        "query": "drum programming techniques",
        "expected_category": "drums",
        "acceptable_categories": ["youtube-tutorials"],
    },
    {
        "query": "808 bass processing",
        "expected_category": "bass",
        "acceptable_categories": ["youtube-tutorials"],
    },
    {
        "query": "producer mindset and workflow",
        "expected_category": "mindset",
        "acceptable_categories": [],
    },
    {
        "query": "subtractive synthesis basics",
        "expected_category": "synthesis",
        "acceptable_categories": [],
    },
    {
        "query": "mixing kick and bass together",
        "expected_category": "mix-mastering",
        "acceptable_categories": ["the-kick", "bass", "youtube-tutorials"],
    },
    {
        "query": "mastering chain setup",
        "expected_category": "mix-mastering",
        "acceptable_categories": [],
    },
    {
        "query": "sidechain compression tutorial",
        "expected_category": "mix-mastering",
        "acceptable_categories": ["bass", "youtube-tutorials"],
    },
    {
        "query": "how to choose kick samples",
        "expected_category": "the-kick",
        "acceptable_categories": [],
    },
    {
        "query": "drum mixing tips",
        "expected_category": "drums",
        "acceptable_categories": ["mix-mastering", "youtube-tutorials"],
    },
    {
        "query": "bass layering techniques",
        "expected_category": "bass",
        "acceptable_categories": ["youtube-tutorials"],
    },
    {
        "query": "staying motivated as producer",
        "expected_category": "mindset",
        "acceptable_categories": [],
    },
    {
        "query": "FM synthesis explained",
        "expected_category": "synthesis",
        "acceptable_categories": [],
    },
    {
        "query": "EQ tips for mixing",
        "expected_category": "mix-mastering",
        "acceptable_categories": ["the-kick", "youtube-tutorials"],  # EQ in kick lessons is OK
    },
    {
        "query": "kick drum frequency range",
        "expected_category": "the-kick",
        "acceptable_categories": ["bass", "youtube-tutorials"],
    },
    {
        "query": "snare drum processing",
        "expected_category": "drums",
        "acceptable_categories": ["mix-mastering"],
    },
    {"query": "sub bass vs mid bass", "expected_category": "bass", "acceptable_categories": []},
    {
        "query": "overcoming creative blocks",
        "expected_category": "mindset",
        "acceptable_categories": [],
    },
    {
        "query": "wavetable synthesis guide",
        "expected_category": "synthesis",
        "acceptable_categories": [],
    },
]


def run_evaluation():
    """Run evaluation and generate reports."""
    results = []
    latencies = []

    print(f"\nRunning {len(QUERIES)} queries against {API_BASE}/search...\n")

    for i, q in enumerate(QUERIES, 1):
        resp = requests.post(f"{API_BASE}/search", json={"query": q["query"], "top_k": 5})
        resp.raise_for_status()
        data = resp.json()

        # Extract categories and source paths from top 5 results
        result_categories = [extract_category(r["source_path"]) for r in data["results"]]
        result_sources = [r["source_path"] for r in data["results"]]

        # Check Hit@5 with graded relevance
        hit_strict = q["expected_category"] in result_categories
        hit_acceptable = any(cat in result_categories for cat in q["acceptable_categories"])
        hit = hit_strict or hit_acceptable

        # Document diversity: count unique source_path in top-k
        unique_docs = len(set(result_sources))

        # Record per-query data
        per_query = {
            "query": q["query"],
            "expected_category": q["expected_category"],
            "acceptable_categories": q["acceptable_categories"],
            "hit_strict": hit_strict,
            "hit_acceptable": hit_acceptable,
            "hit": hit,
            "unique_docs": unique_docs,
            "top_results": [
                {
                    "score": r["score"],
                    "source_path": r["source_path"],
                    "category": extract_category(r["source_path"]),
                }
                for r in data["results"]
            ],
            "latency_ms": data["meta"]["total_ms"],
        }
        results.append(per_query)
        latencies.append(data["meta"]["total_ms"])

        # Progress indicator
        status_icon = "✓" if hit_strict else ("~" if hit_acceptable else "✗")
        print(
            f"  [{i:2d}/20] {status_icon} {q['query'][:50]:50s} ({data['meta']['total_ms']:.0f}ms) [{unique_docs} docs]"
        )

    # Compute aggregate metrics
    hit_strict_count = sum(r["hit_strict"] for r in results)
    hit_acceptable_count = sum(r["hit_acceptable"] for r in results)
    hit_total_count = sum(r["hit"] for r in results)

    hit_strict_rate = hit_strict_count / len(results)
    hit_acceptable_rate = hit_acceptable_count / len(results)
    hit_total_rate = hit_total_count / len(results)

    # Document diversity: average unique docs in top-5
    avg_unique_docs = statistics.mean(r["unique_docs"] for r in results)

    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    max_lat = max(latencies)

    # Write JSON report
    json_output = {
        "total_queries": len(QUERIES),
        "hit_strict": {
            "rate": round(hit_strict_rate, 3),
            "count": hit_strict_count,
        },
        "hit_acceptable": {
            "rate": round(hit_acceptable_rate, 3),
            "count": hit_acceptable_count,
        },
        "hit_total": {
            "rate": round(hit_total_rate, 3),
            "count": hit_total_count,
        },
        "diversity": {
            "avg_unique_docs": round(avg_unique_docs, 2),
            "max_possible": 5,
        },
        "latency": {
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "max_ms": round(max_lat, 1),
        },
        "per_query": results,
    }

    json_path = SCRIPT_DIR / "eval_results.json"
    with json_path.open("w") as f:
        json.dump(json_output, f, indent=2)

    # Write Markdown report
    md_lines = [
        "# Search Evaluation Report",
        "",
        f"**Queries**: {len(QUERIES)}",
        "",
        "## Aggregate Metrics",
        "",
        "### Relevance (Graded)",
        f"- **Hit@5 (Strict)**: {hit_strict_rate:.1%} ({hit_strict_count}/{len(QUERIES)}) — exact category match",
        f"- **Hit@5 (Acceptable)**: {hit_acceptable_rate:.1%} ({hit_acceptable_count}/{len(QUERIES)}) — related category",
        f"- **Hit@5 (Total)**: {hit_total_rate:.1%} ({hit_total_count}/{len(QUERIES)}) — any relevant match",
        "",
        "### Document Diversity",
        f"- **Avg Unique Docs in Top-5**: {avg_unique_docs:.2f} / 5",
        "- **Interpretation**: Higher is better (5.0 = no repetition)",
        "",
        "### Latency",
        f"- **p50**: {p50:.1f}ms",
        f"- **p95**: {p95:.1f}ms",
        f"- **max**: {max_lat:.1f}ms",
        "",
        "## Per-Query Results",
        "",
    ]

    for i, r in enumerate(results, 1):
        if r["hit_strict"]:
            status = "✓ Strict"
        elif r["hit_acceptable"]:
            status = "~ Acceptable"
        else:
            status = "✗ Miss"

        md_lines.append(f"### {i}. {r['query']}")
        md_lines.append(f"- **Expected**: `{r['expected_category']}`")
        if r["acceptable_categories"]:
            md_lines.append(
                f"- **Acceptable**: {', '.join(f'`{c}`' for c in r['acceptable_categories'])}"
            )
        md_lines.append(f"- **Hit**: {status}")
        md_lines.append(f"- **Unique Docs**: {r['unique_docs']}/5")
        md_lines.append(f"- **Latency**: {r['latency_ms']:.0f}ms")
        md_lines.append("- **Top Results**:")
        for j, res in enumerate(r["top_results"][:5], 1):
            md_lines.append(
                f"  {j}. [{res['score']:.3f}] `{res['category']}` — {res['source_path']}"
            )
        md_lines.append("")

    md_path = SCRIPT_DIR / "eval_results.md"
    with md_path.open("w") as f:
        f.write("\n".join(md_lines))

    # Print summary
    print(f"\n{'='*70}")
    print("EVALUATION SUMMARY")
    print(f"{'='*70}")
    print(f"Hit@5 (Strict):      {hit_strict_rate:.1%} ({hit_strict_count}/{len(QUERIES)})")
    print(f"Hit@5 (Acceptable):  {hit_acceptable_rate:.1%} ({hit_acceptable_count}/{len(QUERIES)})")
    print(f"Hit@5 (Total):       {hit_total_rate:.1%} ({hit_total_count}/{len(QUERIES)})")
    print(f"\nDocument Diversity:  {avg_unique_docs:.2f} / 5.0 unique docs per query")
    print(f"\nLatency p50:         {p50:.1f}ms")
    print(f"Latency p95:         {p95:.1f}ms")
    print(f"Latency max:         {max_lat:.1f}ms")
    print("\nResults written to:")
    print(f"  - {json_path}")
    print(f"  - {md_path}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    run_evaluation()
