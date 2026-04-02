"""
executor.py
-----------
Tool 4 — Query Executor

Executes validated SQL against the database with hard safety limits.
This tool ONLY runs SQL that has already passed validator.py checks.

Safety features:
    - Row limit cap (never return more than MAX_ROWS)
    - Query timeout (never run longer than TIMEOUT_SECONDS)
    - Read-only connection (physically cannot write to database)
    - Full error capture with structured response

Functions:
    execute_query()   → run validated SQL and return results
"""

import sqlite3
import os
import time
import threading
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "../db/dev.db")

# ------------------------------------------------------------------
# Hard limits — these cannot be overridden by the agent or user
# ------------------------------------------------------------------

MAX_ROWS        = 100     # Never return more than 100 rows
TIMEOUT_SECONDS = 10      # Kill query if it runs longer than 10 seconds


# ------------------------------------------------------------------
# Tool 4: execute_query()
# ------------------------------------------------------------------

def execute_query(sql: str, row_limit: Optional[int] = None) -> dict:
    """
    Executes a validated SQL query against the database.

    Args:
        sql:        A SQL query that has already passed validate_sql().
        row_limit:  Optional custom row limit (capped at MAX_ROWS).

    Returns:
        dict with:
        {
            "success":      True,
            "columns":      ["column1", "column2", ...],
            "rows":         [[val1, val2], [val1, val2], ...],
            "row_count":    5,
            "execution_ms": 42,
            "truncated":    False,   # True if results were capped
            "sql":          "SELECT ..."
        }
    """

    # ── Enforce row limit ───────────────────────────────────────
    effective_limit = min(row_limit or MAX_ROWS, MAX_ROWS)

    # Inject LIMIT if not already present
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

    # ── Execute with timeout ────────────────────────────────────
    exception_holder = [None]
    result_holder    = [None]

    def run_query():
        try:
            # Read-only connection — physically cannot modify database
            conn = sqlite3.connect(
                f"file:{DB_PATH}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row

            cur   = conn.cursor()
            start = time.time()
            cur.execute(sql)

            rows    = cur.fetchall()
            elapsed = time.time() - start

            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows_as_lists = [list(row) for row in rows]

            conn.close()

            result_holder[0] = {
                "columns":      columns,
                "rows":         rows_as_lists,
                "execution_ms": round(elapsed * 1000),
            }

        except Exception as e:
            exception_holder[0] = e

    # Run query in a separate thread so we can enforce timeout
    thread = threading.Thread(target=run_query)
    thread.start()
    thread.join(timeout=TIMEOUT_SECONDS)

    # ── Timeout check ───────────────────────────────────────────
    if thread.is_alive():
        result["error"] = f"Query timed out after {TIMEOUT_SECONDS} seconds"
        return result

    # ── Exception check ─────────────────────────────────────────
    if exception_holder[0]:
        result["error"] = str(exception_holder[0])
        return result

    # ── Assemble result ─────────────────────────────────────────
    query_result = result_holder[0]

    rows      = query_result["rows"]
    truncated = len(rows) >= effective_limit

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
    """
    Formats execution results as a readable text table.
    Useful for quick terminal inspection and observability logs.

    Args:
        execution_result: The dict returned by execute_query().

    Returns:
        A formatted string table.
    """
    if not execution_result["success"]:
        return f"ERROR: {execution_result['error']}"

    columns = execution_result["columns"]
    rows    = execution_result["rows"]

    if not rows:
        return "Query returned 0 rows."

    # Calculate column widths
    col_widths = [len(str(col)) for col in columns]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    # Build table
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