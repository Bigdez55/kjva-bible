# jupyter

<!-- Source: migrated from ~/.claude/skills/jupyter/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: jupyter -->

**Summary.** Python dashboard engineering with Codename JUPYTER. Covers Plotly Dash multi-page apps with callbacks, Streamlit rapid prototyping with session state, Panel/HoloViz multi-library rendering, Bokeh interactive plots, Altair declarative grammar, FastAPI hybrid backends, and production Gunicorn/Docker deployments. Trigger on: "Python dashboard", "Plotly Dash", "Streamlit app", "Panel dashboard", "Bokeh", "Altair chart", "FastAPI dashboard", "JUPYTER".

# Python Dashboard Engineering (JUPYTER)

## Core Expertise
- Plotly Dash multi-page apps with pattern-matching callbacks for dynamic KPI cards
- Streamlit rapid prototyping with st.cache_data, session_state, and fragments
- Panel/HoloViz for multi-library dashboards combining Bokeh, Plotly, and Matplotlib
- Polars and DuckDB for server-side data aggregation before sending to browser
- FastAPI + Dash hybrid architecture for API endpoints alongside interactive dashboards
- Production deployment with Gunicorn workers, Redis caching, and Docker containers

## When to Use
- Building or modifying a Python-based KPI dashboard (Dash, Streamlit, Panel)
- User references Plotly, Dash callbacks, Streamlit widgets, or Bokeh
- Data science team needs a dashboard built on their existing Python stack
- Dashboard requires heavy server-side computation (penalty calculations, forecasting)
- Rapid prototyping of a KPI display before building a full JS frontend

## Key Patterns

1. **Dash Multi-Page App with Global Store**
```python
# app.py
import dash
from dash import Dash, html, dcc, page_container

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)

app.layout = html.Div([
    html.Nav([
        html.H2("KPI Dashboard"),
        html.Div([
            dcc.Link(page["name"], href=page["relative_path"], className="nav-link")
            for page in dash.page_registry.values()
        ]),
    ], className="sidebar"),
    html.Div([page_container], className="content"),
    dcc.Store(id="global-kpi-store"),
    dcc.Interval(id="refresh-interval", interval=60_000, n_intervals=0),
])
```

2. **Dash Callback with KPI Cards**
```python
# pages/overview.py
import dash
from dash import html, callback, Input, Output
import plotly.express as px

dash.register_page(__name__, path="/", name="Overview")

layout = html.Div([
    html.Div([
        html.Div([html.H3(id="pph-value"), html.P("PPH")], className="kpi-card"),
        html.Div([html.H3(id="otp-value"), html.P("OTP")], className="kpi-card"),
        html.Div([html.H3(id="penalty-value"), html.P("Penalties")], className="kpi-card"),
    ], className="kpi-row"),
    html.Div([dcc.Graph(id="trend-chart"), dcc.Graph(id="penalty-chart")], className="chart-row"),
])

@callback(
    Output("pph-value", "children"), Output("otp-value", "children"),
    Output("penalty-value", "children"), Input("global-kpi-store", "data"),
)
def update_cards(data):
    if not data: return "---", "---", "---"
    return f"{data['pph']:.2f}", f"{data['otp']:.1f}%", f"${data['total_penalties']:,.0f}"
```

3. **Pattern-Matching Callbacks for Dynamic Components**
```python
from dash import callback, Input, Output, ALL, MATCH, ctx

@callback(
    Output({"type": "kpi-status", "index": MATCH}, "children"),
    Output({"type": "kpi-status", "index": MATCH}, "className"),
    Input({"type": "kpi-value", "index": MATCH}, "data"),
)
def update_status(value):
    kpi_name = ctx.triggered_id["index"]
    thresholds = {"pph": {"target": 1.5}, "otp": {"target": 90.0}, "late_trips": {"target": 5.0}}
    threshold = thresholds.get(kpi_name, {})
    if value >= threshold.get("target", 0):
        return "On Target", "status-badge on-target"
    return "Below Target", "status-badge below-target"
```

4. **Streamlit KPI Dashboard with Caching**
```python
import streamlit as st
import polars as pl

@st.cache_data(ttl=300, show_spinner="Loading KPI data...")
def load_kpis(month: str) -> pl.DataFrame:
    return pl.scan_parquet("data/processed/kpis_*.parquet").filter(
        pl.col("month") == month
    ).collect()

def main():
    st.set_page_config(page_title="KPI Dashboard", layout="wide")
    with st.sidebar:
        month = st.selectbox("Month", options=get_months())

    df = load_kpis(month)
    cols = st.columns(4)
    for i, metric in enumerate(compute_metrics(df)):
        with cols[i % 4]:
            st.metric(metric["label"], metric["value"], delta=f"{metric['delta']:+.1f}%")

    tab_trend, tab_penalty = st.tabs(["Trends", "Penalties"])
    with tab_trend:
        st.plotly_chart(create_trend_chart(df), use_container_width=True)
    with tab_penalty:
        st.plotly_chart(create_penalty_chart(df), use_container_width=True)
```

5. **Polars Server-Side Aggregation**
```python
import polars as pl

def compute_monthly_penalties(file_path: str) -> pl.DataFrame:
    return (
        pl.scan_parquet(file_path)
        .with_columns([
            pl.when(pl.col("late_trip_pct") > 5.0).then(10_000)
              .when(pl.col("late_trip_pct") == 0).then(-5_000)
              .otherwise(0).alias("late_penalty"),
            pl.when((pl.lit(1.5) - pl.col("pph")) >= 0.20).then(5_000)
              .otherwise(0).alias("pph_penalty"),
            pl.when((pl.col("otp") > 93.0) & (pl.col("pph") >= 1.5))
              .then((pl.col("otp") - 93.0) * 2_500)
              .otherwise(0).alias("otp_incentive"),
        ])
        .group_by("month")
        .agg([pl.col("late_penalty").sum(), pl.col("pph_penalty").sum(), pl.col("otp_incentive").sum()])
        .sort("month")
        .collect()
    )
```

6. **FastAPI + Dash Hybrid**
```python
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
from dash import Dash

api = FastAPI(title="KPI Dashboard API")

@api.get("/api/v2/kpis")
async def get_kpis(month: str = None):
    return {"status": "success", "data": await fetch_kpi_data(month)}

@api.get("/api/v2/health")
async def health():
    return {"status": "healthy"}

dash_app = Dash(__name__, requests_pathname_prefix="/dashboard/")
setup_dash_layout(dash_app)
api.mount("/dashboard", WSGIMiddleware(dash_app.server))
```

7. **Long Callback with Background Worker**
```python
from dash import callback, Input, Output, DiskcacheManager
import diskcache

cache = diskcache.Cache("./cache")
bg_manager = DiskcacheManager(cache)

@callback(
    Output("analysis-result", "children"), Input("run-btn", "n_clicks"),
    background=True, manager=bg_manager,
    running=[(Output("run-btn", "disabled"), True, False)],
    progress=[Output("progress-bar", "value"), Output("progress-bar", "max")],
    prevent_initial_call=True,
)
def run_analysis(set_progress, n_clicks):
    for step in range(100):
        perform_computation(step)
        set_progress((step + 1, 100))
    return "Analysis complete. 15 anomalies detected."
```

## Standards
- Always aggregate data server-side; never send raw DataFrames with 10K+ rows to browser
- Use Polars over Pandas for datasets exceeding 100K rows (10-100x faster)
- Dash callbacks must wrap logic in try/except and return meaningful error states
- Use long callbacks with DiskcacheManager for any operation exceeding 2 seconds
- Never store mutable global state in multi-worker Gunicorn deployments; use Redis or dcc.Store
- Streamlit apps must use @st.cache_data for expensive computations and session_state for persistence
- All user inputs (dates, ranges, strings) must be validated before processing
