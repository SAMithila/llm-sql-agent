"""
app.py
------
Streamlit Frontend — NL→DB Agent UI

A clean interface for querying the database in plain English.
Connects to the FastAPI backend.

Run locally:
    streamlit run ui/app.py

For AWS deployment:
    Set API_URL environment variable to your EC2 endpoint
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import requests
import json
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

API_URL  = os.getenv("API_URL", "http://localhost:8000")
APP_TITLE = "NL→DB Agent"

# ------------------------------------------------------------------
# Page setup
# ------------------------------------------------------------------

st.set_page_config(
    page_title = APP_TITLE,
    page_icon  = "🔍",
    layout     = "wide",
)

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Settings")

    user_id = st.selectbox(
        "User Role",
        options = ["alice (analyst)", "bob (viewer)", "admin_user (admin)", "guest_user (guest)"],
        index   = 0,
    )
    user_id = user_id.split(" ")[0]

    st.divider()
    st.markdown("### 📊 Example Questions")

    examples = [
        "How many orders do we have in total?",
        "Who are the top 5 customers by revenue?",
        "What is the total revenue by product category?",
        "How many orders were placed in 2024?",
        "Which products have never been ordered?",
        "What percentage of orders were cancelled?",
    ]

    for example in examples:
        if st.button(example, use_container_width=True):
            st.session_state["question"] = example

    st.divider()

    # Health check
    try:
        resp = requests.get(f"{API_URL}/health", timeout=3)
        if resp.status_code == 200:
            st.success("🟢 API Connected")
        else:
            st.error("🔴 API Error")
    except Exception:
        st.warning("🟡 API Offline — Start with: python api/main.py")


# ------------------------------------------------------------------
# Main UI
# ------------------------------------------------------------------

st.title("🔍 NL→DB Agent")
st.caption("Ask any question about your business data in plain English.")

st.divider()

# Question input
question = st.text_input(
    "Your question",
    value       = st.session_state.get("question", ""),
    placeholder = "e.g. Who are our top 5 customers by revenue?",
    key         = "question_input",
)

col1, col2 = st.columns([1, 5])
with col1:
    run_button = st.button("Ask", type="primary", use_container_width=True)
with col2:
    show_sql   = st.checkbox("Show SQL", value=True)
    show_trace = st.checkbox("Show agent trace", value=False)

st.divider()

# ------------------------------------------------------------------
# Query execution
# ------------------------------------------------------------------

if run_button and question.strip():

    with st.spinner("Agent is thinking..."):
        try:
            response = requests.post(
                f"{API_URL}/query",
                json    = {"question": question, "user_id": user_id},
                timeout = 60,
            )
            data = response.json()

        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to API. Start it with: `python api/main.py`")
            st.stop()
        except Exception as e:
            st.error(f"Request failed: {str(e)}")
            st.stop()

    # ── Clarification needed ────────────────────────────────────
    if data.get("needs_clarification"):
        st.warning("⚠️ I need a bit more information to answer accurately.")
        clarification = data.get("clarification", {})

        if clarification:
            st.write(clarification.get("clarification_message", ""))
            for q in clarification.get("questions", []):
                st.write(f"**{q['question']}**")
                cols = st.columns(len(q["options"]))
                for i, option in enumerate(q["options"]):
                    if cols[i].button(option, key=f"opt_{i}"):
                        refined = f"{question} ({option})"
                        st.session_state["question"] = refined
                        st.rerun()

    # ── Error ───────────────────────────────────────────────────
    elif not data.get("success"):
        st.error(f"❌ {data.get('error', 'Something went wrong')}")

    # ── Success ─────────────────────────────────────────────────
    else:
        # Answer
        st.success("✅ " + data.get("answer", ""))

        # Key insights
        insights = data.get("key_insights", [])
        if insights:
            st.markdown("**Key Insights:**")
            for insight in insights:
                st.markdown(f"- {insight}")

        st.divider()

        # Metadata columns
        col1, col2, col3 = st.columns(3)
        col1.metric("Rows Returned",   data.get("row_count", 0))
        col2.metric("Execution Time",  f"{data.get('execution_ms', 0)}ms")
        col3.metric("Status",          "✅ Success")

        # SQL
        if show_sql and data.get("sql"):
            st.markdown("**Generated SQL:**")
            st.code(data["sql"], language="sql")

        # Agent trace
        if show_trace and data.get("trace_summary"):
            st.markdown("**Agent Trace:**")
            trace_df = pd.DataFrame(data["trace_summary"])
            st.dataframe(trace_df, use_container_width=True)


# ------------------------------------------------------------------
# Schema explorer (expander)
# ------------------------------------------------------------------

with st.expander("📋 Database Schema"):
    try:
        schema_resp = requests.get(f"{API_URL}/schema", timeout=5)
        if schema_resp.status_code == 200:
            schema_data = schema_resp.json()
            for table_name, table_info in schema_data.get("tables", {}).items():
                st.markdown(f"**{table_name}** ({table_info['row_count']} rows)")
                cols = [f"{c['name']} ({c['type']})" for c in table_info["columns"]]
                st.caption(" | ".join(cols))
        else:
            st.warning("Could not load schema")
    except Exception:
        st.warning("Start the API to view schema")


# ------------------------------------------------------------------
# Evaluation metrics (expander)
# ------------------------------------------------------------------

with st.expander("📈 Evaluation Metrics"):
    try:
        metrics_resp = requests.get(f"{API_URL}/metrics", timeout=5)
        if metrics_resp.status_code == 200:
            metrics = metrics_resp.json()
            if "total_queries" in metrics:
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Queries",    metrics.get("total_queries", 0))
                col2.metric("Success Rate",     f"{100 - metrics.get('failure_rate', 0)}%")
                col3.metric("Avg Latency",      f"{metrics.get('avg_execution_ms', 0)}ms")
        else:
            st.warning("Could not load metrics")
    except Exception:
        st.warning("Start the API to view metrics")