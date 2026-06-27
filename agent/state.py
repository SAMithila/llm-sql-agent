"""
state.py
--------
Agent State Schema

Defines the state object that flows through every node
in the LangGraph agent graph.

Every node reads from state and writes back to state.
This is the single source of truth for the entire agent run.

Phase 7 update: Added RAG fields for Agentic RAG support.
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
    question:    str  = ""
    user_id:     str  = "default_user"
    session_id:  str  = "default"

    # ── Phase 7: Routing ────────────────────────────────────────
    route:       str  = "SQL"       # "SQL" | "RAG" | "BOTH"
    route_reason: str = ""          # LLM's reasoning for the route
    sql_focus:   Optional[str] = None   # what SQL should find
    rag_focus:   Optional[str] = None   # what RAG should find

    # ── Clarification ───────────────────────────────────────────
    needs_clarification: bool       = False
    clarification_response: Optional[dict] = None

    # ── Schema ──────────────────────────────────────────────────
    schema_context: Optional[dict]  = None

    # ── SQL Generation ──────────────────────────────────────────
    generated_sql:   Optional[str]  = None
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
    execution_result:  Optional[dict] = None
    execution_success: bool           = False

    # ── Phase 7: RAG ────────────────────────────────────────────
    rag_context:   Optional[str]  = None   # formatted context string
    rag_chunks:    list           = field(default_factory=list)   # raw chunks
    rag_sources:   list           = field(default_factory=list)   # source docs cited
    rag_success:   bool           = False

    # ── Response ────────────────────────────────────────────────
    final_response: Optional[dict] = None

    # ── Pipeline metadata ───────────────────────────────────────
    error:        Optional[str]    = None
    error_stage:  Optional[str]    = None
    retry_count:  int              = 0
    max_retries:  int              = 3
    trace:        list             = field(default_factory=list)

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

    def needs_sql(self) -> bool:
        return self.route in ("SQL", "BOTH")

    def needs_rag(self) -> bool:
        return self.route in ("RAG", "BOTH")
