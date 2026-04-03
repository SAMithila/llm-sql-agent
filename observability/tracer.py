"""
tracer.py
---------
Observability — Agent Trace Logger

Records every agent run with full detail:
- Every node visited
- SQL generated
- Validation results
- Guardrail decisions
- Execution stats
- Final response

Traces are saved to observability/traces/ as JSON files.
These are your interview artifacts — real evidence of the
agent reasoning through complex queries.

Functions:
    save_trace()     → save a completed agent run to disk
    load_trace()     → load a saved trace
    list_traces()    → list all saved traces
    print_trace()    → pretty print a trace to terminal
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime
from agent.state import AgentState

TRACES_DIR = Path(__file__).parent / "traces"
TRACES_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------------------
# save_trace()
# ------------------------------------------------------------------

def save_trace(state: AgentState) -> str:
    """
    Saves a completed agent run as a JSON trace file.

    Args:
        state: The final AgentState after a full agent run.

    Returns:
        Path to the saved trace file.
    """
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_q     = "".join(c if c.isalnum() else "_" for c in state.question[:40])
    filename   = f"{timestamp}_{safe_q}.json"
    filepath   = TRACES_DIR / filename

    # Build trace document
    trace_doc = {
        "metadata": {
            "timestamp":    datetime.now().isoformat(),
            "question":     state.question,
            "user_id":      state.user_id,
            "success":      state.execution_success,
            "had_error":    state.has_error(),
            "retry_count":  state.retry_count,
        },
        "pipeline": {
            "clarification_needed": state.needs_clarification,
            "schema_tables":        state.schema_context.get("relevant_tables", []) if state.schema_context else [],
            "generated_sql":        state.generated_sql,
            "sql_confidence":       state.sql_confidence,
            "sql_explanation":      state.sql_explanation,
            "sql_assumptions":      state.sql_assumptions,
            "validation_passed":    state.validation_passed,
            "guardrails_passed":    state.guardrails_passed,
            "execution_success":    state.execution_success,
        },
        "validation": state.validation_result,
        "guardrails": {
            "permissions": state.permission_result,
            "limits":      state.limits_result,
            "safety":      state.safety_result,
        },
        "execution": {
            "row_count":    state.execution_result["row_count"]    if state.execution_result else 0,
            "execution_ms": state.execution_result["execution_ms"] if state.execution_result else 0,
            "truncated":    state.execution_result["truncated"]    if state.execution_result else False,
            "columns":      state.execution_result["columns"]      if state.execution_result else [],
        },
        "response": {
            "summary":      state.final_response.get("summary", "")      if state.final_response else "",
            "key_insights": state.final_response.get("key_insights", []) if state.final_response else [],
        },
        "error": {
            "message": state.error,
            "stage":   state.error_stage,
        },
        "trace": state.trace,
    }

    with open(filepath, "w") as f:
        json.dump(trace_doc, f, indent=2, default=str)

    return str(filepath)


# ------------------------------------------------------------------
# load_trace()
# ------------------------------------------------------------------

def load_trace(filepath: str) -> dict:
    """Loads a saved trace from disk."""
    with open(filepath) as f:
        return json.load(f)


# ------------------------------------------------------------------
# list_traces()
# ------------------------------------------------------------------

def list_traces(limit: int = 20) -> list:
    """
    Lists saved traces, most recent first.

    Returns:
        List of dicts with filename, question, success, timestamp.
    """
    traces = []

    for filepath in sorted(TRACES_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            with open(filepath) as f:
                doc = json.load(f)
            traces.append({
                "filepath":  str(filepath),
                "filename":  filepath.name,
                "question":  doc["metadata"]["question"],
                "success":   doc["metadata"]["success"],
                "timestamp": doc["metadata"]["timestamp"],
                "user_id":   doc["metadata"]["user_id"],
                "retries":   doc["metadata"]["retry_count"],
            })
        except Exception:
            continue

    return traces


# ------------------------------------------------------------------
# print_trace()
# ------------------------------------------------------------------

def print_trace(trace_doc: dict) -> None:
    """
    Pretty prints a trace document to terminal.
    Useful for debugging and interviews.
    """
    meta = trace_doc["metadata"]
    pipe = trace_doc["pipeline"]
    exec_ = trace_doc["execution"]
    resp = trace_doc["response"]
    err  = trace_doc["error"]

    status = "✅ SUCCESS" if meta["success"] else "❌ FAILED"

    print(f"\n{'═' * 65}")
    print(f"{status} | {meta['timestamp']}")
    print(f"{'═' * 65}")
    print(f"Question  : {meta['question']}")
    print(f"User      : {meta['user_id']}")
    print(f"Retries   : {meta['retry_count']}")

    print(f"\n── Pipeline ──")
    print(f"  Clarification needed : {pipe['clarification_needed']}")
    print(f"  Schema tables        : {pipe['schema_tables']}")
    print(f"  SQL confidence       : {pipe['sql_confidence']}")
    print(f"  Validation passed    : {pipe['validation_passed']}")
    print(f"  Guardrails passed    : {pipe['guardrails_passed']}")
    print(f"  Execution success    : {pipe['execution_success']}")

    if pipe.get("generated_sql"):
        print(f"\n── SQL ──")
        print(f"  {pipe['generated_sql']}")

    if meta["success"]:
        print(f"\n── Result ──")
        print(f"  Rows         : {exec_['row_count']}")
        print(f"  Execution ms : {exec_['execution_ms']}")
        print(f"  Summary      : {resp['summary']}")
        for insight in resp.get("key_insights", []):
            print(f"  • {insight}")

    if err["message"]:
        print(f"\n── Error ──")
        print(f"  Stage   : {err['stage']}")
        print(f"  Message : {err['message']}")

    print(f"\n── Agent Steps ──")
    for step in trace_doc.get("trace", []):
        print(f"  [{step['node']:12s}] {step['message']}")

    print(f"{'═' * 65}")


# ------------------------------------------------------------------
# Metrics summary across all traces
# ------------------------------------------------------------------

def get_metrics_summary() -> dict:
    """
    Computes summary metrics across all saved traces.
    Useful for evaluation and observability dashboards.

    Returns:
        dict with success rate, avg execution time, retry rate.
    """
    traces = list_traces(limit=1000)

    if not traces:
        return {"error": "No traces found"}

    total        = len(traces)
    successful   = sum(1 for t in traces if t["success"])
    with_retries = sum(1 for t in traces if t["retries"] > 0)

    # Load full traces for execution time
    exec_times = []
    for t in traces[:50]:   # Sample last 50
        try:
            doc = load_trace(t["filepath"])
            ms  = doc["execution"]["execution_ms"]
            if ms > 0:
                exec_times.append(ms)
        except Exception:
            continue

    avg_exec_ms = round(sum(exec_times) / len(exec_times)) if exec_times else 0

    return {
        "total_queries":    total,
        "success_rate":     round(successful / total * 100, 1),
        "failure_rate":     round((total - successful) / total * 100, 1),
        "retry_rate":       round(with_retries / total * 100, 1),
        "avg_execution_ms": avg_exec_ms,
        "successful":       successful,
        "failed":           total - successful,
    }