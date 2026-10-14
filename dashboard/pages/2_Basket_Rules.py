"""
Dashboard page 3: Basket Rules.

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

A searchable table of association rules (aisle and product level), product
recommendations from frequently_bought_together(), and the Apriori vs FP-Growth
benchmark. Reads the result files of mining/association_rules.py and
mining/benchmark.py, so it needs no database.
"""
import plotly.express as px
import streamlit as st

from dashboard import ui
from mining.association_rules import frequently_bought_together

st.set_page_config(page_title="Basket Rules - StoreSense", layout="wide")
st.title("Basket Rules")
st.caption("What is bought together. **Support**: share of baskets with both items. "
           "**Confidence**: of the baskets with A, the share that also have B. "
           "**Lift**: how many times more often B is bought with A than by chance (1 = no link). "
           "Only rules with lift above 1 are kept.")

rules_tab, recommend_tab, bench_tab = st.tabs(["Rules table", "Recommendations", "Apriori vs FP-Growth"])

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
    min_conf = c3.slider("Minimum confidence", 0.0, 1.0, 0.0, 0.05)
    sort_by = c4.selectbox("Sort by", ["lift", "confidence", "support"])

    shown = rules[(rules["lift"] >= min_lift) & (rules["confidence"] >= min_conf)]
    if search.strip():
        text = search.strip().lower()
        shown = shown[shown["antecedents"].str.lower().str.contains(text, regex=False)
                      | shown["consequents"].str.lower().str.contains(text, regex=False)]
    shown = shown.sort_values(sort_by, ascending=False)

    st.write(f"**{len(shown):,}** of {len(rules):,} rules")
    st.dataframe(
        shown[["antecedents", "consequents", "support", "confidence", "lift", "interpretation"]],
        hide_index=True, height=420,
        column_config={
            "antecedents": "If a basket has...",
            "consequents": "...it also has",
            "support": st.column_config.NumberColumn(format="%.4f"),
            "confidence": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.2f"),
            "lift": st.column_config.NumberColumn(format="%.2f"),
            "interpretation": st.column_config.TextColumn(width="large"),
        },
    )
    st.download_button("Download these rules (CSV)", shown.to_csv(index=False), f"rules_{level}_filtered.csv", "text/csv")
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
    product = c1.selectbox("Product (the most popular first, type to search)", products)
    top_n = c2.slider("How many", 3, 15, 8)
    result = frequently_bought_together(product, top_n)
    if result.empty:
        st.info("No rule for this product.")
    else:
        st.subheader(f"Customers who buy {product} also buy")
        fig = px.bar(result.sort_values("confidence"), x="confidence", y="product", orientation="h",
                     color="lift", color_continuous_scale="Blues", hover_data=["support", "lift"],
                     labels={"confidence": "share of its baskets that also have the product"})
        fig.update_layout(margin=dict(t=10), xaxis_tickformat=".0%")
        st.plotly_chart(fig)
        st.dataframe(result, hide_index=True,
                     column_config={"confidence": st.column_config.NumberColumn(format="%.3f"),
                                    "lift": st.column_config.NumberColumn(format="%.2f"),
                                    "support": st.column_config.NumberColumn(format="%.4f")})
    st.caption("Only the 1,000 most popular products have rules, and only pairs seen often enough "
               "(min_support 0.0015 on a sample of 500,000 baskets). Sorted by confidence, then lift.")

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
        fig = px.line(d, x="min_support", y=metric, color="algorithm", markers=True, log_y=True, title=title)
        fig.update_xaxes(autorange="reversed", type="category", title="min_support (lower = more itemsets)")
        col.plotly_chart(fig)
    st.dataframe(d, hide_index=True)
    st.markdown(
        "- **Product level, low support:** FP-Growth is faster (about 3 times at `min_support` 0.0015) and ends up lighter in memory.\n"
        "- **Aisle level (132 items):** Apriori was faster and lighter at every setting. This is the opposite of the textbook result; "
        "our guess is the fixed cost of building the FP-tree in Python, which we did not test.\n"
        "- Both algorithms found exactly the same itemsets at every setting."
    )
    st.caption("Measured on 100,000 orders, itemsets capped at 3 items, Apriori in low-memory mode, one run per setting.")
