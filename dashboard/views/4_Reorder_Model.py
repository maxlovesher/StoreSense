"""
Dashboard page 5: Reorder Model (stretch goal).

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

Metrics of the two reorder models, the feature importance of the better one, and a
threshold explorer: pick a probability threshold and see the confusion matrix,
precision, recall and F1 that it gives on the test users. Reads the result files of
mining/reorder_model.py, so it needs no database.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard import ui
from dashboard.data import FIGURES_DIR

MODEL_NAMES = {"logistic_regression": "Logistic Regression", "lightgbm": "LightGBM"}
MODEL_COLORS = {"Logistic Regression": "#8a96a5", "LightGBM": ui.SERIES[0]}   # baseline in grey
PRECISION_COLOR, RECALL_COLOR = ui.SERIES[1], ui.SERIES[2]


def with_rates(curve: pd.DataFrame) -> pd.DataFrame:
    tp, fp, fn = curve["tp"], curve["fp"], curve["fn"]
    precision = tp / (tp + fp)   # undefined (NaN, a gap in the chart) when nothing is flagged
    recall = tp / (tp + fn)
    f1 = (2 * precision * recall / (precision + recall)).fillna(0)
    return curve.assign(precision=precision, recall=recall, f1=f1, flagged=tp + fp)


st.set_page_config(page_title="Reorder Model - StoreSense", page_icon=":material/autorenew:", layout="wide")
st.title("Reorder Model")
st.caption("Will a customer buy a product again in their latest order? The label is built from the user's latest "
           "(train) order, and every feature comes from their earlier (prior) orders only, so the answer never leaks into the inputs.")

try:
    metrics = ui.load_result("reorder_metrics.csv")
    importance = ui.load_result("reorder_feature_importance.csv")
    curve = with_rates(ui.load_result("reorder_threshold_curve.csv"))
except FileNotFoundError as error:
    ui.stop_on_missing(error)
metrics = metrics.assign(name=metrics["model"].map(MODEL_NAMES).fillna(metrics["model"]))

best = metrics.sort_values("roc_auc", ascending=False).iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Best model", best["name"], border=True)
c2.metric("ROC-AUC", f"{best['roc_auc']:.3f}", help="0.5 = random guessing, 1.0 = perfect.", border=True)
c3.metric("Precision", f"{best['precision']:.1%}", border=True,
          help="Of the products we predict will be reordered, the share that really are.")
c4.metric("Recall", f"{best['recall']:.1%}", help="Of the products really reordered, the share we find.", border=True)
st.caption(f"Evaluated on {int(best['n_test_rows']):,} user-product pairs of users the model never saw "
           f"(the split is by user). The probability threshold ({best['threshold']:.2f} for this model) was chosen on separate validation users.")

# --- threshold explorer --------------------------------------------------------------------------------------
st.subheader("Try a different threshold")
s1, s2 = st.columns([1, 2])
model_name = s1.radio("Model", list(metrics.sort_values("roc_auc", ascending=False)["name"]), horizontal=True)
row = metrics[metrics["name"] == model_name].iloc[0]
chosen = round(float(row["threshold"]), 2)
threshold = s2.slider("Predict a reorder when the model's probability is at least", 0.01, 0.99, chosen, 0.01,
                      key=f"threshold_{row['model']}",
                      help=f"The threshold chosen on the validation users is {row['threshold']:.3f}.")
model_curve = curve[curve["model"] == row["model"]].sort_values("threshold")
at = model_curve.iloc[(model_curve["threshold"] - threshold).abs().argmin()]
total = int(at[["tp", "fp", "fn", "tn"]].sum())

k1, k2, k3, k4 = st.columns(4)
k1.metric("Precision", "n/a" if pd.isna(at["precision"]) else f"{at['precision']:.1%}", border=True,
          help="Of the products flagged as reorders, the share that really were.")
k2.metric("Recall", f"{at['recall']:.1%}", help="Of the real reorders, the share flagged.", border=True)
k3.metric("F1", f"{at['f1']:.3f}", help="The balance of precision and recall.", border=True)
k4.metric("Products flagged", f"{int(at['flagged']):,}", help=f"Out of {total:,} user-product pairs.", border=True)

left, right = st.columns(2, gap="large")
with left:
    st.markdown("**Confusion matrix on the test users**")
    counts = [[int(at["tn"]), int(at["fp"])], [int(at["fn"]), int(at["tp"])]]
    names = [["correctly left out", "wrongly flagged"], ["missed reorders", "correctly flagged"]]
    fig = go.Figure(go.Heatmap(
        z=counts, x=["predicted: no reorder", "predicted: reorder"], y=["actual: no reorder", "actual: reorder"],
        colorscale=ui.BLUES, showscale=False, xgap=3, ygap=3,
        text=[[f"<b>{n:,}</b><br>{name}<br>{n / total:.1%}" for n, name in zip(r, nr)] for r, nr in zip(counts, names)],
        texttemplate="%{text}", textfont=dict(size=13), hoverinfo="skip"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(side="top", showgrid=False)
    fig.update_layout(height=320, margin=dict(t=30, l=10, r=10, b=10))
    ui.chart(fig)
with right:
    st.markdown("**Precision and recall at every threshold**")
    long = model_curve.melt(id_vars="threshold", value_vars=["precision", "recall"], var_name="measure", value_name="value")
    fig = px.line(long, x="threshold", y="value", color="measure",
                  color_discrete_map={"precision": PRECISION_COLOR, "recall": RECALL_COLOR},
                  labels={"threshold": "probability threshold", "value": ""})
    fig.update_traces(line_width=2, hovertemplate="%{y:.1%}<extra>%{fullData.name}</extra>")
    fig.add_vline(x=threshold, line_dash="dot", line_color="#18212d",
                  annotation_text=f"your threshold {threshold:.2f}", annotation_position="bottom right")
    fig.add_vline(x=row["threshold"], line_color=ui.OTHER, line_width=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.02])
    fig.update_layout(height=320, hovermode="x unified", margin=dict(t=30))
    ui.chart(fig)
st.caption("A lower threshold flags more products: it finds more of the real reorders (recall up) but more of the "
           "flags are wrong (precision down). The grey line is the threshold chosen on the validation users.")

# --- models and features --------------------------------------------------------------------------------------
left, right = st.columns(2, gap="large")
with left:
    st.subheader("The two models compared")
    long = metrics.melt(id_vars="name", value_vars=["precision", "recall", "f1", "roc_auc"],
                        var_name="metric", value_name="score")
    long["metric"] = long["metric"].map({"precision": "Precision", "recall": "Recall", "f1": "F1", "roc_auc": "ROC-AUC"})
    fig = px.bar(long, x="metric", y="score", color="name", barmode="group", range_y=[0, 1], text_auto=".2f",
                 color_discrete_map=MODEL_COLORS, labels={"metric": "", "score": "", "name": ""})
    fig.update_traces(textposition="outside")
    fig.update_layout(margin=dict(t=30), height=360)
    ui.chart(fig)
    st.dataframe(metrics.drop(columns="name"), hide_index=True)
with right:
    st.subheader("What drives a reorder?")
    imp = importance.sort_values("importance")
    fig = px.bar(imp, x="importance", y="feature", orientation="h", text=imp["importance"].map("{:.0%}".format))
    fig.update_traces(marker_color=ui.SERIES[0], textposition="outside", cliponaxis=False)
    fig.update_layout(margin=dict(t=10), xaxis_tickformat=".0%", yaxis_title="", height=420,
                      xaxis_range=[0, imp["importance"].max() * 1.15])
    ui.chart(fig)
    st.caption(f"Importance of each feature in the better model ({MODEL_NAMES.get(importance['model'].iloc[0], importance['model'].iloc[0])}); "
               "the shares add up to 100%.")

roc = FIGURES_DIR / "reorder_roc.png"
if roc.exists():
    with st.expander("ROC curve on the test users"):
        st.image(str(roc), width=480)

with st.expander("How to read these numbers"):
    st.markdown(
        "- **Why not accuracy?** Only about 1 pair in 10 is a real reorder. A model that always says \"no\" is about 90% accurate and finds nothing, "
        "so we judge the models on precision, recall, F1 and ROC-AUC.\n"
        "- **The top features** are how recently the customer bought the product and how often. Habit decides a reorder much more than who the customer is.\n"
        "- **The gain from LightGBM is small.** It beats Logistic Regression by about 0.007 ROC-AUC, on one split and without tuning.\n"
        "- **Only products bought before** are candidates, so the model cannot predict a first-time purchase."
    )
