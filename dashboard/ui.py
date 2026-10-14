"""
Small helpers shared by every dashboard page: cached queries and friendly errors.

Owner: Member 6 (Dashboard & Integration)

Each query is cached by Streamlit (the same filters give the same answer without
asking the warehouse again). Result files are cached for 60 seconds, so a freshly
re-run mining script shows up within a minute without restarting the app.
"""
import streamlit as st

from dashboard import data

kpis = st.cache_data(show_spinner=False)(data.kpis)
orders_by_hour = st.cache_data(show_spinner=False)(data.orders_by_hour)
department_totals = st.cache_data(show_spinner=False)(data.department_totals)
choices = st.cache_data(show_spinner=False)(data.choices)
olap_group = st.cache_data(show_spinner="Querying the warehouse...")(data.olap_group)
olap_rollup = st.cache_data(show_spinner="Querying the warehouse...")(data.olap_rollup)
olap_pivot = st.cache_data(show_spinner="Querying the warehouse...")(data.olap_pivot)
olap_cube = st.cache_data(show_spinner="Building the cube...")(data.olap_cube)
load_result = st.cache_data(ttl=60, show_spinner=False)(data.load_result)


def stop_on_missing(error: Exception) -> None:
    """Show a plain message (what is missing, and the command that fixes it) and stop the page."""
    if isinstance(error, data.ResultMissing):
        st.warning(str(error))
    else:
        st.error(f"{error}\n\nBuild the warehouse first: `python etl/load.py`")
    st.stop()


def fmt_int(n: float) -> str:
    return f"{int(round(n)):,}"
