"""
metrics.py
----------
Evaluation Framework

Runs the full benchmark query suite against the agent and
measures accuracy across all difficulty tiers.

Metrics tracked:
    - Execution success rate (did the query run?)
    - Answer accuracy (did it return the right data?)
    - Clarification accuracy (did it ask when it should?)
    - Retry rate (how often did SQL generation need retries?)
    - Latency (how long did each query take?)

Usage:
    python -m evaluation.metrics
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from agent.graph          import run_query
from agent.state          import AgentState
from observability.tracer import save_trace


BENCHMARK_PATH = Path(__file__).parent / "benchmark_queries.json"
RESULTS_PATH   = Path(__file__).parent / "eval_results.json"


# ------------------------------------------------------------------
# Core evaluation runner
# ------------------------------------------------------------------

def run_evaluation(user_id: str = "alice", verbose: bool = True) -> dict:
    """
    Runs all benchmark queries and computes accuracy metrics.

    Args:
        user_id: User to run queries as.
        verbose: Print results as they run.

    Returns:
        Full evaluation report dict.
    """

    with open(BENCHMARK_PATH) as f:
        benchmarks = json.load(f)

    results     = []
    start_time  = time.time()

    if verbose:
        print("=" * 65)
        print("EVALUATION RUN")
        print(f"Timestamp : {datetime.now().isoformat()}")
        print(f"User      : {user_id}")
        print(f"Queries   : {len(benchmarks)}")
        print("=" * 65)

    for bench in benchmarks:
        result = _evaluate_single(bench, user_id, verbose)
        results.append(result)

        # Save trace for every query
        if result.get("state"):
            save_trace(result["state"])
            result.pop("state")   # Don't serialize state object

    total_time = round(time.time() - start_time, 2)

    # Compute metrics
    report = _compute_metrics(results, total_time)
    report["results"] = results

    # Save results
    with open(RESULTS_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    if verbose:
        _print_report(report)

    return report


# ------------------------------------------------------------------
# Single query evaluator
# ------------------------------------------------------------------

def _evaluate_single(bench: dict, user_id: str, verbose: bool) -> dict:
    """Runs one benchmark query and evaluates the result."""

    query_id  = bench["id"]
    tier      = bench["tier"]
    question  = bench["question"]

    if verbose:
        print(f"\n[{query_id}] {tier.upper()}: {question}")

    start = time.time()
    state = run_query(question, user_id)
    elapsed_ms = round((time.time() - start) * 1000)

    result = {
        "id":           query_id,
        "tier":         tier,
        "question":     question,
        "elapsed_ms":   elapsed_ms,
        "retry_count":  state.retry_count,
        "state":        state,   # Removed before serialization
    }

    # ── Clarification tier ──────────────────────────────────────
    if tier == "clarification":
        clarification_correct = state.needs_clarification
        result.update({
            "expected":               "clarification_triggered",
            "clarification_triggered": clarification_correct,
            "passed":                 clarification_correct,
            "failure_reason":         None if clarification_correct else "No clarification triggered",
        })
        status = "✅" if clarification_correct else "❌"
        if verbose:
            print(f"  {status} Clarification triggered: {clarification_correct}")
        return result

    # ── Execution check ─────────────────────────────────────────
    if not state.execution_success:
        result.update({
            "passed":         False,
            "failure_reason": state.error or "Execution failed",
            "row_count":      0,
            "sql":            state.generated_sql,
        })
        if verbose:
            print(f"  ❌ FAILED: {state.error}")
        return result

    exec_result = state.execution_result
    row_count   = exec_result["row_count"]
    columns     = exec_result["columns"]

    # ── Row count check ─────────────────────────────────────────
    expected_rows = bench.get("expected_row_count")
    row_count_ok  = True
    if expected_rows is not None:
        row_count_ok = (row_count == expected_rows)

    # ── Column check ────────────────────────────────────────────
    expected_cols = bench.get("expected_columns")
    columns_ok    = True
    if expected_cols:
        columns_lower   = [c.lower() for c in columns]
        columns_ok      = all(ec.lower() in columns_lower for ec in expected_cols)

    # ── Value check ─────────────────────────────────────────────
    expected_val  = bench.get("expected_value")
    value_ok      = True
    if expected_val and exec_result["rows"]:
        first_row = dict(zip(columns, exec_result["rows"][0]))
        for key, val in expected_val.items():
            actual = first_row.get(key)
            if actual != val:
                value_ok = False
                break

    passed = row_count_ok and columns_ok and value_ok
    failure_reasons = []
    if not row_count_ok:
        failure_reasons.append(f"row_count: expected {expected_rows}, got {row_count}")
    if not columns_ok:
        failure_reasons.append(f"missing columns: {expected_cols}")
    if not value_ok:
        failure_reasons.append(f"value mismatch for {expected_val}")

    result.update({
        "passed":         passed,
        "failure_reason": "; ".join(failure_reasons) if failure_reasons else None,
        "row_count":      row_count,
        "columns":        columns,
        "sql":            state.generated_sql,
        "sql_confidence": state.sql_confidence,
    })

    status = "✅" if passed else "❌"
    if verbose:
        msg = f"rows={row_count}"
        if not passed:
            msg += f" | FAIL: {'; '.join(failure_reasons)}"
        print(f"  {status} {msg} ({elapsed_ms}ms)")

    return result


# ------------------------------------------------------------------
# Metrics computation
# ------------------------------------------------------------------

def _compute_metrics(results: list, total_time: float) -> dict:
    """Computes aggregate metrics across all results."""

    by_tier = {"easy": [], "medium": [], "hard": [], "clarification": []}
    for r in results:
        tier = r.get("tier", "unknown")
        if tier in by_tier:
            by_tier[tier].append(r)

    def tier_stats(tier_results):
        if not tier_results:
            return {"count": 0, "passed": 0, "accuracy": 0}
        passed = sum(1 for r in tier_results if r.get("passed"))
        return {
            "count":    len(tier_results),
            "passed":   passed,
            "accuracy": round(passed / len(tier_results) * 100, 1),
        }

    total   = len(results)
    passed  = sum(1 for r in results if r.get("passed"))
    retried = sum(1 for r in results if r.get("retry_count", 0) > 0)

    latencies = [r["elapsed_ms"] for r in results if "elapsed_ms" in r]
    avg_ms    = round(sum(latencies) / len(latencies)) if latencies else 0

    return {
        "timestamp":      datetime.now().isoformat(),
        "summary": {
            "total_queries":  total,
            "passed":         passed,
            "failed":         total - passed,
            "overall_accuracy": round(passed / total * 100, 1) if total else 0,
            "retry_rate":     round(retried / total * 100, 1) if total else 0,
            "avg_latency_ms": avg_ms,
            "total_time_s":   total_time,
        },
        "by_tier": {
            "easy":          tier_stats(by_tier["easy"]),
            "medium":        tier_stats(by_tier["medium"]),
            "hard":          tier_stats(by_tier["hard"]),
            "clarification": tier_stats(by_tier["clarification"]),
        },
    }


# ------------------------------------------------------------------
# Report printer
# ------------------------------------------------------------------

def _print_report(report: dict) -> None:
    """Prints a clean evaluation report."""

    s  = report["summary"]
    bt = report["by_tier"]

    print(f"\n{'=' * 65}")
    print("EVALUATION RESULTS")
    print(f"{'=' * 65}")
    print(f"  Overall accuracy  : {s['overall_accuracy']}%  ({s['passed']}/{s['total_queries']})")
    print(f"  Retry rate        : {s['retry_rate']}%")
    print(f"  Avg latency       : {s['avg_latency_ms']}ms")
    print(f"  Total time        : {s['total_time_s']}s")

    print(f"\n── By Tier ──")
    for tier, stats in bt.items():
        if stats["count"] > 0:
            bar = "█" * int(stats["accuracy"] / 10)
            print(f"  {tier:15s} : {stats['accuracy']:5.1f}%  {bar}  ({stats['passed']}/{stats['count']})")

    # Print failures
    failures = [r for r in report.get("results", []) if not r.get("passed")]
    if failures:
        print(f"\n── Failed Queries ──")
        for r in failures:
            print(f"  [{r['id']}] {r['question']}")
            print(f"         Reason: {r.get('failure_reason', 'unknown')}")

    print(f"{'=' * 65}")
    print(f"Results saved to: evaluation/eval_results.json")
    print(f"{'=' * 65}")


# ------------------------------------------------------------------
# Load and display previous results
# ------------------------------------------------------------------

def load_results() -> dict:
    """Loads the most recent evaluation results."""
    if not RESULTS_PATH.exists():
        return {"error": "No evaluation results found. Run evaluation first."}
    with open(RESULTS_PATH) as f:
        return json.load(f)


if __name__ == "__main__":
    run_evaluation(user_id="alice", verbose=True)