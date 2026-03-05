"""Tests for the Excel data loader."""

import sys
import os
import tempfile

import pandas as pd

# Add ADK_Agentic/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ADK_Agentic"))


def _create_test_excel(path: str):
    """Create a small test Excel file."""
    df = pd.DataFrame([
        {"OrderNbr": "WO-001", "Customer_name": "Acme Corp", "Status": "Open", "Ship_to": "Miami"},
        {"OrderNbr": "WO-002", "Customer_name": "Beta Inc", "Status": "Closed", "Ship_to": "Dallas"},
        {"OrderNbr": "WO-003", "Customer_name": "Acme Corp", "Status": "Open", "Ship_to": "Tampa"},
    ])
    df.to_excel(path, index=False)


def test_load_excel():
    """DataLoader loads records from Excel."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        _create_test_excel(f.name)
        os.environ["EXCEL_PATH"] = f.name

        from data_loader import DataLoader
        loader = DataLoader()

        orders = loader.get_all_orders()
        assert len(orders) == 3
        assert orders[0]["OrderNbr"] == "WO-001"

        os.unlink(f.name)


def test_get_all_orders_limit():
    """get_all_orders respects limit parameter."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        _create_test_excel(f.name)
        os.environ["EXCEL_PATH"] = f.name

        from data_loader import DataLoader
        loader = DataLoader()

        orders = loader.get_all_orders(limit=2)
        assert len(orders) == 2

        os.unlink(f.name)


def test_search_orders():
    """search_orders finds matching records."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        _create_test_excel(f.name)
        os.environ["EXCEL_PATH"] = f.name

        from data_loader import DataLoader
        loader = DataLoader()

        results = loader.search_orders("Acme")
        assert len(results) == 2
        assert all(r["Customer_name"] == "Acme Corp" for r in results)

        os.unlink(f.name)


def test_search_orders_case_insensitive():
    """search_orders is case insensitive."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        _create_test_excel(f.name)
        os.environ["EXCEL_PATH"] = f.name

        from data_loader import DataLoader
        loader = DataLoader()

        results = loader.search_orders("acme")
        assert len(results) == 2

        os.unlink(f.name)


def test_get_order_by_id_found():
    """get_order_by_id returns the correct record."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        _create_test_excel(f.name)
        os.environ["EXCEL_PATH"] = f.name

        from data_loader import DataLoader
        loader = DataLoader()

        order = loader.get_order_by_id("WO-002")
        assert order is not None
        assert order["Customer_name"] == "Beta Inc"

        os.unlink(f.name)


def test_get_order_by_id_not_found():
    """get_order_by_id returns None for missing ID."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        _create_test_excel(f.name)
        os.environ["EXCEL_PATH"] = f.name

        from data_loader import DataLoader
        loader = DataLoader()

        order = loader.get_order_by_id("WO-999")
        assert order is None

        os.unlink(f.name)


def test_load_missing_file():
    """DataLoader handles missing Excel file gracefully."""
    os.environ["EXCEL_PATH"] = "/nonexistent/path/fake.xlsx"

    from data_loader import DataLoader
    loader = DataLoader()

    orders = loader.get_all_orders()
    assert orders == []
