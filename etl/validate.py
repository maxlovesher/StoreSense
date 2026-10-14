"""
ETL step 4: Validate.

Owner: Member 1 (Data & ETL Lead)
Spec:  docs/PROJECT_BRIEF.md, section 6.1

Checks the finished warehouse: row counts, foreign keys with no matching
dimension row ("orphans"), NULL keys, duplicate keys and value ranges.

Every check is a SQL query that counts PROBLEMS, so 0 means pass.

Run from the project root (exit code 1 if any check fails):
    python etl/validate.py
"""
import argparse
import sys
from pathlib import Path

import duckdb

from common.db import RAW_DIR, WAREHOUSE_PATH, get_connection
from etl.extract import missing_raw_files, raw_row_counts, register_raw_views


def _orphans(child: str, child_key: str, parent: str, parent_key: str) -> str:
    """SQL counting child rows whose key has no row in the parent table."""
    return (
        f"SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON c.{child_key} = p.{parent_key} "
        f"WHERE p.{parent_key} IS NULL"
    )


def _duplicates(table: str, key: str) -> str:
    """SQL counting how many rows share a key value with another row."""
    return f"SELECT COUNT(*) - COUNT(DISTINCT {key}) FROM {table}"


def _count_differs(table: str, expected: int) -> str:
    """SQL returning how far a table's row count is from the expected count."""
    return f"SELECT ABS((SELECT COUNT(*) FROM {table}) - {expected})"


def build_checks(raw_counts: dict[str, int] | None) -> list[tuple[str, str]]:
    """The list of (check name, SQL returning the number of problems)."""
    checks = [
        # --- Row counts --------------------------------------------------------
        ("dim_time has 168 rows (7 days x 24 hours)", _count_differs("dim_time", 168)),
        ("fact_order.basket_size adds up to the fact_order_line row count",
         "SELECT ABS((SELECT SUM(basket_size) FROM fact_order) - (SELECT COUNT(*) FROM fact_order_line))"),
        ("dim_user has one row per distinct user in fact_order",
         "SELECT ABS((SELECT COUNT(*) FROM dim_user) - (SELECT COUNT(DISTINCT user_key) FROM fact_order))"),
    ]
    if raw_counts:
        checks += [
            ("dim_product rows = products.csv rows", _count_differs("dim_product", raw_counts["raw_products"])),
            ("fact_order rows = orders.csv rows", _count_differs("fact_order", raw_counts["raw_orders"])),
            ("fact_order_line rows = prior + train rows",
             _count_differs("fact_order_line",
                            raw_counts["raw_order_products_prior"] + raw_counts["raw_order_products_train"])),
        ]

    checks += [
        # --- Foreign keys: every key must exist in its dimension ----------------
        ("fact_order_line.product_key -> dim_product", _orphans("fact_order_line", "product_key", "dim_product", "product_key")),
        ("fact_order_line.user_key -> dim_user",       _orphans("fact_order_line", "user_key", "dim_user", "user_key")),
        ("fact_order_line.time_key -> dim_time",       _orphans("fact_order_line", "time_key", "dim_time", "time_key")),
        ("fact_order_line.order_id -> fact_order",     _orphans("fact_order_line", "order_id", "fact_order", "order_id")),
        ("fact_order.user_key -> dim_user",            _orphans("fact_order", "user_key", "dim_user", "user_key")),
        ("fact_order.time_key -> dim_time",            _orphans("fact_order", "time_key", "dim_time", "time_key")),

        # --- Keys are unique ----------------------------------------------------
        ("dim_time.time_key is unique",       _duplicates("dim_time", "time_key")),
        ("dim_product.product_key is unique", _duplicates("dim_product", "product_key")),
        ("dim_user.user_key is unique",       _duplicates("dim_user", "user_key")),
        ("fact_order.order_id is unique",     _duplicates("fact_order", "order_id")),

        # --- No NULL keys -------------------------------------------------------
        ("no NULL keys in fact_order_line",
         "SELECT COUNT(*) FROM fact_order_line "
         "WHERE order_id IS NULL OR product_key IS NULL OR user_key IS NULL OR time_key IS NULL"),
        ("no NULL keys in fact_order",
         "SELECT COUNT(*) FROM fact_order WHERE user_key IS NULL OR time_key IS NULL"),

        # --- The product hierarchy joined completely ----------------------------
        ("every product has an aisle and a department",
         "SELECT COUNT(*) FROM dim_product WHERE aisle IS NULL OR department IS NULL"),

        # --- NULL policy and value ranges ---------------------------------------
        ("days_since_prior is NULL on every first order and only there",
         "SELECT COUNT(*) FROM fact_order "
         "WHERE (order_number = 1 AND days_since_prior IS NOT NULL) "
         "   OR (order_number > 1 AND days_since_prior IS NULL)"),
        ("days_since_prior is between 0 and 30",
         "SELECT COUNT(*) FROM fact_order WHERE days_since_prior NOT BETWEEN 0 AND 30"),
        ("reordered is only 0 or 1",
         "SELECT COUNT(*) FROM fact_order_line WHERE reordered NOT IN (0, 1)"),
        ("time_key is between 0 and 167",
         "SELECT COUNT(*) FROM fact_order WHERE time_key NOT BETWEEN 0 AND 167"),
    ]
    return checks


def run_checks(con: duckdb.DuckDBPyConnection, raw_dir: Path | None = None) -> list[tuple[str, int]]:
    """
    Run all checks and return [(name, number of problems)].
    If raw_dir holds the CSVs, row counts are also compared with the raw files.
    """
    raw_counts = None
    if raw_dir is not None and not missing_raw_files(raw_dir):
        raw_con = duckdb.connect()  # separate in-memory connection: the warehouse is read-only
        register_raw_views(raw_con, raw_dir)
        raw_counts = raw_row_counts(raw_con)
        raw_con.close()

    return [(name, con.execute(sql).fetchone()[0]) for name, sql in build_checks(raw_counts)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the StoreSense warehouse.")
    parser.add_argument("--db", type=Path, default=WAREHOUSE_PATH, help="warehouse file to check")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR, help="folder with the raw CSVs")
    args = parser.parse_args()

    if missing_raw_files(args.raw_dir):
        print(f"(raw CSVs not found in {args.raw_dir}: skipping the comparison with the raw files)\n")

    con = get_connection(read_only=True, path=args.db)
    try:
        results = run_checks(con, args.raw_dir)
        print("Table sizes:")
        for table in ("dim_time", "dim_product", "dim_user", "fact_order", "fact_order_line"):
            print(f"  {table:<16}{con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:>12,}")
    finally:
        con.close()

    print("\nChecks:")
    for name, problems in results:
        print(f"  [{'PASS' if problems == 0 else 'FAIL'}] {name}" + ("" if problems == 0 else f"  ({problems:,} problems)"))

    failed = sum(1 for _, problems in results if problems)
    print(f"\n{len(results) - failed}/{len(results)} checks passed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
