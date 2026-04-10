"""
conftest.py
-----------
Pytest configuration and shared fixtures.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="session")
def db_path():
    """Returns path to the test database."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "dev.db")


@pytest.fixture(scope="session")
def sample_sql_valid():
    return "SELECT * FROM customers LIMIT 5"


@pytest.fixture(scope="session")
def sample_sql_invalid():
    return "DELETE FROM customers"


@pytest.fixture(scope="session")
def sample_schema_context():
    from tools.schema_inspector import search_schema
    return search_schema("top customers by revenue")