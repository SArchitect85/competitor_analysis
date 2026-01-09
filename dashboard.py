#!/usr/bin/env python3
"""Streamlit dashboard for viewing competitor ads."""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from pathlib import Path

from src.models import SessionLocal, Competitor, Ad, AdSnapshot
from sqlalchemy import func

# Page config
st.set_page_config(
    page_title="Competitor Ad Tracker",
    page_icon="📊",
    layout="wide"
)

# Custom CSS for highlighting winners
st.markdown("""
<style>
    .winner-row {
        background-color: #d4edda !important;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .ad-text-preview {
        max-width: 300px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
</style>
""", unsafe_allow_html=True)


def get_db():
    """Get database session."""
    return SessionLocal()


def load_ads_data():
    """Load all ads with competitor info."""
    db = get_db()
    try:
        ads = db.query(Ad).all()
        competitors = {c.page_id: c.page_name for c in db.query(Competitor).all()}

        data = []
        for ad in ads:
            data.append({
                "ad_id": ad.ad_id,
                "page_id": ad.page_id,
                "competitor": competitors.get(ad.page_id, ad.page_name or ad.page_id),
                "ad_text": ad.ad_text or "",
                "ad_text_preview": (ad.ad_text or "")[:100] + "..." if ad.ad_text and len(ad.ad_text) > 100 else (ad.ad_text or ""),
                "started_running_on": ad.started_running_on,
                "days_running": ad.days_running or 0,
                "media_type": ad.media_type or "Unknown",
                "media_url": ad.media_url,
                "local_media_path": ad.local_media_path,
                "landing_page_url": ad.landing_page_url,
                "has_low_impressions": ad.has_low_impressions,
                "is_active": ad.is_active,
                "cta_type": ad.cta_type,
                "platforms": ", ".join(ad.platforms) if ad.platforms else "",
            })
        return pd.DataFrame(data), competitors
    finally:
        db.close()


def load_stats():
    """Load summary statistics."""
    db = get_db()
    try:
        total_ads = db.query(Ad).count()
        active_ads = db.query(Ad).filter(Ad.is_active == True).count()

        # Ads by competitor
        by_competitor = db.query(
            Ad.page_id,
            func.count(Ad.id)
        ).group_by(Ad.page_id).all()

        # Get competitor names
        competitors = {c.page_id: c.page_name for c in db.query(Competitor).all()}

        competitor_stats = [
            {
                "page_id": page_id,
                "name": competitors.get(page_id, page_id),
                "count": count
            }
            for page_id, count in by_competitor
        ]

        # Media type breakdown
        media_types = db.query(
            Ad.media_type,
            func.count(Ad.id)
        ).group_by(Ad.media_type).all()

        media_stats = {mt or "Unknown": count for mt, count in media_types}

        # Winners (30+ days)
        winners_count = db.query(Ad).filter(Ad.days_running >= 30).count()

        return {
            "total_ads": total_ads,
            "active_ads": active_ads,
            "by_competitor": competitor_stats,
            "media_types": media_stats,
            "winners_count": winners_count
        }
    finally:
        db.close()


def render_overview():
    """Render the overview page."""
    st.header("Overview")

    stats = load_stats()

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Ads", stats["total_ads"])
    with col2:
        st.metric("Active Ads", stats["active_ads"])
    with col3:
        st.metric("Potential Winners (30+ days)", stats["winners_count"])
    with col4:
        st.metric("Competitors Tracked", len(stats["by_competitor"]))

    st.divider()

    # Two column layout
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Ads by Competitor")
        competitor_df = pd.DataFrame(stats["by_competitor"])
        if not competitor_df.empty:
            competitor_df = competitor_df.sort_values("count", ascending=False)
            st.bar_chart(competitor_df.set_index("name")["count"])
            st.dataframe(
                competitor_df[["name", "count"]].rename(columns={"name": "Competitor", "count": "Ads"}),
                hide_index=True,
                use_container_width=True
            )

    with col2:
        st.subheader("Media Type Breakdown")
        media_df = pd.DataFrame([
            {"type": k, "count": v}
            for k, v in stats["media_types"].items()
        ])
        if not media_df.empty:
            media_df = media_df.sort_values("count", ascending=False)
            st.bar_chart(media_df.set_index("type")["count"])
            st.dataframe(
                media_df.rename(columns={"type": "Media Type", "count": "Count"}),
                hide_index=True,
                use_container_width=True
            )


def render_ads_table():
    """Render the ads table page."""
    st.header("All Ads")

    df, competitors = load_ads_data()

    if df.empty:
        st.warning("No ads found in database.")
        return

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        competitor_filter = st.selectbox(
            "Filter by Competitor",
            options=["All"] + sorted(df["competitor"].unique().tolist())
        )

    with col2:
        media_filter = st.selectbox(
            "Filter by Media Type",
            options=["All"] + sorted(df["media_type"].unique().tolist())
        )

    with col3:
        sort_by = st.selectbox(
            "Sort by",
            options=["days_running", "started_running_on", "competitor"],
            index=0
        )

    # Apply filters
    filtered_df = df.copy()
    if competitor_filter != "All":
        filtered_df = filtered_df[filtered_df["competitor"] == competitor_filter]
    if media_filter != "All":
        filtered_df = filtered_df[filtered_df["media_type"] == media_filter]

    # Sort
    ascending = sort_by == "competitor"
    filtered_df = filtered_df.sort_values(sort_by, ascending=ascending, na_position="last")

    st.write(f"Showing {len(filtered_df)} ads")

    # Display table with custom styling
    def highlight_winners(row):
        if row["days_running"] >= 30:
            return ["background-color: #d4edda"] * len(row)
        return [""] * len(row)

    display_df = filtered_df[[
        "competitor", "ad_text_preview", "started_running_on",
        "days_running", "media_type", "has_low_impressions"
    ]].copy()

    display_df.columns = [
        "Competitor", "Ad Text", "Start Date",
        "Days Running", "Media Type", "Low Impressions"
    ]

    styled_df = display_df.style.apply(highlight_winners, axis=1)

    st.dataframe(
        styled_df,
        hide_index=True,
        use_container_width=True,
        height=500
    )

    st.info("Rows highlighted in green are potential winners (running 30+ days)")

    # Ad detail view
    st.divider()
    st.subheader("Ad Detail View")

    ad_options = filtered_df["ad_id"].tolist()
    if ad_options:
        selected_ad = st.selectbox(
            "Select an ad to view details",
            options=ad_options,
            format_func=lambda x: f"{x} - {filtered_df[filtered_df['ad_id'] == x]['competitor'].values[0]}"
        )

        if selected_ad:
            render_ad_detail(selected_ad, filtered_df)


def render_ad_detail(ad_id: str, df: pd.DataFrame):
    """Render detailed view for a single ad."""
    ad_row = df[df["ad_id"] == ad_id].iloc[0]

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("**Competitor:**")
        st.write(ad_row["competitor"])

        st.markdown("**Ad ID:**")
        st.code(ad_row["ad_id"])

        st.markdown("**Start Date:**")
        st.write(ad_row["started_running_on"] or "Unknown")

        st.markdown("**Days Running:**")
        days = ad_row["days_running"]
        if days >= 30:
            st.success(f"{days} days (Potential Winner!)")
        else:
            st.write(f"{days} days")

        st.markdown("**Media Type:**")
        st.write(ad_row["media_type"])

        st.markdown("**Platforms:**")
        st.write(ad_row["platforms"] or "Unknown")

        if ad_row["landing_page_url"]:
            st.markdown("**Landing Page:**")
            st.markdown(f"[{ad_row['landing_page_url'][:50]}...]({ad_row['landing_page_url']})")

        if ad_row["cta_type"]:
            st.markdown("**CTA:**")
            st.write(ad_row["cta_type"])

    with col2:
        st.markdown("**Full Ad Text:**")
        st.text_area(
            label="Ad Text",
            value=ad_row["ad_text"] or "No ad text available",
            height=200,
            disabled=True,
            label_visibility="collapsed"
        )

        # Show media
        st.markdown("**Media:**")
        media_path = ad_row["local_media_path"]

        if media_path:
            media_dir = Path(media_path)

            # Look for media files
            if media_dir.exists():
                media_file = media_dir / "media.mp4"
                image_file = media_dir / "media.jpg"
                thumbnail = media_dir / "thumbnail.jpg"

                if media_file.exists() and ad_row["media_type"] == "VIDEO":
                    st.video(str(media_file))
                elif image_file.exists():
                    st.image(str(image_file))
                elif thumbnail.exists():
                    st.image(str(thumbnail))
                else:
                    st.info("Media file not found locally")
            else:
                st.info("Media directory not found")
        elif ad_row["media_url"]:
            st.markdown(f"Media URL: {ad_row['media_url'][:80]}...")
        else:
            st.info("No media available")


def render_winners():
    """Render the winners tab - ads running 30+ days."""
    st.header("Potential Winners (30+ Days)")

    df, _ = load_ads_data()

    if df.empty:
        st.warning("No ads found in database.")
        return

    # Filter for winners only
    winners_df = df[df["days_running"] >= 30].copy()
    winners_df = winners_df.sort_values("days_running", ascending=False)

    if winners_df.empty:
        st.info("No ads have been running for 30+ days yet.")
        return

    st.success(f"Found {len(winners_df)} potential winners!")

    # Summary by competitor
    st.subheader("Winners by Competitor")
    winner_counts = winners_df.groupby("competitor").size().reset_index(name="count")
    winner_counts = winner_counts.sort_values("count", ascending=False)
    st.bar_chart(winner_counts.set_index("competitor")["count"])

    st.divider()

    # Winners table
    st.subheader("All Winners")

    display_df = winners_df[[
        "competitor", "ad_text_preview", "started_running_on",
        "days_running", "media_type", "landing_page_url"
    ]].copy()

    display_df.columns = [
        "Competitor", "Ad Text", "Start Date",
        "Days Running", "Media Type", "Landing Page"
    ]

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        height=400
    )

    # Winner detail view
    st.divider()
    st.subheader("Winner Detail View")

    selected_winner = st.selectbox(
        "Select a winner to view details",
        options=winners_df["ad_id"].tolist(),
        format_func=lambda x: f"{winners_df[winners_df['ad_id'] == x]['competitor'].values[0]} - {winners_df[winners_df['ad_id'] == x]['days_running'].values[0]} days - {x}"
    )

    if selected_winner:
        render_ad_detail(selected_winner, winners_df)


def main():
    """Main dashboard entry point."""
    st.title("Competitor Ad Tracker")

    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to",
        ["Overview", "All Ads", "Winners (30+ days)"]
    )

    # Refresh button
    if st.sidebar.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    # Page routing
    if page == "Overview":
        render_overview()
    elif page == "All Ads":
        render_ads_table()
    elif page == "Winners (30+ days)":
        render_winners()

    # Footer
    st.sidebar.divider()
    st.sidebar.caption("Last updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
