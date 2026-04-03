"""
graph.py
--------
LangGraph Agent Graph

The main agent orchestration layer.
Wires all tools and guardrails into a deterministic state machine.

Flow:
    START
      → clarify_node       (detect ambiguity)
      → schema_node        (get relevant schema)
      → generate_node      (LLM: question → SQL)
      → validate_node      (syntax + safety check)
      → guardrails_node    (RBAC + limits + safety scan)
      → execute_node       (run query)
      → format_node        (plain English response)
    END

Retry loop:
    validate_node → FAIL → generate_node (max 3 retries)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from typing import Literal
from langgraph.graph import StateGraph, START, END
from agent.state import AgentState

# Tools
from tools.schema_inspector import search_schema
from tools.sql_generator     import generate_sql
from tools.validator         import validate_sql
from tools.executor          import execute_query
from tools.clarifier         import needs_clarification, generate_clarification
from tools.formatter         import format_response, format_error

# Guardrails
from guardrails.permissions  import check_permission
from guardrails.limits       import check_limits, record_query
from guardrails.safety       import safety_check


# ------------------------------------------------------------------
# Node 1: Clarify
# ------------------------------------------------------------------

def clarify_node(state: AgentState) -> AgentState:
    """
    Checks if the question is ambiguous.
    If ambiguous, generates clarification questions and stops.
    If clear, passes through to schema retrieval.
    """
    state.add_trace("clarify", f"Checking question: '{state.question}'")

    check = needs_clarification(state.question)

    if check["needs_clarification"] and check["confidence"] == "high":
        clarification = generate_clarification(
            state.question,
            check["ambiguities"]
        )
        state.needs_clarification    = True
        state.clarification_response = clarification
        state.add_trace("clarify", f"Ambiguity detected: {[a['type'] for a in check['ambiguities']]}")
    else:
        state.needs_clarification = False
        state.add_trace("clarify", "Question is clear — proceeding")

    return state


# ------------------------------------------------------------------
# Node 2: Schema
# ------------------------------------------------------------------

def schema_node(state: AgentState) -> AgentState:
    """
    Retrieves relevant schema context for the question.
    The LLM needs this before generating SQL.
    """
    state.add_trace("schema", "Retrieving relevant schema")

    result = search_schema(state.question)

    if result["success"]:
        state.schema_context = result
        state.add_trace(
            "schema",
            f"Found relevant tables: {result['relevant_tables']}"
        )
    else:
        state.error       = f"Schema retrieval failed: {result.get('error')}"
        state.error_stage = "schema"
        state.add_trace("schema", f"ERROR: {state.error}")

    return state


# ------------------------------------------------------------------
# Node 3: Generate
# ------------------------------------------------------------------

def generate_node(state: AgentState) -> AgentState:
    """
    Calls GPT-4o to convert the question into SQL.
    On retry, passes the previous error for self-correction.
    """
    state.generation_attempt += 1
    state.add_trace("generate", f"Generating SQL (attempt {state.generation_attempt})")

    # Pass previous validation error for self-correction
    previous_error = None
    if state.retry_count > 0 and state.validation_result:
        previous_error = state.validation_result.get("error")

    result = generate_sql(
        question       = state.question,
        schema_context = state.schema_context,
        previous_error = previous_error,
        attempt        = state.generation_attempt,
    )

    if result["success"]:
        state.generated_sql   = result["sql"]
        state.sql_explanation = result["explanation"]
        state.sql_assumptions = result["assumptions"]
        state.sql_confidence  = result["confidence"]
        state.add_trace("generate", f"SQL generated (confidence: {result['confidence']})")
    else:
        state.error       = f"SQL generation failed: {result.get('error')}"
        state.error_stage = "generation"
        state.add_trace("generate", f"ERROR: {state.error}")

    return state


# ------------------------------------------------------------------
# Node 4: Validate
# ------------------------------------------------------------------

def validate_node(state: AgentState) -> AgentState:
    """
    Validates the generated SQL for syntax, safety, and complexity.
    On failure, increments retry counter for the generate node.
    """
    state.add_trace("validate", "Validating SQL")

    result = validate_sql(state.generated_sql)
    state.validation_result = result

    if result["valid"]:
        state.validation_passed = True
        complexity = result["checks"]["complexity"]
        state.add_trace(
            "validate",
            f"Valid — complexity: {complexity['score']}/10 ({complexity['tier']})"
        )
    else:
        state.validation_passed = False
        state.retry_count      += 1
        state.add_trace("validate", f"FAILED: {result['error']} (retry {state.retry_count}/{state.max_retries})")

    return state


# ------------------------------------------------------------------
# Node 5: Guardrails
# ------------------------------------------------------------------

def guardrails_node(state: AgentState) -> AgentState:
    """
    Runs all 3 guardrail checks in sequence:
    1. Permissions (RBAC)
    2. Limits (rate + size)
    3. Safety (injection + exfiltration)

    All 3 must pass before execution.
    """
    state.add_trace("guardrails", "Running guardrail checks")

    # Check 1: Permissions
    perm = check_permission(state.generated_sql, state.user_id)
    state.permission_result = perm
    if not perm["allowed"]:
        state.guardrails_passed = False
        state.error             = perm["reason"]
        state.error_stage       = "permission"
        state.add_trace("guardrails", f"PERMISSION DENIED: {perm['reason']}")
        return state

    # Check 2: Limits
    limits = check_limits(state.generated_sql, state.user_id)
    state.limits_result = limits
    if not limits["allowed"]:
        state.guardrails_passed = False
        state.error             = limits["reason"]
        state.error_stage       = "limits"
        state.add_trace("guardrails", f"LIMITS EXCEEDED: {limits['reason']}")
        return state

    # Check 3: Safety
    safety = safety_check(state.generated_sql, state.user_id)
    state.safety_result = safety
    if not safety["safe"]:
        state.guardrails_passed = False
        state.error             = safety["reason"]
        state.error_stage       = "safety"
        state.add_trace("guardrails", f"SAFETY BLOCKED: {safety['reason']}")
        return state

    state.guardrails_passed = True
    state.add_trace("guardrails", "All guardrails passed ✓")
    return state


# ------------------------------------------------------------------
# Node 6: Execute
# ------------------------------------------------------------------

def execute_node(state: AgentState) -> AgentState:
    """
    Executes the validated, guardrail-checked SQL against the database.
    Records the query for rate limiting.
    """
    state.add_trace("execute", "Executing query")

    result = execute_query(state.generated_sql)
    state.execution_result = result

    if result["success"]:
        state.execution_success = True
        record_query(state.user_id, result["execution_ms"])
        state.add_trace(
            "execute",
            f"Success — {result['row_count']} rows in {result['execution_ms']}ms"
        )
    else:
        state.execution_success = False
        state.error             = result["error"]
        state.error_stage       = "execution"
        state.add_trace("execute", f"ERROR: {result['error']}")

    return state


# ------------------------------------------------------------------
# Node 7: Format
# ------------------------------------------------------------------

def format_node(state: AgentState) -> AgentState:
    """
    Formats the results into a plain English response.
    Handles both success and error cases.
    """
    state.add_trace("format", "Formatting response")

    if state.has_error() or not state.execution_success:
        state.final_response = format_error(
            question = state.question,
            error    = state.error or "Unknown error",
            stage    = state.error_stage or "unknown",
        )
        state.add_trace("format", f"Error response formatted for stage: {state.error_stage}")
        return state

    exec_result = state.execution_result
    state.final_response = format_response(
        question     = state.question,
        sql          = state.generated_sql,
        columns      = exec_result["columns"],
        rows         = exec_result["rows"],
        execution_ms = exec_result["execution_ms"],
        truncated    = exec_result["truncated"],
        explanation  = state.sql_explanation,
        assumptions  = state.sql_assumptions,
    )

    state.add_trace("format", "Response formatted successfully")
    return state


# ------------------------------------------------------------------
# Routing functions — decide which node to go to next
# ------------------------------------------------------------------

def route_after_clarify(state: AgentState) -> Literal["schema", "end"]:
    """If clarification needed, stop. Otherwise continue."""
    if state.needs_clarification:
        return "end"
    return "schema"


def route_after_schema(state: AgentState) -> Literal["generate", "format"]:
    """If schema failed, go to format (error). Otherwise generate."""
    if state.has_error():
        return "format"
    return "generate"


def route_after_generate(state: AgentState) -> Literal["validate", "format"]:
    """If generation failed, go to format (error). Otherwise validate."""
    if state.has_error():
        return "format"
    return "validate"


def route_after_validate(state: AgentState) -> Literal["guardrails", "generate", "format"]:
    """
    If valid → guardrails.
    If invalid + retries remaining → back to generate.
    If invalid + no retries → format (error).
    """
    if state.validation_passed:
        return "guardrails"
    if state.can_retry():
        return "generate"
    return "format"


def route_after_guardrails(state: AgentState) -> Literal["execute", "format"]:
    """If guardrails passed → execute. Otherwise → format (error)."""
    if state.guardrails_passed:
        return "execute"
    return "format"


def route_after_execute(state: AgentState) -> Literal["format"]:
    """Always go to format after execution."""
    return "format"


# ------------------------------------------------------------------
# Build the graph
# ------------------------------------------------------------------

def build_graph() -> StateGraph:
    """
    Constructs and compiles the LangGraph agent graph.
    Returns a compiled graph ready to invoke.
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("clarify",    clarify_node)
    graph.add_node("schema",     schema_node)
    graph.add_node("generate",   generate_node)
    graph.add_node("validate",   validate_node)
    graph.add_node("guardrails", guardrails_node)
    graph.add_node("execute",    execute_node)
    graph.add_node("format",     format_node)

    # Add edges
    graph.add_edge(START, "clarify")

    graph.add_conditional_edges("clarify",    route_after_clarify,    {"schema": "schema",         "end": END})
    graph.add_conditional_edges("schema",     route_after_schema,     {"generate": "generate",     "format": "format"})
    graph.add_conditional_edges("generate",   route_after_generate,   {"validate": "validate",     "format": "format"})
    graph.add_conditional_edges("validate",   route_after_validate,   {"guardrails": "guardrails", "generate": "generate", "format": "format"})
    graph.add_conditional_edges("guardrails", route_after_guardrails, {"execute": "execute",       "format": "format"})
    graph.add_conditional_edges("execute",    route_after_execute,    {"format": "format"})

    graph.add_edge("format", END)

    return graph.compile()


# ------------------------------------------------------------------
# Convenience: run a single question
# ------------------------------------------------------------------

def run_query(question: str, user_id: str = "default_user") -> AgentState:
    """
    Run a natural language question through the full agent pipeline.

    Args:
        question: Plain English question about the database.
        user_id:  The user making the request.

    Returns:
        Final AgentState with all results and trace.
    """
    graph        = build_graph()
    initial_state = AgentState(question=question, user_id=user_id)
    final_state  = graph.invoke(initial_state)

    # LangGraph returns a dict — convert back to AgentState
    if isinstance(final_state, dict):
        state = AgentState(**final_state)
    else:
        state = final_state

    return state