"""
test_validator.py
-----------------
Tests for tools/validator.py
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.validator import validate_sql, complexity_score


class TestValidateSql:

    # ── Valid queries ───────────────────────────────────────────

    def test_simple_select_passes(self):
        result = validate_sql("SELECT * FROM customers LIMIT 10")
        assert result["valid"] is True

    def test_join_query_passes(self):
        sql = """SELECT c.company_name, COUNT(o.order_id)
                 FROM customers c
                 JOIN orders o ON c.customer_id = o.customer_id
                 GROUP BY c.customer_id LIMIT 10"""
        result = validate_sql(sql)
        assert result["valid"] is True

    def test_aggregation_passes(self):
        sql = "SELECT COUNT(*), SUM(freight) FROM orders"
        result = validate_sql(sql)
        assert result["valid"] is True

    # ── Safety checks ───────────────────────────────────────────

    def test_delete_blocked(self):
        result = validate_sql("DELETE FROM orders WHERE order_id = 1")
        assert result["valid"] is False
        assert "safety" in result["error"].lower()

    def test_drop_blocked(self):
        result = validate_sql("DROP TABLE customers")
        assert result["valid"] is False

    def test_insert_blocked(self):
        result = validate_sql("INSERT INTO orders VALUES (1, 2, 3)")
        assert result["valid"] is False

    def test_update_blocked(self):
        result = validate_sql("UPDATE orders SET status='Cancelled'")
        assert result["valid"] is False

    def test_sql_injection_blocked(self):
        result = validate_sql("SELECT * FROM orders; DROP TABLE orders--")
        assert result["valid"] is False

    def test_pragma_blocked(self):
        result = validate_sql("PRAGMA table_info(orders)")
        assert result["valid"] is False

    # ── Syntax checks ───────────────────────────────────────────

    def test_syntax_error_caught(self):
        result = validate_sql("SELECT * FORM customers")
        assert result["valid"] is False
        assert "syntax" in result["error"].lower()

    def test_invalid_column_caught(self):
        result = validate_sql("SELECT nonexistent_column FROM customers")
        assert result["valid"] is False

    # ── All 3 checks present ────────────────────────────────────

    def test_result_has_all_checks(self):
        result = validate_sql("SELECT * FROM customers LIMIT 5")
        assert "safety" in result["checks"]
        assert "syntax" in result["checks"]
        assert "complexity" in result["checks"]


class TestComplexityScore:

    def test_simple_query_low_score(self):
        result = complexity_score("SELECT * FROM customers LIMIT 10")
        assert result["score"] <= 3
        assert result["tier"] == "simple"

    def test_join_increases_score(self):
        sql = "SELECT * FROM orders JOIN customers ON orders.customer_id = customers.customer_id"
        result = complexity_score(sql)
        assert result["score"] > 1

    def test_aggregation_increases_score(self):
        sql = "SELECT COUNT(*), SUM(freight), AVG(freight) FROM orders GROUP BY status"
        result = complexity_score(sql)
        assert result["score"] > 2

    def test_complex_query_high_score(self):
        sql = """
            SELECT c.company_name, SUM(oi.unit_price * oi.quantity) as revenue
            FROM customers c
            JOIN orders o ON c.customer_id = o.customer_id
            JOIN order_items oi ON o.order_id = oi.order_id
            GROUP BY c.customer_id
            HAVING revenue > 1000
            ORDER BY revenue DESC
            LIMIT 10
        """
        result = complexity_score(sql)
        assert result["score"] >= 5
        assert result["tier"] in ("medium", "complex")

    def test_score_capped_at_ten(self):
        sql = """
            SELECT * FROM (
                SELECT * FROM (
                    SELECT COUNT(*), SUM(x), AVG(y), MAX(z)
                    FROM orders
                    JOIN customers ON orders.customer_id = customers.customer_id
                    JOIN order_items ON orders.order_id = order_items.order_id
                    JOIN products ON order_items.product_id = products.product_id
                    GROUP BY orders.order_id
                    HAVING COUNT(*) > 1
                )
            ) ORDER BY 1 LIMIT 10
        """
        result = complexity_score(sql)
        assert result["score"] <= 10