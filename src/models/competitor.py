from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime
from src.models.database import Base


class Competitor(Base):
    """Competitor Facebook pages to track."""

    __tablename__ = "competitors"

    page_id = Column(String(50), primary_key=True)
    page_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Competitor(page_id={self.page_id}, page_name={self.page_name})>"
