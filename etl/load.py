"""
ETL step 3: Load.

Owner: Member 1 (Data & ETL Lead)
Spec:  docs/PROJECT_BRIEF.md, section 6.1

1. Creates the empty star-schema tables by running sql/schema.sql (owned by
   Member 2 - this script only runs it, it never defines the tables itself).
2. Fills each table with `INSERT INTO ... SELECT ...` using the SELECTs in
   transform.py, reading the raw CSVs through the views from extract.py.

Run from the project root:
    python etl/load.py              # build data/warehouse/storesense.duckdb
    python etl/load.py --force      # delete the existing warehouse and rebuild

WARNING: --force also erases dim_user.segment, which the segmentation step
writes later. Re-run mining/segmentation.py after a rebuild.
"""
import argparse
import time
from pathlib import Path

from common.db import RAW_DIR, SQL_DIR, WAREHOUSE_PATH, get_connection
from etl.extract import missing_raw_files, register_raw_views
from etl.transform import LOAD_STEPS

EXPECTED_TABLES = {step[0] for step in LOAD_STEPS}


def schema_defines_tables(schema_sql: str) -> bool:
    """True if the SQL contains at least one CREATE TABLE outside of -- comments."""
    code = "\n".join(
        line for line in schema_sql.splitlines() if not line.strip().startswith("--")
    )
    return "create table" in code.lower()


def build_warehouse(
    db_path: Path = WAREHOUSE_PATH,
    schema_path: Path = SQL_DIR / "schema.sql",
    raw_dir: Path = RAW_DIR,
    force: bool = False,
) -> dict[str, int]:
    """Build the whole warehouse and return {table: row count}."""
    db_path, schema_path = Path(db_path), Path(schema_path)

    # --- Check everything BEFORE touching the existing warehouse --------------
    schema_sql = schema_path.read_text(encoding="utf-8")
    if not schema_defines_tables(schema_sql):
        raise ValueError(
            f"{schema_path} has no CREATE TABLE statements yet. "
            "The star schema is owned by Member 2 (Warehouse & OLAP); "
            "load.py cannot run until it is written."
        )
    missing = missing_raw_files(raw_dir)
    if missing:
        raise FileNotFoundError(f"Missing in {raw_dir}: {', '.join(missing)}")
    if db_path.exists():
        if not force:
            raise FileExistsError(
                f"{db_path} already exists. Use --force to delete it and rebuild."
            )
        db_path.unlink()
        Path(str(db_path) + ".wal").unlink(missing_ok=True)

    # --- Create the tables ----------------------------------------------------
    con = get_connection(read_only=False, path=db_path)
    try:
        con.execute(schema_sql)
        created = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        absent = EXPECTED_TABLES - created
        if absent:
            raise ValueError(f"schema.sql did not create these tables: {sorted(absent)}")

        # --- Fill them, in dependency order -----------------------------------
        register_raw_views(con, raw_dir)
        counts = {}
        for table, columns, select_sql in LOAD_STEPS:
            started = time.time()
            con.execute(f"INSERT INTO {table} ({', '.join(columns)}) {select_sql}")
            counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  loaded {table:<16}{counts[table]:>12,} rows  ({time.time() - started:5.1f}s)")
        return counts
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the StoreSense warehouse.")
    parser.add_argument("--force", action="store_true", help="delete an existing warehouse and rebuild")
    parser.add_argument("--db", type=Path, default=WAREHOUSE_PATH, help="warehouse file to create")
    parser.add_argument("--schema", type=Path, default=SQL_DIR / "schema.sql", help="schema SQL file")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR, help="folder with the raw CSVs")
    args = parser.parse_args()

    print(f"Building {args.db}")
    build_warehouse(args.db, args.schema, args.raw_dir, args.force)
    print("Done. Next: python etl/validate.py")


if __name__ == "__main__":
    main()
