"""Human Visitor Analytics — who's real, what they viewed, how long they stayed.

Reads Gold aggregates from Neon. Every headline number is about PEOPLE and VISITS,
never raw request counts.

Deploy on Streamlit Community Cloud with a secret named NEON_DSN.
requirements.txt: streamlit, pandas, plotly, sqlalchemy, psycopg2-binary
"""
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Visitor Analytics", layout="wide",
                   initial_sidebar_state="collapsed")

INK, BLUE, TEAL, GREY, AMBER = "#1B2A41", "#2E75B6", "#3AAFA9", "#9AA0A6", "#C88A00"
PALETTE = [BLUE, TEAL, AMBER, "#7B68A6", "#8CB369", GREY]

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; max-width: 1400px;}
  [data-testid="stMetricValue"] {font-size: 2.1rem; font-weight: 600;}
  [data-testid="stMetricLabel"] {color: #6B7280; font-size: .82rem;
      text-transform: uppercase; letter-spacing: .04em;}
  h1 {font-weight: 700; letter-spacing: -.02em;}
  h3 {margin-top: .4rem; font-weight: 600;}
  .caption {color:#6B7280; font-size:.86rem; margin-top:-.5rem;}
</style>
""", unsafe_allow_html=True)

engine = create_engine(st.secrets["NEON_DSN"], pool_pre_ping=True)


@st.cache_data(ttl=600)
def q(sql):
    try:
        with engine.connect() as c:
            return pd.read_sql(text(sql), c)
    except Exception:
        return pd.DataFrame()


def chart(fig, h=320):
    fig.update_layout(
        height=h, margin=dict(t=10, b=10, l=10, r=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, sans-serif", size=12),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(0,0,0,.06)"))
    return fig


def cap(t):
    st.markdown(f"<p class='caption'>{t}</p>", unsafe_allow_html=True)


# ------------------------------------------------------------------ load
daily = q("SELECT * FROM gold_daily_summary ORDER BY event_date")
bots = q("SELECT bot_name, SUM(requests) AS requests, SUM(source_ips) AS ips "
         "FROM gold_bot_breakdown WHERE bot_name IS NOT NULL "
         "GROUP BY bot_name ORDER BY requests DESC")
sect = q("SELECT page_category, SUM(views) AS views, SUM(visits) AS visits, "
         "SUM(total_minutes_spent) AS minutes, AVG(avg_time_on_page_sec) AS avg_sec "
         "FROM gold_section_engagement GROUP BY page_category")
perf = q("SELECT endpoint_group, page_category, SUM(views) AS views, "
         "SUM(visitors) AS visitors, AVG(avg_time_on_page_sec) AS avg_sec, "
         "AVG(exit_rate_pct) AS exit_pct FROM gold_page_performance "
         "GROUP BY endpoint_group, page_category ORDER BY views DESC LIMIT 25")
sess = q("SELECT pages_viewed, visit_duration_sec, is_bounce, sections_visited "
         "FROM gold_sessions")
src = q("SELECT arrived_from, SUM(visits) AS visits, "
        "AVG(avg_pages_per_visit) AS pages, AVG(bounce_rate_pct) AS bounce "
        "FROM gold_traffic_sources GROUP BY arrived_from ORDER BY visits DESC LIMIT 10")
dev = q("SELECT device_type, SUM(visits) AS visits FROM gold_devices "
        "GROUP BY device_type ORDER BY visits DESC")
funnel = q("SELECT funnel_market, SUM(visitors) AS visitors, SUM(events) AS events "
           "FROM gold_funnel GROUP BY funnel_market ORDER BY visitors DESC LIMIT 12")

if daily.empty:
    st.error("No data returned from Neon. Check the NEON_DSN secret and that "
             "04_load_neon has run.")
    st.stop()

visitors = int(daily["visitors"].sum())
visits = int(daily["visits"].sum())
page_views = int(daily["page_views"].sum())
bot_req = int(daily["bot_requests"].sum())
human_req = int(daily["human_requests"].sum())
total_req = int(daily["total_requests"].sum())
bot_pct = bot_req / total_req * 100 if total_req else 0
has_time = not sect.empty and sect["minutes"].notna().any()

# ------------------------------------------------------------------ header
st.title("Visitor Analytics")
st.markdown(f"<p class='caption'>Real people and what they did — automated traffic, "
            f"page assets and API calls removed &nbsp;·&nbsp; {len(daily)} days</p>",
            unsafe_allow_html=True)
st.write("")

k = st.columns(5)
k[0].metric("Real people", f"{visitors:,}")
k[1].metric("Visits", f"{visits:,}")
k[2].metric("Pages viewed", f"{page_views:,}")
if not sess.empty:
    k[3].metric("Pages per visit", f"{sess['pages_viewed'].mean():.1f}")
    k[4].metric("Avg visit", f"{sess['visit_duration_sec'].mean()/60:.1f} min")

st.info(f"Servers logged **{total_req:,}** requests, but one page view fires many "
        f"(images, scripts, APIs, tracking). Only **{page_views:,}** were pages a "
        f"person opened, from **{visitors:,}** people across **{visits:,}** visits. "
        f"**{bot_pct:.0f}%** of all traffic was automated.")

st.divider()

# ------------------------------------------------------------------ bots
st.subheader("Bots vs real people")
a, b = st.columns([1, 1.4])
with a:
    f = go.Figure(go.Pie(labels=["Real people", "Automated"],
                         values=[human_req, bot_req], hole=.62,
                         marker_colors=[BLUE, GREY], sort=False,
                         textinfo="percent", textfont_size=15))
    f.update_layout(showlegend=True, legend=dict(orientation="h", y=-.05))
    st.plotly_chart(chart(f, 300), use_container_width=True)
with b:
    if not bots.empty:
        f = px.bar(bots.head(8), x="requests", y="bot_name", orientation="h",
                   color_discrete_sequence=[GREY],
                   labels={"requests": "Requests", "bot_name": ""})
        f.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(chart(f, 300), use_container_width=True)
cap("Search and SEO crawlers are expected. Large unidentified volumes consume "
    "capacity and distort any traffic analysis that doesn't exclude them.")

st.divider()

# ------------------------------------------------------------------ attention
st.subheader("What attracts and holds human attention")
if has_time:
    a, b = st.columns(2)
    with a:
        d = sect.dropna(subset=["minutes"]).sort_values("minutes", ascending=False).head(10)
        f = px.bar(d, x="minutes", y="page_category", orientation="h",
                   color_discrete_sequence=[TEAL],
                   labels={"minutes": "Total minutes spent", "page_category": ""})
        f.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(chart(f, 340), use_container_width=True)
        cap("<b>Total human time</b> per section — the clearest measure of what the "
            "site is actually used for.")
    with b:
        d = sect.dropna(subset=["avg_sec"]).sort_values("avg_sec", ascending=False).head(10)
        f = px.bar(d, x="avg_sec", y="page_category", orientation="h",
                   color_discrete_sequence=[BLUE],
                   labels={"avg_sec": "Avg seconds per page", "page_category": ""})
        f.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(chart(f, 340), use_container_width=True)
        cap("<b>Average dwell time</b> — high means content that holds attention; "
            "very low may mean people didn't find what they wanted.")
else:
    if not sect.empty:
        d = sect.sort_values("views", ascending=False).head(10)
        f = px.bar(d, x="views", y="page_category", orientation="h",
                   color_discrete_sequence=[TEAL],
                   labels={"views": "Page views", "page_category": ""})
        f.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(chart(f, 340), use_container_width=True)
    st.warning("Time-on-page could not be measured yet. It needs visits where a "
               "person viewed two or more pages — load more log files and it will "
               "populate. Sections are ranked by page views instead.")

st.divider()

# ------------------------------------------------------------------ behaviour
st.subheader("How people behave in a visit")
if not sess.empty:
    m = st.columns(4)
    m[0].metric("Bounced (1 page)", f"{sess['is_bounce'].mean()*100:.0f}%")
    m[1].metric("Engaged (3+ pages)", f"{(sess['pages_viewed']>=3).mean()*100:.0f}%")
    med = sess.loc[sess["visit_duration_sec"] > 0, "visit_duration_sec"].median()
    m[2].metric("Median visit", f"{(med or 0)/60:.1f} min")
    m[3].metric("Sections per visit", f"{sess['sections_visited'].mean():.1f}")

    a, b = st.columns([1.3, 1])
    with a:
        bk = pd.cut(sess["pages_viewed"], [0, 1, 2, 5, 10, 1e9],
                    labels=["1 page", "2", "3-5", "6-10", "10+"])
        bc = bk.value_counts().reindex(["1 page", "2", "3-5", "6-10", "10+"]).reset_index()
        bc.columns = ["Pages viewed", "Visits"]
        f = px.bar(bc, x="Pages viewed", y="Visits", color_discrete_sequence=[BLUE])
        st.plotly_chart(chart(f, 300), use_container_width=True)
        cap("Visit depth — how far people get before leaving.")
    with b:
        if not dev.empty:
            f = go.Figure(go.Pie(labels=dev["device_type"], values=dev["visits"],
                                 hole=.55, marker_colors=PALETTE, textinfo="percent"))
            f.update_layout(legend=dict(orientation="h", y=-.05))
            st.plotly_chart(chart(f, 300), use_container_width=True)
            cap("What real people browse on.")

st.divider()

# ------------------------------------------------------------------ pages
st.subheader("Pages people actually viewed")
if not perf.empty:
    t = perf.copy()
    t["avg_sec"] = t["avg_sec"].round(1)
    t["exit_pct"] = t["exit_pct"].round(1)
    t = t.rename(columns={"endpoint_group": "Page", "page_category": "Section",
                          "views": "Views", "visitors": "People",
                          "avg_sec": "Avg time (s)", "exit_pct": "Exit rate %"})
    st.dataframe(t.head(15).reset_index(drop=True),
                 use_container_width=True, hide_index=True)
cap("URLs are grouped — every <code>/plan/...</code> becomes <code>/plan/{slug}</code> — "
    "so popular sections aren't split into thousands of single-view rows. "
    "A high exit rate means people commonly leave from there.")

st.divider()

# ------------------------------------------------------------------ sources + markets
a, b = st.columns(2)
with a:
    st.subheader("Where people arrive from")
    if not src.empty:
        t = src.copy()
        t["pages"] = t["pages"].round(1)
        t["bounce"] = t["bounce"].round(1)
        t = t.rename(columns={"arrived_from": "Source", "visits": "Visits",
                              "pages": "Pages/visit", "bounce": "Bounce %"})
        st.dataframe(t.reset_index(drop=True), use_container_width=True, hide_index=True)
    cap("<code>(direct)</code> means no referrer — typed, bookmarked, or from an app.")
with b:
    st.subheader("Markets attracting the most people")
    if not funnel.empty:
        d = funnel.copy()
        d["label"] = "Market " + d["funnel_market"].astype(str)
        f = px.bar(d, x="visitors", y="label", orientation="h",
                   color_discrete_sequence=[AMBER],
                   labels={"visitors": "Distinct people", "label": ""})
        f.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(chart(f, 360), use_container_width=True)
    cap("Ranked by <b>distinct people</b>, not event counts — one very active user "
        "can't make a market look more popular than it is.")

st.divider()

# ------------------------------------------------------------------ trend
st.subheader("Visitors by day")
d = daily.copy()
d["day"] = pd.to_datetime(d["event_date"]).dt.strftime("%b %d")
f = px.bar(d, x="day", y="visitors", color_discrete_sequence=[BLUE],
           labels={"visitors": "Real people", "day": ""})
st.plotly_chart(chart(f, 300), use_container_width=True)
cap("Bars, not a line — only days present in the data are shown, so gaps between "
    "log files aren't drawn as imaginary traffic.")

with st.expander("How these numbers are calculated, and their limits"):
    st.markdown("""
**Real person** — a distinct Google Analytics client id from the cookie, automated
traffic removed. Not a request count.

**Visit** — a distinct `ASP.NET_SessionId`. One person may visit several times.

**Page view** — a request classified as real page content. Static assets, backend API
calls and tracking beacons are excluded; none is a person looking at a page.

**Time on page** — the gap to that visitor's next page view in the same visit.
*The last page of every visit has no measurable time* — nothing follows it to close the
interval — so those views are excluded, which biases averages toward pages people
navigate away from. Gaps over 30 minutes are treated as the person having left.

**Bot** — flagged when the user agent declares a crawler, when one IP makes an unusually
high number of requests in a day, or when a request has no cookie, no referer and isn't a
page. The reason is stored per row so any classification can be audited.

**Limitation:** visitor counts depend on cookies, so cookie-blocking or multi-device use
can over- or under-count people. **Session-based figures are more reliable.**
""")
