"""
Tests for the dashboard (dashboard/data.py and the Streamlit pages).

Part 1 runs the data layer on a tiny made-up warehouse whose answers are worked
out by hand. Part 2 runs every page headless with Streamlit's AppTest on the real
warehouse and the committed result files; it is skipped until `python etl/load.py`
has been run.

The tiny warehouse (7 order lines, products p1..p4):

    order 1  Sunday 08:00 (weekend, Morning)   Yogurt A, Milk, Banana
    order 2  Monday 20:00 (Evening)            Yogurt A, Yogurt B
    order 3  Saturday 20:00 (weekend, Evening) Banana, Yogurt A
    order 4  a test order with no products     (basket_size 0)

    departments: dairy eggs = Yogurt A x3, Yogurt B, Milk = 5 lines; produce = Banana x2 = 2 lines
    aisles:      yogurt 4, milk 1, fresh fruits 2
    weekend (orders 1 and 3) = 5 lines; dairy eggs, Evening (orders 2 and 3) = 3 lines
    reordered lines: Yogurt A in orders 2 and 3, Banana in order 3 = 3 of 7
"""
import duckdb
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from common.db import PROJECT_ROOT
from dashboard import data

DASHBOARD = PROJECT_ROOT / "dashboard"


@pytest.fixture
def tiny():
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE dim_product (product_key INTEGER, product_name VARCHAR, aisle VARCHAR, department VARCHAR);
        INSERT INTO dim_product VALUES
            (1, 'Yogurt A', 'yogurt', 'dairy eggs'), (2, 'Yogurt B', 'yogurt', 'dairy eggs'),
            (3, 'Milk', 'milk', 'dairy eggs'), (4, 'Banana', 'fresh fruits', 'produce');
        CREATE TABLE dim_time (time_key INTEGER, day_name VARCHAR, is_weekend BOOLEAN,
                               order_hour_of_day INTEGER, hour_band VARCHAR);
        INSERT INTO dim_time VALUES
            (0, 'Sunday', true, 8, 'Morning'), (1, 'Monday', false, 20, 'Evening'),
            (2, 'Saturday', true, 20, 'Evening');
        CREATE TABLE fact_order_line (order_id INTEGER, product_key INTEGER, time_key INTEGER, reordered INTEGER);
        INSERT INTO fact_order_line VALUES
            (1, 1, 0, 0), (1, 3, 0, 0), (1, 4, 0, 0),
            (2, 1, 1, 1), (2, 2, 1, 0),
            (3, 4, 2, 1), (3, 1, 2, 1);
        CREATE TABLE fact_order (order_id INTEGER, basket_size INTEGER);
        INSERT INTO fact_order VALUES (1, 3), (2, 2), (3, 2), (4, 0);
        CREATE TABLE dim_user (user_key INTEGER);
        INSERT INTO dim_user VALUES (1), (2);
    """)
    yield con
    con.close()


# ---------------------------------------------------------------------------
# Part 1: the data layer
# ---------------------------------------------------------------------------
def test_kpis_ignore_test_orders_in_the_average_basket(tiny):
    k = data.kpis(con=tiny)
    assert k["orders"] == 4 and k["users"] == 2 and k["products"] == 4
    assert k["avg_basket_size"] == pytest.approx((3 + 2 + 2) / 3)   # the empty test order is left out
    assert k["reorder_rate"] == pytest.approx(3 / 7)


def test_group_by_department_and_aisle(tiny):
    dept = data.olap_group(["Department"], con=tiny).set_index("Department")
    assert dept["order_lines"].to_dict() == {"dairy eggs": 5, "produce": 2}
    assert dept.loc["dairy eggs", "pct_of_lines"] == pytest.approx(71.43)
    aisle = data.olap_group(["Aisle"], con=tiny).set_index("Aisle")
    assert aisle["order_lines"].to_dict() == {"yogurt": 4, "milk": 1, "fresh fruits": 2}


def test_rollup_has_detail_subtotals_and_grand_total(tiny):
    r = data.olap_rollup(["Department", "Aisle"], con=tiny)
    assert len(r) == 3 + 2 + 1
    assert r.loc[r["level"] == "grand total", "order_lines"].iloc[0] == 7
    totals = r[r["level"] == "Department total"].set_index("Department")["order_lines"].to_dict()
    assert totals == {"dairy eggs": 5, "produce": 2}
    detail = r[r["level"] == "Aisle"].set_index(["Department", "Aisle"])["order_lines"].to_dict()
    assert detail == {("dairy eggs", "yogurt"): 4, ("dairy eggs", "milk"): 1, ("produce", "fresh fruits"): 2}
    # the subtotals add up to the grand total, and so do the details
    assert sum(totals.values()) == 7 and sum(detail.values()) == 7


def test_three_level_rollup_names(tiny):
    assert data.rollup_level_names(["Department", "Aisle", "Product"]) == {
        0: "Product", 1: "Aisle total", 3: "Department total", 7: "grand total"}
    r = data.olap_rollup(["Department", "Aisle", "Product"], {"aisles": ["yogurt"]}, con=tiny)
    assert set(r["level"]) == {"Product", "Aisle total", "Department total", "grand total"}
    assert r.loc[r["level"] == "grand total", "order_lines"].iloc[0] == 4


def test_slice_weekend(tiny):
    r = data.olap_group(["Department"], {"weekend_only": True}, con=tiny).set_index("Department")
    assert r["order_lines"].to_dict() == {"dairy eggs": 3, "produce": 2}   # orders 1 and 3: 5 lines


def test_dice_department_and_hour_band(tiny):
    r = data.olap_group(["Day of week"], {"departments": ["dairy eggs"], "hour_bands": ["Evening"]}, con=tiny)
    assert r.set_index("Day of week")["order_lines"].to_dict() == {"Monday": 2, "Saturday": 1}   # orders 2 and 3


def test_filter_on_a_dimension_not_in_the_grouping(tiny):
    # grouped by department only, filtered by a time column: the time table must still be joined
    r = data.olap_group(["Department"], {"days": ["Sunday"]}, con=tiny).set_index("Department")
    assert r["order_lines"].to_dict() == {"dairy eggs": 2, "produce": 1}   # order 1


def test_pivot_orders_the_days_and_fills_zeros(tiny):
    m = data.olap_pivot("Department", "Day of week", con=tiny)
    assert list(m.columns) == ["Sunday", "Monday", "Saturday"]   # week order, not alphabetical
    assert m.loc["dairy eggs"].tolist() == [2, 2, 1]
    assert m.loc["produce"].tolist() == [1, 0, 1]                # Monday has no produce: 0, not missing
    assert list(data.olap_pivot("Department", "Day of week", top_rows=1, con=tiny).index) == ["dairy eggs"]


def test_cube_has_every_cell_including_empty_ones(tiny):
    cells, axes = data.olap_cube(["Department", "Day of week", "Hour band"], con=tiny)
    assert axes["Department"] == ["dairy eggs", "produce"]            # biggest first
    assert axes["Day of week"] == ["Sunday", "Monday", "Saturday"]     # week order
    assert axes["Hour band"] == ["Morning", "Evening"]                 # time order
    assert len(cells) == 2 * 3 * 2                                     # the full cube, 12 cells
    assert cells["order_lines"].sum() == 7                             # every order line, once
    cell = cells.set_index(["Department", "Day of week", "Hour band"])["order_lines"]
    assert cell[("dairy eggs", "Monday", "Evening")] == 2              # order 2
    assert cell[("produce", "Monday", "Evening")] == 0                 # an empty cell is there, as 0
    assert cell[("dairy eggs", "Sunday", "Evening")] == 0


def test_cube_keeps_only_the_biggest_values_of_a_long_axis(tiny):
    cells, axes = data.olap_cube(["Aisle", "Day of week", "Hour band"], top_values=2, con=tiny)
    assert axes["Aisle"] == ["yogurt", "fresh fruits"]                 # 4 and 2 lines; milk (1) is dropped
    assert set(cells["Aisle"]) == {"yogurt", "fresh fruits"}


def test_highlight_mask_slice_and_dice(tiny):
    cells, _ = data.olap_cube(["Department", "Day of week", "Hour band"], con=tiny)
    assert data.highlight_mask(cells, {}).all()                                   # no picks: the whole cube
    slice_ = data.highlight_mask(cells, {"Day of week": ["Sunday"]})
    assert slice_.sum() == 2 * 1 * 2 and cells.loc[slice_, "order_lines"].sum() == 3   # order 1
    dice = data.highlight_mask(cells, {"Department": ["dairy eggs"], "Hour band": ["Evening"], "Day of week": []})
    assert dice.sum() == 1 * 3 * 1 and cells.loc[dice, "order_lines"].sum() == 3       # orders 2 and 3


def test_demo_extract_gives_the_same_answers_as_the_warehouse(tiny, tmp_path):
    """Build the demo extract from the tiny warehouse, then ask both the same questions."""
    from dashboard.build_demo_data import build_demo_data
    rows = build_demo_data(tiny, tmp_path)
    assert rows == {"line_counts": 7, "dim_product": 4, "dim_time": 3, "kpis": 1}   # 7 lines, each its own product x slot
    demo = data.open_demo_connection(tmp_path)
    try:
        assert data.lines_source(demo) == "line_counts l"
        assert data.lines_source(tiny).startswith("(SELECT")
        assert data.kpis(con=demo) == pytest.approx(data.kpis(con=tiny))
        for ask in (
            lambda c: data.olap_group(["Department", "Day of week"], {"hour_bands": ["Evening"]}, con=c),
            lambda c: data.olap_rollup(["Department", "Aisle", "Product"], con=c),
            lambda c: data.olap_pivot("Aisle", "Hour band", con=c),
            lambda c: data.olap_cube(["Department", "Day of week", "Hour band"], con=c)[0],
        ):
            pd.testing.assert_frame_equal(ask(demo), ask(tiny))
    finally:
        demo.close()


def test_demo_extract_counts_several_lines_per_row(tiny, tmp_path):
    """Two order lines of the same product in the same slot become one row with n = 2."""
    tiny.execute("INSERT INTO fact_order_line VALUES (5, 1, 0, 1)")   # Yogurt A again on Sunday 08:00
    from dashboard.build_demo_data import build_demo_data
    build_demo_data(tiny, tmp_path)
    demo = data.open_demo_connection(tmp_path)
    try:
        assert demo.execute("SELECT n FROM line_counts WHERE product_key = 1 AND time_key = 0").fetchone()[0] == 2
        a = data.olap_group(["Product"], con=demo).set_index("Product")["order_lines"]
        assert a["Yogurt A"] == 4 and a.sum() == 8
    finally:
        demo.close()


def test_data_source_falls_back_to_the_demo_extract(monkeypatch):
    monkeypatch.setenv("STORESENSE_DATA", "demo")
    assert data.data_source() == "demo"   # the demo extract is committed
    con = data.open_connection()
    try:
        assert data.lines_source(con) == "line_counts l"
    finally:
        con.close()


def test_committed_demo_extract_matches_the_warehouse(warehouse):
    """If this fails, the warehouse changed: run `python dashboard/build_demo_data.py` and commit data/demo/."""
    demo = data.open_demo_connection()
    try:
        assert data.kpis(con=demo) == pytest.approx(data.kpis(con=warehouse))
        pd.testing.assert_frame_equal(data.department_totals(con=demo), data.department_totals(con=warehouse))
        pd.testing.assert_frame_equal(data.orders_by_hour(con=demo), data.orders_by_hour(con=warehouse))
        pd.testing.assert_frame_equal(data.olap_cube(["Aisle", "Day of week", "Hour of day"], con=demo)[0],
                                      data.olap_cube(["Aisle", "Day of week", "Hour of day"], con=warehouse)[0])
    finally:
        demo.close()


def test_values_from_the_page_are_parameters_not_sql(tiny):
    evil = "x'; DROP TABLE dim_product; --"
    r = data.olap_group(["Department"], {"departments": [evil]}, con=tiny)
    assert r.empty
    assert tiny.execute("SELECT COUNT(*) FROM dim_product").fetchone()[0] == 4   # nothing was dropped


def test_choices(tiny):
    c = data.choices(con=tiny)
    assert c["departments"] == ["dairy eggs", "produce"]
    assert c["aisles_by_department"]["dairy eggs"] == ["milk", "yogurt"]
    assert c["days"][0] == "Sunday" and c["hour_bands"] == ["Morning", "Afternoon", "Evening", "Night"]


def test_a_missing_result_file_names_the_command_to_make_it(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "RESULTS_DIR", tmp_path)
    with pytest.raises(data.ResultMissing, match="python mining/segmentation.py"):
        data.load_result("segment_profiles.csv")
    (tmp_path / "benchmark.csv").write_text("level,algorithm\naisle,apriori\n")
    assert data.load_result("benchmark.csv").shape == (1, 2)


def test_every_result_file_the_dashboard_reads_is_in_the_repo():
    """The contract says these files are committed so the dashboard works on every laptop."""
    for name in data.RESULT_FILES:
        assert (data.RESULTS_DIR / name).exists(), name


def test_result_columns_match_the_shared_contract():
    rules = pd.read_csv(data.RESULTS_DIR / "rules_product.csv")
    assert list(rules.columns) == ["antecedents", "consequents", "antecedent_support", "consequent_support",
                                   "support", "confidence", "lift", "algorithm", "interpretation"]
    seg = pd.read_csv(data.RESULTS_DIR / "segment_profiles.csv")
    assert {"segment", "users", "share_of_users", "avg_total_orders", "avg_basket_size",
            "avg_days_between_orders", "avg_reorder_ratio", "avg_recency_days", "description"} == set(seg.columns)
    assert list(pd.read_csv(data.RESULTS_DIR / "segment_pca_sample.csv").columns) == ["user_key", "pc1", "pc2", "segment"]
    assert list(pd.read_csv(data.RESULTS_DIR / "reorder_metrics.csv").columns) == [
        "model", "precision", "recall", "f1", "roc_auc", "threshold", "n_train_rows", "n_test_rows"]
    assert list(pd.read_csv(data.RESULTS_DIR / "reorder_feature_importance.csv").columns) == ["model", "feature", "importance"]
    assert list(pd.read_csv(data.RESULTS_DIR / "benchmark.csv").columns) == [
        "level", "algorithm", "min_support", "n_transactions", "n_itemsets", "runtime_seconds", "peak_memory_mb"]


# ---------------------------------------------------------------------------
# Part 2: every page, run headless on the real data
# ---------------------------------------------------------------------------
PAGES = [
    "app.py",
    "views/1_OLAP_Explorer.py",
    "views/2_Basket_Rules.py",
    "views/3_Customer_Segments.py",
    "views/4_Reorder_Model.py",
]


def run_page(name: str) -> AppTest:
    return AppTest.from_file(str(DASHBOARD / name), default_timeout=120).run()


@pytest.mark.parametrize("page", PAGES)
def test_every_page_runs_without_an_error(warehouse, page):
    at = run_page(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_overview_shows_the_real_numbers(warehouse):
    at = run_page("app.py")
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Orders"] == "3,421,083"
    assert metrics["Users"] == "206,209"
    assert metrics["Products"] == "49,688"
    assert metrics["Reorder rate"] == "59.0%"
    assert metrics["Average basket"].startswith("10.11")


def test_olap_page_reacts_to_a_filter(warehouse):
    at = run_page("views/1_OLAP_Explorer.py")
    assert not at.exception
    at.sidebar.checkbox[0].check().run()   # weekend only
    assert not at.exception, [e.value for e in at.exception]
    assert "weekend" in " ".join(s.value for s in at.sidebar.success)


def test_cube_tab_highlights_a_slice(warehouse):
    at = run_page("views/1_OLAP_Explorer.py")
    cube_metric = next(m for m in at.metric if m.label == "Cells in the cube")
    assert cube_metric.value == "588"                                  # 21 departments x 7 days x 4 hour bands
    pick = next(w for w in at.multiselect if w.key and w.key.startswith("cube_pick_1_"))   # the day axis
    pick.set_value(["Sunday"]).run()
    assert not at.exception, [e.value for e in at.exception]
    labels = {m.label: m.value for m in at.metric}
    assert labels["Cells in a slice"] == "84"                          # 21 x 1 x 4
    assert labels["Order lines in a slice"] == "6,533,692"             # all Sunday order lines (section 2)


def test_rules_page_search(warehouse):
    at = run_page("views/2_Basket_Rules.py")
    at.text_input[0].input("pasta").run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("rules" in m.value for m in at.markdown)   # the "N of M rules" line


def test_segments_page_names_the_four_segments(warehouse):
    at = run_page("views/3_Customer_Segments.py")
    labels = " ".join(e.label for e in at.expander)
    for name in ("Loyal frequent shopper", "Occasional small basket"):
        assert name in labels
