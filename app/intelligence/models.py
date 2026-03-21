# app/intelligence/models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import relationship
from app.database.models import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    article_events = relationship("ArticleEvent", back_populates="event", cascade="all, delete-orphan")
    summaries = relationship("EventSummary", back_populates="event", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Event(id={self.id}, name='{self.name}', user_id={self.user_id})>"


class ArticleEvent(Base):
    __tablename__ = "article_events"

    article_id = Column(Integer, ForeignKey("articles.id", ondelete='CASCADE'), primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete='CASCADE'), primary_key=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("Event", back_populates="article_events")
    article = relationship("Article", back_populates="article_events")

    def __repr__(self):
        return f"<ArticleEvent(article_id={self.article_id}, event_id={self.event_id})>"


class EventSummary(Base):
    __tablename__ = "event_summaries"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete='CASCADE'), nullable=False, index=True)
    summary_json = Column(JSON, nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    article_count = Column(Integer, nullable=False)

    event = relationship("Event", back_populates="summaries")

    def __repr__(self):
        return f"<EventSummary(id={self.id}, event_id={self.event_id}, article_count={self.article_count})>"
