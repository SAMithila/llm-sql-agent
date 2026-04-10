"""
test_executor.py
----------------
Tests for tools/executor.py
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.executor import execute_query, format_as_table


class TestExecuteQuery:

    # ── Successful queries ──────────────────────────────────────

    def test_simple_query_succeeds(self):
        result = execute_query("SELECT * FROM customers LIMIT 5")
        assert result["success"] is True
        assert result["row_count"] == 5

    def test_returns_correct_columns(self):
        result = execute_query("SELECT customer_id, company_name FROM customers LIMIT 1")
        assert "customer_id" in result["columns"]
        assert "company_name" in result["columns"]

    def test_count_query(self):
        result = execute_query("SELECT COUNT(*) as total FROM orders")
        assert result["success"] is True
        assert result["rows"][0][0] == 200

    def test_aggregation_query(self):
        result = execute_query(
            "SELECT status, COUNT(*) as cnt FROM orders GROUP BY status ORDER BY cnt DESC"
        )
        assert result["success"] is True
        assert result["row_count"] > 0

    def test_join_query(self):
        result = execute_query(
            """SELECT c.company_name, COUNT(o.order_id) as order_count
               FROM customers c
               JOIN orders o ON c.customer_id = o.customer_id
               GROUP BY c.customer_id LIMIT 5"""
        )
        assert result["success"] is True
        assert result["row_count"] == 5

    def test_view_query(self):
        result = execute_query(
            "SELECT * FROM order_revenue ORDER BY revenue DESC LIMIT 5"
        )
        assert result["success"] is True
        assert "revenue" in result["columns"]

    # ── Safety limits ───────────────────────────────────────────

    def test_row_limit_enforced(self):
        result = execute_query("SELECT * FROM order_items", row_limit=10)
        assert result["row_count"] <= 10

    def test_auto_limit_injected(self):
        result = execute_query("SELECT * FROM customers")
        assert result["row_count"] <= 100

    def test_truncated_flag_set(self):
        result = execute_query("SELECT * FROM order_items LIMIT 100")
        # order_items has 578 rows — truncated should be True
        assert result["truncated"] is True

    def test_not_truncated_for_small_results(self):
        result = execute_query("SELECT * FROM categories LIMIT 10")
        assert result["truncated"] is False

    # ── Metadata ────────────────────────────────────────────────

    def test_execution_ms_recorded(self):
        result = execute_query("SELECT COUNT(*) FROM orders")
        assert result["execution_ms"] >= 0

    def test_sql_preserved_in_result(self):
        sql = "SELECT * FROM customers LIMIT 3"
        result = execute_query(sql)
        assert result["sql"] is not None

    # ── Error handling ──────────────────────────────────────────

    def test_invalid_table_returns_error(self):
        result = execute_query("SELECT * FROM nonexistent_table")
        assert result["success"] is False
        assert result["error"] is not None

    def test_invalid_column_returns_error(self):
        result = execute_query("SELECT nonexistent_col FROM customers")
        assert result["success"] is False


class TestFormatAsTable:

    def test_formats_successful_result(self):
        result = execute_query("SELECT customer_id, company_name FROM customers LIMIT 3")
        table_str = format_as_table(result)
        assert "customer_id" in table_str
        assert "company_name" in table_str
        assert "3 row(s)" in table_str

    def test_formats_empty_result(self):
        result = {
            "success":   True,
            "columns":   [],
            "rows":      [],
            "row_count": 0,
            "execution_ms": 1,
            "truncated": False,
        }
        table_str = format_as_table(result)
        assert "0 rows" in table_str

    def test_formats_error_result(self):
        result = {
            "success": False,
            "error":   "Table not found",
        }
        table_str = format_as_table(result)
        assert "ERROR" in table_str