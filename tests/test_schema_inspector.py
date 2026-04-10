"""
test_schema_inspector.py
------------------------
Tests for tools/schema_inspector.py
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.schema_inspector import get_schema, search_schema, get_table_sample


class TestGetSchema:

    def test_returns_all_tables(self):
        result = get_schema()
        assert result["success"] is True
        tables = result["schema"]["tables"]
        expected = {"customers", "orders", "order_items", "products", "categories", "suppliers", "employees"}
        assert expected.issubset(set(tables.keys()))

    def test_returns_views(self):
        result = get_schema()
        views = result["schema"]["views"]
        assert "order_revenue" in views
        assert "product_sales_summary" in views

    def test_single_table_schema(self):
        result = get_schema(table_name="customers")
        assert result["success"] is True
        assert "customers" in result["schema"]["tables"]

    def test_table_has_columns(self):
        result = get_schema(table_name="orders")
        columns = [c["name"] for c in result["schema"]["tables"]["orders"]["columns"]]
        assert "order_id" in columns
        assert "customer_id" in columns
        assert "order_date" in columns

    def test_table_has_row_count(self):
        result = get_schema(table_name="orders")
        row_count = result["schema"]["tables"]["orders"]["row_count"]
        assert row_count == 200

    def test_table_has_foreign_keys(self):
        result = get_schema(table_name="orders")
        fk_columns = [fk["column"] for fk in result["schema"]["tables"]["orders"]["foreign_keys"]]
        assert "customer_id" in fk_columns

    def test_invalid_table_returns_empty(self):
        result = get_schema(table_name="nonexistent_table")
        assert result["success"] is True
        assert "nonexistent_table" not in result["schema"]["tables"]


class TestSearchSchema:

    def test_order_question_returns_orders(self):
        result = search_schema("How many orders were placed?")
        assert result["success"] is True
        assert "orders" in result["relevant_tables"]

    def test_product_question_returns_products(self):
        result = search_schema("What are the top selling products?")
        assert result["success"] is True
        assert "products" in result["relevant_tables"]

    def test_customer_question_returns_customers(self):
        result = search_schema("Who are our top customers?")
        assert result["success"] is True
        assert "customers" in result["relevant_tables"]

    def test_revenue_question_returns_view(self):
        result = search_schema("What is the total revenue?")
        assert result["success"] is True
        assert "order_revenue" in result["relevant_views"]

    def test_unknown_question_returns_defaults(self):
        result = search_schema("xyz abc 123")
        assert result["success"] is True
        assert len(result["relevant_tables"]) > 0


class TestGetTableSample:

    def test_returns_sample_rows(self):
        result = get_table_sample("customers", limit=3)
        assert result["success"] is True
        assert len(result["sample_rows"]) == 3

    def test_respects_limit(self):
        result = get_table_sample("orders", limit=2)
        assert len(result["sample_rows"]) <= 2

    def test_hard_cap_at_five(self):
        result = get_table_sample("orders", limit=10)
        assert len(result["sample_rows"]) <= 5

    def test_returns_correct_columns(self):
        result = get_table_sample("customers", limit=1)
        assert "customer_id" in result["columns"]
        assert "company_name" in result["columns"]

    def test_invalid_table_returns_error(self):
        result = get_table_sample("nonexistent_table")
        assert result["success"] is False
        assert "error" in result