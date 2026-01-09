from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text, JSON
from src.models.database import Base


class ScrapeRun(Base):
    """Metadata and stats for each scrape run."""

    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_type = Column(String(20), nullable=False)  # full, backfill, single
    status = Column(String(20), default="running")  # running, completed, failed
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    competitors_total = Column(Integer, default=0)
    competitors_processed = Column(Integer, default=0)
    competitors_failed = Column(Integer, default=0)
    ads_found = Column(Integer, default=0)
    ads_new = Column(Integer, default=0)
    ads_updated = Column(Integer, default=0)
    ads_deleted = Column(Integer, default=0)
    media_downloaded = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    run_metadata = Column(JSON)  # Additional metadata like CLI args

    def __repr__(self):
        return f"<ScrapeRun(id={self.id}, type={self.run_type}, status={self.status})>"

    def mark_completed(self):
        """Mark the run as completed."""
        self.status = "completed"
        self.completed_at = datetime.utcnow()

    def mark_failed(self):
        """Mark the run as failed."""
        self.status = "failed"
        self.completed_at = datetime.utcnow()


class ScrapeError(Base):
    """Error logging with screenshots for debugging."""

    __tablename__ = "scrape_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scrape_run_id = Column(Integer, nullable=False, index=True)
    page_id = Column(String(50), index=True)
    error_type = Column(String(100))
    error_message = Column(Text)
    stack_trace = Column(Text)
    screenshot_path = Column(Text)
    page_url = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ScrapeError(id={self.id}, page_id={self.page_id}, type={self.error_type})>"
