# MISTAKES.md

## Bug 1: LLM hallucinating view columns
**Date:** Phase 4

**Symptom:** "What is the total revenue by product category?" failed 3 retries

**Root cause:** LLM treated `order_revenue` view as a base table and tried to 
access `oi.unit_price` and `oi.product_id` which don't exist in the view

**Fix:** 
1. Added `order_items` to revenue keyword mapping in schema_inspector
2. Added explicit view column descriptions to sql_generator system prompt

**Lesson:** Views must be described with their actual columns in the schema 
context — the LLM cannot infer view structure from the name alone
