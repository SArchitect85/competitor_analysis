from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Date, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from src.models.database import Base


class Ad(Base):
    """Facebook ads tracked from Ad Library."""

    __tablename__ = "ads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ad_id = Column(String(100), unique=True, nullable=False, index=True)
    page_id = Column(String(50), ForeignKey("competitors.page_id"), nullable=False, index=True)
    page_name = Column(String(255))
    ad_text = Column(Text)
    started_running_on = Column(Date)
    is_active = Column(Boolean, default=True)
    has_low_impressions = Column(Boolean, default=False)
    media_type = Column(String(20))  # VIDEO, IMAGE, CAROUSEL
    media_url = Column(Text)
    thumbnail_url = Column(Text)
    cta_type = Column(String(50))
    landing_page_url = Column(Text)
    platforms = Column(JSON)  # Array of platforms
    regions = Column(JSON)  # Array of regions
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    days_running = Column(Integer, default=0)
    media_downloaded = Column(Boolean, default=False)
    local_media_path = Column(Text)

    # Winner detection fields
    winner_score = Column(Integer, default=0)  # 0-100 score
    scaling_cluster_id = Column(String(100), index=True)  # Groups similar ads together
    snapshot_count = Column(Integer, default=1)  # Number of times seen in snapshots

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    competitor = relationship("Competitor", backref="ads")

    def __repr__(self):
        return f"<Ad(ad_id={self.ad_id}, page_id={self.page_id})>"

    def calculate_days_running(self):
        """Calculate number of days the ad has been running."""
        if self.started_running_on:
            delta = datetime.utcnow().date() - self.started_running_on
            self.days_running = delta.days
        return self.days_running
