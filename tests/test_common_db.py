"""Tests for the shared path / connection helpers in common/db.py."""
import pytest

from common import db


def test_get_connection_missing_warehouse_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        db.get_connection(read_only=True, path=tmp_path / "nope.duckdb")


def test_write_then_read_roundtrip(tmp_path):
    path = tmp_path / "sub" / "t.duckdb"  # the sub folder does not exist yet
    con = db.get_connection(read_only=False, path=path)
    con.execute("CREATE TABLE t AS SELECT 1 AS a UNION ALL SELECT 2")
    con.close()

    df = db.query_df("SELECT SUM(a) AS total FROM t", path=path)
    assert df["total"].iloc[0] == 3


def test_query_df_supports_parameters(tmp_path):
    path = tmp_path / "t.duckdb"
    con = db.get_connection(read_only=False, path=path)
    con.execute("CREATE TABLE t AS SELECT * FROM range(5) r(a)")
    con.close()

    df = db.query_df("SELECT COUNT(*) AS n FROM t WHERE a >= ?", [3], path=path)
    assert df["n"].iloc[0] == 2


def test_raw_csv_missing_and_present(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "RAW_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        db.raw_csv("orders.csv")

    (tmp_path / "orders.csv").write_text("order_id\n1\n")
    assert db.raw_csv("orders.csv") == tmp_path / "orders.csv"
