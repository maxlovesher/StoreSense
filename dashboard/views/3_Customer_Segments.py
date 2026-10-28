"""
Dashboard page 4: Customer Segments.

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

One card per segment, how each segment differs from the average user, the PCA
picture of the K-Means clusters (one small panel per segment) and the profile table.
Reads the result files of mining/segmentation.py, so it needs no database.
"""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard import ui

st.set_page_config(page_title="Customer Segments - StoreSense", page_icon=":material/groups:", layout="wide")
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
table = profiles.sort_values("users", ascending=False)
order = table["segment"].tolist()
colors = {name: color for name, color in zip(order, ui.SERIES)}   # largest segment first, in the fixed slot order

# --- one card per segment ----------------------------------------------------------------------------------
total_users = int(profiles["users"].sum())
for col, (_, seg) in zip(st.columns(len(table)), table.iterrows()):
    with col.container(border=True):
        st.markdown(f"<span style='color:{colors[seg['segment']]};font-size:1.3em'>&#9679;</span> "
                    f"**{seg['segment']}**", unsafe_allow_html=True)
        st.metric("share of users", f"{seg['share_of_users']:.1%}")
        st.markdown(f"{int(seg['users']):,} users  \n"
                    f"**{seg['avg_total_orders']:.0f}** orders, one every **{seg['avg_days_between_orders']:.0f}** days  \n"
                    f"**{seg['avg_basket_size']:.1f}** items per basket  \n"
                    f"**{seg['avg_reorder_ratio']:.0%}** of items reordered")
        st.caption(ACTIONS.get(seg["segment"], ""))

# --- how they differ ------------------------------------------------------------------------------------------
st.subheader("How do they differ from the average user?")
features = {"avg_total_orders": "orders", "avg_basket_size": "items per basket",
            "avg_reorder_ratio": "reorder ratio", "avg_recency_days": "last gap (days)"}
weights = profiles["users"] / profiles["users"].sum()
index = profiles.set_index("segment")[list(features)]
overall = (index.mul(weights.values, axis=0)).sum()
relative = (index / overall * 100).rename(columns=features).reset_index().melt(
    id_vars="segment", var_name="feature", value_name="index")
fig = px.bar(relative, x="feature", y="index", color="segment", barmode="group", color_discrete_map=colors,
             category_orders={"segment": order}, labels={"index": "index (average user = 100)", "feature": ""},
             text=relative["index"].round().astype(int))
fig.update_traces(textposition="outside", cliponaxis=False,
                  hovertemplate="%{x}<br><b>%{y:.0f}</b> (average = 100)<extra>%{fullData.name}</extra>")
fig.add_hline(y=100, line_dash="dot", line_color="#6b7a8c")
fig.update_layout(margin=dict(t=40), height=380)
ui.chart(fig)
st.caption(f"100 = the average of all {total_users:,} users. 200 means twice the average.")

# --- the clusters, one panel per segment --------------------------------------------------------------------
st.subheader("The segments in two dimensions")
fig = make_subplots(rows=1, cols=len(order), shared_xaxes=True, shared_yaxes=True, horizontal_spacing=0.02,
                    subplot_titles=order)
for i, name in enumerate(order, start=1):
    others = sample[sample["segment"] != name]
    mine = sample[sample["segment"] == name]
    fig.add_trace(go.Scattergl(x=others["pc1"], y=others["pc2"], mode="markers", hoverinfo="skip", showlegend=False,
                               marker=dict(size=3, color=ui.OTHER, opacity=0.25)), row=1, col=i)
    fig.add_trace(go.Scattergl(x=mine["pc1"], y=mine["pc2"], mode="markers", name=name, showlegend=False,
                               marker=dict(size=3.5, color=colors[name], opacity=0.7),
                               hovertemplate=name + "<br>PC1 %{x:.2f}, PC2 %{y:.2f}<extra></extra>"), row=1, col=i)
fig.update_annotations(font_size=13)
fig.update_xaxes(title_text="PC1", showgrid=False)
fig.update_yaxes(showgrid=False)
fig.update_yaxes(title_text="PC2", row=1, col=1)
fig.update_layout(height=360, margin=dict(t=40))
ui.chart(fig)
st.caption(f"A random sample of {len(sample):,} users projected onto the first two principal components (PCA); "
           "each panel shows one segment in colour over all the others in grey. The frequent shoppers sit clearly apart "
           "and the small-basket group sits at the bottom, but the two middle groups overlap: shoppers are a continuum "
           "and K-Means cuts it into pieces.")

# --- profiles ---------------------------------------------------------------------------------------------
st.subheader("Segment profiles")
st.dataframe(
    table.drop(columns="description").assign(share_of_users=table["share_of_users"] * 100,
                                             avg_reorder_ratio=table["avg_reorder_ratio"] * 100),
    hide_index=True,
    column_config={
        "users": st.column_config.NumberColumn(format="localized"),
        "share_of_users": st.column_config.NumberColumn("share of users", format="%.1f%%"),
        "avg_total_orders": st.column_config.NumberColumn("orders", format="%.1f"),
        "avg_basket_size": st.column_config.NumberColumn("items per basket", format="%.1f"),
        "avg_days_between_orders": st.column_config.NumberColumn("days between orders", format="%.1f"),
        "avg_reorder_ratio": st.column_config.NumberColumn("reorder ratio", format="%.0f%%"),
        "avg_recency_days": st.column_config.NumberColumn("last gap (days)", format="%.1f"),
    },
)

st.subheader("What would a store do?")
for _, row in table.iterrows():
    with st.expander(f"{row['segment']} ({row['share_of_users']:.1%} of users)"):
        st.write(row["description"])
        st.write("**Idea:** " + ACTIONS.get(row["segment"], "No standard action is written for this segment yet."))
