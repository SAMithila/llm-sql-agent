"""
executor.py
-----------
Tool 4 — Query Executor

Executes validated SQL against the database with hard safety limits.
This tool ONLY runs SQL that has already passed validator.py checks.

Safety features:
    - Row limit cap (never return more than MAX_ROWS)
    - Query timeout (never run longer than TIMEOUT_SECONDS)
    - Dynamic database connection via db_connector
    - Full error capture with structured response

Functions:
    execute_query()   → run validated SQL and return results
"""

import os
import sys
import time
import threading
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ------------------------------------------------------------------
# Hard limits — these cannot be overridden by the agent or user
# ------------------------------------------------------------------

MAX_ROWS        = 100
TIMEOUT_SECONDS = 10


# ------------------------------------------------------------------
# Tool 4: execute_query()
# ------------------------------------------------------------------

def execute_query(
    sql:        str,
    row_limit:  Optional[int] = None,
    session_id: str           = "default",
) -> dict:
    """
    Executes a validated SQL query against the database.

    Args:
        sql:        A SQL query that has already passed validate_sql().
        row_limit:  Optional custom row limit (capped at MAX_ROWS).
        session_id: Database session to use (from db_connector).

    Returns:
        dict with success, columns, rows, row_count, execution_ms, truncated, sql
    """
    from db_connector import get_active_engine
    from sqlalchemy import text as sa_text

    # ── Enforce row limit ───────────────────────────────────────
    effective_limit = min(row_limit or MAX_ROWS, MAX_ROWS)

    sql_upper = sql.strip().upper()
    if "LIMIT" not in sql_upper:
        sql = f"{sql.rstrip(';')} LIMIT {effective_limit}"

    result = {
        "success":      False,
        "columns":      [],
        "rows":         [],
        "row_count":    0,
        "execution_ms": 0,
        "truncated":    False,
        "sql":          sql,
        "error":        None,
    }

    exception_holder = [None]
    result_holder    = [None]

    def run_query():
        try:
            engine = get_active_engine(session_id)
            start  = time.time()

            with engine.connect() as conn:
                result_proxy = conn.execute(sa_text(sql))
                rows         = result_proxy.fetchall()
                elapsed      = time.time() - start
                columns      = list(result_proxy.keys())

            rows_as_lists = [list(row) for row in rows]

            result_holder[0] = {
                "columns":      columns,
                "rows":         rows_as_lists,
                "execution_ms": round(elapsed * 1000),
            }

        except Exception as e:
            exception_holder[0] = e

    # ── Run with timeout ────────────────────────────────────────
    thread = threading.Thread(target=run_query)
    thread.start()
    thread.join(timeout=TIMEOUT_SECONDS)

    if thread.is_alive():
        result["error"] = f"Query timed out after {TIMEOUT_SECONDS} seconds"
        return result

    if exception_holder[0]:
        result["error"] = str(exception_holder[0])
        return result

    query_result = result_holder[0]
    rows         = query_result["rows"]
    truncated    = len(rows) >= effective_limit

    result.update({
        "success":      True,
        "columns":      query_result["columns"],
        "rows":         rows[:effective_limit],
        "row_count":    len(rows[:effective_limit]),
        "execution_ms": query_result["execution_ms"],
        "truncated":    truncated,
        "error":        None,
    })

    return result


def format_as_table(execution_result: dict) -> str:
    """Formats execution results as a readable text table."""
    if not execution_result["success"]:
        return f"ERROR: {execution_result['error']}"

    columns = execution_result["columns"]
    rows    = execution_result["rows"]

    if not rows:
        return "Query returned 0 rows."

    col_widths = [len(str(col)) for col in columns]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    separator = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header    = "| " + " | ".join(str(col).ljust(col_widths[i]) for i, col in enumerate(columns)) + " |"

    lines = [separator, header, separator]
    for row in rows:
        line = "| " + " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)) + " |"
        lines.append(line)
    lines.append(separator)

    footer = f"\n{execution_result['row_count']} row(s) returned in {execution_result['execution_ms']}ms"
    if execution_result["truncated"]:
        footer += f" (truncated at {MAX_ROWS} rows)"

    return "\n".join(lines) + footer


# ------------------------------------------------------------------
# Quick self-test
# ------------------------------------------------------------------

if __name__ == "__main__":

    test_cases = [
        (
            "Simple: all customers",
            "SELECT customer_id, company_name, country FROM customers ORDER BY company_name",
        ),
        (
            "Aggregation: top 5 products by revenue",
            """SELECT product_name, category_name, total_revenue
               FROM product_sales_summary
               ORDER BY total_revenue DESC
               LIMIT 5""",
        ),
        (
            "Join: orders with customer names",
            """SELECT o.order_id, c.company_name, o.order_date, o.status
               FROM orders o
               JOIN customers c ON o.customer_id = c.customer_id
               ORDER BY o.order_date DESC
               LIMIT 5""",
        ),
        (
            "Count: orders by status",
            """SELECT status, COUNT(*) as order_count
               FROM orders
               GROUP BY status
               ORDER BY order_count DESC""",
        ),
    ]

    print("=" * 60)
    print("EXECUTOR TESTS")
    print("=" * 60)

    all_passed = True
    for desc, sql in test_cases:
        print(f"\n{'─' * 60}")
        print(f"TEST: {desc}")
        print(f"{'─' * 60}")

        result = execute_query(sql)

        if result["success"]:
            print(format_as_table(result))
        else:
            all_passed = False
            print(f"❌ ERROR: {result['error']}")

    print("\n" + "=" * 60)
    print(f"{'✅ All tests passed' if all_passed else '❌ Some tests failed'}")
    print("=" * 60)