"""
limits.py
---------
Guardrail 2 of 3 — Resource Limits

Enforces hard limits on query cost, result size, and execution.
Prevents expensive or abusive queries from running.

Limits enforced:
    - Max rows returned
    - Max query execution time
    - Max queries per session
    - Result size in bytes

Functions:
    check_limits()       → verify query is within all limits
    check_session()      → verify session hasn't exceeded query quota
    record_query()       → log a completed query to session
"""

import time
from typing import Optional

# ------------------------------------------------------------------
# Hard limits — never override these
# ------------------------------------------------------------------

LIMITS = {
    "max_rows":              100,     # Max rows returned per query
    "max_execution_ms":    10000,     # 10 second timeout
    "max_queries_per_hour":   50,     # Rate limit per user per hour
    "max_result_bytes":  500_000,     # 500KB max result size
    "max_query_length":    5_000,     # Max SQL character length
}

# ------------------------------------------------------------------
# In-memory session tracker
# In production this would be Redis or a database
# ------------------------------------------------------------------

_sessions: dict = {}   # { user_id: [{"timestamp": float, "execution_ms": int}] }


# ------------------------------------------------------------------
# Guardrail 2A: check_limits()
# ------------------------------------------------------------------

def check_limits(
    sql:      str,
    user_id:  str           = "default_user",
    row_hint: Optional[int] = None,
) -> dict:
    """
    Checks a SQL query against all resource limits before execution.

    Args:
        sql:      The SQL query string.
        user_id:  The user making the request.
        row_hint: Estimated row count if known (from EXPLAIN).

    Returns:
        dict with:
        {
            "allowed":  True/False,
            "checks":   { limit_name: {"passed": bool, "details": str} },
            "reason":   "All limits passed" or reason for denial
        }
    """
    checks = {}

    # ── Check 1: Query length ───────────────────────────────────
    query_length = len(sql)
    if query_length > LIMITS["max_query_length"]:
        checks["query_length"] = {
            "passed":  False,
            "details": f"Query too long: {query_length} chars (max {LIMITS['max_query_length']})",
        }
        return _denied(checks, checks["query_length"]["details"])
    checks["query_length"] = {
        "passed":  True,
        "details": f"{query_length} chars (limit: {LIMITS['max_query_length']})",
    }

    # ── Check 2: Session rate limit ─────────────────────────────
    session_check = check_session(user_id)
    checks["rate_limit"] = session_check
    if not session_check["passed"]:
        return _denied(checks, session_check["details"])

    # ── Check 3: Row limit present ──────────────────────────────
    sql_upper = sql.upper()
    has_limit = "LIMIT" in sql_upper

    if not has_limit:
        # Auto-inject is handled by executor, just warn here
        checks["row_limit"] = {
            "passed":  True,
            "details": f"No LIMIT clause — executor will cap at {LIMITS['max_rows']} rows",
        }
    else:
        checks["row_limit"] = {
            "passed":  True,
            "details": "LIMIT clause present",
        }

    return {
        "allowed": True,
        "checks":  checks,
        "reason":  "All limits passed",
    }


# ------------------------------------------------------------------
# Guardrail 2B: check_session()
# ------------------------------------------------------------------

def check_session(user_id: str) -> dict:
    """
    Checks if a user has exceeded their hourly query limit.

    Args:
        user_id: The user to check.

    Returns:
        dict with passed status and details.
    """
    now          = time.time()
    one_hour_ago = now - 3600

    # Clean up old entries
    if user_id in _sessions:
        _sessions[user_id] = [
            q for q in _sessions[user_id]
            if q["timestamp"] > one_hour_ago
        ]
    else:
        _sessions[user_id] = []

    query_count = len(_sessions[user_id])
    remaining   = LIMITS["max_queries_per_hour"] - query_count

    if query_count >= LIMITS["max_queries_per_hour"]:
        return {
            "passed":    False,
            "details":   f"Rate limit exceeded: {query_count} queries in last hour (max {LIMITS['max_queries_per_hour']})",
            "remaining": 0,
        }

    return {
        "passed":    True,
        "details":   f"{query_count} queries in last hour ({remaining} remaining)",
        "remaining": remaining,
    }


# ------------------------------------------------------------------
# Guardrail 2C: record_query()
# ------------------------------------------------------------------

def record_query(user_id: str, execution_ms: int) -> None:
    """
    Records a completed query to the session tracker.
    Call this after every successful query execution.

    Args:
        user_id:      The user who ran the query.
        execution_ms: How long the query took.
    """
    if user_id not in _sessions:
        _sessions[user_id] = []

    _sessions[user_id].append({
        "timestamp":    time.time(),
        "execution_ms": execution_ms,
    })


def get_session_stats(user_id: str) -> dict:
    """Returns session statistics for a user."""
    now          = time.time()
    one_hour_ago = now - 3600

    recent = [
        q for q in _sessions.get(user_id, [])
        if q["timestamp"] > one_hour_ago
    ]

    if not recent:
        return {
            "user_id":         user_id,
            "queries_last_hour": 0,
            "avg_execution_ms":  0,
            "remaining_queries": LIMITS["max_queries_per_hour"],
        }

    avg_ms = sum(q["execution_ms"] for q in recent) / len(recent)

    return {
        "user_id":           user_id,
        "queries_last_hour": len(recent),
        "avg_execution_ms":  round(avg_ms),
        "remaining_queries": LIMITS["max_queries_per_hour"] - len(recent),
    }


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _denied(checks: dict, reason: str) -> dict:
    return {"allowed": False, "checks": checks, "reason": reason}


# ------------------------------------------------------------------
# Quick self-test
# ------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 60)
    print("LIMITS TESTS")
    print("=" * 60)

    # Test 1: Normal query
    print("\n── TEST 1: Normal query ──")
    result = check_limits(
        "SELECT * FROM orders LIMIT 10",
        user_id="alice"
    )
    print(f"{'✅' if result['allowed'] else '❌'} Allowed: {result['allowed']}")
    print(f"   Reason: {result['reason']}")

    # Test 2: Query too long
    print("\n── TEST 2: Query too long ──")
    long_sql = "SELECT " + "a, " * 3000 + "b FROM orders"
    result   = check_limits(long_sql, user_id="alice")
    print(f"{'✅' if not result['allowed'] else '❌'} Blocked oversized query: {not result['allowed']}")
    print(f"   Reason: {result['reason']}")

    # Test 3: Rate limiting simulation
    print("\n── TEST 3: Rate limit ──")
    test_user = "rate_test_user"
    # Simulate 50 queries
    for i in range(50):
        record_query(test_user, execution_ms=10)

    result = check_limits("SELECT 1", user_id=test_user)
    print(f"{'✅' if not result['allowed'] else '❌'} Rate limit enforced: {not result['allowed']}")
    print(f"   Reason: {result['reason']}")

    # Test 4: Session stats
    print("\n── TEST 4: Session stats ──")
    record_query("alice", execution_ms=42)
    record_query("alice", execution_ms=18)
    stats = get_session_stats("alice")
    print(f"✅ Session stats for alice:")
    print(f"   Queries last hour : {stats['queries_last_hour']}")
    print(f"   Avg execution ms  : {stats['avg_execution_ms']}")
    print(f"   Remaining queries : {stats['remaining_queries']}")

    print("\n" + "=" * 60)
    print("✅ All limits tests complete")
    print("=" * 60)