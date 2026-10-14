"""
Streamlit dashboard: entry point (the Overview page and the page menu).

Owner: Member 6 (Dashboard & Integration)
Spec:  docs/PROJECT_BRIEF.md, section 6.6

Overview page with the headline numbers and the main shape of demand. The other
pages (OLAP Explorer, Basket Rules, Customer Segments, Reorder Model) are in
dashboard/views/ and are listed in the sidebar by st.navigation below, so the
first entry is called "Overview" instead of the file name.

Run from the project root:
    streamlit run dashboard/app.py
"""
import plotly.express as px
import streamlit as st

from dashboard import ui
from dashboard.data import DAY_ORDER


def overview() -> None:
    st.title("StoreSense")
    st.caption("Retail data warehouse and market basket analysis on the Instacart grocery data. "
               "Use the pages in the sidebar to explore the warehouse and the mining results.")

    try:
        k = ui.kpis()
        hours = ui.orders_by_hour()
        departments = ui.department_totals()
    except FileNotFoundError as error:
        ui.stop_on_missing(error)

    # --- the five headline numbers ------------------------------------------------------
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Orders", ui.fmt_int(k["orders"]))
    c2.metric("Users", ui.fmt_int(k["users"]))
    c3.metric("Products", ui.fmt_int(k["products"]))
    c4.metric("Average basket", f"{k['avg_basket_size']:.2f} items",
              help="Orders with at least one item. 75,000 test orders have no products and are left out.")
    c5.metric("Reorder rate", f"{k['reorder_rate']:.1%}",
              help="Share of order lines that are a product the user bought before.")

    # --- when and what --------------------------------------------------------------------
    left, right = st.columns(2)
    with left:
        st.subheader("When do people shop?")
        fig = px.line(hours, x="hour", y="order_lines", color="day_name",
                      category_orders={"day_name": DAY_ORDER},
                      labels={"hour": "hour of day", "order_lines": "order lines", "day_name": "day"})
        fig.update_layout(legend_title_text="", margin=dict(t=10))
        st.plotly_chart(fig)
        st.caption("Order lines = one product in one order (there are no prices). Day 0 is assumed to be Sunday.")

    with right:
        st.subheader("What do they buy?")
        top = departments.head(10).sort_values("order_lines")
        fig = px.bar(top, x="order_lines", y="department", orientation="h", text="pct_of_lines",
                     labels={"order_lines": "order lines", "department": ""})
        fig.update_traces(texttemplate="%{text}%", textposition="outside", cliponaxis=False)
        fig.update_xaxes(range=[0, top["order_lines"].max() * 1.18])   # room for the label of the longest bar
        fig.update_layout(margin=dict(t=10))
        st.plotly_chart(fig)
        st.caption("The ten biggest of the 21 departments, with their share of all order lines.")

    # --- findings that come straight from the numbers above -------------------------------
    day_totals = hours.groupby("day_name")["order_lines"].sum()
    hour_totals = hours.groupby("hour")["order_lines"].sum()
    top2 = departments.head(2)
    st.subheader("What the numbers say")
    st.markdown(
        f"- **{top2.iloc[0]['department'].title()} and {top2.iloc[1]['department'].title()}** make up "
        f"**{top2['pct_of_lines'].sum():.1f}%** of everything sold.\n"
        f"- **{day_totals.idxmax()}** is the busiest day and **{day_totals.idxmin()}** the quietest "
        f"({day_totals.max() / day_totals.min():.2f} times as busy).\n"
        f"- The busiest hour is **{int(hour_totals.idxmax())}:00**.\n"
        f"- **{k['reorder_rate']:.0%}** of order lines are products the customer has bought before."
    )
    st.info("Explore further: **OLAP Explorer** (roll-up, drill-down, slice, dice, pivot), **Basket Rules**, "
            "**Customer Segments** and **Reorder Model**.")


st.set_page_config(page_title="StoreSense", layout="wide")
pages = [
    st.Page(overview, title="Overview", default=True),
    st.Page("views/1_OLAP_Explorer.py", title="OLAP Explorer"),
    st.Page("views/2_Basket_Rules.py", title="Basket Rules"),
    st.Page("views/3_Customer_Segments.py", title="Customer Segments"),
    st.Page("views/4_Reorder_Model.py", title="Reorder Model"),
]
st.navigation(pages).run()
