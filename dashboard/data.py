"""
Data access for the dashboard: every query and every result file it shows.

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

The pages only draw things; all SQL and file reading lives here, so it can be
tested without a browser. The warehouse is opened read-only for each query, so
the dashboard never blocks the one script that writes to it (segmentation).

Result files written by the mining modules (see handoff/PHASE4_SHARED_CONTRACT.md)
are read from reports/results/. If one is missing, load_result() raises
ResultMissing with the command that creates it, and the page shows that message.
"""
import pandas as pd

from common.db import PROJECT_ROOT, get_connection

RESULTS_DIR = PROJECT_ROOT / "reports" / "results"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

DAY_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
BAND_ORDER = ["Morning", "Afternoon", "Evening", "Night"]

# What each result file is called and which command writes it.
RESULT_FILES = {
    "rules_aisle.csv": "python mining/association_rules.py",
    "rules_product.csv": "python mining/association_rules.py",
    "benchmark.csv": "python mining/benchmark.py",
    "segment_profiles.csv": "python mining/segmentation.py",
    "segment_pca_sample.csv": "python mining/segmentation.py",
    "reorder_metrics.csv": "python mining/reorder_model.py",
    "reorder_feature_importance.csv": "python mining/reorder_model.py",
}


class ResultMissing(FileNotFoundError):
    """A result file has not been created yet."""


def load_result(name: str) -> pd.DataFrame:
    path = RESULTS_DIR / name
    if not path.exists():
        raise ResultMissing(f"{name} not found. Create it with: {RESULT_FILES.get(name, 'the mining script')}")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Warehouse queries
# ---------------------------------------------------------------------------
def run_query(sql: str, params: list | None = None, con=None) -> pd.DataFrame:
    """Run one read-only query. Pass con to reuse a connection (tests do), else open and close one."""
    own = con is None
    con = con or get_connection(read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        if own:
            con.close()


def kpis(con=None) -> dict:
    """The five headline numbers of the Overview page."""
    row = run_query("""
        SELECT (SELECT COUNT(*) FROM fact_order)                               AS orders,
               (SELECT COUNT(*) FROM dim_user)                                 AS users,
               (SELECT COUNT(*) FROM dim_product)                              AS products,
               (SELECT AVG(basket_size) FROM fact_order WHERE basket_size > 0) AS avg_basket_size,
               (SELECT AVG(reordered) FROM fact_order_line)                    AS reorder_rate
    """, con=con).iloc[0]
    return row.to_dict()


def orders_by_hour(con=None) -> pd.DataFrame:
    """Order lines for every day-of-week and hour slot (168 rows), for the Overview charts."""
    return run_query("""
        SELECT t.day_name, t.order_dow, t.order_hour_of_day AS hour, COUNT(*) AS order_lines
        FROM fact_order_line l JOIN dim_time t ON l.time_key = t.time_key
        GROUP BY t.day_name, t.order_dow, t.order_hour_of_day
        ORDER BY t.order_dow, hour
    """, con=con)


def department_totals(con=None) -> pd.DataFrame:
    return run_query("""
        SELECT p.department, COUNT(*) AS order_lines,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_lines
        FROM fact_order_line l JOIN dim_product p ON l.product_key = p.product_key
        GROUP BY p.department ORDER BY order_lines DESC
    """, con=con)


# ---------------------------------------------------------------------------
# OLAP Explorer: one small query builder instead of five fixed queries
#
# Column names and tables come from the DIMENSIONS whitelist below, and every
# value the user picks goes in as a ? parameter, so nothing typed on the page
# is ever pasted into the SQL text.
# ---------------------------------------------------------------------------
# label -> (SQL expression, table alias it needs)
DIMENSIONS = {
    "Department": ("p.department", "p"),
    "Aisle": ("p.aisle", "p"),
    "Product": ("p.product_name", "p"),
    "Day of week": ("t.day_name", "t"),
    "Hour band": ("t.hour_band", "t"),
    "Hour of day": ("t.order_hour_of_day", "t"),
}
PRODUCT_HIERARCHY = ["Department", "Aisle", "Product"]
TIME_HIERARCHY = ["Hour band", "Hour of day"]

_JOINS = {
    "p": "JOIN dim_product p ON l.product_key = p.product_key",
    "t": "JOIN dim_time t ON l.time_key = t.time_key",
}


def _filters_sql(filters: dict | None) -> tuple[str, list, set]:
    """WHERE clause, its parameters and the tables it needs, from the page's filter choices."""
    filters = filters or {}
    clauses, params, needs = [], [], set()
    for key, column, alias in (
        ("departments", "p.department", "p"),
        ("aisles", "p.aisle", "p"),
        ("days", "t.day_name", "t"),
        ("hour_bands", "t.hour_band", "t"),
    ):
        values = list(filters.get(key) or [])
        if values:
            clauses.append(f"{column} IN ({', '.join('?' * len(values))})")
            params += values
            needs.add(alias)
    if filters.get("weekend_only"):
        clauses.append("t.is_weekend")
        needs.add("t")
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params, needs


def _from_sql(dims: list[str], extra_needs: set) -> str:
    needs = {DIMENSIONS[d][1] for d in dims} | extra_needs
    return "FROM fact_order_line l " + " ".join(_JOINS[a] for a in ("p", "t") if a in needs)


def olap_group(dims: list[str], filters: dict | None = None, limit: int | None = None, con=None) -> pd.DataFrame:
    """Order lines grouped by the chosen dimensions (slice and dice come from the filters)."""
    where, params, needs = _filters_sql(filters)
    cols = [DIMENSIONS[d][0] for d in dims]
    select = ", ".join(f"{c} AS \"{d}\"" for c, d in zip(cols, dims))
    sql = (f"SELECT {select}, COUNT(*) AS order_lines, "
           f"ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_lines "
           f"{_from_sql(dims, needs)}{where} GROUP BY {', '.join(cols)} ORDER BY order_lines DESC")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return run_query(sql, params, con)


def rollup_level_names(levels: list[str]) -> dict[int, str]:
    """
    Names for the GROUPING() bit mask of ROLLUP (a, b, c): 0 is a detail row, 1 is
    the subtotal over c ('b total', the rows of level b), 3 is 'a total', and
    all bits set is the grand total.
    """
    n = len(levels)
    names = {0: levels[-1]}
    for i in range(1, n):
        names[2 ** i - 1] = f"{levels[n - 1 - i]} total"
    names[2 ** n - 1] = "grand total"
    return names


def olap_rollup(levels: list[str], filters: dict | None = None, con=None) -> pd.DataFrame:
    """
    ROLLUP over a hierarchy (for example Department, Aisle): the detail rows, a
    subtotal for each level above them, and a grand total. 'level' says which.
    """
    where, params, needs = _filters_sql(filters)
    cols = [DIMENSIONS[d][0] for d in levels]
    select = ", ".join(f"{c} AS \"{d}\"" for c, d in zip(cols, levels))
    case = " ".join(f"WHEN {m} THEN '{name}'" for m, name in rollup_level_names(levels).items())
    sql = (f"SELECT CASE GROUPING({', '.join(cols)}) {case} END AS level, {select}, COUNT(*) AS order_lines "
           f"{_from_sql(levels, needs)}{where} GROUP BY ROLLUP ({', '.join(cols)}) "
           f"ORDER BY GROUPING({', '.join(cols)}) DESC, order_lines DESC")
    return run_query(sql, params, con)


def olap_pivot(row_dim: str, col_dim: str, filters: dict | None = None, top_rows: int = 25, con=None) -> pd.DataFrame:
    """
    A pivot table: row_dim down the side, col_dim across the top, order lines in the cells.
    If row_dim has many values (aisles, products) only the top_rows biggest are kept.
    """
    long = olap_group([row_dim, col_dim], filters, con=con)
    totals = long.groupby(row_dim)["order_lines"].sum().sort_values(ascending=False)
    keep = list(totals.index[:top_rows])
    matrix = long[long[row_dim].isin(keep)].pivot_table(
        index=row_dim, columns=col_dim, values="order_lines", aggfunc="sum", fill_value=0)
    matrix = matrix.loc[keep]
    if col_dim == "Day of week":
        matrix = matrix.reindex(columns=[d for d in DAY_ORDER if d in matrix.columns])
    elif col_dim == "Hour band":
        matrix = matrix.reindex(columns=[b for b in BAND_ORDER if b in matrix.columns])
    if row_dim == "Day of week":
        matrix = matrix.reindex([d for d in DAY_ORDER if d in matrix.index])
    elif row_dim == "Hour band":
        matrix = matrix.reindex([b for b in BAND_ORDER if b in matrix.index])
    elif row_dim == "Hour of day":
        matrix = matrix.sort_index()
    return matrix


def choices(con=None) -> dict:
    """The values for the filter widgets: departments, aisles per department, days and hour bands."""
    prod = run_query("SELECT DISTINCT department, aisle FROM dim_product ORDER BY department, aisle", con=con)
    return {
        "departments": sorted(prod["department"].dropna().unique()),
        "aisles_by_department": {d: sorted(g["aisle"].dropna()) for d, g in prod.groupby("department")},
        "days": DAY_ORDER,
        "hour_bands": BAND_ORDER,
    }
