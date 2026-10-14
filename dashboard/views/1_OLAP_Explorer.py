"""
Dashboard page 2: OLAP Explorer.

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

Roll-up / drill-down along the product or time hierarchy, slice and dice with
sidebar filters, a pivot heatmap, and a rotatable 3-D cube in which a slice or a
dice is highlighted. Every number is a live query on the warehouse (order
lines = one product in one order, there are no prices).
"""
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard import ui
from dashboard.data import CUBE_DIMENSIONS, DIMENSIONS, PRODUCT_HIERARCHY, TIME_HIERARCHY, highlight_mask


def cube_figure(cells, axes: dict, dims: list[str], mask) -> go.Figure:
    """A 3-D scatter with one ball per cube cell (size and colour = order lines), inside a wireframe box.
    Cells outside the highlighted slice or dice are drawn faint and grey."""
    position = {d: {v: i for i, v in enumerate(axes[d])} for d in dims}
    xyz = [cells[d].map(position[d]).to_numpy() for d in dims]
    lines = cells["order_lines"].to_numpy()
    size = 3 + 27 * np.sqrt(lines / max(lines.max(), 1))   # area grows with the sales
    hover = [f"{dims[0]}: {a}<br>{dims[1]}: {b}<br>{dims[2]}: {c}<br><b>{n:,} order lines</b>"
             for a, b, c, n in zip(cells[dims[0]], cells[dims[1]], cells[dims[2]], lines)]
    hover = np.array(hover)
    inside = mask.to_numpy()

    fig = go.Figure()
    if (~inside).any():
        fig.add_trace(go.Scatter3d(
            x=xyz[0][~inside], y=xyz[1][~inside], z=xyz[2][~inside], mode="markers", name="outside the selection",
            marker=dict(size=size[~inside], color="lightgrey", opacity=0.12, line=dict(width=0)),
            hovertext=hover[~inside], hoverinfo="text"))
    fig.add_trace(go.Scatter3d(
        x=xyz[0][inside], y=xyz[1][inside], z=xyz[2][inside], mode="markers",
        name="selected cells" if (~inside).any() else "cells",
        marker=dict(size=size[inside], color=lines[inside], colorscale="Viridis", opacity=0.9,
                    colorbar=dict(title="order lines"), line=dict(width=0)),
        hovertext=hover[inside], hoverinfo="text"))

    # the 12 edges of the cube, half a step outside the outermost cells
    lo, hi = -0.5, [len(axes[d]) - 0.5 for d in dims]
    corners = [(x, y, z) for x in (lo, hi[0]) for y in (lo, hi[1]) for z in (lo, hi[2])]
    edge_x, edge_y, edge_z = [], [], []
    for i, a in enumerate(corners):
        for b in corners[i + 1:]:
            if sum(p != q for p, q in zip(a, b)) == 1:   # corners that differ on one axis share an edge
                edge_x += [a[0], b[0], None]
                edge_y += [a[1], b[1], None]
                edge_z += [a[2], b[2], None]
    fig.add_trace(go.Scatter3d(x=edge_x, y=edge_y, z=edge_z, mode="lines", hoverinfo="skip",
                               line=dict(color="grey", width=2), showlegend=False))

    def axis(d):
        return dict(title=d, tickvals=list(range(len(axes[d]))), ticktext=[str(v) for v in axes[d]],
                    range=[-0.6, len(axes[d]) - 0.4])
    fig.update_layout(
        scene=dict(xaxis=axis(dims[0]), yaxis=axis(dims[1]), zaxis=axis(dims[2]), aspectmode="cube"),
        height=720, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.02),
    )
    return fig

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

roll_tab, cut_tab, pivot_tab, cube_tab = st.tabs(["Roll-up and drill-down", "Slice and dice", "Pivot heatmap", "3D cube"])

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

# --- 3-D cube ----------------------------------------------------------------------------------
with cube_tab:
    st.markdown("The data cube itself: three dimensions on three axes, and one ball per **cell** "
                "(for example *produce, Sunday, Morning*). The bigger and brighter the ball, the more order lines. "
                "Drag to rotate, scroll to zoom, hover for the numbers.")
    c1, c2, c3 = st.columns(3)
    dims = [c1.selectbox("X axis", CUBE_DIMENSIONS, index=0, key="cube_x"),
            c2.selectbox("Y axis", CUBE_DIMENSIONS, index=2, key="cube_y"),
            c3.selectbox("Z axis", CUBE_DIMENSIONS, index=3, key="cube_z")]
    if len(set(dims)) < 3:
        st.warning("Pick three different dimensions.")
    else:
        cells, axes = ui.olap_cube(dims, filters)
        st.markdown("**Highlight a slice or a dice.** Pick values on one axis for a slice, on two or three axes for a dice.")
        h1, h2, h3 = st.columns(3)
        picks = {d: col.multiselect(f"{d}", axes[d], key=f"cube_pick_{i}_{d}")   # key includes the dimension, so
                 for i, (col, d) in enumerate(zip((h1, h2, h3), dims))}          # changing an axis resets its picks
        mask = highlight_mask(cells, picks)
        n_axes = sum(bool(v) for v in picks.values())
        kind = {0: "the whole cube", 1: "a slice"}.get(n_axes, "a dice")

        st.plotly_chart(cube_figure(cells, axes, dims, mask))
        total = int(cells["order_lines"].sum())
        chosen = int(cells.loc[mask, "order_lines"].sum())
        m1, m2, m3 = st.columns(3)
        m1.metric("Cells in the cube", f"{len(cells):,}",
                  help=" x ".join(f"{len(axes[d])} {d.lower()}" for d in dims))
        m2.metric(f"Cells in {kind}", f"{int(mask.sum()):,}")
        m3.metric(f"Order lines in {kind}", ui.fmt_int(chosen), f"{chosen / total:.1%} of the cube" if total else None,
                  delta_color="off")
        st.caption("Aisle axes keep the 15 biggest aisles. The sidebar filters still apply: they change which "
                   "order lines are counted, while the picks above only highlight cells.")
