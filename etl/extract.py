"""
ETL step 1: Extract.

Owner: Member 1 (Data & ETL Lead)
Spec:  docs/PROJECT_BRIEF.md, section 6.1

Exposes the six raw Kaggle CSVs to DuckDB as *views* named raw_orders,
raw_products, ... A view stores no data: DuckDB reads the CSV only when a
query runs. That is why the 32M-row prior-orders file never has to fit in
memory, and pandas is not involved at all.

Run on its own to check the raw files and print their row counts:
    python etl/extract.py
"""
from pathlib import Path

import duckdb

from common.db import RAW_DIR, RAW_FILES

# view name -> (csv file, {column: type}).
# Giving the types explicitly is faster than letting DuckDB guess them, and it
# means every team member gets identical types on every machine.
RAW_SOURCES = {
    "raw_orders": (
        "orders.csv",
        {
            "order_id": "INTEGER",
            "user_id": "INTEGER",
            "eval_set": "VARCHAR",              # 'prior', 'train' or 'test'
            "order_number": "INTEGER",          # 1 = the user's first order
            "order_dow": "INTEGER",             # day of week, 0..6 (INTEGER, not TINYINT: order_dow * 24 would overflow)
            "order_hour_of_day": "INTEGER",     # 0..23
            "days_since_prior_order": "DOUBLE", # empty (NULL) on a user's first order
        },
    ),
    "raw_order_products_prior": (
        "order_products__prior.csv",
        {
            "order_id": "INTEGER",
            "product_id": "INTEGER",
            "add_to_cart_order": "INTEGER",
            "reordered": "TINYINT",             # 1 if the user bought it before
        },
    ),
    "raw_order_products_train": (
        "order_products__train.csv",
        {
            "order_id": "INTEGER",
            "product_id": "INTEGER",
            "add_to_cart_order": "INTEGER",
            "reordered": "TINYINT",
        },
    ),
    "raw_products": (
        "products.csv",
        {
            "product_id": "INTEGER",
            "product_name": "VARCHAR",
            "aisle_id": "INTEGER",
            "department_id": "INTEGER",
        },
    ),
    "raw_aisles": ("aisles.csv", {"aisle_id": "INTEGER", "aisle": "VARCHAR"}),
    "raw_departments": ("departments.csv", {"department_id": "INTEGER", "department": "VARCHAR"}),
}


def missing_raw_files(raw_dir: Path = RAW_DIR) -> list[str]:
    """Names of the expected CSVs that are not in raw_dir (empty list = all there)."""
    return [name for name in RAW_FILES if not (Path(raw_dir) / name).exists()]


def register_raw_views(con: duckdb.DuckDBPyConnection, raw_dir: Path = RAW_DIR) -> None:
    """Create one raw_* view per CSV on this connection."""
    missing = missing_raw_files(raw_dir)
    if missing:
        raise FileNotFoundError(
            f"Missing in {raw_dir}: {', '.join(missing)}. "
            "Download the Instacart CSVs first (see the README, 'Get the data')."
        )

    for view, (filename, columns) in RAW_SOURCES.items():
        csv_path = (Path(raw_dir) / filename).as_posix().replace("'", "''")
        column_spec = ", ".join(f"'{name}': '{dtype}'" for name, dtype in columns.items())
        con.execute(
            f"""
            CREATE OR REPLACE VIEW {view} AS
            SELECT * FROM read_csv('{csv_path}', header = true, columns = {{{column_spec}}})
            """
        )


def raw_row_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Row count of every raw_* view (reads each CSV once)."""
    return {view: con.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0] for view in RAW_SOURCES}


def main() -> None:
    con = duckdb.connect()  # in-memory: nothing is written to disk
    register_raw_views(con)
    print(f"Raw files found in {RAW_DIR}\n")
    for view, n in raw_row_counts(con).items():
        print(f"  {view:<28}{n:>12,} rows")


if __name__ == "__main__":
    main()
