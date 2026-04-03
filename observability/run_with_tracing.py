"""
run_with_tracing.py
-------------------
Agent Runner with Full Observability

Runs queries through the agent and saves every trace to disk.
Use this instead of run_agent.py for production-like runs.

Usage:
    python observability/run_with_tracing.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from agent.graph              import run_query
from observability.tracer     import save_trace, print_trace, load_trace, get_metrics_summary


def run_and_trace(question: str, user_id: str = "default_user") -> dict:
    """
    Runs a query and saves the full trace to disk.

    Args:
        question: Natural language question.
        user_id:  User making the request.

    Returns:
        The saved trace document.
    """
    print(f"\n🔍 Running: '{question}' (user: {user_id})")

    state     = run_query(question, user_id)
    filepath  = save_trace(state)
    trace_doc = load_trace(filepath)

    print_trace(trace_doc)
    print(f"📁 Trace saved: {filepath}")

    return trace_doc


if __name__ == "__main__":

    # Representative query set — covers all difficulty tiers
    queries = [
        # Easy
        ("alice", "How many orders do we have in total?"),
        ("alice", "List all product categories"),
        ("alice", "How many customers are from the UK?"),

        # Medium
        ("alice", "Who are the top 5 customers by total revenue?"),
        ("alice", "What is the total revenue by product category?"),
        ("alice", "How many orders were placed in 2024?"),

        # Hard
        ("alice", "Which employee processed the most orders?"),
        ("alice", "What is the average order value by country?"),

        # Clarification
        ("alice", "What were our best selling products recently?"),

        # Permission denied
        ("bob",   "Show me all customer contact details"),
    ]

    print("=" * 65)
    print("RUNNING AGENT WITH FULL OBSERVABILITY")
    print("=" * 65)

    for user_id, question in queries:
        run_and_trace(question, user_id)

    # Print metrics summary
    print(f"\n{'=' * 65}")
    print("METRICS SUMMARY")
    print(f"{'=' * 65}")
    metrics = get_metrics_summary()
    for key, value in metrics.items():
        print(f"  {key:25s} : {value}")