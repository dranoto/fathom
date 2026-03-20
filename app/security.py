# app/security.py
import logging
from typing import Set
from fastapi import HTTPException
from sqlalchemy.orm import Session as SQLAlchemySession

from . import database

logger = logging.getLogger(__name__)


def get_user_feed_source_ids(db: SQLAlchemySession, user_id: int) -> Set[int]:
    """
    Returns set of FeedSource IDs for user's subscribed feeds.
    """
    subs = db.query(database.UserFeedSubscription.feed_source_id).filter(
        database.UserFeedSubscription.user_id == user_id
    ).all()
    return {s[0] for s in subs}


def verify_article_access(db: SQLAlchemySession, article_id: int, user_id: int) -> database.Article:
    """
    Verifies user has access to article via their feeds.
    Raises 404 if article doesn't exist or user doesn't have access.
    """
    feed_source_ids = get_user_feed_source_ids(db, user_id)
    
    if not feed_source_ids:
        raise HTTPException(status_code=404, detail="Article not found")
    
    article = db.query(database.Article).filter(
        database.Article.id == article_id,
        database.Article.feed_source_id.in_(feed_source_ids)
    ).first()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return article