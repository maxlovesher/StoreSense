"""
Dashboard page 3: Basket Rules.

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

A searchable table of association rules (aisle and product level), product
recommendations from frequently_bought_together(), a network of the strongest
pairs, and the Apriori vs FP-Growth benchmark. Reads the result files of
mining/association_rules.py and mining/benchmark.py, so it needs no database.
"""
import math

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard import ui
from mining.association_rules import frequently_bought_together

ALGORITHM_COLORS = {"apriori": ui.SERIES[0], "fpgrowth": ui.SERIES[1]}


def pair_edges(rules: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """The strongest one-item-to-one-item links. A -> B and B -> A have the same lift, so each pair is kept once."""
    single = rules[~rules["antecedents"].str.contains(" + ", regex=False)
                   & ~rules["consequents"].str.contains(" + ", regex=False)].copy()
    single["a"] = single[["antecedents", "consequents"]].min(axis=1)
    single["b"] = single[["antecedents", "consequents"]].max(axis=1)
    pairs = (single.sort_values("confidence", ascending=False)
             .groupby(["a", "b"], as_index=False)
             .agg(lift=("lift", "max"), support=("support", "max"), confidence=("confidence", "max")))
    return pairs.sort_values(["lift", "support"], ascending=False).head(top_n)


def spring_layout(nodes: list[str], edges: pd.DataFrame, iterations: int = 400, seed: int = 42) -> dict:
    """Force-directed positions: linked items pull together, all items push apart (Fruchterman-Reingold),
    with a pull to the centre so separate groups stay close. The settings were tuned on the aisle rules for the
    widest gaps between items (fewest overlapping labels). A fixed seed keeps the picture stable."""
    index = {n: i for i, n in enumerate(nodes)}
    lo, hi = edges["lift"].min(), edges["lift"].max()
    links = [(index[a], index[b], 1 + (0 if hi == lo else (l - lo) / (hi - lo)))
             for a, b, l in zip(edges["a"], edges["b"], edges["lift"])]
    pos = np.random.default_rng(seed).uniform(-1, 1, (len(nodes), 2))
    k = math.sqrt(16.0 / len(nodes))   # the ideal distance between two items
    step = 0.2
    for _ in range(iterations):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.maximum(np.linalg.norm(delta, axis=-1), 0.01)
        np.fill_diagonal(dist, np.inf)
        move = (delta / dist[..., None] * (k * k / dist)[..., None]).sum(axis=1)   # every pair pushes apart
        for i, j, weight in links:                                                 # linked pairs pull together
            d = pos[i] - pos[j]
            length = max(float(np.linalg.norm(d)), 0.01)
            pull = d / length * (length * length / k) * weight
            move[i] -= pull
            move[j] += pull
        move -= 3.0 * pos   # pull to the centre: keeps separate groups close, so each group is not squeezed
        size = np.maximum(np.linalg.norm(move, axis=1), 0.01)
        pos += move / size[:, None] * np.minimum(size, step)[:, None]
        step = max(step * 0.985, 0.005)
    pos -= pos.mean(axis=0)
    pos /= np.abs(pos).max(axis=0)
    return {n: (float(pos[i, 0]), float(pos[i, 1])) for n, i in index.items()}


def network_figure(edges: pd.DataFrame, popularity: dict) -> go.Figure:
    nodes = sorted(set(edges["a"]) | set(edges["b"]))
    pos = spring_layout(nodes, edges)
    fig = go.Figure()
    lo, hi = edges["lift"].min(), edges["lift"].max()
    for _, e in edges.iterrows():
        strength = 0.0 if hi == lo else (e["lift"] - lo) / (hi - lo)
        (x0, y0), (x1, y1) = pos[e["a"]], pos[e["b"]]
        fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(width=1.5 + 5 * strength, color=ui.SERIES[0]), opacity=0.25 + 0.6 * strength))
    # an invisible point in the middle of each line carries its hover text
    fig.add_trace(go.Scatter(
        x=[(pos[a][0] + pos[b][0]) / 2 for a, b in zip(edges["a"], edges["b"])],
        y=[(pos[a][1] + pos[b][1]) / 2 for a, b in zip(edges["a"], edges["b"])],
        mode="markers", marker=dict(size=14, opacity=0), showlegend=False,
        hovertext=[f"<b>{a}</b> and <b>{b}</b><br>lift {l:.2f} · in {s:.2%} of baskets"
                   for a, b, l, s in zip(edges["a"], edges["b"], edges["lift"], edges["support"])],
        hoverinfo="text"))
    sizes = [popularity.get(n, 0) for n in nodes]
    top = max(sizes) or 1
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers+text", showlegend=False,
        marker=dict(size=[10 + 24 * math.sqrt(s / top) for s in sizes], color="#ffffff",
                    line=dict(width=2, color=ui.ACCENT)),
        text=[n if len(n) <= 26 else n[:24] + "…" for n in nodes], textposition="top center",
        textfont=dict(size=12, color="#18212d"),
        hovertext=[f"<b>{n}</b><br>in {popularity.get(n, 0):.1%} of baskets" for n in nodes], hoverinfo="text"))
    fig.update_xaxes(visible=False, range=[-1.2, 1.2])
    fig.update_yaxes(visible=False, range=[-1.15, 1.2])
    fig.update_layout(height=620, margin=dict(l=0, r=0, t=10, b=0))
    return fig


st.set_page_config(page_title="Basket Rules - StoreSense", page_icon=":material/shopping_basket:", layout="wide")
st.title("Basket Rules")
st.caption("What is bought together. **Support**: share of baskets with both items. "
           "**Confidence**: of the baskets with A, the share that also have B. "
           "**Lift**: how many times more often B is bought with A than by chance (1 = no link). "
           "Only rules with lift above 1 are kept.")

rules_tab, recommend_tab, network_tab, bench_tab = st.tabs(
    ["Rules table", "Recommendations", "Rule network", "Apriori vs FP-Growth"])

# --- rules table -----------------------------------------------------------------------------
with rules_tab:
    level = st.radio("Level", ["aisle", "product"], horizontal=True,
                     help="Aisle: 132 aisles. Product: the 1,000 most popular products.")
    try:
        rules = ui.load_result(f"rules_{level}.csv")
    except FileNotFoundError as error:
        ui.stop_on_missing(error)

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    search = c1.text_input("Search", placeholder="for example pasta, yogurt, banana")
    min_lift = c2.slider("Minimum lift", 1.0, float(round(rules["lift"].max(), 1)), 1.0, 0.1)
    min_conf = c3.slider("Minimum confidence", 0, 100, 0, 5, format="%d%%")
    sort_by = c4.selectbox("Sort by", ["lift", "confidence", "support"])

    shown = rules[(rules["lift"] >= min_lift) & (rules["confidence"] >= min_conf / 100)]
    if search.strip():
        text = search.strip().lower()
        shown = shown[shown["antecedents"].str.lower().str.contains(text, regex=False)
                      | shown["consequents"].str.lower().str.contains(text, regex=False)]
    shown = shown.sort_values(sort_by, ascending=False).reset_index(drop=True)
    view = shown.assign(support_pct=shown["support"] * 100, confidence_pct=shown["confidence"] * 100)

    st.write(f"**{len(shown):,}** of {len(rules):,} rules · select a row to read it in full")
    event = st.dataframe(
        view[["antecedents", "consequents", "support_pct", "confidence_pct", "lift", "interpretation"]],
        hide_index=True, height=420, on_select="rerun", selection_mode="single-row", key=f"rules_table_{level}",
        column_config={
            "antecedents": st.column_config.TextColumn("If a basket has...", width="medium"),
            "consequents": st.column_config.TextColumn("...it also has", width="medium"),
            "support_pct": st.column_config.NumberColumn("support", format="%.2f%%",
                                                         help="Share of all baskets that contain both sides."),
            "confidence_pct": st.column_config.ProgressColumn("confidence", min_value=0, max_value=100, format="%.0f%%"),
            "lift": st.column_config.NumberColumn("lift", format="%.2f"),
            "interpretation": st.column_config.TextColumn("in plain words", width="large"),
        },
    )
    picked = event.selection.rows if event is not None else []
    if picked:
        rule = shown.iloc[picked[0]]
        with st.container(border=True):
            st.markdown(f"**{rule['antecedents']}** &nbsp;→&nbsp; **{rule['consequents']}**")
            m1, m2, m3 = st.columns(3)
            m1.metric("Support", f"{rule['support']:.2%}", help="Share of all baskets that contain both sides.")
            m2.metric("Confidence", f"{rule['confidence']:.1%}", help="Of the baskets with the left side, the share with the right side.")
            m3.metric("Lift", f"{rule['lift']:.2f}", help="How many times more often than by chance.")
            st.write(rule["interpretation"])
    st.download_button("Download these rules (CSV)", shown.to_csv(index=False), f"rules_{level}_filtered.csv",
                       "text/csv", icon=":material/download:")
    st.caption("Both algorithms find the same itemsets, so each rule is listed once. The aisle file keeps the 5,000 rules with the highest lift.")

# --- recommendations ------------------------------------------------------------------------------
with recommend_tab:
    try:
        product_rules = ui.load_result("rules_product.csv")
    except FileNotFoundError as error:
        ui.stop_on_missing(error)
    singles = product_rules[~product_rules["antecedents"].str.contains(" + ", regex=False)]
    products = (singles.sort_values("antecedent_support", ascending=False)["antecedents"].drop_duplicates().tolist())
    c1, c2 = st.columns([3, 1])
    product = c1.selectbox("Product", products, help="The most popular products first. Type to search.")
    top_n = c2.slider("How many", 3, 15, 8)
    result = frequently_bought_together(product, top_n)
    if result.empty:
        st.info("No rule for this product.")
    else:
        own = singles[singles["antecedents"] == product]
        k1, k2, k3 = st.columns(3)
        k1.metric("Baskets with this product", f"{own['antecedent_support'].iloc[0]:.2%}", border=True)
        k2.metric("Products linked to it", f"{own['consequents'].nunique():,}", border=True)
        k3.metric("Strongest link (lift)", f"{own['lift'].max():.1f}", border=True)
        st.subheader(f"Customers who buy {product} also buy")
        chart_data = result.sort_values("confidence")
        fig = px.bar(chart_data, x="confidence", y="product", orientation="h",
                     text=[f"{c:.0%} · lift {l:.1f}" for c, l in zip(chart_data["confidence"], chart_data["lift"])],
                     labels={"confidence": "share of its baskets that also have the product", "product": ""})
        fig.update_traces(marker_color=ui.SERIES[0], textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}<br><b>%{x:.1%}</b> of baskets with " + product + "<extra></extra>")
        fig.update_xaxes(tickformat=".0%", range=[0, chart_data["confidence"].max() * 1.3])
        fig.update_layout(margin=dict(t=10), height=120 + 34 * len(chart_data))
        ui.chart(fig)
        with st.expander("The numbers"):
            st.dataframe(result.assign(confidence=result["confidence"] * 100, support=result["support"] * 100),
                         hide_index=True,
                         column_config={"confidence": st.column_config.NumberColumn(format="%.1f%%"),
                                        "lift": st.column_config.NumberColumn(format="%.2f"),
                                        "support": st.column_config.NumberColumn(format="%.2f%%")})
    st.caption("Only the 1,000 most popular products have rules, and only pairs seen often enough "
               "(min_support 0.0015 on a sample of 500,000 baskets). Sorted by confidence, then lift.")

# --- network --------------------------------------------------------------------------------------------
with network_tab:
    c1, c2 = st.columns([1, 2])
    net_level = c1.radio("Level", ["aisle", "product"], horizontal=True, key="net_level")
    n_pairs = c2.slider("Strongest pairs to draw", 10, 40, 24, key="net_pairs")
    try:
        net_rules = ui.load_result(f"rules_{net_level}.csv")
    except FileNotFoundError as error:
        ui.stop_on_missing(error)
    edges = pair_edges(net_rules, n_pairs)
    if edges.empty:
        st.info("No one-to-one rules at this level.")
    else:
        popularity = (net_rules.drop_duplicates("antecedents").set_index("antecedents")["antecedent_support"].to_dict())
        ui.chart(network_figure(edges, popularity))
        st.caption("Each line joins two items that are bought together more often than chance; the thicker and darker "
                   "the line, the higher the lift. A bigger circle is an item found in more baskets. "
                   "Hover over a line or a circle for the numbers.")

# --- benchmark ----------------------------------------------------------------------------------------
with bench_tab:
    try:
        bench = ui.load_result("benchmark.csv")
    except FileNotFoundError as error:
        ui.stop_on_missing(error)
    bench_level = st.radio("Level ", ["aisle", "product"], horizontal=True, key="bench_level")
    d = bench[bench["level"] == bench_level].copy()
    d["min_support"] = d["min_support"].astype(str)
    c1, c2 = st.columns(2)
    for col, metric, title in ((c1, "runtime_seconds", "Runtime of the mining step (seconds)"),
                               (c2, "peak_memory_mb", "Peak extra memory (MB)")):
        fig = px.line(d, x="min_support", y=metric, color="algorithm", markers=True, log_y=True, title=title,
                      color_discrete_map=ALGORITHM_COLORS)
        fig.update_traces(line_width=2, marker_size=8)
        fig.update_xaxes(autorange="reversed", type="category", title="min_support (lower = more itemsets)")
        fig.update_layout(title_font_size=15, legend=dict(y=1.12))
        with col:
            ui.chart(fig)
    st.dataframe(d, hide_index=True)
    st.markdown(
        "- **Product level, low support:** FP-Growth is faster (about 3 times at `min_support` 0.0015) and ends up lighter in memory.\n"
        "- **Aisle level (132 items):** Apriori was faster and lighter at every setting. This is the opposite of the textbook result; "
        "our guess is the fixed cost of building the FP-tree in Python, which we did not test.\n"
        "- Both algorithms found exactly the same itemsets at every setting."
    )
    st.caption("Measured on 100,000 orders, itemsets capped at 3 items, Apriori in low-memory mode, one run per setting.")
