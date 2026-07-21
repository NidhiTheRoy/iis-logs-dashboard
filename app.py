"""Website Visitor Analytics — bots vs real people, and what the people did.

Answers the brief directly:
  - How many REAL PEOPLE visited (not requests)
  - Which traffic is automated, and which bots
  - What those people actually looked at (real pages, not APIs)
  - How they behaved (pages per visit, duration, bounce, entry pages)

Deploy on Streamlit Community Cloud with a secret named NEON_DSN.
"""
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Visitor Analytics", layout="wide")

BLUE, GREY, GREEN, AMBER = "#2E75B6", "#9AA0A6", "#548235", "#C88A00"
engine = create_engine(st.secrets["NEON_DSN"])


@st.cache_data(ttl=600)
def q(sql):
    with engine.connect() as c:
        return pd.read_sql(text(sql), c)


daily = q("SELECT * FROM gold_daily_summary ORDER BY event_date")
bots = q("SELECT bot_name, SUM(requests) AS requests FROM gold_bot_breakdown "
         "GROUP BY bot_name ORDER BY requests DESC")
pages = q("SELECT cs_uri_stem, page_category, SUM(views) AS views, SUM(visits) AS visits "
          "FROM gold_top_pages GROUP BY cs_uri_stem, page_category "
          "ORDER BY views DESC LIMIT 20")
cats = q("SELECT page_category, SUM(views) AS views, SUM(visits) AS visits "
         "FROM gold_page_categories GROUP BY page_category ORDER BY views DESC")
sess = q("SELECT pages_viewed, duration_sec, is_bounce, entry_page FROM gold_sessions")
funnel = q("SELECT funnel_market, SUM(visitors) AS visitors, SUM(events) AS events "
           "FROM gold_funnel GROUP BY funnel_market ORDER BY visitors DESC LIMIT 10")

# ---------------------------------------------------------------- headline nums
visitors = int(daily["visitors"].sum())
visits = int(daily["visits"].sum())
page_views = int(daily["page_views"].sum())
human_req = int(daily["human_requests"].sum())
bot_req = int(daily["bot_requests"].sum())
total_req = int(daily["total_requests"].sum())
bot_pct = bot_req / total_req * 100 if total_req else 0

st.title("Website Visitor Analytics")
st.caption("Real people vs automated traffic, and what the real people did. "
           "Counts below are **people and visits**, not raw server requests.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Real visitors", f"{visitors:,}",
          help="Distinct people (browsers), excluding bots. Not request counts.")
c2.metric("Visits", f"{visits:,}",
          help="Distinct sessions. One person can visit more than once.")
c3.metric("Pages viewed", f"{page_views:,}",
          help="Actual content pages loaded by humans — excludes images, APIs and tracking calls.")
c4.metric("Automated traffic", f"{bot_pct:.0f}%",
          delta=f"{bot_req:,} of {total_req:,} requests", delta_color="off")

st.info(f"**Why these numbers are smaller than raw request counts:** the servers logged "
        f"{total_req:,} requests, but one page view triggers many requests (images, scripts, "
        f"API and tracking calls). Only **{page_views:,}** were real pages a person looked at, "
        f"from **{visitors:,}** distinct people.")

st.divider()

# ---------------------------------------------------------------- bots vs human
left, right = st.columns([1, 1.2])
with left:
    st.subheader("Bots vs real people")
    fig = go.Figure(go.Pie(labels=["Real people", "Automated"],
                           values=[human_req, bot_req], hole=.6,
                           marker_colors=[BLUE, GREY], sort=False, textinfo="percent"))
    fig.update_layout(height=290, margin=dict(t=6, b=6, l=6, r=6),
                      legend=dict(orientation="h", y=-.08))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"**{bot_pct:.0f}% of all server traffic is automated.** Any analysis based on "
               "raw traffic without removing this is materially wrong.")

with right:
    st.subheader("Which bots, and what they cost us")
    if len(bots):
        bfig = px.bar(bots.head(10), x="requests", y="bot_name", orientation="h",
                      color_discrete_sequence=[GREY],
                      labels={"requests": "Requests", "bot_name": ""})
        bfig.update_layout(height=290, margin=dict(t=6, b=6, l=6, r=6),
                           yaxis=dict(autorange="reversed"))
        st.plotly_chart(bfig, use_container_width=True)
        st.caption("Search engines and SEO crawlers are expected. Large volumes from "
                   "unidentified sources are worth investigating — they consume capacity "
                   "and distort analytics.")

st.divider()

# ---------------------------------------------------------------- what they did
st.subheader("What did real people actually do?")
s1, s2, s3, s4 = st.columns(4)
if len(sess):
    s1.metric("Pages per visit", f"{sess['pages_viewed'].mean():.1f}")
    med_dur = sess.loc[sess["duration_sec"] > 0, "duration_sec"].median()
    s2.metric("Typical visit length", f"{(med_dur or 0)/60:.1f} min")
    s3.metric("Bounced (1 page only)", f"{sess['is_bounce'].mean()*100:.0f}%",
              help="Visits where the person viewed a single page and left")
    engaged = (sess["pages_viewed"] >= 3).mean() * 100
    s4.metric("Engaged visits (3+ pages)", f"{engaged:.0f}%")

st.caption("These describe **behaviour per visit** — the clickstream view of how people "
           "move through the site, not how many files the server sent.")

st.divider()

# ---------------------------------------------------------------- content
cl, cr = st.columns([1, 1.2])
with cl:
    st.subheader("What kind of content?")
    if len(cats):
        cfig = px.bar(cats, x="views", y="page_category", orientation="h",
                      color_discrete_sequence=[BLUE],
                      labels={"views": "Page views", "page_category": ""})
        cfig.update_layout(height=330, margin=dict(t=6, b=6, l=6, r=6),
                           yaxis=dict(autorange="reversed"))
        st.plotly_chart(cfig, use_container_width=True)
        st.caption("The mix of content people look at — home plans, communities, "
                   "search pages — showing what visitors come for.")

with cr:
    st.subheader("Most-viewed pages (real pages only)")
    t = pages.head(12).rename(columns={
        "cs_uri_stem": "Page", "page_category": "Type",
        "views": "Views", "visits": "Visits"})
    t["Views"] = t["Views"].map(lambda v: f"{int(v):,}")
    t["Visits"] = t["Visits"].map(lambda v: f"{int(v):,}")
    st.dataframe(t.reset_index(drop=True), use_container_width=True, hide_index=True)
    st.caption("Images, scripts, API calls and tracking beacons are excluded — these are "
               "pages a person genuinely opened.")

st.divider()

# ---------------------------------------------------------------- markets
st.subheader("Which markets attract the most people?")
if len(funnel):
    funnel["label"] = "Market " + funnel["funnel_market"].astype(str)
    ffig = px.bar(funnel, x="visitors", y="label", orientation="h",
                  color_discrete_sequence=[GREEN],
                  labels={"visitors": "Distinct visitors", "label": ""})
    ffig.update_layout(height=350, margin=dict(t=6, b=6, l=6, r=6),
                       yaxis=dict(autorange="reversed"))
    st.plotly_chart(ffig, use_container_width=True)
    st.caption("Ranked by **distinct people**, not event counts — so one very active user "
               "cannot make a market look more popular than it is.")

st.divider()

# ---------------------------------------------------------------- trend
st.subheader("Visitors by day")
d = daily.copy()
d["day"] = pd.to_datetime(d["event_date"]).dt.strftime("%b %d")
dfig = px.bar(d, x="day", y="visitors", color_discrete_sequence=[BLUE],
              labels={"visitors": "Real visitors", "day": ""})
dfig.update_layout(height=300, margin=dict(t=6, b=6, l=6, r=6))
st.plotly_chart(dfig, use_container_width=True)
st.caption("Only days present in the data are shown. Bars, not a line — we don't invent "
           "traffic across gaps between log files.")

st.divider()
with st.expander("How these numbers are calculated"):
    st.markdown("""
**Real visitor** — a distinct browser identified by the Google Analytics client id in the
cookie, after removing automated traffic. Not a request count.

**Visit (session)** — a distinct `ASP.NET_SessionId`. One person may have several visits.

**Page view** — a request classified as real page content. Static assets (images, CSS, JS,
fonts), backend API calls (`/ajax/`, `/signalr/`, `/googleanalytics/`) and tracking beacons
(`/eventlogger/`) are excluded, because none of them is a person looking at a page.

**Bot** — flagged when the user agent declares a crawler, when one IP makes an unusually
high number of requests in a day, or when a request has no cookie, no referer and is not a
page. The reason for each flag is stored so any classification can be audited.

*Limitation:* visitors are counted from cookies, so a person blocking cookies or using
several devices may be counted more than once or not at all. Session-based counts are the
more reliable measure.
""")
