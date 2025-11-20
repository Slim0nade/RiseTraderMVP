"""
News events model.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class NewsEvent(Base, TimestampMixin):
    """
    News events table storing economic calendar events.

    Contains news and economic events that may impact trading.
    """

    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Event timing
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    local_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Event metadata
    source: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)

    # Event details
    title: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_news_events_time", "time"),
        Index("ix_news_events_source", "source"),
        Index("ix_news_events_event_type", "event_type"),
        Index("ix_news_events_time_source", "time", "source"),
    )

    def __repr__(self) -> str:
        return (
            f"<NewsEvent(id={self.id}, time={self.time}, "
            f"source='{self.source}', type='{self.event_type}', "
            f"title='{self.title[:50]}...')>"
        )

    @property
    def is_high_impact(self) -> bool:
        """
        Check if event is high impact based on type.

        This is a simplified check - in production would use more sophisticated logic.
        """
        high_impact_keywords = [
            "NFP",
            "FOMC",
            "Interest Rate",
            "GDP",
            "CPI",
            "Employment",
            "Inflation",
        ]
        return any(keyword.lower() in self.title.lower() for keyword in high_impact_keywords)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "time": self.time.isoformat() if self.time else None,
            "local_time": self.local_time.isoformat() if self.local_time else None,
            "source": self.source,
            "event_type": self.event_type,
            "title": self.title,
            "detail": self.detail,
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
