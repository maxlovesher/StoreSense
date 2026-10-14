"""
Dashboard page 5: Reorder Model (stretch goal).

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

Metrics of the two reorder models and the feature importance of the better one.
Reads the result files of mining/reorder_model.py, so it needs no database.
"""
import plotly.express as px
import streamlit as st

from dashboard import ui
from dashboard.data import FIGURES_DIR

st.set_page_config(page_title="Reorder Model - StoreSense", layout="wide")
st.title("Reorder Model")
st.caption("Will a customer buy a product again in their latest order? The label is built from the user's latest "
           "(train) order, and every feature comes from their earlier (prior) orders only, so the answer never leaks into the inputs.")

try:
    metrics = ui.load_result("reorder_metrics.csv")
    importance = ui.load_result("reorder_feature_importance.csv")
except FileNotFoundError as error:
    ui.stop_on_missing(error)

best = metrics.sort_values("roc_auc", ascending=False).iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Best model", best["model"].replace("_", " "))
c2.metric("ROC-AUC", f"{best['roc_auc']:.3f}", help="0.5 = random guessing, 1.0 = perfect.")
c3.metric("Precision", f"{best['precision']:.1%}", help="Of the products we predict will be reordered, the share that really are.")
c4.metric("Recall", f"{best['recall']:.1%}", help="Of the products really reordered, the share we find.")
st.caption(f"Evaluated on {int(best['n_test_rows']):,} user-product pairs of users the model never saw "
           f"(the split is by user). The probability threshold ({best['threshold']:.2f} for this model) was chosen on separate validation users.")

left, right = st.columns(2)
with left:
    st.subheader("The two models compared")
    long = metrics.melt(id_vars="model", value_vars=["precision", "recall", "f1", "roc_auc"],
                        var_name="metric", value_name="score")
    fig = px.bar(long, x="metric", y="score", color="model", barmode="group", range_y=[0, 1], text_auto=".2f")
    fig.update_layout(margin=dict(t=10), legend_title_text="")
    st.plotly_chart(fig)
    st.dataframe(metrics, hide_index=True)
with right:
    st.subheader("What drives a reorder?")
    imp = importance.sort_values("importance")
    fig = px.bar(imp, x="importance", y="feature", orientation="h")
    fig.update_layout(margin=dict(t=10), xaxis_tickformat=".0%", yaxis_title="")
    st.plotly_chart(fig)
    st.caption(f"Importance of each feature in the better model ({importance['model'].iloc[0].replace('_', ' ')}); the shares add up to 100%.")

roc = FIGURES_DIR / "reorder_roc.png"
if roc.exists():
    st.subheader("ROC curve on the test users")
    st.image(str(roc), width=480)

with st.expander("How to read these numbers"):
    st.markdown(
        "- **Why not accuracy?** Only about 1 pair in 10 is a real reorder. A model that always says \"no\" is about 90% accurate and finds nothing, "
        "so we judge the models on precision, recall, F1 and ROC-AUC.\n"
        "- **The top features** are how recently the customer bought the product and how often. Habit decides a reorder much more than who the customer is.\n"
        "- **The gain from LightGBM is small.** It beats Logistic Regression by about 0.007 ROC-AUC, on one split and without tuning.\n"
        "- **Only products bought before** are candidates, so the model cannot predict a first-time purchase."
    )
