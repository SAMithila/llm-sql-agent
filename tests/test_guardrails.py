"""
test_guardrails.py
------------------
Tests for guardrails/permissions.py, limits.py, safety.py
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from guardrails.permissions import check_permission, get_user_role, get_allowed_tables
from guardrails.limits      import check_limits, record_query, get_session_stats, LIMITS
from guardrails.safety      import safety_check, scan_for_injection, scan_for_exfiltration


class TestPermissions:

    # ── Admin access ────────────────────────────────────────────

    def test_admin_can_access_employees(self):
        result = check_permission(
            "SELECT first_name, salary FROM employees",
            user_id="admin_user"
        )
        assert result["allowed"] is True

    def test_admin_can_access_all_tables(self):
        result = check_permission(
            "SELECT * FROM customers JOIN orders ON customers.customer_id = orders.customer_id",
            user_id="admin_user"
        )
        assert result["allowed"] is True

    # ── Analyst access ──────────────────────────────────────────

    def test_analyst_can_access_orders(self):
        result = check_permission(
            "SELECT * FROM orders LIMIT 10",
            user_id="alice"
        )
        assert result["allowed"] is True

    def test_analyst_blocked_from_salary(self):
        result = check_permission(
            "SELECT first_name, salary FROM employees",
            user_id="alice"
        )
        assert result["allowed"] is False

    def test_analyst_blocked_from_employees(self):
        result = check_permission(
            "SELECT * FROM employees",
            user_id="alice"
        )
        assert result["allowed"] is False

    # ── Viewer access ───────────────────────────────────────────

    def test_viewer_can_access_orders(self):
        result = check_permission(
            "SELECT * FROM orders LIMIT 5",
            user_id="bob"
        )
        assert result["allowed"] is True

    def test_viewer_blocked_from_customers(self):
        result = check_permission(
            "SELECT * FROM customers",
            user_id="bob"
        )
        assert result["allowed"] is False

    # ── Guest access ────────────────────────────────────────────

    def test_guest_can_access_products(self):
        result = check_permission(
            "SELECT product_name, unit_price FROM products",
            user_id="guest_user"
        )
        assert result["allowed"] is True

    def test_guest_blocked_from_orders(self):
        result = check_permission(
            "SELECT * FROM orders",
            user_id="guest_user"
        )
        assert result["allowed"] is False

    # ── Response structure ──────────────────────────────────────

    def test_result_has_required_fields(self):
        result = check_permission("SELECT * FROM products", user_id="alice")
        assert "allowed" in result
        assert "role" in result
        assert "tables_in_query" in result
        assert "reason" in result

    def test_get_user_role_returns_role(self):
        result = get_user_role("alice")
        assert result["role"] == "analyst"
        assert result["user_id"] == "alice"

    def test_get_allowed_tables_for_guest(self):
        tables = get_allowed_tables("guest_user")
        assert "products" in tables
        assert "categories" in tables


class TestLimits:

    def test_normal_query_allowed(self):
        result = check_limits("SELECT * FROM orders LIMIT 10", user_id="test_limits_1")
        assert result["allowed"] is True

    def test_oversized_query_blocked(self):
        long_sql = "SELECT " + "a, " * 3000 + "b FROM orders"
        result   = check_limits(long_sql, user_id="test_limits_2")
        assert result["allowed"] is False
        assert "too long" in result["reason"].lower()

    def test_rate_limit_enforced(self):
        user = "rate_limit_test_user_unique"
        for i in range(LIMITS["max_queries_per_hour"]):
            record_query(user, execution_ms=10)
        result = check_limits("SELECT 1", user_id=user)
        assert result["allowed"] is False
        assert "rate limit" in result["reason"].lower()

    def test_session_stats_tracked(self):
        user = "stats_test_user_unique"
        record_query(user, execution_ms=100)
        record_query(user, execution_ms=200)
        stats = get_session_stats(user)
        assert stats["queries_last_hour"] >= 2
        assert stats["avg_execution_ms"] > 0

    def test_result_has_required_fields(self):
        result = check_limits("SELECT 1", user_id="test_fields")
        assert "allowed" in result
        assert "checks" in result
        assert "reason" in result


class TestSafety:

    # ── Clean queries pass ──────────────────────────────────────

    def test_clean_select_passes(self):
        result = safety_check(
            "SELECT product_name, unit_price FROM products ORDER BY unit_price DESC LIMIT 10"
        )
        assert result["safe"] is True

    def test_clean_join_passes(self):
        result = safety_check(
            """SELECT c.company_name, COUNT(o.order_id)
               FROM customers c JOIN orders o ON c.customer_id = o.customer_id
               GROUP BY c.customer_id"""
        )
        assert result["safe"] is True

    # ── Injection patterns blocked ──────────────────────────────

    def test_union_injection_blocked(self):
        result = safety_check("SELECT * FROM products UNION SELECT password FROM users")
        assert result["safe"] is False

    def test_always_true_blocked(self):
        result = safety_check("SELECT * FROM orders WHERE 1=1")
        assert result["safe"] is False

    def test_schema_enumeration_blocked(self):
        result = safety_check("SELECT * FROM sqlite_master")
        assert result["safe"] is False

    def test_sleep_injection_blocked(self):
        result = safety_check("SELECT * FROM orders WHERE SLEEP(5)")
        assert result["safe"] is False

    # ── Exfiltration blocked ────────────────────────────────────

    def test_salary_extraction_blocked(self):
        result = safety_check("SELECT first_name, salary FROM employees")
        assert result["safe"] is False

    def test_password_extraction_blocked(self):
        result = safety_check("SELECT password FROM users")
        assert result["safe"] is False

    # ── Response structure ──────────────────────────────────────

    def test_result_has_required_fields(self):
        result = safety_check("SELECT * FROM products LIMIT 5")
        assert "safe" in result
        assert "checks" in result
        assert "reason" in result

    def test_scan_for_injection_clean(self):
        result = scan_for_injection("SELECT * FROM customers LIMIT 10")
        assert result["passed"] is True
        assert result["threat"] is None

    def test_scan_for_exfiltration_clean(self):
        result = scan_for_exfiltration("SELECT product_name FROM products")
        assert result["passed"] is True