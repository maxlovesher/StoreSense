"""
Dashboard page 2: OLAP Explorer.

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

Roll-up / drill-down along the product or time hierarchy, slice and dice with
sidebar filters, and a pivot heatmap. Every number is a live query on the
warehouse (order lines = one product in one order, there are no prices).
"""
import plotly.express as px
import streamlit as st

from dashboard import ui
from dashboard.data import DIMENSIONS, PRODUCT_HIERARCHY, TIME_HIERARCHY

st.set_page_config(page_title="OLAP Explorer - StoreSense", layout="wide")
st.title("OLAP Explorer")
st.caption("Roll up, drill down, slice, dice and pivot the order lines. "
           "Use the filters in the sidebar: one filter is a **slice**, several together are a **dice**.")

try:
    options = ui.choices()
except FileNotFoundError as error:
    ui.stop_on_missing(error)

# --- sidebar: slice and dice -----------------------------------------------------------
st.sidebar.header("Slice and dice")
departments = st.sidebar.multiselect("Department", options["departments"])
aisle_pool = sorted({a for d in (departments or options["departments"]) for a in options["aisles_by_department"][d]})
aisles = st.sidebar.multiselect("Aisle", aisle_pool, help="Choices follow the departments picked above.")
days = st.sidebar.multiselect("Day of week", options["days"])
bands = st.sidebar.multiselect("Hour band", options["hour_bands"])
weekend = st.sidebar.checkbox("Weekend only")
filters = {"departments": departments, "aisles": aisles, "days": days, "hour_bands": bands, "weekend_only": weekend}
active = [name for name, on in (("department", departments), ("aisle", aisles), ("day", days),
                                ("hour band", bands), ("weekend", weekend)) if on]
if active:
    st.sidebar.success(f"Active filters: {', '.join(active)}")
else:
    st.sidebar.info("No filters: the whole warehouse.")

roll_tab, cut_tab, pivot_tab = st.tabs(["Roll-up and drill-down", "Slice and dice", "Pivot heatmap"])

# --- roll-up / drill-down ----------------------------------------------------------------
with roll_tab:
    hierarchy_name = st.radio("Hierarchy", ["Product (department > aisle > product)", "Time (hour band > hour)"], horizontal=True)
    full = PRODUCT_HIERARCHY if hierarchy_name.startswith("Product") else TIME_HIERARCHY
    depth = st.select_slider("Level of detail", options=list(range(1, len(full) + 1)), value=min(2, len(full)),
                             format_func=lambda n: " > ".join(full[:n]),
                             help="Lower the level to roll up, raise it to drill down.")
    levels = full[:depth]

    if levels == PRODUCT_HIERARCHY and not (departments or aisles):
        st.info("A product-level view has about 50,000 rows. Pick a department or an aisle in the sidebar to drill into it.")
    else:
        rolled = ui.olap_rollup(levels, filters)
        grand = int(rolled.loc[rolled["level"] == "grand total", "order_lines"].iloc[0])
        st.metric("Order lines in this view (grand total)", ui.fmt_int(grand))
        detail = rolled[rolled["level"] == levels[-1]].head(30)
        fig = px.bar(detail, x="order_lines", y=levels[-1], orientation="h",
                     color=levels[0] if len(levels) > 1 else None,
                     labels={"order_lines": "order lines"})
        fig.update_layout(yaxis=dict(categoryorder="total ascending"), margin=dict(t=10), height=min(900, 120 + 22 * len(detail)))
        st.plotly_chart(fig)
        st.caption("The 30 biggest rows at the chosen level.")
        st.markdown("**The full roll-up table**: detail rows, a subtotal for every higher level, and the grand total.")
        st.dataframe(rolled, hide_index=True,
                     column_config={"order_lines": st.column_config.NumberColumn("order lines", format="%d")})

# --- slice and dice ------------------------------------------------------------------------
with cut_tab:
    group_by = st.multiselect("Group the order lines by", list(DIMENSIONS), default=["Department"],
                              max_selections=2)
    if not group_by:
        st.info("Pick one or two dimensions to group by.")
    else:
        cut = ui.olap_group(group_by, filters, limit=500)
        st.metric("Order lines in the current slice or dice", ui.fmt_int(cut["order_lines"].sum()),
                  help="Rows beyond the top 500 groups are not counted here.")
        x = group_by[0]
        fig = px.bar(cut.head(40), x=x, y="order_lines", color=group_by[1] if len(group_by) > 1 else None,
                     labels={"order_lines": "order lines"})
        fig.update_layout(margin=dict(t=10))
        st.plotly_chart(fig)
        st.dataframe(cut, hide_index=True)

# --- pivot ---------------------------------------------------------------------------------
with pivot_tab:
    c1, c2, c3 = st.columns(3)
    row_dim = c1.selectbox("Rows", list(DIMENSIONS), index=0)
    col_dim = c2.selectbox("Columns", [d for d in DIMENSIONS if d != row_dim], index=2)
    top_rows = c3.slider("Show the biggest rows", 5, 40, 20)
    if DIMENSIONS[row_dim][1] == "p" and row_dim == "Product" and not (departments or aisles):
        st.info("Pick a department or an aisle in the sidebar first: there are about 50,000 products.")
    else:
        matrix = ui.olap_pivot(row_dim, col_dim, filters, top_rows)
        fig = px.imshow(matrix, aspect="auto", color_continuous_scale="Blues", text_auto=".3s",
                        labels={"x": col_dim, "y": row_dim, "color": "order lines"})
        fig.update_layout(margin=dict(t=10), height=max(350, 28 * len(matrix) + 120))
        st.plotly_chart(fig)
        with st.expander("The numbers behind the heatmap"):
            st.dataframe(matrix)
