"""
test_agent.py
-------------
Integration tests for the full agent pipeline.

These tests run real queries through the complete agent
and verify end-to-end behavior.

Note: Requires OPENAI_API_KEY to be set.
Skip with: pytest tests/ -k "not test_agent"
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Skip all tests in this file if no API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)

from agent.graph  import run_query
from agent.state  import AgentState


class TestAgentPipeline:

    # ── Easy queries ────────────────────────────────────────────

    def test_simple_count_query(self):
        state = run_query("How many orders do we have in total?")
        assert state.execution_success is True
        assert state.final_response["success"] is True
        assert state.execution_result["row_count"] == 1

    def test_list_categories(self):
        state = run_query("List all product categories")
        assert state.execution_success is True
        assert state.execution_result["row_count"] == 8

    def test_date_filter_query(self):
        state = run_query("How many orders were placed in 2024?")
        assert state.execution_success is True
        assert state.execution_result["rows"][0][0] == 109

    # ── Medium queries ──────────────────────────────────────────

    def test_top_customers_query(self):
        state = run_query("Who are the top 5 customers by total revenue?")
        assert state.execution_success is True
        assert state.execution_result["row_count"] == 5

    def test_revenue_by_category(self):
        state = run_query("What is the total revenue by product category?")
        assert state.execution_success is True
        assert state.execution_result["row_count"] == 8

    # ── Clarification ───────────────────────────────────────────

    def test_ambiguous_question_triggers_clarification(self):
        state = run_query("What were our best selling products recently?")
        assert state.needs_clarification is True
        assert state.clarification_response is not None

    def test_clear_question_skips_clarification(self):
        state = run_query("How many orders do we have?")
        assert state.needs_clarification is False

    # ── Guardrails ──────────────────────────────────────────────

    def test_permission_denied_for_viewer(self):
        state = run_query("Show me all customer contact details", user_id="bob")
        assert state.guardrails_passed is False
        assert state.error_stage == "permission"

    def test_admin_can_access_all(self):
        state = run_query("How many employees do we have?", user_id="admin_user")
        assert state.execution_success is True

    # ── Agent state ─────────────────────────────────────────────

    def test_trace_is_populated(self):
        state = run_query("How many orders do we have?")
        assert len(state.trace) > 0
        node_names = [t["node"] for t in state.trace]
        assert "clarify" in node_names
        assert "schema" in node_names
        assert "generate" in node_names
        assert "validate" in node_names
        assert "execute" in node_names
        assert "format" in node_names

    def test_sql_is_generated(self):
        state = run_query("How many customers do we have?")
        assert state.generated_sql is not None
        assert state.generated_sql.strip().upper().startswith("SELECT")

    def test_final_response_has_summary(self):
        state = run_query("List all product categories")
        assert state.final_response is not None
        assert "summary" in state.final_response
        assert len(state.final_response["summary"]) > 0

    def test_zero_retries_on_clear_question(self):
        state = run_query("How many orders do we have in total?")
        assert state.retry_count == 0