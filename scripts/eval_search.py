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

# 20 labeled queries covering music production categories
QUERIES = [
    {"query": "how to make a punchy kick drum", "expected_category": "the-kick"},
    {"query": "layering kick samples", "expected_category": "the-kick"},
    {"query": "drum programming techniques", "expected_category": "drums"},
    {"query": "808 bass processing", "expected_category": "bass"},
    {"query": "producer mindset and workflow", "expected_category": "mindset"},
    {"query": "subtractive synthesis basics", "expected_category": "synthesis"},
    {"query": "mixing kick and bass together", "expected_category": "mix-mastering"},
    {"query": "mastering chain setup", "expected_category": "mix-mastering"},
    {"query": "sidechain compression tutorial", "expected_category": "mix-mastering"},
    {"query": "how to choose kick samples", "expected_category": "the-kick"},
    {"query": "drum mixing tips", "expected_category": "drums"},
    {"query": "bass layering techniques", "expected_category": "bass"},
    {"query": "staying motivated as producer", "expected_category": "mindset"},
    {"query": "FM synthesis explained", "expected_category": "synthesis"},
    {"query": "EQ tips for mixing", "expected_category": "mix-mastering"},
    {"query": "kick drum frequency range", "expected_category": "the-kick"},
    {"query": "snare drum processing", "expected_category": "drums"},
    {"query": "sub bass vs mid bass", "expected_category": "bass"},
    {"query": "overcoming creative blocks", "expected_category": "mindset"},
    {"query": "wavetable synthesis guide", "expected_category": "synthesis"},
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

        # Extract categories from top 5 results
        result_categories = [extract_category(r["source_path"]) for r in data["results"]]

        # Check Hit@5: expected category in top 5 results?
        hit = q["expected_category"] in result_categories

        # Record per-query data
        per_query = {
            "query": q["query"],
            "expected_category": q["expected_category"],
            "hit": hit,
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
        status = "✓" if hit else "✗"
        print(f"  [{i:2d}/20] {status} {q['query'][:50]:50s} ({data['meta']['total_ms']:.0f}ms)")

    # Compute aggregate metrics
    hit_count = sum(r["hit"] for r in results)
    hit_at_5 = hit_count / len(results)
    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    max_lat = max(latencies)

    # Write JSON report
    json_output = {
        "total_queries": len(QUERIES),
        "hit_at_5": hit_at_5,
        "hit_count": hit_count,
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
        f"- **Hit@5**: {hit_at_5:.1%} ({hit_count}/{len(QUERIES)} queries)",
        f"- **Latency (p50)**: {p50:.1f}ms",
        f"- **Latency (p95)**: {p95:.1f}ms",
        f"- **Latency (max)**: {max_lat:.1f}ms",
        "",
        "## Per-Query Results",
        "",
    ]

    for i, r in enumerate(results, 1):
        status = "✓" if r["hit"] else "✗"
        md_lines.append(f"### {i}. {r['query']}")
        md_lines.append(f"- **Expected**: `{r['expected_category']}`")
        md_lines.append(f"- **Hit**: {status}")
        md_lines.append(f"- **Latency**: {r['latency_ms']:.0f}ms")
        md_lines.append("- **Top Results**:")
        for j, res in enumerate(r["top_results"][:3], 1):
            md_lines.append(f"  {j}. [{res['score']:.3f}] `{res['category']}` — {res['source_path']}")
        md_lines.append("")

    md_path = SCRIPT_DIR / "eval_results.md"
    with md_path.open("w") as f:
        f.write("\n".join(md_lines))

    # Print summary
    print(f"\n{'='*60}")
    print("EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Hit@5:        {hit_at_5:.1%} ({hit_count}/{len(QUERIES)})")
    print(f"Latency p50:  {p50:.1f}ms")
    print(f"Latency p95:  {p95:.1f}ms")
    print(f"Latency max:  {max_lat:.1f}ms")
    print("\nResults written to:")
    print(f"  - {json_path}")
    print(f"  - {md_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_evaluation()
