"""
Instagram Trend Tracker
Built by SYNTH. Media

Aggregates signals from:
  ✅ Google Trends (pytrends — no key needed)
  ✅ Meta Ads Library (free API — needs access token)
  ✅ Exploding Topics (scraped — no key needed)
  ✅ Social Blade (scraped — no key needed)
  ✅ Instagram Graph API (official — needs Business account token)

Run: streamlit run app.py
"""

import os
import time
from datetime import datetime
from pathlib import Path

# Auto-load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import streamlit as st

# ── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Instagram Trend Tracker — SYNTH. Media",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Global */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* Header */
  .main-header {
    background: linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 50%, #16213e 100%);
    border-radius: 16px;
    padding: 32px 40px;
    margin-bottom: 24px;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .main-header h1 {
    font-size: 2.4rem; font-weight: 700; color: #ffffff; margin: 0;
    background: linear-gradient(90deg, #fff 0%, #a78bfa 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .main-header p { color: #9ca3af; margin: 6px 0 0 0; font-size: 0.95rem; }

  /* Trend Cards */
  .trend-card {
    background: #111827;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 12px;
    transition: border-color 0.2s;
  }
  .trend-card:hover { border-color: rgba(167,139,250,0.4); }
  .trend-card-title {
    font-size: 1rem; font-weight: 600; color: #f9fafb; margin-bottom: 6px;
  }
  .trend-card-meta {
    font-size: 0.78rem; color: #6b7280; display: flex; gap: 12px; flex-wrap: wrap;
  }
  .badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 20px; font-size: 0.72rem; font-weight: 500;
  }
  .badge-now    { background: #064e3b; color: #34d399; }
  .badge-soon   { background: #1e1b4b; color: #a78bfa; }
  .badge-source { background: #1f2937; color: #9ca3af; }
  .badge-multi  { background: #7c2d12; color: #fb923c; }

  /* Score Bar */
  .score-bar-bg {
    background: #1f2937; border-radius: 4px; height: 4px;
    margin-top: 10px; overflow: hidden;
  }
  .score-bar-fill {
    height: 100%; border-radius: 4px;
    background: linear-gradient(90deg, #7c3aed, #a78bfa);
  }

  /* Reels Cards */
  .reel-card {
    background: #0f172a;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
  }
  .reel-url a {
    color: #818cf8; font-size: 0.85rem; text-decoration: none;
    word-break: break-all;
  }
  .reel-url a:hover { color: #a78bfa; text-decoration: underline; }
  .reel-stats { font-size: 0.78rem; color: #6b7280; margin-top: 8px; }

  /* Source Status */
  .source-ok       { color: #34d399; }
  .source-error     { color: #f87171; }
  .source-disabled  { color: #6b7280; }
  .source-no_data   { color: #fbbf24; }

  /* Section Headers */
  .section-header {
    font-size: 1.2rem; font-weight: 700; color: #f9fafb;
    margin: 24px 0 12px 0; padding-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }

  /* Metric cards */
  div[data-testid="metric-container"] {
    background: #111827; border-radius: 10px; padding: 12px;
    border: 1px solid rgba(255,255,255,0.06);
  }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background: #0d1117 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
  }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: #0d1117; }
  ::-webkit-scrollbar-thumb { background: #374151; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ── Session State Init ─────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "last_fetched" not in st.session_state:
    st.session_state.last_fetched = None
if "is_loading" not in st.session_state:
    st.session_state.is_loading = False


# ── Sidebar — Configuration ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    st.markdown("---")

    st.markdown("**🔑 API Keys**")
    meta_token = st.text_input(
        "Meta Access Token",
        value=os.getenv("META_ACCESS_TOKEN", ""),
        type="password",
        help="Free from developers.facebook.com → your App → Marketing API",
    )
    ig_token = st.text_input(
        "Instagram Access Token",
        value=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        type="password",
        help="Instagram Graph API token — for fetching actual Reels URLs",
    )
    ig_account_id = st.text_input(
        "Instagram Business Account ID",
        value=os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""),
        help="Your Instagram Business/Creator account ID (numeric)",
    )
    sb_key = st.text_input(
        "Social Blade API Key (optional)",
        value=os.getenv("SOCIAL_BLADE_API_KEY", ""),
        type="password",
        help="Optional — paid key from socialblade.com/business/api",
    )

    st.markdown("---")
    st.markdown("**🎯 Focus Niches**")
    niches = st.multiselect(
        "Content Niches",
        ["fashion", "beauty", "fitness", "food", "travel", "comedy", "dance", "music", "gaming", "lifestyle"],
        default=["fashion", "beauty", "fitness"],
        help="Narrows Instagram hashtag discovery to these categories",
    )

    st.markdown("---")
    st.markdown("**🌍 Region**")
    country = st.selectbox(
        "Google Trends Country",
        ["US", "GB", "IN", "AU", "CA", "DE", "FR", "BR", "MX"],
        index=0,
    )

    st.markdown("---")
    st.markdown("**⚡ Sources**")
    en_google = st.toggle("Google Trends", value=True)
    en_meta = st.toggle("Meta Ads Library", value=bool(meta_token))
    en_exploding = st.toggle("Exploding Topics", value=True)
    en_social_blade = st.toggle("Social Blade", value=True)
    en_instagram = st.toggle("Instagram Graph API", value=bool(ig_token and ig_account_id))

    st.markdown("---")
    fetch_btn = st.button("🔄 Fetch Trends", type="primary", use_container_width=True)

    if st.session_state.last_fetched:
        st.caption(f"Last updated: {st.session_state.last_fetched}")

    st.markdown("---")
    st.markdown(
        "<div style='color:#4b5563;font-size:0.72rem'>Built by SYNTH. Media<br>Powered by 5 live data sources</div>",
        unsafe_allow_html=True,
    )


# ── Header ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>📈 Instagram Trend Tracker</h1>
  <p>Real-time signal aggregation from Google Trends · Meta Ads Library · Exploding Topics · Social Blade · Instagram Graph API</p>
</div>
""", unsafe_allow_html=True)


# ── Fetch Handler ──────────────────────────────────────────────────────────
def run_fetch():
    from engine.aggregator import AggregatorConfig, TrendAggregator

    config = AggregatorConfig(
        enable_google=en_google,
        google_country=country,
        enable_meta=en_meta,
        meta_access_token=meta_token,
        enable_exploding=en_exploding,
        enable_social_blade=en_social_blade,
        enable_instagram=en_instagram,
        instagram_access_token=ig_token,
        instagram_business_account_id=ig_account_id,
        social_blade_api_key=sb_key,
        niches=niches or ["fashion", "beauty", "fitness"],
        max_trending_now=15,
        max_upcoming=15,
        max_reels=20,
    )
    agg = TrendAggregator(config)
    return agg.run()


if fetch_btn:
    with st.spinner("Fetching live trend data from all sources..."):
        try:
            st.session_state.results = run_fetch()
            st.session_state.last_fetched = datetime.now().strftime("%H:%M:%S")
            st.rerun()
        except Exception as e:
            st.error(f"Error during fetch: {e}")
            import traceback
            st.code(traceback.format_exc())


# ── No Data State ──────────────────────────────────────────────────────────
if st.session_state.results is None:
    st.markdown("""
    <div style="text-align:center;padding:60px 20px;color:#6b7280;">
      <div style="font-size:3rem;margin-bottom:16px">🚀</div>
      <div style="font-size:1.2rem;color:#9ca3af;font-weight:600">Ready to track trends</div>
      <div style="font-size:0.9rem;margin-top:8px">
        Configure your API keys in the sidebar, then click <strong>Fetch Trends</strong>
      </div>
      <br>
      <div style="font-size:0.78rem;color:#4b5563;max-width:480px;margin:0 auto">
        Google Trends and Exploding Topics work without any API keys.<br>
        Add Meta + Instagram tokens to unlock Reels URL discovery.
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# ── Results Layout ─────────────────────────────────────────────────────────
results = st.session_state.results

# ── Source Status Bar ──────────────────────────────────────────────────────
status_icons = {"ok": "🟢", "error": "🔴", "disabled": "⚪", "no_data": "🟡"}
statuses = results.get("sources_status", [])
if statuses:
    cols = st.columns(len(statuses))
    for col, s in zip(cols, statuses):
        icon = status_icons.get(s["status"], "⚪")
        col.markdown(
            f"<div style='text-align:center;padding:8px;background:#111827;"
            f"border-radius:8px;border:1px solid rgba(255,255,255,0.05)'>"
            f"<div style='font-size:1.2rem'>{s['icon']}</div>"
            f"<div style='font-size:0.72rem;color:#9ca3af;margin-top:2px'>{s['name']}</div>"
            f"<div style='font-size:0.7rem'>{icon} {s['status'].upper()}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown("<br>", unsafe_allow_html=True)

# ── KPI Metrics ────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Trending NOW", len(results.get("trending_now", [])))
c2.metric("Upcoming Trends", len(results.get("upcoming", [])))
c3.metric("Trending Reels", len(results.get("trending_reels", [])))
c4.metric("Potential Viral Reels", len(results.get("upcoming_reels", [])))

st.markdown("<br>", unsafe_allow_html=True)

# ── Main Content: Two columns ──────────────────────────────────────────────
left_col, right_col = st.columns([1, 1], gap="large")


def render_trend_card(item: dict, badge_type: str):
    kw = item.get("keyword", "Unknown")
    score = item.get("score", 0)
    sources = item.get("sources", [item.get("source", "unknown")])
    if isinstance(sources, str):
        sources = [sources]
    velocity = item.get("velocity", 1.0)
    source_count = item.get("source_count", len(sources))

    badge_html = (
        '<span class="badge badge-now">🔥 Trending NOW</span>'
        if badge_type == "now"
        else '<span class="badge badge-soon">⚡ Upcoming</span>'
    )
    if source_count > 1:
        badge_html += f'<span class="badge badge-multi">🔀 {source_count} sources</span>'

    source_tags = " ".join(
        f'<span class="badge badge-source">{s.replace("_", " ").title()}</span>'
        for s in sources[:3]
    )

    velocity_text = ""
    if velocity > 1.5:
        velocity_text = f"<span style='color:#34d399'>▲ {velocity:.1f}x growth</span>"
    elif velocity > 1.1:
        velocity_text = f"<span style='color:#fbbf24'>↑ {velocity:.1f}x growth</span>"

    score_pct = min(int(score), 100)
    bar_width = score_pct

    # Extra metadata
    extra = ""
    meta = item.get("metadata", {})
    if "growth_pct" in meta and meta["growth_pct"]:
        extra = f"<span>📊 +{int(meta['growth_pct'])}% growth</span>"
    elif "google_category" in meta and meta["google_category"]:
        extra = f"<span>🏷 {meta['google_category']}</span>"

    st.markdown(f"""
    <div class="trend-card">
      <div class="trend-card-title">{kw}</div>
      <div class="trend-card-meta">
        {badge_html}
        {source_tags}
        {velocity_text}
        {extra}
        <span>Score: <strong style='color:#a78bfa'>{score_pct}</strong></span>
      </div>
      <div class="score-bar-bg">
        <div class="score-bar-fill" style="width:{bar_width}%"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_reel_card(reel: dict, label: str):
    url = reel.get("permalink") or reel.get("url", "")
    hashtag = reel.get("hashtag", "")
    likes = reel.get("like_count", 0)
    comments = reel.get("comments_count", 0)
    score = reel.get("trend_score", reel.get("score", 0))
    caption = reel.get("caption_preview", "")
    has_signals = reel.get("has_trend_signals", False)
    posted = reel.get("posted_at", "")

    badge = (
        '<span class="badge badge-now">🔥 Trending</span>'
        if label == "trending"
        else '<span class="badge badge-soon">⚡ Potential Viral</span>'
    )
    signal_badge = '<span class="badge badge-multi">💡 Trend Signal</span>' if has_signals else ""

    likes_fmt = f"{likes:,}" if likes else "N/A"
    comments_fmt = f"{comments:,}" if comments else "N/A"

    url_html = (
        f'<div class="reel-url"><a href="{url}" target="_blank">🔗 {url}</a></div>'
        if url
        else '<div style="color:#4b5563;font-size:0.8rem">URL requires Instagram API token</div>'
    )

    caption_html = (
        f'<div style="color:#6b7280;font-size:0.78rem;margin-top:8px;font-style:italic">"{caption}"</div>'
        if caption
        else ""
    )

    st.markdown(f"""
    <div class="reel-card">
      <div style="margin-bottom:8px">{badge} {signal_badge}</div>
      {url_html}
      {caption_html}
      <div class="reel-stats">
        ❤️ {likes_fmt} likes &nbsp;·&nbsp;
        💬 {comments_fmt} comments &nbsp;·&nbsp;
        #{hashtag} &nbsp;·&nbsp;
        Trend Score: <strong style="color:#a78bfa">{int(score)}</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Left Column: Keyword Trends ────────────────────────────────────────────
with left_col:
    # Trending NOW
    st.markdown('<div class="section-header">🔥 Trending NOW</div>', unsafe_allow_html=True)
    trending_now = results.get("trending_now", [])
    if trending_now:
        for item in trending_now:
            render_trend_card(item, "now")
    else:
        st.info("No trending signals fetched yet. Enable sources in the sidebar.")

    st.markdown("<br>", unsafe_allow_html=True)

    # Upcoming
    st.markdown('<div class="section-header">⚡ Upcoming Trends</div>', unsafe_allow_html=True)
    upcoming = results.get("upcoming", [])
    if upcoming:
        for item in upcoming:
            render_trend_card(item, "soon")
    else:
        st.info("No upcoming trend signals found.")


# ── Right Column: Reels URLs ───────────────────────────────────────────────
with right_col:
    # Trending Reels
    st.markdown('<div class="section-header">📱 Trending Reels URLs</div>', unsafe_allow_html=True)
    st.markdown(
        "<div style='color:#6b7280;font-size:0.78rem;margin-bottom:12px'>"
        "These Reels are currently viral — other creators are copying their templates.</div>",
        unsafe_allow_html=True,
    )
    trending_reels = results.get("trending_reels", [])
    if trending_reels:
        for reel in trending_reels:
            render_reel_card(reel, "trending")
    else:
        st.markdown("""
        <div style="background:#111827;border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:24px;text-align:center">
          <div style="font-size:2rem;margin-bottom:8px">📸</div>
          <div style="color:#9ca3af;font-size:0.9rem;font-weight:500">Instagram API not connected</div>
          <div style="color:#6b7280;font-size:0.78rem;margin-top:8px">
            To get live Reels URLs:<br>
            1. Add your Instagram Access Token in the sidebar<br>
            2. Add your Instagram Business Account ID<br>
            3. Click Fetch Trends again
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Upcoming / Potential Viral Reels
    st.markdown('<div class="section-header">🌱 Potential Upcoming Viral Reels</div>', unsafe_allow_html=True)
    st.markdown(
        "<div style='color:#6b7280;font-size:0.78rem;margin-bottom:12px'>"
        "Recent Reels gaining traction fast — these may be the next templates everyone copies.</div>",
        unsafe_allow_html=True,
    )
    upcoming_reels = results.get("upcoming_reels", [])
    if upcoming_reels:
        for reel in upcoming_reels:
            render_reel_card(reel, "upcoming")
    else:
        st.markdown("""
        <div style="background:#111827;border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:24px;text-align:center">
          <div style="color:#6b7280;font-size:0.78rem">
            Upcoming Reels will appear here once Instagram API is connected.<br>
            Meanwhile, use the Trending Keywords above to find content templates manually.
          </div>
        </div>
        """, unsafe_allow_html=True)


# ── Full Width: Raw Trend Table ────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("📊 Full Trend Data Table", expanded=False):
    import pandas as pd

    all_trends = [
        {**t, "trend_type": "Trending NOW"}
        for t in results.get("trending_now", [])
    ] + [
        {**t, "trend_type": "Upcoming"}
        for t in results.get("upcoming", [])
    ]

    if all_trends:
        df = pd.DataFrame(all_trends)
        display_cols = ["keyword", "trend_type", "score", "velocity", "sources", "source_count"]
        display_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[display_cols].sort_values("score", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        csv = df.to_csv(index=False)
        st.download_button(
            "⬇️ Download CSV",
            data=csv,
            file_name=f"instagram_trends_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )
    else:
        st.info("No data to display.")


# ── Errors Panel ──────────────────────────────────────────────────────────
errors = results.get("errors", {})
if errors:
    with st.expander("⚠️ Source Errors", expanded=True):
        for source, err in errors.items():
            st.error(f"**{source}**: {err}")

# ── Debug Panel ────────────────────────────────────────────────────────────
with st.expander("🔍 Debug Info", expanded=False):
    st.json({
        "sources_status": results.get("sources_status", []),
        "errors": results.get("errors", {}),
        "total_signals": results.get("total_signals_processed", 0),
        "trending_now_count": len(results.get("trending_now", [])),
        "upcoming_count": len(results.get("upcoming", [])),
    })


# ── Auto-Refresh ───────────────────────────────────────────────────────────
st.markdown("---")
col_a, col_b = st.columns([3, 1])
with col_a:
    auto_refresh = st.checkbox("Auto-refresh every 30 minutes", value=False)
with col_b:
    if st.button("🔄 Refresh Now", use_container_width=True):
        with st.spinner("Refreshing..."):
            try:
                st.session_state.results = run_fetch()
                st.session_state.last_fetched = datetime.now().strftime("%H:%M:%S")
                st.rerun()
            except Exception as e:
                st.error(f"Refresh failed: {e}")

if auto_refresh:
    time.sleep(1800)
    st.rerun()
