"""
clarifier.py
------------
Tool 5 — Query Clarifier

Detects ambiguous questions and generates targeted clarification questions BEFORE attempting SQL generation.

This prevents the agent from guessing wrong and returning misleading results to the user.

When to clarify:
    - Time period is vague ("recently", "last year", "this quarter")
    - Metric is ambiguous ("best", "top", "most")
    - Scope is unclear ("all products" vs "active products only")
    - Multiple interpretations exist

Functions:
    needs_clarification()    → detect if question is ambiguous
    generate_clarification() → produce specific clarifying questions
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
# Ambiguity patterns — rule-based fast check before LLM call
# ------------------------------------------------------------------

AMBIGUOUS_PATTERNS = [
    # Time ambiguity
    (r"\brecently\b",          "time_period",  "What time period counts as 'recently'?"),
    (r"\blast year\b",         "time_period",  "Do you mean the last 12 months or calendar year 2023?"),
    (r"\bthis year\b",         "time_period",  "Do you mean calendar year 2024 or the last 12 months?"),
    (r"\bthis quarter\b",      "time_period",  "Which quarter are you referring to?"),
    (r"\blast quarter\b",      "time_period",  "Which quarter — Q1, Q2, Q3, or Q4?"),
    (r"\brecent\b",            "time_period",  "What time range counts as 'recent'?"),

    # Metric ambiguity
    (r"\bbest\b",              "metric",       "What defines 'best' — revenue, quantity sold, or profit margin?"),
    (r"\btop\b",               "metric",       "Top by what metric — revenue, volume, or number of orders?"),
    (r"\bmost popular\b",      "metric",       "Popular by units sold or by number of orders?"),
    (r"\bworst\b",             "metric",       "Worst by what measure — lowest revenue or fewest orders?"),
    (r"\bperforming\b",        "metric",       "How do you define performance — revenue or order count?"),

    # Scope ambiguity
    (r"\ball\b",               "scope",        "Should discontinued products/cancelled orders be included?"),
    (r"\bactive\b",            "scope",        "What defines 'active' — ordered in last 90 days?"),
    (r"\bcurrent\b",           "scope",        "Does 'current' mean today or this month?"),
]


# ------------------------------------------------------------------
# Tool 5A: needs_clarification()
# ------------------------------------------------------------------

def needs_clarification(question: str) -> dict:
    """
    Quickly checks if a question contains ambiguous terms.
    Uses rule-based pattern matching — no LLM call needed.

    Args:
        question: The user's natural language question.

    Returns:
        dict with:
        {
            "needs_clarification": True/False,
            "ambiguities": [
                {"type": "time_period", "hint": "What time period counts as recently?"},
                ...
            ],
            "confidence": "high|low"   # high = definitely ambiguous, low = borderline
        }
    """
    question_lower = question.lower()
    ambiguities    = []
    seen_types     = set()

    for pattern, ambiguity_type, hint in AMBIGUOUS_PATTERNS:
        if re.search(pattern, question_lower):
            # Only report one ambiguity per type
            if ambiguity_type not in seen_types:
                ambiguities.append({
                    "type": ambiguity_type,
                    "hint": hint,
                })
                seen_types.add(ambiguity_type)

    if not ambiguities:
        return {
            "needs_clarification": False,
            "ambiguities":         [],
            "confidence":          "high",
        }

    return {
        "needs_clarification": True,
        "ambiguities":         ambiguities,
        "confidence":          "high" if len(ambiguities) >= 2 else "low",
    }


# ------------------------------------------------------------------
# Tool 5B: generate_clarification()
# ------------------------------------------------------------------

def generate_clarification(question: str, ambiguities: list) -> dict:
    """
    Generates specific, friendly clarification questions for the user.
    Uses LLM to produce natural, context-aware questions.

    Args:
        question:    The original ambiguous question.
        ambiguities: List of ambiguity dicts from needs_clarification().

    Returns:
        dict with:
        {
            "success": True,
            "clarification_message": "To answer accurately, I need a bit more detail...",
            "questions": [
                {
                    "question": "What time period are you asking about?",
                    "options":  ["Last 30 days", "Last 90 days", "Year 2024", "All time"]
                },
                ...
            ]
        }
    """

    ambiguity_summary = "\n".join(
        f"- {a['type']}: {a['hint']}" for a in ambiguities
    )

    prompt = f"""A user asked this database question:
"{question}"

The following ambiguities were detected:
{ambiguity_summary}

Generate a friendly clarification message that:
1. Acknowledges their question positively
2. Explains briefly why clarification helps
3. Asks 1-2 focused questions with clear answer options

Respond ONLY with valid JSON in this exact format:
{{
    "clarification_message": "Brief friendly intro (1 sentence)",
    "questions": [
        {{
            "question": "Specific question text",
            "options": ["Option 1", "Option 2", "Option 3"]
        }}
    ]
}}

Keep options to 3-4 maximum. Be concise and business-friendly.
Nothing else. No markdown. Just the JSON.
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        data    = json.loads(cleaned)

        return {
            "success":               True,
            "clarification_message": data.get("clarification_message", ""),
            "questions":             data.get("questions", []),
        }

    except Exception as e:
        # Fallback: use rule-based hints if LLM fails
        return {
            "success":               True,
            "clarification_message": "To give you the most accurate answer, I need a bit more detail.",
            "questions": [
                {
                    "question": a["hint"],
                    "options":  ["Please specify"]
                }
                for a in ambiguities[:2]
            ],
        }


# ------------------------------------------------------------------
# Quick self-test
# ------------------------------------------------------------------

if __name__ == "__main__":

    test_questions = [
        # (description, question, expect_clarification)
        ("Clear question",
         "Who are the top 5 customers by total revenue in 2024?",
         False),

        ("Ambiguous time",
         "What were our best selling products recently?",
         True),

        ("Ambiguous metric + time",
         "Show me the top performing employees last quarter",
         True),

        ("Ambiguous scope",
         "List all products",
         True),

        ("Clear aggregation",
         "How many orders were placed in January 2024?",
         False),
    ]

    print("=" * 60)
    print("CLARIFIER TESTS")
    print("=" * 60)

    for desc, question, expect_clarification in test_questions:
        print(f"\n{'─' * 60}")
        print(f"TEST     : {desc}")
        print(f"QUESTION : {question}")
        print(f"{'─' * 60}")

        # Step 1: Check if clarification needed
        check = needs_clarification(question)
        status = "✅" if check["needs_clarification"] == expect_clarification else "❌"
        print(f"{status} Needs clarification: {check['needs_clarification']} (expected: {expect_clarification})")

        if check["needs_clarification"]:
            print(f"   Ambiguities: {[a['type'] for a in check['ambiguities']]}")

            # Step 2: Generate clarification questions
            clarification = generate_clarification(question, check["ambiguities"])
            if clarification["success"]:
                print(f"   Message: {clarification['clarification_message']}")
                for q in clarification["questions"]:
                    print(f"   Q: {q['question']}")
                    print(f"      Options: {q['options']}")