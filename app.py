import os
import pandas as pd
import streamlit as st
import plotly.express as px
from sqlalchemy import create_engine

st.set_page_config(page_title="IIS Logs Analytics", layout="wide")

DSN = st.secrets["NEON_DSN"]
engine = create_engine(DSN)

@st.cache_data(ttl=600)
def q(sql):
    return pd.read_sql(sql, engine)

st.title("IIS Web Logs — Analytics")

traffic = q("SELECT * FROM gold_traffic_hourly ORDER BY event_date, event_hour")
c1, c2, c3 = st.columns(3)
c1.metric("Total requests", f"{int(traffic['requests'].sum()):,}")
c2.metric("Bot requests", f"{int(traffic['bot_requests'].sum()):,}")
c3.metric("Avg latency (ms)", f"{traffic['avg_time_ms'].mean():.0f}")

st.subheader("Traffic by hour")
traffic["ts"] = pd.to_datetime(traffic["event_date"].astype(str)) + pd.to_timedelta(traffic["event_hour"], unit="h")
st.plotly_chart(px.line(traffic, x="ts", y="requests"), use_container_width=True)

st.subheader("Response status codes")
status = q("SELECT sc_status, SUM(cnt) AS total FROM gold_status_daily GROUP BY sc_status ORDER BY total DESC")
st.plotly_chart(px.bar(status, x="sc_status", y="total"), use_container_width=True)

st.subheader("Top pages")
pages = q("SELECT cs_uri_stem, SUM(views) AS views FROM gold_top_pages GROUP BY cs_uri_stem ORDER BY views DESC LIMIT 20")
st.dataframe(pages, use_container_width=True)

st.subheader("Engagement funnel — top markets")
funnel = q("SELECT funnel_market, SUM(events) AS events, SUM(unique_visitors) AS visitors FROM gold_funnel GROUP BY funnel_market ORDER BY events DESC LIMIT 15")
st.plotly_chart(px.bar(funnel, x="funnel_market", y="events"), use_container_width=True)
