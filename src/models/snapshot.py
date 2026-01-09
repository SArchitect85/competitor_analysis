from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Date, Integer, Text, JSON, ForeignKey
from src.models.database import Base


class AdSnapshot(Base):
    """Daily snapshots of ads for tracking changes over time."""

    __tablename__ = "ad_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ad_id = Column(String(100), ForeignKey("ads.ad_id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    scrape_run_id = Column(Integer, ForeignKey("scrape_runs.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    has_low_impressions = Column(Boolean, default=False)
    ad_text = Column(Text)
    media_url = Column(Text)
    landing_page_url = Column(Text)
    platforms = Column(JSON)
    regions = Column(JSON)
    raw_data = Column(JSON)  # Store full raw scraped data
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AdSnapshot(ad_id={self.ad_id}, date={self.snapshot_date})>"
