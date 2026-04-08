"""
main.py
-------
FastAPI Backend — NL→DB Agent API

Exposes the agent as a REST API with:
    POST /query          → run a natural language query
    GET  /health         → health check
    GET  /schema         → get database schema
    GET  /metrics        → get evaluation metrics
    GET  /traces         → list recent agent traces

Designed for AWS deployment:
    - Environment-based configuration
    - CORS enabled for Streamlit frontend
    - Structured JSON responses
    - Request/response logging
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import time
from datetime import datetime

from agent.graph              import run_query
from observability.tracer     import save_trace, list_traces, get_metrics_summary
from tools.schema_inspector   import get_schema
from evaluation.metrics       import load_results


# ------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------

app = FastAPI(
    title       = "NL→DB Agent API",
    description = "Natural language to database query agent",
    version     = "1.0.0",
)

# CORS — allow Streamlit frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # Restrict in production
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ------------------------------------------------------------------
# Request/Response models
# ------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str
    user_id:  str = "default_user"

class QueryResponse(BaseModel):
    success:              bool
    question:             str
    answer:               Optional[str]    = None
    key_insights:         Optional[list]   = None
    sql:                  Optional[str]    = None
    row_count:            Optional[int]    = None
    execution_ms:         Optional[int]    = None
    needs_clarification:  bool             = False
    clarification:        Optional[dict]   = None
    error:                Optional[str]    = None
    trace_summary:        Optional[list]   = None
    timestamp:            str              = ""


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/health")
def health_check():
    """Health check endpoint for AWS load balancer."""
    return {
        "status":    "healthy",
        "timestamp": datetime.now().isoformat(),
        "version":   "1.0.0",
    }


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    """
    Main endpoint — run a natural language query through the agent.

    Request body:
        {
            "question": "Who are our top 5 customers?",
            "user_id":  "alice"
        }

    Returns structured response with answer, SQL, and metadata.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    start = time.time()

    try:
        state = run_query(request.question, request.user_id)

        # Save trace
        save_trace(state)

        elapsed_ms = round((time.time() - start) * 1000)

        # Clarification needed
        if state.needs_clarification:
            return QueryResponse(
                success             = False,
                question            = request.question,
                needs_clarification = True,
                clarification       = state.clarification_response,
                timestamp           = datetime.now().isoformat(),
            )

        # Error
        if not state.execution_success:
            return QueryResponse(
                success   = False,
                question  = request.question,
                error     = state.final_response.get("error_message") if state.final_response else state.error,
                timestamp = datetime.now().isoformat(),
            )

        # Success
        final    = state.final_response or {}
        exec_res = state.execution_result or {}

        return QueryResponse(
            success      = True,
            question     = request.question,
            answer       = final.get("summary", ""),
            key_insights = final.get("key_insights", []),
            sql          = state.generated_sql,
            row_count    = exec_res.get("row_count", 0),
            execution_ms = exec_res.get("execution_ms", 0),
            trace_summary = [
                {"node": t["node"], "message": t["message"]}
                for t in state.trace
            ],
            timestamp    = datetime.now().isoformat(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schema")
def schema():
    """Returns the full database schema."""
    result = get_schema()
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result["schema"]


@app.get("/metrics")
def metrics():
    """Returns the latest evaluation metrics."""
    return get_metrics_summary()


@app.get("/traces")
def traces(limit: int = 10):
    """Returns recent agent traces."""
    return {"traces": list_traces(limit=limit)}


# ------------------------------------------------------------------
# Run locally
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host    = "0.0.0.0",
        port    = int(os.getenv("PORT", 8000)),
        reload  = True,
    )