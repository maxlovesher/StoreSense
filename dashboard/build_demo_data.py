"""
Build the demo extract the hosted dashboard runs on.

Owner: Member 6 (Dashboard & Integration)

The warehouse (0.23 GB) is not in git, so a hosted copy of the dashboard has no
database. This script writes a small extract to data/demo/ that gives the
Overview and OLAP pages exactly the same numbers:

    line_counts.parquet   order lines counted per product and day-hour slot
                          (product_key, time_key, n): 3.0M rows instead of 33.8M
    dim_product.parquet   product, aisle and department names
    dim_time.parquet      the 168 day-hour slots
    kpis.parquet          the five headline numbers, computed on the warehouse

It holds counts only: no orders, users or baskets. Every OLAP question in the
dashboard (any grouping or filter by product, aisle, department, day or hour)
can be answered from these counts, because none of them looks inside an order.

Run from the project root after building the warehouse, and commit data/demo/:
    python dashboard/build_demo_data.py
"""
from pathlib import Path

from common.db import get_connection
from dashboard.data import DEMO_DIR, KPI_SQL

EXTRACT_SQL = {
    "line_counts": """
        SELECT product_key::INTEGER AS product_key, time_key::SMALLINT AS time_key, COUNT(*)::INTEGER AS n
        FROM fact_order_line GROUP BY product_key, time_key ORDER BY product_key, time_key
    """,
    "dim_product": "SELECT product_key, product_name, aisle, department FROM dim_product ORDER BY product_key",
    "dim_time": "SELECT * FROM dim_time ORDER BY time_key",
    "kpis": KPI_SQL,
}


def build_demo_data(con, out_dir: Path = DEMO_DIR) -> dict[str, int]:
    """Write one Parquet file per extract table; return the row count of each."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = {}
    for name, sql in EXTRACT_SQL.items():
        path = (out_dir / f"{name}.parquet").as_posix().replace("'", "''")
        con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
        rows[name] = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()[0]
    return rows


def main() -> None:
    con = get_connection(read_only=True)
    try:
        rows = build_demo_data(con)
    finally:
        con.close()
    size = sum(f.stat().st_size for f in DEMO_DIR.glob("*.parquet")) / 1e6
    print(", ".join(f"{name}: {n:,} rows" for name, n in rows.items()))
    print(f"{size:.1f} MB written to {DEMO_DIR}")


if __name__ == "__main__":
    main()
