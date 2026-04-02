"""
permissions.py
--------------
Guardrail 1 of 3 — Role-Based Access Control (RBAC)

Controls which users can access which tables and data.
This runs BEFORE any query reaches the executor.

Roles:
    admin       → full access to all tables
    analyst     → read access, no salary/personal data
    viewer      → limited tables, no employee/financial data
    guest       → public data only (products, categories)

Functions:
    check_permission()   → verify user can run this query
    get_user_role()      → get role for a user
    get_allowed_tables() → list tables a role can access
"""

import re
from typing import Optional

# ------------------------------------------------------------------
# Role definitions — what each role can access
# ------------------------------------------------------------------

ROLES = {
    "admin": {
        "allowed_tables":    "*",           # All tables
        "denied_tables":     [],
        "description":       "Full access to all tables and data",
        "can_see_salaries":  True,
        "can_see_pii":       True,          # PII = personal contact info
    },
    "analyst": {
        "allowed_tables": [
            "orders", "order_items", "order_revenue",
            "products", "product_sales_summary",
            "categories", "suppliers", "customers",
        ],
        "denied_tables":     ["employees"],  # No salary data
        "description":       "Business analytics access, no HR data",
        "can_see_salaries":  False,
        "can_see_pii":       True,
    },
    "viewer": {
        "allowed_tables": [
            "orders", "order_items", "order_revenue",
            "products", "product_sales_summary",
            "categories",
        ],
        "denied_tables":     ["employees", "suppliers", "customers"],
        "description":       "Read-only access to sales and product data",
        "can_see_salaries":  False,
        "can_see_pii":       False,
    },
    "guest": {
        "allowed_tables":    ["products", "categories"],
        "denied_tables":     ["employees", "orders", "order_items", "customers", "suppliers"],
        "description":       "Public product catalog only",
        "can_see_salaries":  False,
        "can_see_pii":       False,
    },
}

# ------------------------------------------------------------------
# Mock user database
# In production this would connect to your auth system
# ------------------------------------------------------------------

USERS = {
    "admin_user":   {"role": "admin",   "name": "Admin User"},
    "alice":        {"role": "analyst", "name": "Alice Chen"},
    "bob":          {"role": "viewer",  "name": "Bob Smith"},
    "guest_user":   {"role": "guest",   "name": "Guest"},
    "default_user": {"role": "analyst", "name": "Default User"},
}


# ------------------------------------------------------------------
# Guardrail 1: check_permission()
# ------------------------------------------------------------------

def check_permission(
    sql:      str,
    user_id:  str = "default_user",
) -> dict:
    """
    Checks if a user has permission to execute a SQL query.
    Extracts table names from SQL and verifies against user's role.

    Args:
        sql:     The validated SQL query.
        user_id: The user attempting the query.

    Returns:
        dict with:
        {
            "allowed":        True/False,
            "user_id":        "alice",
            "role":           "analyst",
            "tables_in_query": ["orders", "customers"],
            "denied_tables":  [],
            "reason":         "Access granted" or reason for denial
        }
    """

    # Get user role
    user     = USERS.get(user_id, USERS["default_user"])
    role     = user["role"]
    role_def = ROLES[role]

    # Extract tables referenced in the SQL
    tables_in_query = _extract_tables_from_sql(sql)

    # Admin gets everything
    if role_def["allowed_tables"] == "*":
        return {
            "allowed":         True,
            "user_id":         user_id,
            "role":            role,
            "tables_in_query": tables_in_query,
            "denied_tables":   [],
            "reason":          "Admin access granted",
        }

    # Check each table against denied list
    denied = []
    for table in tables_in_query:
        if table in role_def["denied_tables"]:
            denied.append(table)
        elif table not in role_def["allowed_tables"]:
            denied.append(table)

    # Check for salary columns specifically
    if not role_def["can_see_salaries"]:
        if re.search(r"\bsalary\b", sql, re.IGNORECASE):
            return {
                "allowed":         False,
                "user_id":         user_id,
                "role":            role,
                "tables_in_query": tables_in_query,
                "denied_tables":   ["salary column"],
                "reason":          "Your role does not have access to salary data.",
            }

    if denied:
        return {
            "allowed":         False,
            "user_id":         user_id,
            "role":            role,
            "tables_in_query": tables_in_query,
            "denied_tables":   denied,
            "reason":          f"Access denied. Your role '{role}' cannot access: {', '.join(denied)}",
        }

    return {
        "allowed":         True,
        "user_id":         user_id,
        "role":            role,
        "tables_in_query": tables_in_query,
        "denied_tables":   [],
        "reason":          "Access granted",
    }


def get_user_role(user_id: str) -> dict:
    """Returns the role and permissions for a user."""
    user     = USERS.get(user_id, USERS["default_user"])
    role     = user["role"]
    role_def = ROLES[role]

    return {
        "user_id":        user_id,
        "name":           user["name"],
        "role":           role,
        "description":    role_def["description"],
        "allowed_tables": role_def["allowed_tables"],
        "denied_tables":  role_def["denied_tables"],
    }


def get_allowed_tables(user_id: str) -> list:
    """Returns list of tables a user can access."""
    user     = USERS.get(user_id, USERS["default_user"])
    role_def = ROLES[user["role"]]

    if role_def["allowed_tables"] == "*":
        return ["all tables"]
    return role_def["allowed_tables"]


# ------------------------------------------------------------------
# Helper: extract table names from SQL
# ------------------------------------------------------------------

def _extract_tables_from_sql(sql: str) -> list:
    """
    Extracts table/view names referenced in a SQL query.
    Handles FROM and JOIN clauses.
    """
    tables  = set()
    pattern = r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
    matches = re.findall(pattern, sql, re.IGNORECASE)

    for match in matches:
        # Exclude SQL keywords that might be matched
        if match.upper() not in ("SELECT", "WHERE", "ON", "AND", "OR"):
            tables.add(match.lower())

    return list(tables)


# ------------------------------------------------------------------
# Quick self-test
# ------------------------------------------------------------------

if __name__ == "__main__":

    test_cases = [
        # (description, sql, user_id, expected_allowed)
        (
            "Admin: full access",
            "SELECT * FROM employees WHERE salary > 70000",
            "admin_user",
            True,
        ),
        (
            "Analyst: allowed tables",
            "SELECT c.company_name, SUM(o.freight) FROM customers c JOIN orders o ON c.customer_id = o.customer_id",
            "alice",
            True,
        ),
        (
            "Analyst: denied employee table",
            "SELECT first_name, salary FROM employees",
            "alice",
            False,
        ),
        (
            "Viewer: allowed sales data",
            "SELECT * FROM orders LIMIT 10",
            "bob",
            True,
        ),
        (
            "Viewer: denied customers table",
            "SELECT * FROM customers",
            "bob",
            False,
        ),
        (
            "Guest: allowed products",
            "SELECT product_name, unit_price FROM products",
            "guest_user",
            True,
        ),
        (
            "Guest: denied orders",
            "SELECT * FROM orders",
            "guest_user",
            False,
        ),
    ]

    print("=" * 60)
    print("PERMISSIONS TESTS")
    print("=" * 60)

    all_passed = True
    for desc, sql, user_id, expected in test_cases:
        result = check_permission(sql, user_id)
        status = "✅" if result["allowed"] == expected else "❌"
        if result["allowed"] != expected:
            all_passed = False

        print(f"\n{status} {desc}")
        print(f"   User    : {user_id} ({result['role']})")
        print(f"   Allowed : {result['allowed']} (expected: {expected})")
        print(f"   Tables  : {result['tables_in_query']}")
        if not result["allowed"]:
            print(f"   Reason  : {result['reason']}")

    print("\n" + "=" * 60)
    print(f"{'✅ All tests passed' if all_passed else '❌ Some tests failed'}")
    print("=" * 60)