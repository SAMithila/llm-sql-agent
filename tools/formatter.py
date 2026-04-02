"""
formatter.py
------------
Tool 6 — Response Formatter

Takes raw query results and converts them into clear,
plain English responses that non-technical users can understand.

This is the last step in the pipeline — the agent's "voice."

Functions:
    format_response()    → convert raw results to plain English
    format_error()       → convert errors to friendly messages
    format_no_results()  → handle empty result sets gracefully
"""

import os
import json
import re
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL  = "gpt-4o"


# ------------------------------------------------------------------
# Tool 6A: format_response()
# ------------------------------------------------------------------

def format_response(
    question:         str,
    sql:              str,
    columns:          list,
    rows:             list,
    execution_ms:     int,
    truncated:        bool  = False,
    explanation:      str   = "",
    assumptions:      str   = "",
) -> dict:
    """
    Converts raw query results into a plain English response.

    Args:
        question:     The original user question.
        sql:          The SQL that was executed.
        columns:      Column names from the result.
        rows:         Data rows from the result.
        execution_ms: Query execution time in milliseconds.
        truncated:    Whether results were capped at row limit.
        explanation:  SQL explanation from sql_generator.
        assumptions:  Assumptions made during SQL generation.

    Returns:
        dict with:
        {
            "success":       True,
            "summary":       "Plain English answer to the question",
            "key_insights":  ["Insight 1", "Insight 2"],
            "data_table":    {"columns": [...], "rows": [...]},
            "metadata":      {"execution_ms": 42, "row_count": 5, ...}
        }
    """

    # Handle empty results
    if not rows:
        return format_no_results(question)

    # Build data preview for LLM (max 10 rows to keep prompt lean)
    preview_rows = rows[:10]
    data_preview = _build_data_preview(columns, preview_rows)

    prompt = f"""A user asked this business question:
"{question}"

The database returned these results:
{data_preview}

Total rows returned: {len(rows)}
{"Note: Results were truncated at 100 rows maximum." if truncated else ""}
{"SQL assumption: " + assumptions if assumptions else ""}

Write a clear, concise business response that:
1. Directly answers their question in 1-2 sentences
2. Highlights 2-3 key insights from the data
3. Uses specific numbers from the results
4. Sounds like a helpful data analyst, not a robot

Respond ONLY with valid JSON in this exact format:
{{
    "summary": "Direct answer to their question (1-2 sentences with key numbers)",
    "key_insights": [
        "Specific insight 1 with actual numbers",
        "Specific insight 2 with actual numbers"
    ]
}}

Nothing else. No markdown. Just the JSON.
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )

        raw     = response.choices[0].message.content.strip()
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        data    = json.loads(cleaned)

        return {
            "success":      True,
            "summary":      data.get("summary", ""),
            "key_insights": data.get("key_insights", []),
            "data_table":   {"columns": columns, "rows": rows},
            "metadata": {
                "execution_ms": execution_ms,
                "row_count":    len(rows),
                "truncated":    truncated,
                "sql":          sql,
            },
        }

    except Exception as e:
        # Fallback: return structured data without LLM summary
        return {
            "success":      True,
            "summary":      f"Query returned {len(rows)} result(s).",
            "key_insights": [],
            "data_table":   {"columns": columns, "rows": rows},
            "metadata": {
                "execution_ms": execution_ms,
                "row_count":    len(rows),
                "truncated":    truncated,
                "sql":          sql,
                "warning":      f"Summary generation failed: {str(e)}",
            },
        }


# ------------------------------------------------------------------
# Tool 6B: format_error()
# ------------------------------------------------------------------

def format_error(question: str, error: str, stage: str) -> dict:
    """
    Converts a pipeline error into a friendly user message.

    Args:
        question: The original user question.
        error:    The technical error message.
        stage:    Where in the pipeline the error occurred.

    Returns:
        dict with a user-friendly error message.
    """

    # Map technical errors to friendly messages
    friendly_messages = {
        "validation":  "I couldn't safely generate a query for that question. Could you rephrase it?",
        "execution":   "The query ran into an issue. This might be a complex question — try breaking it into smaller parts.",
        "timeout":     "That query took too long to run. Try adding more specific filters (like a date range or specific category).",
        "permission":  "You don't have access to that data. Please contact your administrator.",
        "generation":  "I had trouble understanding that question. Could you be more specific?",
    }

    message = friendly_messages.get(
        stage,
        "Something went wrong. Please try rephrasing your question."
    )

    return {
        "success":       False,
        "error_message": message,
        "stage":         stage,
        "technical":     error,   # Logged internally, not shown to user
    }


# ------------------------------------------------------------------
# Tool 6C: format_no_results()
# ------------------------------------------------------------------

def format_no_results(question: str) -> dict:
    """
    Handles the case where a valid query returns zero rows.
    This is not an error — it's a real answer.

    Args:
        question: The original user question.

    Returns:
        dict with a friendly no-results message.
    """
    return {
        "success":      True,
        "summary":      "No results found for your question. The data may not exist for the criteria specified.",
        "key_insights": [
            "Try broadening your filters (wider date range, different category)",
            "Double-check the spelling of any names or IDs you specified",
        ],
        "data_table":   {"columns": [], "rows": []},
        "metadata":     {"row_count": 0},
    }


# ------------------------------------------------------------------
# Helper: build readable data preview for LLM prompt
# ------------------------------------------------------------------

def _build_data_preview(columns: list, rows: list) -> str:
    """Formats data as a simple text table for the LLM prompt."""
    if not rows:
        return "No data returned."

    header = " | ".join(str(col) for col in columns)
    lines  = [header, "-" * len(header)]

    for row in rows:
        lines.append(" | ".join(str(val) for val in row))

    return "\n".join(lines)


# ------------------------------------------------------------------
# Quick self-test
# ------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 60)
    print("FORMATTER TESTS")
    print("=" * 60)

    # Test 1: Format real query results
    print("\n── TEST 1: Top products by revenue ──")
    result = format_response(
        question     = "What are the top 5 products by revenue?",
        sql          = "SELECT product_name, total_revenue FROM product_sales_summary ORDER BY total_revenue DESC LIMIT 5",
        columns      = ["product_name", "total_revenue"],
        rows         = [
            ["Sir Rodney's Marmalade", 35170.2],
            ["Mishi Kobe Niku",        33028.5],
            ["Carnarvon Tigers",       23050.0],
            ["Northwoods Cranberry",   15842.0],
            ["Queso Manchego",         14489.4],
        ],
        execution_ms = 2,
        truncated    = False,
    )

    if result["success"]:
        print(f"✅ Summary      : {result['summary']}")
        for insight in result["key_insights"]:
            print(f"   Insight      : {insight}")
        print(f"   Row count    : {result['metadata']['row_count']}")
        print(f"   Execution ms : {result['metadata']['execution_ms']}")
    else:
        print(f"❌ {result}")

    # Test 2: Format error
    print("\n── TEST 2: Error formatting ──")
    error_result = format_error(
        question = "Delete all orders",
        error    = "Safety check failed: Query must start with SELECT",
        stage    = "validation",
    )
    print(f"✅ Error message : {error_result['error_message']}")
    print(f"   Stage        : {error_result['stage']}")

    # Test 3: No results
    print("\n── TEST 3: No results ──")
    no_result = format_no_results("Show orders from 1990")
    print(f"✅ Summary       : {no_result['summary']}")
    for insight in no_result["key_insights"]:
        print(f"   Insight      : {insight}")

    print("\n" + "=" * 60)
    print("✅ All formatter tests complete")
    print("=" * 60)