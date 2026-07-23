"""Visitor Analytics — bots vs real people, and what the people did.

Reads Gold aggregates from Neon. Every headline number counts PEOPLE and VISITS,
never raw requests.

Deploy on Streamlit Community Cloud with secret NEON_DSN.
requirements.txt: streamlit, pandas, plotly, sqlalchemy, psycopg2-binary
"""
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Visitor Analytics", layout="wide",
                   initial_sidebar_state="collapsed")

# Dark palette
BG, CARD, LINE = "#0E1117", "#161B27", "rgba(255,255,255,.07)"
CYAN, VIOLET, AMBER = "#22D3EE", "#A78BFA", "#FBBF24"
EMERALD, ROSE, SLATE = "#34D399", "#FB7185", "#64748B"
TEXT, MUTED = "#E5E7EB", "#94A3B8"
SEQ = [CYAN, VIOLET, AMBER, EMERALD, ROSE, "#38BDF8", SLATE]

st.markdown(f"""
<style>
  .stApp {{ background: {BG}; }}
  .block-container {{ padding-top: 2rem; max-width: 1450px; }}
  h1, h2, h3 {{ color: {TEXT} !important; letter-spacing: -.02em; }}
  h1 {{ font-weight: 700; }}
  [data-testid="stMetric"] {{
      background: {CARD}; border: 1px solid {LINE};
      border-radius: 14px; padding: 16px 18px;
  }}
  [data-testid="stMetricValue"] {{ font-size: 1.9rem; font-weight: 650; color: {TEXT}; }}
  [data-testid="stMetricLabel"] {{
      color: {MUTED}; font-size: .74rem; text-transform: uppercase;
      letter-spacing: .07em; font-weight: 600;
  }}
  .cap {{ color: {MUTED}; font-size: .85rem; line-height: 1.5; margin-top: -.4rem; }}
  .cap b {{ color: {TEXT}; }}
  hr {{ border-color: {LINE}; }}
  [data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 12px; }}
  .banner {{
      background: linear-gradient(90deg, rgba(34,211,238,.10), rgba(167,139,250,.10));
      border: 1px solid {LINE}; border-left: 3px solid {CYAN};
      border-radius: 12px; padding: 16px 20px; color: {TEXT};
      font-size: .95rem; line-height: 1.6;
  }}
  .banner b {{ color: {CYAN}; }}
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


def style(fig, h=320, legend=False):
    fig.update_layout(
        height=h, margin=dict(t=12, b=12, l=12, r=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, sans-serif", size=12, color=MUTED),
        showlegend=legend,
        legend=dict(orientation="h", y=-.12, font=dict(color=MUTED)),
        xaxis=dict(showgrid=False, zeroline=False, color=MUTED),
        yaxis=dict(gridcolor=LINE, zeroline=False, color=MUTED),
        hoverlabel=dict(bgcolor=CARD, font_color=TEXT, bordercolor=LINE))
    return fig


def cap(t):
    st.markdown(f"<p class='cap'>{t}</p>", unsafe_allow_html=True)


# ---------------------------------------------------------------- load
daily = q("SELECT * FROM gold_daily_summary ORDER BY event_date")
bots = q("SELECT bot_name, SUM(requests) AS requests FROM gold_bot_breakdown "
         "WHERE bot_name IS NOT NULL GROUP BY bot_name ORDER BY requests DESC")
sect = q("SELECT page_category, SUM(views) AS views, SUM(visitors) AS visitors, "
         "SUM(total_minutes_spent) AS minutes, AVG(avg_time_on_page_sec) AS avg_sec "
         "FROM gold_section_engagement GROUP BY page_category")
perf = q("SELECT endpoint_group, page_category, SUM(views) AS views, "
         "SUM(visitors) AS visitors, AVG(avg_time_on_page_sec) AS avg_sec, "
         "AVG(exit_rate_pct) AS exit_pct FROM gold_page_performance "
         "GROUP BY endpoint_group, page_category ORDER BY views DESC LIMIT 25")
# has_pages filters out sessions with no page view — they distort every average.
sess = q("SELECT pages_viewed, visit_duration_sec, is_bounce, sections_visited "
         "FROM gold_sessions WHERE has_pages")
src = q("SELECT arrived_from, SUM(visits) AS visits, "
        "AVG(avg_pages_per_visit) AS pages, AVG(bounce_rate_pct) AS bounce "
        "FROM gold_traffic_sources GROUP BY arrived_from ORDER BY visits DESC LIMIT 10")
dev = q("SELECT device_type, SUM(visits) AS visits FROM gold_devices "
        "GROUP BY device_type ORDER BY visits DESC")
funnel = q("SELECT funnel_market, SUM(visitors) AS visitors FROM gold_funnel "
           "GROUP BY funnel_market ORDER BY visitors DESC LIMIT 12")

if daily.empty:
    st.error("No data from Neon — check NEON_DSN and that 04_load_neon has run.")
    st.stop()

visitors = int(daily["visitors"].sum())
visits = int(daily["visits"].sum())
page_views = int(daily["page_views"].sum())
bot_req = int(daily["bot_requests"].sum())
human_req = int(daily["human_requests"].sum())
total_req = int(daily["total_requests"].sum())
bot_pct = bot_req / total_req * 100 if total_req else 0
# Derived from headline figures so it can't disagree with them.
pages_per_visit = page_views / visits if visits else 0
has_time = not sect.empty and sect["minutes"].notna().any()

# ---------------------------------------------------------------- header
st.title("Visitor Analytics")
st.markdown(f"<p class='cap'>Real people and what they did — automated traffic, page "
            f"assets and API calls removed &nbsp;·&nbsp; {len(daily)} days</p>",
            unsafe_allow_html=True)
st.write("")

k = st.columns(5)
k[0].metric("Real people", f"{visitors:,}")
k[1].metric("Visits", f"{visits:,}")
k[2].metric("Pages viewed", f"{page_views:,}")
k[3].metric("Pages per visit", f"{pages_per_visit:.1f}")
if not sess.empty:
    med = sess.loc[sess["visit_duration_sec"] > 0, "visit_duration_sec"].median()
    k[4].metric("Median visit", f"{(med or 0)/60:.1f} min")

st.write("")
st.markdown(f"""<div class='banner'>Servers logged <b>{total_req:,}</b> requests, but one
page view fires many (images, scripts, APIs, tracking). Only <b>{page_views:,}</b> were
pages a person opened, from <b>{visitors:,}</b> people across <b>{visits:,}</b> visits.
<b>{bot_pct:.0f}%</b> of all traffic was automated.</div>""", unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------- bots
st.subheader("Bots vs real people — share of server requests")
a, b = st.columns([1, 1.4])
with a:
    f = go.Figure(go.Pie(labels=["Human requests", "Automated requests"],
                         values=[human_req, bot_req], hole=.66, sort=False,
                         marker=dict(colors=[CYAN, SLATE],
                                     line=dict(color=BG, width=3)),
                         textinfo="percent", textfont=dict(size=15, color=BG)))
    st.plotly_chart(style(f, 300, legend=True), use_container_width=True)
with b:
    if not bots.empty:
        f = px.bar(bots.head(8), x="requests", y="bot_name", orientation="h",
                   color="requests", color_continuous_scale=["#1E293B", VIOLET],
                   labels={"requests": "Requests", "bot_name": ""})
        f.update_layout(coloraxis_showscale=False, yaxis=dict(autorange="reversed"))
        st.plotly_chart(style(f, 300), use_container_width=True)
cap(f"This chart shows <b>requests, not people</b>. The {visitors:,} real people above "
    f"generated the {human_req:,} human requests shown here — one person makes many "
    "requests. Search and SEO crawlers are expected; large unidentified volumes consume "
    "capacity and distort any analysis that doesn't exclude them.")

st.divider()

# ---------------------------------------------------------------- attention
st.subheader("What attracts and holds human attention")
if has_time:
    a, b = st.columns(2)
    with a:
        d = sect.dropna(subset=["minutes"]).sort_values("minutes", ascending=False).head(10)
        f = px.bar(d, x="minutes", y="page_category", orientation="h",
                   color="minutes", color_continuous_scale=["#134E4A", EMERALD],
                   labels={"minutes": "Total minutes spent", "page_category": ""})
        f.update_layout(coloraxis_showscale=False, yaxis=dict(autorange="reversed"))
        st.plotly_chart(style(f, 340), use_container_width=True)
        cap("<b>Total human time</b> per section — what the site is actually used for.")
    with b:
        d = sect.dropna(subset=["avg_sec"]).sort_values("avg_sec", ascending=False).head(10)
        f = px.bar(d, x="avg_sec", y="page_category", orientation="h",
                   color="avg_sec", color_continuous_scale=["#164E63", CYAN],
                   labels={"avg_sec": "Avg seconds per page", "page_category": ""})
        f.update_layout(coloraxis_showscale=False, yaxis=dict(autorange="reversed"))
        st.plotly_chart(style(f, 340), use_container_width=True)
        cap("<b>Average dwell time</b> — high means content that holds attention.")
    st.info("These two rank almost inversely: the highest-volume sections hold attention "
            "the least, while the most absorbing content is rarely reached.")
else:
    if not sect.empty:
        d = sect.sort_values("views", ascending=False).head(10)
        f = px.bar(d, x="views", y="page_category", orientation="h",
                   color_discrete_sequence=[EMERALD],
                   labels={"views": "Page views", "page_category": ""})
        f.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(style(f, 340), use_container_width=True)
    st.warning("Time on page not measurable yet — it needs visits with two or more "
               "pages. Sections ranked by views instead.")

st.divider()

# ---------------------------------------------------------------- behaviour
st.subheader("How people behave in a visit")
if not sess.empty:
    m = st.columns(4)
    m[0].metric("Bounced (1 page)", f"{sess['is_bounce'].mean()*100:.0f}%")
    m[1].metric("Engaged (3+ pages)", f"{(sess['pages_viewed']>=3).mean()*100:.0f}%")
    med = sess.loc[sess["visit_duration_sec"] > 0, "visit_duration_sec"].median()
    m[2].metric("Median visit", f"{(med or 0)/60:.1f} min")
    m[3].metric("Sections per visit", f"{sess['sections_visited'].mean():.1f}")
    st.write("")

    a, b = st.columns([1.3, 1])
    with a:
        bk = pd.cut(sess["pages_viewed"], [0, 1, 2, 5, 10, 1e9],
                    labels=["1 page", "2", "3-5", "6-10", "10+"])
        bc = bk.value_counts().reindex(["1 page", "2", "3-5", "6-10", "10+"]).reset_index()
        bc.columns = ["Pages viewed", "Visits"]
        f = px.bar(bc, x="Pages viewed", y="Visits", color="Visits",
                   color_continuous_scale=["#312E81", VIOLET])
        f.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style(f, 300), use_container_width=True)
        cap("Visit depth — how far people get before leaving.")
    with b:
        if not dev.empty:
            f = go.Figure(go.Pie(labels=dev["device_type"], values=dev["visits"],
                                 hole=.6, marker=dict(colors=SEQ,
                                 line=dict(color=BG, width=3)),
                                 textinfo="percent", textfont=dict(size=13, color=BG)))
            st.plotly_chart(style(f, 300, legend=True), use_container_width=True)
            cap("What real people browse on.")

st.divider()

# ---------------------------------------------------------------- pages
st.subheader("Pages people actually viewed")
if not perf.empty:
    t = perf.copy()
    t["avg_sec"] = t["avg_sec"].round(1)
    t["exit_pct"] = t["exit_pct"].round(1)
    t = t.rename(columns={"endpoint_group": "Page", "page_category": "Section",
                          "views": "Views", "visitors": "People",
                          "avg_sec": "Avg time (s)", "exit_pct": "Exit rate %"})
    st.dataframe(t.head(15).reset_index(drop=True), use_container_width=True,
                 hide_index=True,
                 column_config={"Views": st.column_config.NumberColumn(format="%d"),
                                "People": st.column_config.NumberColumn(format="%d")})
cap("URLs are grouped — every <code>/plan/...</code> becomes <code>/plan/{slug}</code> — "
    "so sections aren't split into thousands of single-view rows. A high exit rate means "
    "people commonly leave from there.")

st.divider()

# ---------------------------------------------------------------- sources + markets
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
    cap("<code>(direct)</code> means no referrer. Internal domains are movement within "
        "the site network, not new arrivals — <b>volume and quality differ sharply</b>.")
with b:
    st.subheader("Markets attracting the most people")
    if not funnel.empty:
        d = funnel.copy()
        d["label"] = "Market " + d["funnel_market"].astype(str)
        f = px.bar(d, x="visitors", y="label", orientation="h",
                   color="visitors", color_continuous_scale=["#78350F", AMBER],
                   labels={"visitors": "Distinct people", "label": ""})
        f.update_layout(coloraxis_showscale=False, yaxis=dict(autorange="reversed"))
        st.plotly_chart(style(f, 360), use_container_width=True)
    cap("Ranked by <b>distinct people</b>, not events — one active user can't inflate a "
        "market.")

st.divider()

# ---------------------------------------------------------------- trend
st.subheader("Visitors by day")
d = daily.copy()
d["day"] = pd.to_datetime(d["event_date"]).dt.strftime("%b %d")
f = px.bar(d, x="day", y="visitors", color="visitors",
           color_continuous_scale=["#164E63", CYAN],
           labels={"visitors": "Real people", "day": ""})
f.update_layout(coloraxis_showscale=False)
st.plotly_chart(style(f, 300), use_container_width=True)
cap("Bars, not a line — only days present in the data, so gaps between log files aren't "
    "drawn as imaginary traffic.")

with st.expander("How these numbers are calculated, and their limits"):
    st.markdown("""
**Real person** — a distinct Google Analytics client id from the cookie, automated traffic
removed. Not a request count.

**Visit** — a distinct `ASP.NET_SessionId`. Sessions containing no page view are excluded
from behaviour averages, since they represent background activity rather than a person
browsing.

**Pages per visit** — total page views divided by total visits, so it always agrees with
the headline figures.

**Page view** — a request classified as real page content. Static assets, backend API
calls and tracking beacons are excluded.

**Median visit** — the middle value, not the mean. Session ids live in cookies, so a few
sessions span hours and would pull an average far above typical behaviour.

**Time on page** — the gap to that visitor's next page view in the same visit. *The last
page of every visit has no measurable time*, so those views are excluded, which biases
averages toward pages people navigate away from. Gaps over 30 minutes are treated as the
person having left.

**Bot** — flagged when the user agent declares a crawler, when one IP makes an unusually
high number of requests in a day, or when a request has no cookie, no referer and isn't a
page. The reason is stored per row so any classification can be audited.

**Limitation:** visitor counts depend on cookies, so cookie blocking or multi-device use
can over- or under-count people. Visit-based figures are more reliable.
""")
