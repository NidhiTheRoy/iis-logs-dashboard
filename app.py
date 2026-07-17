"""IIS Web Logs — stakeholder dashboard.

Reads Gold aggregates from Neon Postgres and presents them in plain language:
percentages, context, and readable labels instead of raw counts and field names.

Deploy on Streamlit Community Cloud with a secret named NEON_DSN.
"""
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Web Traffic Analytics", layout="wide")

BLUE = "#2E75B6"
GREEN = "#548235"
AMBER = "#C88A00"
RED = "#C0392B"
GREY = "#8A8A8A"

engine = create_engine(st.secrets["NEON_DSN"])


@st.cache_data(ttl=600)
def q(sql):
    with engine.connect() as c:
        return pd.read_sql(text(sql), c)


traffic = q("SELECT * FROM gold_traffic_hourly")
status = q("SELECT sc_status, SUM(cnt) AS total FROM gold_status_daily GROUP BY sc_status")
pages = q("SELECT cs_uri_stem, SUM(views) AS views FROM gold_top_pages GROUP BY cs_uri_stem")
funnel = q("SELECT funnel_market, SUM(events) AS events, SUM(unique_visitors) AS visitors "
           "FROM gold_funnel GROUP BY funnel_market")

total_requests = int(traffic["requests"].sum())
bot_requests = int(traffic["bot_requests"].sum())
bot_pct = (bot_requests / total_requests * 100) if total_requests else 0
human_requests = total_requests - bot_requests
avg_latency_s = traffic["avg_time_ms"].mean() / 1000 if len(traffic) else 0

total_status = int(status["total"].sum()) if len(status) else 0


def status_band(df, lo, hi):
    m = (df["sc_status"] >= lo) & (df["sc_status"] < hi)
    return int(df.loc[m, "total"].sum())


success = status_band(status, 200, 300)
redirect = status_band(status, 300, 400)
client_err = status_band(status, 400, 500)
server_err = status_band(status, 500, 600)
success_pct = (success / total_status * 100) if total_status else 0
error_pct = ((client_err + server_err) / total_status * 100) if total_status else 0
n_days = traffic["event_date"].nunique() if "event_date" in traffic else 0

st.title("Web Traffic Analytics")
st.caption(f"newhomesource.com web server logs \u00b7 {n_days} days of data \u00b7 "
           f"{total_requests:,} total requests")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total requests", f"{total_requests/1e6:.2f}M")
k2.metric("Real visitors", f"{human_requests/1e6:.2f}M",
          help="Requests from humans, excluding bots and crawlers")
k3.metric("Bot traffic", f"{bot_pct:.0f}%",
          delta=f"{bot_requests:,} requests", delta_color="off",
          help="Share of all traffic from crawlers, monitors and scrapers")
latency_flag = "\u2705" if avg_latency_s < 1 else "\u26a0\ufe0f"
k4.metric("Avg response time", f"{avg_latency_s:.2f}s {latency_flag}",
          help="Under 1s is good; higher suggests slow endpoints")

st.divider()

left, right = st.columns([1, 1.3])
with left:
    st.subheader("Who is visiting?")
    donut = go.Figure(go.Pie(
        labels=["Real visitors", "Bots & crawlers"],
        values=[human_requests, bot_requests],
        hole=0.6, marker_colors=[BLUE, GREY],
        textinfo="percent", sort=False))
    donut.update_layout(showlegend=True, height=300, margin=dict(t=10, b=10, l=10, r=10),
                        legend=dict(orientation="h", y=-0.1))
    st.plotly_chart(donut, use_container_width=True)
    st.caption(f"**{bot_pct:.0f}% of traffic is automated.** Nearly "
               f"{'a third' if bot_pct>28 else 'a quarter'} of requests are not real "
               "people \u2014 worth accounting for in any traffic or conversion analysis.")

with right:
    st.subheader("Is the site healthy?")
    h1, h2, h3 = st.columns(3)
    h1.metric("Successful", f"{success_pct:.1f}%")
    h2.metric("Redirects", f"{redirect/total_status*100:.1f}%" if total_status else "\u2014")
    h3.metric("Errors", f"{error_pct:.1f}%",
              delta="healthy" if error_pct < 2 else "elevated",
              delta_color="normal" if error_pct < 2 else "inverse")
    health = pd.DataFrame({
        "Outcome": ["Success (2xx)", "Redirect (3xx)", "Client error (4xx)", "Server error (5xx)"],
        "Requests": [success, redirect, client_err, server_err],
    })
    bar = px.bar(health, x="Requests", y="Outcome", orientation="h",
                 color="Outcome",
                 color_discrete_sequence=[GREEN, BLUE, AMBER, RED])
    bar.update_layout(showlegend=False, height=230, margin=dict(t=10, b=10, l=10, r=10),
                      yaxis_title="", xaxis_title="")
    st.plotly_chart(bar, use_container_width=True)
    st.caption(f"**{success_pct:.0f}% of requests succeed.** Errors are "
               f"{'within a normal range' if error_pct < 2 else 'higher than ideal and worth a look'}.")

st.divider()

st.subheader("Traffic by day")
daily = (traffic.groupby("event_date")["requests"].sum().reset_index()
         .sort_values("event_date"))
daily["event_date"] = pd.to_datetime(daily["event_date"]).dt.strftime("%b %d")
dbar = px.bar(daily, x="event_date", y="requests", color_discrete_sequence=[BLUE])
dbar.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10),
                   xaxis_title="", yaxis_title="Requests")
st.plotly_chart(dbar, use_container_width=True)
st.caption("Each bar is one full day of logs. Only days present in the data are shown \u2014 "
           "gaps between files are intentionally not connected.")

st.divider()

st.subheader("What content gets the most views?")
NOISE = ("/signalr", "/googleanalytics", "/getadparameters", "/ajax",
         "/setutmparameters", "/gettypeaheadoptions", "/segment", "/eventlogger")


def is_page(path):
    p = str(path).lower()
    return not any(p.startswith(n) for n in NOISE)


real_pages = pages[pages["cs_uri_stem"].apply(is_page)].copy()
show_all = st.toggle("Include tracking & API endpoints", value=False,
                     help="On: shows every request path including backend calls. "
                          "Off: shows only real content pages.")
table = (pages if show_all else real_pages).sort_values("views", ascending=False).head(10)
table = table.rename(columns={"cs_uri_stem": "Page", "views": "Views"})
table["Views"] = table["Views"].map(lambda v: f"{int(v):,}")
st.dataframe(table.reset_index(drop=True), use_container_width=True, hide_index=True)
st.caption("Backend and tracking calls are hidden by default so this reflects actual "
           "pages visitors look at. Toggle above to see all endpoints.")

st.divider()

st.subheader("Which markets drive the most engagement?")
top_markets = funnel.sort_values("events", ascending=False).head(10).copy()
top_markets["label"] = "Market " + top_markets["funnel_market"].astype(str)
mbar = px.bar(top_markets, x="events", y="label", orientation="h",
              color_discrete_sequence=[BLUE],
              labels={"events": "Engagement events", "label": ""})
mbar.update_layout(height=380, margin=dict(t=10, b=10, l=10, r=10),
                   yaxis=dict(autorange="reversed"))
st.plotly_chart(mbar, use_container_width=True)
st.caption("Top 10 markets by engagement events (from the site's own activity beacons). "
           "Market IDs shown as-is \u2014 mapping them to market names would make this even "
           "clearer if a lookup is available.")

st.divider()
st.caption("Data refreshes automatically as new log files are processed. "
           "Built on Databricks (processing) \u2192 Neon (serving) \u2192 Streamlit (this view).")
