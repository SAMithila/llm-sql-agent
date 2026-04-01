# NL→DB Agent
> 🚧 Currently building — work in progress

A deterministic agentic system that lets anyone query a database 
using plain English — no SQL knowledge required.

## The Problem
Most employees can't access their own company's data without filing 
a ticket and waiting days for the data team to respond.

## The Solution
A controlled AI agent that:
- Understands natural language questions
- Inspects the database schema automatically
- Generates and validates SQL safely
- Executes queries with guardrails
- Returns plain English answers

## Architecture
```
User Question → Planner Agent → Schema Inspector → SQL Generator 
→ Validator → Guardrails → Executor → Response Formatter
```

## Tech Stack
- **Agent framework**: LangGraph
- **LLM**: GPT-4o
- **Database**: SQLite (dev) → PostgreSQL (prod)
- **Backend**: FastAPI
- **Frontend**: Streamlit

## Project Status
- [x] Phase 1 — Database foundation (Northwind)
- [x] Phase 2 — Core tools (in progress)
- [ ] Phase 3 — Guardrails
- [ ] Phase 4 — LangGraph agent
- [ ] Phase 5 — Observability
- [ ] Phase 6 — Evaluation framework
- [ ] Phase 7 — API + UI

## Evaluation (coming in Phase 6)
Queries categorized into 3 tiers:
- Easy: single table, explicit filters
- Medium: joins, aggregations, date ranges  
- Hard: ambiguous intent, multi-step reasoning