"""
Small helpers shared by every dashboard page: cached queries, friendly errors and one chart style.

Owner: Member 6 (Dashboard & Integration)

Each query is cached by Streamlit (the same filters give the same answer without
asking the warehouse again). Result files are cached for 60 seconds, so a freshly
re-run mining script shows up within a minute without restarting the app.

Every chart is drawn with chart(), which applies the "storesense" Plotly template below:
the same font, grid, legend position and colours on every page.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from dashboard import data

# ---------------------------------------------------------------------------
# Colours. The categorical slots are in a fixed order that was checked for colour-blind
# readers (adjacent pairs); a colour always belongs to the same thing, never to a rank.
# ---------------------------------------------------------------------------
ACCENT = "#1d4e89"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
OTHER = "#b4bcc6"           # every category beyond the named ones, and context marks
BLUES = [[0.0, "#eef4fc"], [0.15, "#cde2fb"], [0.3, "#9ec5f4"], [0.45, "#6da7ec"],
         [0.6, "#3987e5"], [0.75, "#256abf"], [0.88, "#184f95"], [1.0, "#0d366b"]]   # one hue, light to dark

# The seven biggest departments keep one colour on every page; the other fourteen share grey.
DEPARTMENT_COLORS = dict(zip(["produce", "dairy eggs", "snacks", "beverages", "frozen", "pantry", "bakery"], SERIES))


def department_colors(names) -> dict:
    return {n: DEPARTMENT_COLORS.get(n, OTHER) for n in names}


pio.templates["storesense"] = go.layout.Template(layout=dict(
    font=dict(family='"Source Sans", "Source Sans Pro", "Source Sans 3", "Segoe UI", sans-serif',
              size=13, color="#3b4859"),
    colorway=SERIES,
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#e8edf3", linecolor="#cfd8e3", zerolinecolor="#cfd8e3", ticks="", title_standoff=8),
    yaxis=dict(gridcolor="#e8edf3", linecolor="#cfd8e3", zerolinecolor="#cfd8e3", ticks="", title_standoff=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""),
    hoverlabel=dict(bgcolor="white", bordercolor="#cfd8e3", font=dict(color="#18212d", size=13)),
    margin=dict(l=10, r=10, t=30, b=10),
    coloraxis=dict(colorscale=BLUES),
    barcornerradius=4,
))
pio.templates.default = "plotly_white+storesense"


def chart(fig, **kwargs) -> None:
    """Draw a Plotly figure in the StoreSense style (Streamlit's own chart theme would replace the colours)."""
    st.plotly_chart(fig, theme=None, config={"displaylogo": False,
                                             "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]},
                    **kwargs)

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
        st.error(f"{error}\n\nBuild the warehouse (`python etl/load.py`), or the demo extract from it "
                 "(`python dashboard/build_demo_data.py`).")
    st.stop()


def fmt_int(n: float) -> str:
    return f"{int(round(n)):,}"
