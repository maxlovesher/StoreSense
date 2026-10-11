"""
Tests for the ETL (etl/extract.py, transform.py, load.py, validate.py).

A tiny synthetic Instacart dataset is written to a temp folder, the REAL
pipeline is run on it, and the results are compared with numbers worked out
by hand (shown in the comments below).

The last test runs the checks on the real warehouse; it is skipped until
`python etl/load.py` has been run.
"""
import shutil
from pathlib import Path

import pytest

from common.db import get_connection
from etl.load import build_warehouse
from etl.validate import run_checks

TEST_SCHEMA = Path(__file__).parent / "fixtures" / "etl_test_schema.sql"

# ---------------------------------------------------------------------------
# Synthetic raw data. Five orders from two users:
#
#   order  user  set    #  dow hour  days  basket  reordered
#     1     10   prior  1   0    8   NULL    2        0      (Sunday morning)
#     2     10   prior  2   6   20     7     3        2      (Saturday evening)
#     3     10   train  3   2   14    12     2        1
#     4     11   prior  1   3   23   NULL    1        0      (Wednesday night)
#     5     11   test   2   3    2    30     0        0      (test order: no products)
# ---------------------------------------------------------------------------
RAW_FILES = {
    "orders.csv": """order_id,user_id,eval_set,order_number,order_dow,order_hour_of_day,days_since_prior_order
1,10,prior,1,0,8,
2,10,prior,2,6,20,7.0
3,10,train,3,2,14,12.0
4,11,prior,1,3,23,
5,11,test,2,3,2,30.0
""",
    "order_products__prior.csv": """order_id,product_id,add_to_cart_order,reordered
1,100,1,0
1,101,2,0
2,100,1,1
2,102,2,0
2,101,3,1
4,102,1,0
""",
    "order_products__train.csv": """order_id,product_id,add_to_cart_order,reordered
3,100,1,1
3,103,2,0
""",
    "products.csv": """product_id,product_name,aisle_id,department_id
100,Banana,1,1
101,Organic Avocado,1,1
102,"Chips, Salted",2,2
103,Sparkling Water,2,2
""",
    "aisles.csv": """aisle_id,aisle
1,fresh fruits
2,chips pretzels
""",
    "departments.csv": """department_id,department
1,produce
2,snacks
""",
}


def write_raw_files(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in RAW_FILES.items():
        (folder / name).write_text(content, encoding="utf-8")
    return folder


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    return write_raw_files(tmp_path_factory.mktemp("raw"))


@pytest.fixture(scope="module")
def built(tmp_path_factory, raw_dir):
    """Build one warehouse from the synthetic data and share it between tests."""
    db_path = tmp_path_factory.mktemp("wh") / "test.duckdb"
    counts = build_warehouse(db_path=db_path, schema_path=TEST_SCHEMA, raw_dir=raw_dir)
    con = get_connection(read_only=True, path=db_path)
    yield con, counts, db_path
    con.close()


def test_row_counts(built):
    _, counts, _ = built
    assert counts == {
        "dim_time": 168,        # 7 days x 24 hours
        "dim_product": 4,
        "fact_order_line": 8,   # 6 prior lines + 2 train lines
        "fact_order": 5,        # all 5 orders, including the test order
        "dim_user": 2,
    }


def test_dim_time_hierarchy(built):
    con, _, _ = built
    rows = {
        r[0]: r[1:]
        for r in con.execute(
            "SELECT time_key, day_name, is_weekend, hour_band FROM dim_time WHERE time_key IN (8, 164, 95)"
        ).fetchall()
    }
    assert rows[8] == ("Sunday", True, "Morning")       # dow 0, 08:00
    assert rows[164] == ("Saturday", True, "Evening")   # dow 6, 20:00
    assert rows[95] == ("Wednesday", False, "Night")    # dow 3, 23:00


def test_hour_bands_cover_every_hour(built):
    con, _, _ = built
    bands = dict(con.execute(
        "SELECT hour_band, COUNT(*) FROM dim_time GROUP BY hour_band"
    ).fetchall())
    # Per day: Morning 5-11 = 7h, Afternoon 12-16 = 5h, Evening 17-20 = 4h, Night 21-4 = 8h.
    assert bands == {"Morning": 7 * 7, "Afternoon": 5 * 7, "Evening": 4 * 7, "Night": 8 * 7}


def test_product_hierarchy_and_quoted_comma(built):
    con, _, _ = built
    row = con.execute(
        "SELECT product_name, aisle, department FROM dim_product WHERE product_key = 102"
    ).fetchone()
    assert row == ("Chips, Salted", "chips pretzels", "snacks")


def test_fact_order_values(built):
    con, _, _ = built
    rows = con.execute(
        "SELECT order_id, user_key, time_key, order_number, days_since_prior, basket_size, reordered_items "
        "FROM fact_order ORDER BY order_id"
    ).fetchall()
    assert rows == [
        (1, 10, 8, 1, None, 2, 0),
        (2, 10, 164, 2, 7, 3, 2),
        (3, 10, 62, 3, 12, 2, 1),
        (4, 11, 95, 1, None, 1, 0),
        (5, 11, 74, 2, 30, 0, 0),   # the test order is kept, with an empty basket
    ]


def test_first_orders_keep_null_not_zero(built):
    con, _, _ = built
    nulls = con.execute(
        "SELECT order_number FROM fact_order WHERE days_since_prior IS NULL ORDER BY order_id"
    ).fetchall()
    assert nulls == [(1,), (1,)]


def test_fact_order_line_carries_user_and_time(built):
    con, _, _ = built
    # Order 2 happened on a Saturday at 20:00 -> time_key 164, user 10.
    keys = con.execute(
        "SELECT DISTINCT user_key, time_key FROM fact_order_line WHERE order_id = 2"
    ).fetchall()
    assert keys == [(10, 164)]


def test_dim_user_aggregates(built):
    con, _, _ = built
    rows = {
        r[0]: r[1:]
        for r in con.execute(
            "SELECT user_key, total_orders, avg_basket_size, avg_days_between_orders, reorder_ratio, segment "
            "FROM dim_user"
        ).fetchall()
    }
    # User 10: 3 orders, baskets 2/3/2 -> 7/3, gaps 7 and 12 -> 9.5, reordered 3 of 7 items.
    total, basket, days, ratio, segment = rows[10]
    assert total == 3
    assert basket == pytest.approx(7 / 3)
    assert days == pytest.approx(9.5)
    assert ratio == pytest.approx(3 / 7)
    assert segment is None   # filled in later by the segmentation step

    # User 11: 2 orders, but the empty test order is ignored for the basket average.
    total, basket, days, ratio, _ = rows[11]
    assert total == 2
    assert basket == pytest.approx(1.0)
    assert days == pytest.approx(30.0)   # only one non-NULL gap
    assert ratio == pytest.approx(0.0)


def test_validation_passes_on_a_good_warehouse(built, raw_dir):
    con, _, _ = built
    results = run_checks(con, raw_dir)
    failed = [(name, n) for name, n in results if n]
    assert failed == []
    # Including the comparison with the raw files: 3 extra checks.
    assert any("orders.csv" in name for name, _ in results)


def test_validation_detects_an_orphan_key(tmp_path, raw_dir):
    db_path = tmp_path / "broken.duckdb"
    build_warehouse(db_path=db_path, schema_path=TEST_SCHEMA, raw_dir=raw_dir)

    # Break the warehouse: remove a product that order lines still refer to.
    writer = get_connection(read_only=False, path=db_path)
    writer.execute("DELETE FROM dim_product WHERE product_key = 100")
    writer.close()

    con = get_connection(read_only=True, path=db_path)
    results = dict(run_checks(con, raw_dir))
    con.close()

    assert results["fact_order_line.product_key -> dim_product"] == 3   # 3 lines bought product 100
    assert results["dim_product rows = products.csv rows"] == 1


def test_validation_detects_a_wrong_null(tmp_path, raw_dir):
    db_path = tmp_path / "broken2.duckdb"
    build_warehouse(db_path=db_path, schema_path=TEST_SCHEMA, raw_dir=raw_dir)

    writer = get_connection(read_only=False, path=db_path)
    writer.execute("UPDATE fact_order SET days_since_prior = NULL WHERE order_id = 2")
    writer.close()

    con = get_connection(read_only=True, path=db_path)
    results = dict(run_checks(con, raw_dir))
    con.close()
    assert results["days_since_prior is NULL on every first order and only there"] == 1


def test_empty_schema_is_rejected_with_a_clear_message(tmp_path, raw_dir):
    empty = tmp_path / "schema.sql"
    empty.write_text("-- nothing here yet\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no CREATE TABLE"):
        build_warehouse(db_path=tmp_path / "x.duckdb", schema_path=empty, raw_dir=raw_dir)
    assert not (tmp_path / "x.duckdb").exists()


def test_existing_warehouse_needs_force(tmp_path, raw_dir):
    db_path = tmp_path / "wh.duckdb"
    build_warehouse(db_path=db_path, schema_path=TEST_SCHEMA, raw_dir=raw_dir)
    with pytest.raises(FileExistsError):
        build_warehouse(db_path=db_path, schema_path=TEST_SCHEMA, raw_dir=raw_dir)
    # --force rebuilds cleanly.
    counts = build_warehouse(db_path=db_path, schema_path=TEST_SCHEMA, raw_dir=raw_dir, force=True)
    assert counts["fact_order"] == 5


def test_missing_raw_file_does_not_touch_existing_warehouse(tmp_path, raw_dir):
    db_path = tmp_path / "wh.duckdb"
    build_warehouse(db_path=db_path, schema_path=TEST_SCHEMA, raw_dir=raw_dir)

    incomplete = tmp_path / "raw_incomplete"
    shutil.copytree(raw_dir, incomplete)
    (incomplete / "orders.csv").unlink()

    with pytest.raises(FileNotFoundError):
        build_warehouse(db_path=db_path, schema_path=TEST_SCHEMA, raw_dir=incomplete, force=True)
    assert db_path.exists()   # the old warehouse was not deleted


def test_real_warehouse_passes_validation(warehouse):
    """Runs only after `python etl/load.py` has built the real warehouse."""
    failed = [(name, n) for name, n in run_checks(warehouse) if n]
    assert failed == []
