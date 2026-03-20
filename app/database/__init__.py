# app/database/__init__.py
"""
Database package - models, migrations, and session management.
"""

from .models import (
    Base,
    engine,
    SessionLocal,
    DATABASE_URL,
    db_session_scope,
    get_db,
    User,
    UserArticleState,
    UserFeedSubscription,
    UserSettings,
    FeedSource,
    Article,
    Summary,
    ChatHistory,
    Tag,
    article_tag_association,
)

from .migrations import create_db_and_tables

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "DATABASE_URL",
    "db_session_scope",
    "get_db",
    "User",
    "UserArticleState",
    "UserFeedSubscription",
    "UserSettings",
    "FeedSource",
    "Article",
    "Summary",
    "ChatHistory",
    "Tag",
    "article_tag_association",
    "create_db_and_tables",
]