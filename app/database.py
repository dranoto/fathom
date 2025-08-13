# app/database.py
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, Index, Table, inspect, Boolean
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession, relationship, declarative_base # Mapped, mapped_column for newer SQLAlchemy
from sqlalchemy.sql import func, text
from contextlib import contextmanager
from typing import Generator, Any, Optional # Added Optional

from . import config

DATABASE_URL = config.DATABASE_URL

# Ensure the directory for the SQLite database exists
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
    db_file_path = DATABASE_URL.replace("sqlite:///", "/") # Ensure correct path for absolute
    db_dir = os.path.dirname(db_file_path)
    if db_dir and not os.path.exists(db_dir): # Check if the directory component exists
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

# --- Association Table for Article and Tag ---
article_tag_association = Table('article_tag_association', Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True), # Added ondelete
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True) # Added ondelete
)

# --- Database Models ---
class RSSFeedSource(Base):
    __tablename__ = "rss_feed_sources"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    fetch_interval_minutes = Column(Integer, default=60)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    articles = relationship("Article", back_populates="feed_source", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RSSFeedSource(id={self.id}, url='{self.url}', name='{self.name}')>"

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    # Ensure feed_source_id has ON DELETE SET NULL or similar if feeds can be deleted independently
    # or handle it via cascade from RSSFeedSource if articles should be deleted when feed is.
    # Current setup: cascade="all, delete-orphan" on RSSFeedSource.articles means articles are deleted.
    feed_source_id = Column(Integer, ForeignKey("rss_feed_sources.id"), nullable=True)

    url = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=True)
    publisher_name = Column(String, nullable=True)
    published_date = Column(DateTime(timezone=True), nullable=True, index=True)

    # NEW: To store the plain-text description from the RSS feed entry.
    rss_description = Column(Text, nullable=True)

    # This field will store the primary textual content, often extracted as innerText or a cleaned version.
    scraped_text_content = Column(Text, nullable=True)
    
    # NEW FIELD: To store the full HTML content fetched from the article.
    # This will be sanitized before being sent to the frontend.
    full_html_content = Column(Text, nullable=True)

    # NEW FIELD: To store the word count of the scraped text content.
    word_count = Column(Integer, nullable=True, index=True)

    # NEW FIELD: For favoriting articles
    is_favorite = Column(Boolean, default=False, nullable=False, index=True)


    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    feed_source = relationship("RSSFeedSource", back_populates="articles")
    summaries = relationship("Summary", back_populates="article", cascade="all, delete-orphan")
    chat_history = relationship("ChatHistory", back_populates="article", cascade="all, delete-orphan")
    
    tags = relationship("Tag", secondary=article_tag_association, back_populates="articles")

    __table_args__ = (
        Index('ix_articles_published_date_id', 'published_date', 'id'),
    )

    def __repr__(self):
        return f"<Article(id={self.id}, title='{self.title[:50] if self.title else ''}...', url='{self.url}')>"

class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete='CASCADE'), nullable=False, index=True) # Added ondelete

    summary_text = Column(Text, nullable=False)
    prompt_used = Column(Text, nullable=True)
    model_used = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    article = relationship("Article", back_populates="summaries")

    def __repr__(self):
        return f"<Summary(id={self.id}, article_id={self.article_id}, text_start='{self.summary_text[:50]}...')>"

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete='CASCADE'), nullable=False, index=True) # Added ondelete

    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    prompt_used = Column(Text, nullable=True)
    model_used = Column(String, nullable=True)

    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    article = relationship("Article", back_populates="chat_history")

    def __repr__(self):
        return f"<ChatHistory(id={self.id}, article_id={self.article_id}, question='{self.question[:50]}...')>"

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    articles = relationship("Article", secondary=article_tag_association, back_populates="tags")

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"

def create_db_and_tables():
    print("DATABASE: Attempting to create database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("DATABASE: Database tables checked/created successfully.")

        # Simple migration logic to add missing columns
        inspector = inspect(engine)
        table_name = "articles"
        if not inspector.has_table(table_name):
            print(f"DATABASE: Table '{table_name}' not found, skipping migration check.")
            return

        columns = inspector.get_columns(table_name)
        column_names = {c['name'] for c in columns}

        # List of columns to check and add if they don't exist
        # Each tuple is (column_name, column_type)
        # E.g., ('rss_description', 'TEXT')
        columns_to_add = [
            ('rss_description', 'TEXT'),
            ('full_html_content', 'TEXT'),
            ('word_count', 'INTEGER'),
            ('is_favorite', 'BOOLEAN')
        ]

        with engine.connect() as connection:
            with connection.begin(): # Start a transaction
                for column_name, column_type in columns_to_add:
                    if column_name not in column_names:
                        print(f"DATABASE: Column '{column_name}' not found in '{table_name}'. Adding it.")
                        try:
                            # Use text() for literal SQL
                            connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type};'))
                            print(f"DATABASE: Successfully added column '{column_name}'.")
                        except Exception as alter_e:
                            print(f"DATABASE: Error adding column '{column_name}': {alter_e}")
                            # The transaction will be rolled back automatically on exception

    except Exception as e:
        print(f"DATABASE: Error during database setup: {e}")


if __name__ == "__main__":
    # This is typically for direct script execution, e.g., initial setup
    print("DATABASE: Running database setup directly.")
    create_db_and_tables()
