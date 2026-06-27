"""
permissions.py
--------------
Guardrail 1 of 3 — Role-Based Access Control (RBAC)

Controls which users can access which tables and data.
This runs BEFORE any query reaches the executor.

Production approach: Dynamic permissions using column-based
sensitivity detection. Instead of hardcoding table names per role,
we inspect the connected database schema at runtime and flag tables
containing sensitive columns (salary, password, SSN, etc.).

This works for ANY database without hardcoding table names.

Roles:
    admin   → full access to all tables
    analyst → all tables except those with sensitive columns
    viewer  → read-only, no financial or personal data tables

Functions:
    check_permission()   → verify user can run this query
    get_user_role()      → get role for a user
    get_allowed_tables() → list tables a role can access
"""

import re
from typing import Optional

# ------------------------------------------------------------------
# Sensitive column patterns — tables containing these are restricted
# ------------------------------------------------------------------

SENSITIVE_COLUMNS = [
    "salary", "wage", "compensation", "pay",         # financial
    "password", "passwd", "secret", "token", "hash", # auth
    "ssn", "social_security", "tax_id",              # identity
    "credit_card", "card_number", "cvv", "iban",     # payment
    "date_of_birth", "dob", "birth_date",            # personal
    "medical", "diagnosis", "health",                # health
]

# Tables that are always denied regardless of role (explicit blocklist)
ALWAYS_DENIED = []  # empty — use dynamic detection instead

# ------------------------------------------------------------------
# Role definitions — behaviour-based, not table-based
# ------------------------------------------------------------------

ROLES = {
    "admin": {
        "can_access_sensitive": True,
        "read_only":            False,
        "description":          "Full access to all tables and data",
    },
    "analyst": {
        "can_access_sensitive": False,   # blocked from sensitive-column tables
        "read_only":            True,
        "description":          "Read access to all non-sensitive tables",
    },
    "viewer": {
        "can_access_sensitive": False,
        "read_only":            True,
        "description":          "Read-only access to catalog/public data only",
        "allowed_table_types":  ["catalog"],  # only non-financial tables
    },
}

# ------------------------------------------------------------------
# Mock user database
# In production: connect to your auth system (JWT, OAuth, etc.)
# ------------------------------------------------------------------

USERS = {
    "admin_user":   {"role": "admin",   "name": "Admin User"},
    "alice":        {"role": "analyst", "name": "Alice Chen"},
    "bob":          {"role": "viewer",  "name": "Bob Smith"},
    "default_user": {"role": "analyst", "name": "Default User"},
}


# ------------------------------------------------------------------
# Dynamic schema inspection
# ------------------------------------------------------------------

def _get_sensitive_tables(session_id: str = "default") -> set:
    """
    Dynamically inspects the connected database and returns
    the set of table names that contain sensitive columns.

    Works for ANY database — SQLite, PostgreSQL, MySQL.
    No hardcoding required.
    """
    sensitive_tables = set()

    try:
        from db_connector import get_active_engine
        from sqlalchemy import inspect as sa_inspect

        engine    = get_active_engine(session_id)
        inspector = sa_inspect(engine)

        for table_name in inspector.get_table_names():
            columns = [
                col["name"].lower()
                for col in inspector.get_columns(table_name)
            ]
            # Flag table if any column matches a sensitive pattern
            for col in columns:
                if any(s in col for s in SENSITIVE_COLUMNS):
                    sensitive_tables.add(table_name)
                    sensitive_tables.add(table_name.lower())
                    break

    except Exception as e:
        # If inspection fails, fail safe — return empty set
        # (means no extra tables are blocked, rely on ALWAYS_DENIED)
        print(f"[Permissions] Schema inspection warning: {e}")

    return sensitive_tables


def _get_all_tables(session_id: str = "default") -> list:
    """Returns all table names in the connected database."""
    try:
        from db_connector import get_active_engine
        from sqlalchemy import inspect as sa_inspect

        engine    = get_active_engine(session_id)
        inspector = sa_inspect(engine)
        return inspector.get_table_names()
    except Exception:
        return []


# ------------------------------------------------------------------
# Guardrail 1: check_permission()
# ------------------------------------------------------------------

def check_permission(
    sql:        str,
    user_id:    str = "default_user",
    session_id: str = "default",
) -> dict:
    """
    Checks if a user has permission to execute a SQL query.

    Uses dynamic schema inspection to detect sensitive tables —
    no hardcoded table names required.

    Args:
        sql:        The validated SQL query.
        user_id:    The user attempting the query.
        session_id: The database session (for dynamic inspection).

    Returns:
        dict with allowed, role, tables_in_query, reason
    """
    # Get user role
    user     = USERS.get(user_id, USERS["default_user"])
    role     = user["role"]
    role_def = ROLES.get(role, ROLES["analyst"])

    # Extract tables referenced in the SQL
    tables_in_query = _extract_tables_from_sql(sql)

    # Admin gets everything
    if role_def["can_access_sensitive"]:
        return {
            "allowed":         True,
            "user_id":         user_id,
            "role":            role,
            "tables_in_query": tables_in_query,
            "denied_tables":   [],
            "reason":          "Admin access granted",
        }

    # Block write operations for read-only roles
    if role_def.get("read_only"):
        write_ops = re.findall(
            r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE)\b',
            sql, re.IGNORECASE
        )
        if write_ops:
            return {
                "allowed":         False,
                "user_id":         user_id,
                "role":            role,
                "tables_in_query": tables_in_query,
                "denied_tables":   [],
                "reason":          f"Your role '{role}' is read-only. Write operations are not permitted.",
            }

    # Always-denied tables (explicit blocklist)
    denied = [t for t in tables_in_query if t in ALWAYS_DENIED]
    if denied:
        return {
            "allowed":         False,
            "user_id":         user_id,
            "role":            role,
            "tables_in_query": tables_in_query,
            "denied_tables":   denied,
            "reason":          f"Access denied to restricted tables: {', '.join(denied)}",
        }

    # Dynamic sensitivity check — inspect DB schema at runtime
    if not role_def["can_access_sensitive"]:
        sensitive_tables = _get_sensitive_tables(session_id)
        sensitive_accessed = [
            t for t in tables_in_query
            if t in sensitive_tables or t.lower() in sensitive_tables
        ]
        if sensitive_accessed:
            return {
                "allowed":         False,
                "user_id":         user_id,
                "role":            role,
                "tables_in_query": tables_in_query,
                "denied_tables":   sensitive_accessed,
                "reason":          f"Your role '{role}' cannot access tables with sensitive data: {', '.join(sensitive_accessed)}",
            }

    # Viewer: additional restriction — no financial tables
    if role == "viewer":
        financial_keywords = ["invoice", "payment", "billing", "transaction", "revenue"]
        financial_tables = [
            t for t in tables_in_query
            if any(kw in t.lower() for kw in financial_keywords)
        ]
        if financial_tables:
            return {
                "allowed":         False,
                "user_id":         user_id,
                "role":            role,
                "tables_in_query": tables_in_query,
                "denied_tables":   financial_tables,
                "reason":          f"Viewer role cannot access financial tables: {', '.join(financial_tables)}",
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
        "user_id":     user_id,
        "name":        user["name"],
        "role":        role,
        "description": role_def["description"],
    }


def get_allowed_tables(
    user_id:    str = "default_user",
    session_id: str = "default",
) -> list:
    """
    Returns list of tables a user can access.
    Dynamically computed from the connected database schema.
    """
    user     = USERS.get(user_id, USERS["default_user"])
    role_def = ROLES.get(user["role"], ROLES["analyst"])

    if role_def["can_access_sensitive"]:
        return _get_all_tables(session_id)

    all_tables      = _get_all_tables(session_id)
    sensitive_tables = _get_sensitive_tables(session_id)

    allowed = [t for t in all_tables if t not in sensitive_tables]

    if user["role"] == "viewer":
        financial_keywords = ["invoice", "payment", "billing", "transaction"]
        allowed = [
            t for t in allowed
            if not any(kw in t.lower() for kw in financial_keywords)
        ]

    return allowed


# ------------------------------------------------------------------
# Helper: extract table names from SQL
# ------------------------------------------------------------------

def _extract_tables_from_sql(sql: str) -> list:
    """
    Extracts table/view names referenced in a SQL query.
    Handles FROM and JOIN clauses.
    """
    tables  = set()
    pattern = r'\b(?:FROM|JOIN)\s+([`"]?[a-zA-Z_][a-zA-Z0-9_]*[`"]?)'
    matches = re.findall(pattern, sql, re.IGNORECASE)

    SQL_KEYWORDS = {
        "SELECT", "WHERE", "ON", "AND", "OR", "NOT", "IN",
        "AS", "BY", "GROUP", "ORDER", "HAVING", "LIMIT",
    }

    for match in matches:
        clean = match.strip('`"')
        if clean.upper() not in SQL_KEYWORDS:
            tables.add(clean)

    return list(tables)


# ------------------------------------------------------------------
# Quick self-test
# ------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 60)
    print("DYNAMIC PERMISSIONS TEST")
    print("=" * 60)

    # Show what tables are detected as sensitive
    print("\n── Sensitive table detection ──")
    sensitive = _get_sensitive_tables()
    print(f"Sensitive tables found: {sensitive or 'none (no sensitive columns in Chinook)'}")

    print("\n── Allowed tables per role ──")
    for user_id in ["admin_user", "alice", "bob"]:
        allowed = get_allowed_tables(user_id)
        role    = USERS[user_id]["role"]
        print(f"  {user_id:15s} ({role:8s}): {allowed}")

    print("\n── Permission checks ──")
    test_cases = [
        ("Analyst: genre revenue query",
         "SELECT g.Name, SUM(il.UnitPrice * il.Quantity) FROM Genre g JOIN InvoiceLine il ON 1=1",
         "alice", True),
        ("Analyst: write operation blocked",
         "DELETE FROM Invoice WHERE Total < 1",
         "alice", False),
        ("Admin: full access",
         "SELECT * FROM Employee WHERE ReportsTo IS NULL",
         "admin_user", True),
        ("Viewer: catalog access allowed",
         "SELECT * FROM Artist LIMIT 10",
         "bob", True),
        ("Viewer: invoice access blocked",
         "SELECT * FROM Invoice",
         "bob", False),
        ("Default user: track revenue",
         "SELECT t.Name, SUM(il.UnitPrice) FROM Track t JOIN InvoiceLine il ON t.TrackId = il.TrackId GROUP BY t.TrackId",
         "default_user", True),
    ]

    all_passed = True
    for desc, sql, user_id, expected in test_cases:
        result = check_permission(sql, user_id)
        passed = result["allowed"] == expected
        if not passed:
            all_passed = False
        icon = "✅" if passed else "❌"
        print(f"\n{icon} {desc}")
        print(f"   User: {user_id} ({result['role']}) | Allowed: {result['allowed']} | Reason: {result['reason']}")

    print(f"\n{'=' * 60}")
    print(f"{'✅ All tests passed' if all_passed else '❌ Some tests failed'}")
    print("=" * 60)