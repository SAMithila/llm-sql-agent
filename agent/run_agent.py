"""
run_agent.py
------------
Agent Runner

Simple script to test the full agent pipeline end-to-end.
Run this to verify everything is wired correctly.

Usage:
    python agent/run_agent.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from agent.graph import run_query


def print_result(state, question: str):
    """Pretty print agent results."""

    print(f"\n{'=' * 65}")
    print(f"QUESTION: {question}")
    print(f"{'=' * 65}")

    # Clarification needed
    if state.needs_clarification:
        print("⚠️  CLARIFICATION NEEDED")
        cr = state.clarification_response
        if cr:
            print(f"   {cr['clarification_message']}")
            for q in cr.get("questions", []):
                print(f"   Q: {q['question']}")
                print(f"      Options: {q['options']}")
        return

    # Error
    if state.final_response and not state.final_response.get("success"):
        print(f"❌ ERROR: {state.final_response.get('error_message')}")
        print(f"   Stage: {state.final_response.get('stage')}")
        return

    # Success
    if state.final_response and state.final_response.get("success"):
        print(f"✅ ANSWER: {state.final_response['summary']}")

        insights = state.final_response.get("key_insights", [])
        if insights:
            print("\n📊 KEY INSIGHTS:")
            for insight in insights:
                print(f"   • {insight}")

        metadata = state.final_response.get("metadata", {})
        print(f"\n⚙️  METADATA:")
        print(f"   Rows         : {metadata.get('row_count', 0)}")
        print(f"   Execution    : {metadata.get('execution_ms', 0)}ms")
        print(f"   Truncated    : {metadata.get('truncated', False)}")

        print(f"\n🔍 SQL USED:")
        print(f"   {state.generated_sql}")

    # Agent trace
    print(f"\n📍 AGENT TRACE:")
    for step in state.trace:
        print(f"   [{step['node']:12s}] {step['message']}")


if __name__ == "__main__":

    test_questions = [
        # Easy — single table
        ("alice",        "How many orders do we have in total?"),

        # Medium — join + aggregation
        ("alice",        "Who are the top 5 customers by total revenue?"),

        # Medium — date filter
        ("alice",        "How many orders were placed in 2024?"),

        # Ambiguous — should trigger clarification
        ("alice",        "What were our best selling products recently?"),

        # Permission test — viewer can't see customers
        ("bob",          "Show me all customer contact details"),

        # Hard — multi-table aggregation
        ("alice",        "What is the total revenue by product category?"),
    ]

    for user_id, question in test_questions:
        state = run_query(question, user_id=user_id)
        print_result(state, question)

    print(f"\n{'=' * 65}")
    print("✅ Agent pipeline test complete")
    print(f"{'=' * 65}")