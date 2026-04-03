"""
schema_inspector.py
-------------------
Tool 1 of 6 — Schema Inspector

Gives the agent a complete understanding of the database structure
BEFORE it attempts to generate any SQL.

The LLM should ALWAYS call get_schema() or search_schema() first.
Never generate SQL without knowing the schema.

Functions:
    get_schema()         → full schema of all tables
    search_schema()      → find relevant tables for a question
    get_table_sample()   → show example rows from a table
"""

import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "../db/dev.db")


def _get_connection() -> sqlite3.Connection:
    """Get a read-only database connection."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ------------------------------------------------------------------
# Tool 1A: get_schema()
# ------------------------------------------------------------------

def get_schema(table_name: Optional[str] = None) -> dict:
    """
    Returns the full database schema or a single table's schema.

    Args:
        table_name: Optional. If provided, returns only that table's schema.
                    If None, returns all tables.

    Returns:
        dict with structure:
        {
            "tables": {
                "orders": {
                    "columns": [
                        {"name": "order_id", "type": "INTEGER", "nullable": False, "primary_key": True},
                        ...
                    ],
                    "foreign_keys": [
                        {"column": "customer_id", "references_table": "customers", "references_column": "customer_id"},
                        ...
                    ],
                    "row_count": 200
                },
                ...
            },
            "views": ["order_revenue", "product_sales_summary"]
        }
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()

        # Get all tables or just the requested one
        if table_name:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
        else:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )

        tables = [row["name"] for row in cur.fetchall()]

        # Get views
        cur.execute("SELECT name FROM sqlite_master WHERE type='view'")
        views = [row["name"] for row in cur.fetchall()]

        schema = {"tables": {}, "views": views}

        for tbl in tables:
            # Column info
            cur.execute(f"PRAGMA table_info({tbl})")
            columns = []
            for col in cur.fetchall():
                columns.append({
                    "name":        col["name"],
                    "type":        col["type"],
                    "nullable":    not col["notnull"],
                    "primary_key": bool(col["pk"]),
                    "default":     col["dflt_value"],
                })

            # Foreign key info
            cur.execute(f"PRAGMA foreign_key_list({tbl})")
            foreign_keys = []
            for fk in cur.fetchall():
                foreign_keys.append({
                    "column":             fk["from"],
                    "references_table":   fk["table"],
                    "references_column":  fk["to"],
                })

            # Row count
            cur.execute(f"SELECT COUNT(*) as cnt FROM {tbl}")
            row_count = cur.fetchone()["cnt"]

            schema["tables"][tbl] = {
                "columns":      columns,
                "foreign_keys": foreign_keys,
                "row_count":    row_count,
            }

        conn.close()
        return {"success": True, "schema": schema}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ------------------------------------------------------------------
# Tool 1B: search_schema()
# ------------------------------------------------------------------

def search_schema(question: str) -> dict:
    """
    Finds the most relevant tables for a natural language question.
    Uses keyword matching against table names, column names, and descriptions.

    Args:
        question: The user's natural language question.

    Returns:
        dict with the most relevant tables and their schemas.

    Example:
        search_schema("What are the top selling products?")
        → returns schemas for: products, order_items, categories
    """

    # Keyword → table mapping (domain knowledge)
    TABLE_KEYWORDS = {
        "customers":   ["customer", "client", "buyer", "company", "contact", "who bought"],
        "orders":      ["order", "purchase", "sale", "bought", "transaction", "shipped", "pending"],
        "order_items": ["item", "line item", "product in order", "quantity", "discount", "revenue", "category"],
        "products":    ["product", "item", "goods", "stock", "inventory", "price", "sell"],
        "employees":   ["employee", "staff", "rep", "salesperson", "who processed", "manager"],
        "categories":  ["category", "type", "group", "kind", "segment"],
        "suppliers":   ["supplier", "vendor", "source", "manufacturer"],
    }

    # View keywords
    VIEW_KEYWORDS = {
        "order_revenue":          ["revenue", "total", "sales amount", "income", "earning"],
        "product_sales_summary":  ["top product", "best selling", "product revenue", "units sold"],
    }

    question_lower = question.lower()
    relevant_tables = set()
    relevant_views  = set()

    # Match tables
    for table, keywords in TABLE_KEYWORDS.items():
        if any(kw in question_lower for kw in keywords):
            relevant_tables.add(table)

    # Match views
    for view, keywords in VIEW_KEYWORDS.items():
        if any(kw in question_lower for kw in keywords):
            relevant_views.add(view)

    # Default: if nothing matched, return core tables
    if not relevant_tables:
        relevant_tables = {"orders", "order_items", "products", "customers"}

    # Get schemas for relevant tables
    result = {}
    for table in relevant_tables:
        table_schema = get_schema(table_name=table)
        if table_schema["success"]:
            result[table] = table_schema["schema"]["tables"][table]

    return {
        "success":         True,
        "question":        question,
        "relevant_tables": list(relevant_tables),
        "relevant_views":  list(relevant_views),
        "schemas":         result,
    }


# ------------------------------------------------------------------
# Tool 1C: get_table_sample()
# ------------------------------------------------------------------

def get_table_sample(table_name: str, limit: int = 3) -> dict:
    """
    Returns sample rows from a table so the agent understands
    the actual data format (date formats, ID formats, value ranges).

    Args:
        table_name: Name of the table to sample.
        limit:      Number of rows to return (max 5, default 3).

    Returns:
        dict with column names and sample rows.
    """
    limit = min(limit, 5)  # Hard cap — never return more than 5 sample rows

    try:
        conn = _get_connection()
        cur  = conn.cursor()

        cur.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,))
        rows    = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

        conn.close()

        return {
            "success":    True,
            "table":      table_name,
            "columns":    columns,
            "sample_rows": [dict(zip(columns, row)) for row in rows],
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ------------------------------------------------------------------
# Quick self-test
# ------------------------------------------------------------------

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("TEST 1: get_schema() — all tables")
    print("=" * 60)
    result = get_schema()
    if result["success"]:
        for tbl, info in result["schema"]["tables"].items():
            col_names = [c["name"] for c in info["columns"]]
            print(f"  {tbl:20s} | rows: {info['row_count']:4d} | columns: {col_names}")
        print(f"  Views: {result['schema']['views']}")
    else:
        print(f"  ERROR: {result['error']}")

    print("\n" + "=" * 60)
    print("TEST 2: search_schema() — 'top selling products'")
    print("=" * 60)
    result = search_schema("What are the top selling products by revenue?")
    if result["success"]:
        print(f"  Relevant tables : {result['relevant_tables']}")
        print(f"  Relevant views  : {result['relevant_views']}")
    else:
        print(f"  ERROR: {result['error']}")

    print("\n" + "=" * 60)
    print("TEST 3: get_table_sample() — customers")
    print("=" * 60)
    result = get_table_sample("customers", limit=3)
    if result["success"]:
        print(f"  Columns: {result['columns']}")
        for row in result["sample_rows"]:
            print(f"  {row}")
    else:
        print(f"  ERROR: {result['error']}")