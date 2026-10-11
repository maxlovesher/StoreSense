"""
Shared paths and DuckDB helpers.

Every script (ETL, mining, dashboard) imports its file locations and its
database connection from here, so nobody hard-codes paths.

    from common.db import get_connection, query_df, raw_csv
"""
from pathlib import Path

import duckdb
import pandas as pd

# The project root is the folder that contains common/, etl/, mining/, ...
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
WAREHOUSE_PATH = PROJECT_ROOT / "data" / "warehouse" / "storesense.duckdb"
SQL_DIR = PROJECT_ROOT / "sql"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

# The six Kaggle files the ETL expects in data/raw/.
RAW_FILES = (
    "orders.csv",
    "order_products__prior.csv",
    "order_products__train.csv",
    "products.csv",
    "aisles.csv",
    "departments.csv",
)


def raw_csv(name: str) -> Path:
    """Return the path to one raw CSV, with a clear error if it is missing."""
    path = RAW_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download the Instacart CSVs into data/raw/ "
            "(see the README, section 'Get the data')."
        )
    return path


def get_connection(read_only: bool = True, path: Path = WAREHOUSE_PATH) -> duckdb.DuckDBPyConnection:
    """
    Open the warehouse.

    read_only=True  -> for mining, the dashboard and tests (safe, many readers allowed).
    read_only=False -> for the ETL load and for writing dim_user.segment; creates
                       the data/warehouse/ folder if needed. DuckDB allows only one
                       writer at a time, so close the connection when you are done.
    """
    path = Path(path)
    if read_only:
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Build the warehouse first: python etl/load.py"
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def query_df(sql: str, params: list | None = None, path: Path = WAREHOUSE_PATH) -> pd.DataFrame:
    """Run one read-only query and return the result as a pandas DataFrame."""
    con = get_connection(read_only=True, path=path)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()
