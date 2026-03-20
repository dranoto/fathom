# app/routers/admin_routes.py
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session as SQLAlchemySession

from .. import database
from .. import config as app_config
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

def require_admin(current_user: database.User = Depends(get_current_user)):
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

class UserResponse(BaseModel):
    id: int
    email: str
    is_admin: bool
    created_at: Optional[datetime] = None
    feed_count: int = 0
    article_state_count: int = 0

    class Config:
        from_attributes = True

class FeedSourceWithUserCount(BaseModel):
    id: int
    url: str
    name: str
    fetch_interval_minutes: int
    user_count: int
    article_count: int
    last_fetch_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class GlobalSettingsResponse(BaseModel):
    summary_model: Optional[str] = None
    chat_model: Optional[str] = None
    tag_model: Optional[str] = None
    summary_max_output_tokens: Optional[int] = None
    chat_max_output_tokens: Optional[int] = None
    tag_max_output_tokens: Optional[int] = None
    summary_prompt: Optional[str] = None
    chat_prompt: Optional[str] = None
    tag_prompt: Optional[str] = None

class UpdateGlobalSettingsRequest(BaseModel):
    summary_model: Optional[str] = None
    chat_model: Optional[str] = None
    tag_model: Optional[str] = None
    summary_max_output_tokens: Optional[int] = None
    chat_max_output_tokens: Optional[int] = None
    tag_max_output_tokens: Optional[int] = None
    summary_prompt: Optional[str] = None
    chat_prompt: Optional[str] = None
    tag_prompt: Optional[str] = None

class AddFeedRequest(BaseModel):
    url: str
    name: Optional[str] = None
    fetch_interval_minutes: Optional[int] = None

from datetime import datetime
from typing import Optional
from pydantic import BaseModel

@router.get("/users")
async def get_all_users(
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """Get all users with their feed and article state counts."""
    users = db.query(database.User).all()
    result = []
    for user in users:
        feed_count = db.query(database.UserFeedSubscription).filter(
            database.UserFeedSubscription.user_id == user.id
        ).count()
        state_count = db.query(database.UserArticleState).filter(
            database.UserArticleState.user_id == user.id
        ).count()
        result.append(UserResponse(
            id=user.id,
            email=user.email,
            is_admin=getattr(user, 'is_admin', False),
            created_at=user.created_at,
            feed_count=feed_count,
            article_state_count=state_count
        ))
    return result

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """Delete a user and all their data (cascades)."""
    if user_id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    user = db.query(database.User).filter(database.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    email = user.email
    db.delete(user)
    db.commit()
    logger.info(f"Admin {admin_user.id} deleted user {user_id} ({email})")
    return {"message": f"User {email} deleted"}

@router.get("/feeds")
async def get_all_feeds(
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """Get all feed sources with user counts."""
    feeds = db.query(database.FeedSource).all()
    result = []
    for feed in feeds:
        user_count = db.query(database.UserFeedSubscription).filter(
            database.UserFeedSubscription.feed_source_id == feed.id
        ).count()
        article_count = db.query(database.Article).filter(
            database.Article.feed_source_id == feed.id
        ).count()
        result.append(FeedSourceWithUserCount(
            id=feed.id,
            url=feed.url,
            name=feed.name,
            fetch_interval_minutes=feed.fetch_interval_minutes or 60,
            user_count=user_count,
            article_count=article_count,
            last_fetch_at=feed.last_fetched_at
        ))
    return result

@router.post("/feeds")
async def add_feed_source(
    request: AddFeedRequest,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """Add a new global feed source."""
    existing = db.query(database.FeedSource).filter(
        database.FeedSource.url == request.url
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Feed URL already exists")
    
    feed_name = request.name
    if not feed_name:
        try:
            feed_name = request.url.split('/')[2].replace("www.", "")
        except IndexError:
            feed_name = request.url
    
    new_feed = database.FeedSource(
        url=request.url,
        name=feed_name,
        fetch_interval_minutes=request.fetch_interval_minutes or app_config.DEFAULT_RSS_FETCH_INTERVAL_MINUTES
    )
    db.add(new_feed)
    db.commit()
    db.refresh(new_feed)
    
    logger.info(f"Admin {admin_user.id} added new feed source: {request.url}")
    return {"id": new_feed.id, "url": new_feed.url, "name": new_feed.name}

@router.put("/feeds/{feed_id}")
async def update_feed_source(
    feed_id: int,
    request: AddFeedRequest,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """Update a feed source name and/or fetch interval."""
    feed_db = db.query(database.FeedSource).filter(
        database.FeedSource.id == feed_id
    ).first()
    if not feed_db:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    if request.name is not None:
        feed_db.name = request.name
    if request.fetch_interval_minutes is not None:
        if request.fetch_interval_minutes <= 0:
            raise HTTPException(status_code=400, detail="Fetch interval must be positive")
        feed_db.fetch_interval_minutes = request.fetch_interval_minutes
    
    db.commit()
    db.refresh(feed_db)
    logger.info(f"Admin {admin_user.id} updated feed source {feed_id}")
    return {"id": feed_db.id, "url": feed_db.url, "name": feed_db.name, "fetch_interval_minutes": feed_db.fetch_interval_minutes}

@router.delete("/feeds/{feed_id}")
async def delete_feed_source(
    feed_id: int,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """Delete a feed source. Cascade deletes all user subscriptions."""
    feed_db = db.query(database.FeedSource).filter(
        database.FeedSource.id == feed_id
    ).first()
    if not feed_db:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    user_count = db.query(database.UserFeedSubscription).filter(
        database.UserFeedSubscription.feed_source_id == feed_id
    ).count()
    
    db.delete(feed_db)
    db.commit()
    logger.info(f"Admin {admin_user.id} deleted feed source {feed_id} ({user_count} subscriptions cascade deleted)")
    return {"message": "Feed deleted"}

@router.get("/settings/global")
async def get_global_settings(
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """Get global model and prompt settings."""
    from .. import settings_database
    
    def get_int(db, key, default):
        val = settings_database.get_setting(db, key, str(default))
        return int(val) if val else default
    
    with settings_database.db_session_scope() as settings_db:
        return GlobalSettingsResponse(
            summary_model=settings_database.get_setting(settings_db, "summary_model_name", app_config.DEFAULT_SUMMARY_MODEL_NAME),
            chat_model=settings_database.get_setting(settings_db, "chat_model_name", app_config.DEFAULT_CHAT_MODEL_NAME),
            tag_model=settings_database.get_setting(settings_db, "tag_model_name", app_config.DEFAULT_TAG_MODEL_NAME),
            summary_max_output_tokens=get_int(settings_db, "summary_max_output_tokens", app_config.SUMMARY_MAX_OUTPUT_TOKENS),
            chat_max_output_tokens=get_int(settings_db, "chat_max_output_tokens", app_config.CHAT_MAX_OUTPUT_TOKENS),
            tag_max_output_tokens=get_int(settings_db, "tag_max_output_tokens", app_config.TAG_MAX_OUTPUT_TOKENS),
            summary_prompt=settings_database.get_setting(settings_db, "summary_prompt", app_config.DEFAULT_SUMMARY_PROMPT),
            chat_prompt=settings_database.get_setting(settings_db, "chat_prompt", app_config.DEFAULT_CHAT_PROMPT),
            tag_prompt=settings_database.get_setting(settings_db, "tag_prompt", app_config.DEFAULT_TAG_GENERATION_PROMPT),
        )

@router.put("/settings/global")
async def update_global_settings(
    request: UpdateGlobalSettingsRequest,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """Update global model and prompt settings."""
    from .. import settings_database
    
    with settings_database.db_session_scope() as settings_db:
        if request.summary_model is not None:
            settings_database.set_setting(settings_db, "summary_model_name", request.summary_model)
        if request.chat_model is not None:
            settings_database.set_setting(settings_db, "chat_model_name", request.chat_model)
        if request.tag_model is not None:
            settings_database.set_setting(settings_db, "tag_model_name", request.tag_model)
        if request.summary_max_output_tokens is not None:
            settings_database.set_setting(settings_db, "summary_max_output_tokens", str(request.summary_max_output_tokens))
        if request.chat_max_output_tokens is not None:
            settings_database.set_setting(settings_db, "chat_max_output_tokens", str(request.chat_max_output_tokens))
        if request.tag_max_output_tokens is not None:
            settings_database.set_setting(settings_db, "tag_max_output_tokens", str(request.tag_max_output_tokens))
        if request.summary_prompt is not None:
            settings_database.set_setting(settings_db, "summary_prompt", request.summary_prompt)
        if request.chat_prompt is not None:
            settings_database.set_setting(settings_db, "chat_prompt", request.chat_prompt)
        if request.tag_prompt is not None:
            settings_database.set_setting(settings_db, "tag_prompt", request.tag_prompt)
        
        logger.info(f"Admin {admin_user.id} updated global settings")
        return {"message": "Settings updated"}
