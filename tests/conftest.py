"""Shared pytest fixtures."""
import pytest

from common.db import WAREHOUSE_PATH, get_connection


@pytest.fixture(scope="session")
def warehouse():
    """
    Read-only connection to the real warehouse.
    Tests that use it are skipped (not failed) until `python etl/load.py` has run.
    """
    if not WAREHOUSE_PATH.exists():
        pytest.skip("warehouse not built yet: run python etl/load.py")
    con = get_connection(read_only=True)
    yield con
    con.close()
