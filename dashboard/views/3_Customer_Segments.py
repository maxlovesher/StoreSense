"""
Dashboard page 4: Customer Segments.

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

Segment sizes, profiles and a 2-D (PCA) scatter plot of the K-Means clusters.
Reads the result files of mining/segmentation.py, so it needs no database.
"""
import plotly.express as px
import streamlit as st

from dashboard import ui

st.set_page_config(page_title="Customer Segments - StoreSense", layout="wide")
st.title("Customer Segments")
st.caption("K-Means on four features per user: how long the gap before the last order was (recency proxy), "
           "total orders, average basket size and reorder ratio. There are no dates or prices in the data, "
           "so recency and basket size are proxies.")

try:
    profiles = ui.load_result("segment_profiles.csv")
    sample = ui.load_result("segment_pca_sample.csv")
except FileNotFoundError as error:
    ui.stop_on_missing(error)

# What a store could do for each segment (the names come from mining/segmentation.py).
ACTIONS = {
    "Loyal frequent shopper": "Protect them: a buy-it-again list, a standing order or loyalty reward, and no stock-outs on their usual items.",
    "Infrequent big-basket shopper": "Win them back sooner: a reminder or offer around the three-week mark, free delivery above a basket value, multipack deals.",
    "Regular mid-frequency shopper": "Cross-sell and build the habit: recommendations from the basket rules, and a suggested weekly list.",
    "Occasional small basket": "Low-cost nudges: a minimum-order incentive or a suggestion to add one more item.",
}
order = profiles.sort_values("users", ascending=False)["segment"].tolist()
colors = {name: color for name, color in zip(order, px.colors.qualitative.Safe)}

# --- sizes and what they mean ---------------------------------------------------------------------
total_users = int(profiles["users"].sum())
c1, c2 = st.columns([1, 1])
with c1:
    st.subheader("How big is each segment?")
    fig = px.bar(profiles.sort_values("users"), x="users", y="segment", orientation="h", color="segment",
                 color_discrete_map=colors, text=profiles.sort_values("users")["share_of_users"].map("{:.1%}".format))
    fig.update_layout(showlegend=False, margin=dict(t=10), yaxis_title="")
    st.plotly_chart(fig)
    st.caption(f"{total_users:,} users in total.")

with c2:
    st.subheader("How do they differ from the average user?")
    features = {"avg_total_orders": "orders", "avg_basket_size": "items per basket",
                "avg_reorder_ratio": "reorder ratio", "avg_recency_days": "last gap (days)"}
    weights = profiles["users"] / profiles["users"].sum()
    index = profiles.set_index("segment")[list(features)]
    overall = (index.mul(weights.values, axis=0)).sum()
    relative = (index / overall * 100).rename(columns=features).reset_index().melt(
        id_vars="segment", var_name="feature", value_name="index")
    fig = px.bar(relative, x="feature", y="index", color="segment", barmode="group", color_discrete_map=colors,
                 labels={"index": "index (average user = 100)"})
    fig.add_hline(y=100, line_dash="dot")
    fig.update_layout(margin=dict(t=10), legend_title_text="")
    st.plotly_chart(fig)
    st.caption("100 = the average of all users. 200 means twice the average.")

# --- scatter --------------------------------------------------------------------------------------------
st.subheader("The segments in two dimensions")
fig = px.scatter(sample, x="pc1", y="pc2", color="segment", color_discrete_map=colors, opacity=0.5,
                 category_orders={"segment": order}, labels={"pc1": "PC1", "pc2": "PC2"})
fig.update_traces(marker=dict(size=4))
fig.update_layout(margin=dict(t=10), legend_title_text="", height=520)
st.plotly_chart(fig)
st.caption(f"A random sample of {len(sample):,} users projected onto the first two principal components (PCA). "
           "The frequent shoppers sit clearly apart and the small-basket group sits at the bottom, "
           "but the two middle groups overlap: shoppers are a continuum and K-Means cuts it into pieces.")

# --- profiles ---------------------------------------------------------------------------------------------
st.subheader("Segment profiles")
table = profiles.sort_values("users", ascending=False)
st.dataframe(
    table.drop(columns="description"), hide_index=True,
    column_config={
        "users": st.column_config.NumberColumn(format="%d"),
        "share_of_users": st.column_config.NumberColumn("share of users", format="%.3f"),
        "avg_total_orders": st.column_config.NumberColumn("orders", format="%.1f"),
        "avg_basket_size": st.column_config.NumberColumn("items per basket", format="%.1f"),
        "avg_days_between_orders": st.column_config.NumberColumn("days between orders", format="%.1f"),
        "avg_reorder_ratio": st.column_config.NumberColumn("reorder ratio", format="%.2f"),
        "avg_recency_days": st.column_config.NumberColumn("last gap (days)", format="%.1f"),
    },
)

st.subheader("What would a store do?")
for _, row in table.iterrows():
    with st.expander(f"{row['segment']} ({row['share_of_users']:.1%} of users)"):
        st.write(row["description"])
        st.write("**Idea:** " + ACTIONS.get(row["segment"], "No standard action is written for this segment yet."))
