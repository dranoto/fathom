# app/database/models.py
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, Index, Table, Boolean
from sqlalchemy.types import JSON
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession, relationship, declarative_base
from sqlalchemy.sql import func
from contextlib import contextmanager
from typing import Generator

from .. import config

DATABASE_URL = config.DATABASE_URL

if DATABASE_URL.startswith("sqlite:///./"):
    db_file_path = DATABASE_URL.replace("sqlite:///./", "")
    db_dir = os.path.dirname(db_file_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            print(f"DATABASE: Created directory '{db_dir}' for SQLite database.")
        except OSError as e:
            print(f"DATABASE: Error creating directory '{db_dir}': {e}. Database might fail to create if path is invalid.")
elif DATABASE_URL.startswith("sqlite:///"):
    db_file_path = DATABASE_URL.replace("sqlite:///", "/")
    db_dir = os.path.dirname(db_file_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            print(f"DATABASE: Created directory '{db_dir}' for SQLite database (absolute path).")
        except OSError as e:
            print(f"DATABASE: Error creating directory '{db_dir}': {e}.")

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 15
    } if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

@contextmanager
def db_session_scope() -> Generator[SQLAlchemySession, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_db() -> Generator[SQLAlchemySession, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    article_states = relationship("UserArticleState", back_populates="user", cascade="all, delete-orphan")
    feed_subscriptions = relationship("UserFeedSubscription", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="user", cascade="all, delete-orphan")
    chat_history = relationship("ChatHistory", back_populates="user", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"

class UserArticleState(Base):
    __tablename__ = "user_article_states"

    user_id = Column(Integer, ForeignKey("users.id", ondelete='CASCADE'), primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete='CASCADE'), primary_key=True)
    is_read = Column(Boolean, default=False, nullable=False)
    is_favorite = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="article_states")
    article = relationship("Article", back_populates="user_article_states")

    __table_args__ = (
        Index('ix_user_article_states_user_article', 'user_id', 'article_id'),
    )

    def __repr__(self):
        return f"<UserArticleState(user_id={self.user_id}, article_id={self.article_id}, read={self.is_read}, fav={self.is_favorite})>"

class UserFeedSubscription(Base):
    __tablename__ = "user_feed_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete='CASCADE'), nullable=False, index=True)
    feed_source_id = Column(Integer, ForeignKey("feed_sources.id", ondelete='CASCADE'), nullable=False, index=True)
    custom_name = Column(String, nullable=True)
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="feed_subscriptions")
    feed_source = relationship("FeedSource", back_populates="subscriptions")

    __table_args__ = (
        UniqueConstraint('user_id', 'feed_source_id', name='uq_user_feed_subscription'),
    )

    def __repr__(self):
        return f"<UserFeedSubscription(id={self.id}, user_id={self.user_id}, feed_source_id={self.feed_source_id})>"

class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(Integer, ForeignKey("users.id", ondelete='CASCADE'), primary_key=True)
    page_size = Column(Integer, default=6)
    fetch_interval_minutes = Column(Integer, default=60)
    summary_prompt = Column(Text, nullable=True)
    chat_prompt = Column(Text, nullable=True)
    tag_prompt = Column(Text, nullable=True)

    user = relationship("User", back_populates="settings")

    def __repr__(self):
        return f"<UserSettings(user_id={self.user_id})>"

article_tag_association = Table('article_tag_association', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('article_id', Integer, ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_article_tag_assoc_user_article', 'user_id', 'article_id')
)

class FeedSource(Base):
    __tablename__ = "feed_sources"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    fetch_interval_minutes = Column(Integer, default=60)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    articles = relationship("Article", back_populates="feed_source")
    subscriptions = relationship("UserFeedSubscription", back_populates="feed_source", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<FeedSource(id={self.id}, url='{self.url}', name='{self.name}')>"

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    feed_source_id = Column(Integer, ForeignKey("feed_sources.id"), nullable=True, index=True)

    url = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=True)
    publisher_name = Column(String, nullable=True)
    published_date = Column(DateTime(timezone=True), nullable=True, index=True)

    rss_description = Column(Text, nullable=True)
    raw_rss_item = Column(JSON, nullable=True)
    scraped_text_content = Column(Text, nullable=True)
    full_html_content = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    feed_source = relationship("FeedSource", back_populates="articles")
    summaries = relationship("Summary", back_populates="article", cascade="all, delete-orphan")
    chat_history = relationship("ChatHistory", back_populates="article", cascade="all, delete-orphan")
    user_article_states = relationship("UserArticleState", back_populates="article", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=article_tag_association, back_populates="articles")
    article_events = relationship("ArticleEvent", back_populates="article", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_articles_published_date_id', 'published_date', 'id'),
    )

    def __repr__(self):
        return f"<Article(id={self.id}, title='{self.title[:50] if self.title else ''}...', url='{self.url}')>"

class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete='CASCADE'), nullable=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete='CASCADE'), nullable=False, index=True)

    summary_text = Column(Text, nullable=False)
    prompt_used = Column(Text, nullable=True)
    model_used = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="summaries")
    article = relationship("Article", back_populates="summaries")

    __table_args__ = (
        UniqueConstraint('user_id', 'article_id', name='uq_summary_user_article'),
        Index('ix_summaries_user_article', 'user_id', 'article_id'),
    )

    def __repr__(self):
        return f"<Summary(id={self.id}, user_id={self.user_id}, article_id={self.article_id})>"

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete='CASCADE'), nullable=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete='CASCADE'), nullable=False, index=True)

    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    prompt_used = Column(Text, nullable=True)
    model_used = Column(String, nullable=True)

    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="chat_history")
    article = relationship("Article", back_populates="chat_history")

    __table_args__ = (
        Index('ix_chat_history_user_article', 'user_id', 'article_id'),
    )

    def __repr__(self):
        return f"<ChatHistory(id={self.id}, user_id={self.user_id}, article_id={self.article_id})>"

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String, index=True, nullable=False)
    normalized_name = Column(String, index=True, nullable=True)

    user = relationship("User", back_populates="tags")
    articles = relationship("Article", secondary=article_tag_association, back_populates="tags")

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_tag_user_name'),
        UniqueConstraint('user_id', 'normalized_name', name='uq_tag_user_normalized_name'),
    )

    def __repr__(self):
        return f"<Tag(id={self.id}, user_id={self.user_id}, name='{self.name}')>"