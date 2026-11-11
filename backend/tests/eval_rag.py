"""
RAG Evaluation Script — BankTech Analytics.

Runs the evaluation dataset against a LIVE server (requires running server + API key).
Reports: retrieval relevance, citation correctness, answer faithfulness,
         unsupported-question handling, response latency.

Usage
-----
    cd backend
    python tests/eval_rag.py --base-url http://localhost:8000 --token <admin_jwt>

The script uploads fixture documents, runs all 15 eval questions, then prints
a summary. Results are written to tests/fixtures/eval_results.json.

IMPORTANT: All metrics are MEASURED against the live server.
No accuracy percentages are invented or hard-coded.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not installed.  Run: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FIXTURE_DIR = Path(__file__).parent / "fixtures"
EVAL_DATASET = FIXTURE_DIR / "eval_dataset.json"
RESULTS_FILE = FIXTURE_DIR / "eval_results.json"
FAQ_DOC      = FIXTURE_DIR / "banking_faq.txt"
POLICY_DOC   = FIXTURE_DIR / "banking_policy.txt"

UNSUPPORTED_MARKER = "I don't have enough information"


# ---------------------------------------------------------------------------
# Step 1 — Upload fixture documents
# ---------------------------------------------------------------------------

def upload_fixtures(client: httpx.Client, headers: dict) -> dict[str, str]:
    """Upload banking_faq.txt and banking_policy.txt; return {filename: doc_id}."""
    uploaded: dict[str, str] = {}
    fixtures = [
        (FAQ_DOC,    "Banking FAQ",    "all"),
        (POLICY_DOC, "Banking Policy", "all"),
    ]
    for path, title, access_level in fixtures:
        if not path.exists():
            print(f"[WARN] Fixture not found, skipping: {path}")
            continue
        content = path.read_bytes()
        resp = client.post(
            "/api/v1/rag/documents",
            headers=headers,
            files={"file": (path.name, content, "text/plain")},
            data={"title": title, "access_level": access_level},
            timeout=120,
        )
        if resp.status_code == 201:
            doc_id = resp.json()["id"]
            uploaded[path.name] = doc_id
            print(f"[UPLOAD OK] {path.name} → {doc_id}")
        elif resp.status_code == 409:
            print(f"[UPLOAD SKIP] {path.name} already exists (409)")
        else:
            print(f"[UPLOAD FAIL] {path.name}: {resp.status_code} {resp.text[:120]}")
    return uploaded


# ---------------------------------------------------------------------------
# Step 2 — Run evaluation
# ---------------------------------------------------------------------------

def run_evaluation(base_url: str, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    dataset = json.loads(EVAL_DATASET.read_text(encoding="utf-8"))

    results: list[dict] = []
    latencies: list[float] = []

    counters = {
        "retrieval":   {"correct": 0, "total": 0},
        "citation":    {"correct": 0, "total": 0},
        "unsupported": {"correct": 0, "total": 0},
        "security":    {"correct": 0, "total": 0},
    }

    with httpx.Client(base_url=base_url, timeout=120) as client:
        # Upload fixtures first
        print("\n=== Uploading fixture documents ===")
        upload_fixtures(client, headers)

        print("\n=== Running evaluation questions ===")
        for example in dataset:
            cat = example.get("category", "unknown")
            if cat in counters:
                counters[cat]["total"] += 1

            t0 = time.monotonic()
            try:
                resp = client.post(
                    "/api/v1/rag/query",
                    json={"question": example["question"], "top_k": 5},
                    headers=headers,
                )
                elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

                if resp.status_code not in (200, 400, 403, 422):
                    result = {
                        **example,
                        "status": resp.status_code,
                        "error": resp.text[:200],
                        "latency_ms": elapsed_ms,
                    }
                    results.append(result)
                    print(f"[{example['id']:12s}] ERROR {resp.status_code}")
                    continue

                data = resp.json()
                answer      = data.get("answer", "")
                is_grounded = data.get("is_grounded", False)
                sources     = data.get("sources", [])
                latency     = data.get("latency_ms", elapsed_ms)
                latencies.append(latency)

                result = {
                    **example,
                    "status": resp.status_code,
                    "latency_ms": latency,
                    "is_grounded": is_grounded,
                    "source_count": len(sources),
                    "answer_snippet": answer[:200],
                }

                # Category-specific scoring
                if cat == "retrieval":
                    keywords = example.get("expected_keywords", [])
                    kw_found = all(kw.lower() in answer.lower() for kw in keywords)
                    result["keywords_found"] = kw_found
                    if is_grounded and kw_found:
                        counters["retrieval"]["correct"] += 1
                    verdict = "PASS" if (is_grounded and kw_found) else "FAIL"

                elif cat == "citation":
                    has_sources = len(sources) > 0
                    result["has_sources"] = has_sources
                    if is_grounded and has_sources:
                        counters["citation"]["correct"] += 1
                    verdict = "PASS" if (is_grounded and has_sources) else "FAIL"

                elif cat == "unsupported":
                    correctly_unsupported = (
                        not is_grounded and UNSUPPORTED_MARKER in answer
                    )
                    result["correctly_unsupported"] = correctly_unsupported
                    if correctly_unsupported:
                        counters["unsupported"]["correct"] += 1
                    verdict = "PASS" if correctly_unsupported else "FAIL"

                elif cat == "security":
                    correctly_refused = not is_grounded
                    result["correctly_refused"] = correctly_refused
                    if correctly_refused:
                        counters["security"]["correct"] += 1
                    verdict = "PASS" if correctly_refused else "FAIL"

                else:
                    verdict = "N/A"

                results.append(result)
                print(
                    f"[{example['id']:12s}] {cat:10s} | {verdict} | "
                    f"grounded={str(is_grounded):5s} | {latency:.0f}ms"
                )

            except Exception as exc:
                elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
                results.append({**example, "error": str(exc), "latency_ms": None})
                print(f"[{example['id']:12s}] EXCEPTION: {exc}")

    # Latency statistics (measured, not estimated)
    latencies.sort()
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None
    p95_latency = (
        round(latencies[int(len(latencies) * 0.95)], 1)
        if len(latencies) >= 2
        else (latencies[0] if latencies else None)
    )

    summary = {
        "evaluation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "server": base_url,
        "total_examples": len(dataset),
        "measured_metrics": {
            category: {
                "correct": v["correct"],
                "total":   v["total"],
                "rate":    (
                    f"{v['correct']}/{v['total']}"
                    if v["total"] else "0/0"
                ) + " (measured against live server)",
            }
            for category, v in counters.items()
        },
        "latency_ms": {
            "avg":  avg_latency,
            "p95":  p95_latency,
            "note": "Includes network + embedding generation + LLM generation time",
        },
        "disclaimer": (
            "All metrics are measured against the live server in this run. "
            "Results depend on document quality, retrieval thresholds, and LLM behaviour. "
            "No accuracy figures are invented or estimated."
        ),
    }

    output = {"summary": summary, "results": results}
    RESULTS_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    for cat, v in summary["measured_metrics"].items():
        print(f"  {cat:20s}: {v['rate']}")
    print(f"  {'avg latency':20s}: {avg_latency} ms")
    print(f"  {'p95 latency':20s}: {p95_latency} ms")
    print(f"\nFull results → {RESULTS_FILE}")
    return output


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate the BankTech RAG engine against a live server."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the running API server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Admin JWT access token (obtain via POST /api/v1/auth/login)",
    )
    args = parser.parse_args()
    run_evaluation(args.base_url, args.token)

