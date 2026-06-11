"""
state.py
--------
Agent State Schema

Defines the state object that flows through every node
in the LangGraph agent graph.

Every node reads from state and writes back to state.
This is the single source of truth for the entire agent run.
"""

from typing import Optional, Any
from dataclasses import dataclass, field


@dataclass
class AgentState:
    """
    The state object passed between every node in the agent graph.
    Each field is populated as the agent progresses through the pipeline.
    """

    # ── Input ───────────────────────────────────────────────────
    question:    str  = ""          # Original user question
    user_id:     str  = "default_user"
    session_id:  str  = "default"


    # ── Clarification ───────────────────────────────────────────
    needs_clarification: bool       = False
    clarification_response: Optional[dict] = None

    # ── Schema ──────────────────────────────────────────────────
    schema_context: Optional[dict]  = None   # From schema_inspector

    # ── SQL Generation ──────────────────────────────────────────
    generated_sql:  Optional[str]   = None   # From sql_generator
    sql_explanation: str            = ""
    sql_assumptions: str            = ""
    sql_confidence:  str            = ""
    generation_attempt: int         = 0

    # ── Validation ──────────────────────────────────────────────
    validation_result: Optional[dict] = None
    validation_passed: bool           = False

    # ── Guardrails ──────────────────────────────────────────────
    permission_result: Optional[dict] = None
    limits_result:     Optional[dict] = None
    safety_result:     Optional[dict] = None
    guardrails_passed: bool           = False

    # ── Execution ───────────────────────────────────────────────
    execution_result: Optional[dict] = None
    execution_success: bool          = False

    # ── Response ────────────────────────────────────────────────
    final_response: Optional[dict]  = None

    # ── Pipeline metadata ───────────────────────────────────────
    error:        Optional[str]     = None
    error_stage:  Optional[str]     = None
    retry_count:  int               = 0
    max_retries:  int               = 3
    trace:        list              = field(default_factory=list)

    def add_trace(self, node: str, message: str) -> None:
        """Add a trace entry for observability."""
        import time
        self.trace.append({
            "node":      node,
            "message":   message,
            "timestamp": round(time.time(), 3),
        })

    def has_error(self) -> bool:
        return self.error is not None

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries