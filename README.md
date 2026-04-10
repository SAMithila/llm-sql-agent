# NL→DB Agent

> A deterministic agentic system for secure natural language database interaction with validation, guardrails, and observability layers.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-teal)
![Accuracy](https://img.shields.io/badge/Accuracy-96%25-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Tests](https://img.shields.io/badge/Tests-75%20passed-brightgreen)

**Live Demo:** https://nl-db-agent-qfsbi8vgngsfa5qpwepcmb.streamlit.app

**Live API:** https://nl-db-agent-140623834959.us-central1.run.app/docs

---

## The Problem

Most employees can't access their own company's data without filing a ticket and waiting days for the data team to respond. The bottleneck isn't the data — it's access.

> *"Last month I watched someone spend 45 minutes trying to get a single number. He knew the data existed. He knew which database it was in. He just couldn't get to it."*

This project is the answer to that problem.

---

## What It Does

Ask any business question in plain English. Get a direct answer — no SQL knowledge required.

```
"Who are our top 5 customers by revenue?"
→ Chop-suey Chinese leads with $27,026.94, followed by Berglunds snabbköp at $22,946.56...

"What percentage of orders were cancelled?"
→ 7% of orders were cancelled (14 out of 200 total orders)

"Which products have never been ordered?"
→ Query returned 0 results — all products have been ordered at least once
```

---

## Architecture

This is not a naive Text-to-SQL wrapper. It is a **controlled, deterministic enterprise agent** with explicit decision points, safety layers, and observability.

```
User Question
      ↓
┌─────────────────────────────────────────────────┐
│                  LangGraph Agent                 │
│                                                  │
│  [Clarify] → [Schema] → [Generate] → [Validate] │
│                              ↑______________|    │
│                           (retry loop, max 3)    │
│                                                  │
│              ↓ (if valid)                        │
│         [Guardrails] → [Execute] → [Format]      │
└─────────────────────────────────────────────────┘
      ↓
Plain English Answer + Key Insights
```

### 7 Agent Nodes

| Node | Responsibility |
|------|---------------|
| Clarify | Detects ambiguous questions, asks for clarification |
| Schema | Retrieves relevant tables before SQL generation |
| Generate | GPT-4o converts question → SQL at temperature=0 |
| Validate | Syntax + safety + complexity check (blocks bad SQL) |
| Guardrails | RBAC + rate limits + injection detection |
| Execute | Read-only, row-capped, timeout-protected execution |
| Format | Converts raw results to plain English insights |

### 6 Tools

```python
schema_inspector.py   # get_schema(), search_schema(), get_table_sample()
sql_generator.py      # generate_sql() — only LLM call in the pipeline
validator.py          # validate_sql(), complexity_score()
executor.py           # execute_query() — read-only, 100 row cap, 10s timeout
clarifier.py          # needs_clarification(), generate_clarification()
formatter.py          # format_response(), format_error(), format_no_results()
```

### 3 Guardrail Layers

```python
permissions.py   # Role-based access control (admin/analyst/viewer/guest)
limits.py        # Rate limiting (50 queries/hour), query length, row caps
safety.py        # SQL injection, UNION attacks, exfiltration pattern detection
```

---

## Evaluation Results

Benchmarked against 25 categorized queries across 4 difficulty tiers.

```
Overall accuracy  : 96%  (24/25)
Retry rate        : 0%
Avg latency       : 4,580ms (GPT-4o API)

Easy           : 100%  ██████████  (8/8)
Medium         : 100%  ██████████  (8/8)
Hard           : 100%  ██████████  (6/6)
Clarification  :  67%  ██████      (2/3)
```

**Failure analysis:** C003 *"Which products are doing well?"* — vague metric pattern
not in keyword list. Fix: add `"doing well"` to `AMBIGUOUS_PATTERNS`.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent framework | LangGraph |
| LLM | GPT-4o (temperature=0) |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL (AWS RDS) |
| Backend API | FastAPI |
| Frontend | Streamlit |
| Deployment | AWS EC2 |
| Observability | Custom JSON trace logger |

---

## Project Structure

```
nl-db-agent/
├── agent/
│   ├── graph.py              # LangGraph state machine (7 nodes)
│   ├── state.py              # Agent state schema
│   └── run_agent.py          # End-to-end test runner
├── tools/
│   ├── schema_inspector.py   # Tool 1: database schema retrieval
│   ├── sql_generator.py      # Tool 2: LLM SQL generation
│   ├── validator.py          # Tool 3: syntax + safety validation
│   ├── executor.py           # Tool 4: safe query execution
│   ├── clarifier.py          # Tool 5: ambiguity detection
│   └── formatter.py          # Tool 6: plain English responses
├── guardrails/
│   ├── permissions.py        # RBAC — 4 role tiers
│   ├── limits.py             # Rate limits + resource caps
│   └── safety.py             # Injection + exfiltration detection
├── observability/
│   ├── tracer.py             # JSON trace logger
│   ├── traces/               # Saved agent run traces
│   └── run_with_tracing.py   # Observable agent runner
├── evaluation/
│   ├── benchmark_queries.json # 25 queries across 4 tiers
│   ├── metrics.py             # Evaluation framework
│   └── eval_results.json      # Latest benchmark results
├── api/
│   └── main.py               # FastAPI backend (5 endpoints)
├── ui/
│   └── app.py                # Streamlit frontend
├── db/
│   ├── schema.sql            # Northwind database schema
│   ├── seed_data.py          # Reproducible seed (random.seed(42))
│   └── dev.db                # SQLite dev database
├── MISTAKES.md               # Real bugs caught and fixed
├── AWS_DEPLOYMENT.md         # AWS deployment guide
├── Dockerfile                # Container for AWS EC2
└── requirements.txt
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/SAMithila/nl-db-agent.git
cd nl-db-agent
pip install -r requirements.txt
```

### 2. Set up environment

```bash
cp .env.example .env
# Add your OpenAI API key to .env
```

### 3. Seed the database

```bash
python db/seed_data.py
```

### 4. Run the agent (terminal)

```bash
python -m agent.run_agent
```

### 5. Run with API + UI

```bash
# Terminal 1
python api/main.py

# Terminal 2
streamlit run ui/app.py
```

Open `http://localhost:8501`

### 6. Run evaluation

```bash
python -m evaluation.metrics
```

---

## Key Engineering Decisions

**Why LangGraph over LangChain?**
LangGraph gives explicit state machine control — every node, every transition, every decision point is visible and auditable. Enterprise systems need deterministic, traceable behavior. LangGraph provides this; LangChain's agent executor does not.

**Why temperature=0 for SQL generation?**
SQL is deterministic by nature. A question about revenue should return the same SQL every time. Temperature=0 eliminates randomness from the most critical step in the pipeline.

**Why validate before guardrails?**
Validation catches syntax errors early, before spending resources on permission checks. Fast failures are cheaper than slow ones.

**Why a retry loop with error context?**
Instead of failing silently, the agent passes the SQL error back to the LLM for self-correction. This is how production systems recover from transient failures without human intervention.

---

## Real Bugs Caught

See `MISTAKES.md` for full details.

**Bug 1: LLM hallucinating view columns**
GPT-4o treated the `order_revenue` view as a base table and tried to access `oi.unit_price` — a column that doesn't exist in the view. Fixed by adding explicit view column descriptions to the system prompt and updating schema keyword mapping.

**Lesson:** Schema context quality directly determines SQL quality. Views must be described with their actual columns — the LLM cannot infer view structure from the name alone.


---

## About

Built as a capstone portfolio project targeting senior AI/ML engineering roles.
Part of a 4-project portfolio demonstrating production-grade AI systems engineering.

**Portfolio:** github.com/SAMithila
