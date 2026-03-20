# app/routers/user_routes.py
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session as SQLAlchemySession
from pydantic import BaseModel

from .. import database
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["users"])


class PublicFeedResponse(BaseModel):
    feed_source_id: int
    url: str
    name: Optional[str] = None
    added_by_user_id: int

    class Config:
        from_attributes = True


class UserFeedResponse(BaseModel):
    id: int
    feed_source_id: int
    url: str
    name: Optional[str] = None
    custom_name: Optional[str] = None
    subscribed_at: datetime

    class Config:
        from_attributes = True


class AddFeedRequest(BaseModel):
    url: str
    custom_name: Optional[str] = None


class UpdateFeedRequest(BaseModel):
    custom_name: Optional[str] = None


class UserSettingsResponse(BaseModel):
    page_size: int
    fetch_interval_minutes: int
    summary_prompt: Optional[str] = None
    chat_prompt: Optional[str] = None
    tag_prompt: Optional[str] = None

    class Config:
        from_attributes = True


class UpdateSettingsRequest(BaseModel):
    page_size: Optional[int] = None
    fetch_interval_minutes: Optional[int] = None
    summary_prompt: Optional[str] = None
    chat_prompt: Optional[str] = None
    tag_prompt: Optional[str] = None


@router.get("/feeds/public", response_model=List[PublicFeedResponse])
async def get_public_feeds(
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Returns all unique feed sources added by any user (for feed discovery).
    Excludes feeds the current user already subscribes to.
    """
    logger.info(f"API: Fetching public feeds for user {current_user.id}")
    
    user_subs_feed_ids = {s.feed_source_id for s in db.query(database.UserFeedSubscription.feed_source_id).filter(
        database.UserFeedSubscription.user_id == current_user.id
    ).all()}
    
    first_adder_subq = db.query(
        database.UserFeedSubscription.feed_source_id,
        database.UserFeedSubscription.user_id
    ).distinct(database.UserFeedSubscription.feed_source_id).subquery()
    
    first_adders = db.query(
        first_adder_subq.c.feed_source_id,
        first_adder_subq.c.user_id
    ).all()
    
    unique_feeds = []
    for fa in first_adders:
        if fa.feed_source_id not in user_subs_feed_ids:
            feed_source = db.query(database.FeedSource).filter(database.FeedSource.id == fa.feed_source_id).first()
            if feed_source:
                unique_feeds.append(PublicFeedResponse(
                    feed_source_id=fa.feed_source_id,
                    url=feed_source.url,
                    name=feed_source.name,
                    added_by_user_id=fa.user_id
                ))
    
    return unique_feeds


@router.get("/users/feeds", response_model=List[UserFeedResponse])
async def get_user_feeds(
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Returns all feeds the current user is subscribed to.
    """
    logger.info(f"API: Fetching feeds for user {current_user.id}")
    
    subs = db.query(database.UserFeedSubscription).filter(
        database.UserFeedSubscription.user_id == current_user.id
    ).order_by(database.UserFeedSubscription.subscribed_at.desc()).all()
    
    result = []
    for sub in subs:
        feed_source = db.query(database.FeedSource).filter(database.FeedSource.id == sub.feed_source_id).first()
        if feed_source:
            result.append(UserFeedResponse(
                id=sub.id,
                feed_source_id=sub.feed_source_id,
                url=feed_source.url,
                name=feed_source.name,
                custom_name=sub.custom_name,
                subscribed_at=sub.subscribed_at
            ))
    
    return result


@router.post("/users/feeds", response_model=UserFeedResponse, status_code=201)
async def add_user_feed(
    request: AddFeedRequest,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Adds a new feed for the current user.
    If the URL doesn't exist in FeedSource yet, creates it so it will be scraped.
    """
    logger.info(f"API: User {current_user.id} adding feed: {request.url}")
    
    feed_source = db.query(database.FeedSource).filter(
        database.FeedSource.url == request.url
    ).first()
    
    if not feed_source:
        feed_name = request.custom_name
        if not feed_name:
            try:
                feed_name = request.url.split('/')[2].replace("www.", "")
            except IndexError:
                feed_name = request.url
        
        feed_source = database.FeedSource(
            url=request.url,
            name=feed_name
        )
        db.add(feed_source)
        db.commit()
        db.refresh(feed_source)
        logger.info(f"API: Created new FeedSource for URL: {request.url}")
    
    existing = db.query(database.UserFeedSubscription).filter(
        database.UserFeedSubscription.user_id == current_user.id,
        database.UserFeedSubscription.feed_source_id == feed_source.id
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail="Feed already subscribed")
    
    new_sub = database.UserFeedSubscription(
        user_id=current_user.id,
        feed_source_id=feed_source.id,
        custom_name=request.custom_name
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)
    
    logger.info(f"API: Feed subscribed for user {current_user.id}: {request.url}")
    
    return UserFeedResponse(
        id=new_sub.id,
        feed_source_id=new_sub.feed_source_id,
        url=feed_source.url,
        name=feed_source.name,
        custom_name=new_sub.custom_name,
        subscribed_at=new_sub.subscribed_at
    )


@router.patch("/users/feeds/{subscription_id}", response_model=UserFeedResponse)
async def update_user_feed(
    subscription_id: int,
    request: UpdateFeedRequest,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Updates a feed subscription (e.g., custom_name) for the current user.
    """
    logger.info(f"API: User {current_user.id} updating feed subscription {subscription_id}")
    
    sub = db.query(database.UserFeedSubscription).filter(
        database.UserFeedSubscription.id == subscription_id,
        database.UserFeedSubscription.user_id == current_user.id
    ).first()
    
    if not sub:
        raise HTTPException(status_code=404, detail="Feed subscription not found")
    
    feed_source = db.query(database.FeedSource).filter(database.FeedSource.id == sub.feed_source_id).first()
    
    if request.custom_name is not None:
        sub.custom_name = request.custom_name
    
    db.commit()
    db.refresh(sub)
    
    return UserFeedResponse(
        id=sub.id,
        feed_source_id=sub.feed_source_id,
        url=feed_source.url if feed_source else "",
        name=feed_source.name if feed_source else None,
        custom_name=sub.custom_name,
        subscribed_at=sub.subscribed_at
    )


@router.delete("/users/feeds/{subscription_id}", status_code=204)
async def delete_user_feed(
    subscription_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Removes a feed from the current user's subscription.
    Does not delete the feed from the library or affect other users.
    """
    logger.info(f"API: User {current_user.id} deleting feed subscription {subscription_id}")
    
    sub = db.query(database.UserFeedSubscription).filter(
        database.UserFeedSubscription.id == subscription_id,
        database.UserFeedSubscription.user_id == current_user.id
    ).first()
    
    if not sub:
        raise HTTPException(status_code=404, detail="Feed subscription not found")
    
    db.delete(sub)
    db.commit()
    
    return None


@router.post("/users/feeds/{subscription_id}/trigger-fetch", status_code=202)
async def trigger_user_feed_fetch(
    subscription_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Manually triggers a fetch for a specific user's feed subscription.
    """
    logger.info(f"API: User {current_user.id} triggering fetch for subscription {subscription_id}")
    
    sub = db.query(database.UserFeedSubscription).filter(
        database.UserFeedSubscription.id == subscription_id,
        database.UserFeedSubscription.user_id == current_user.id
    ).first()
    
    if not sub:
        raise HTTPException(status_code=404, detail="Feed subscription not found")
    
    feed_source = db.query(database.FeedSource).filter(database.FeedSource.id == sub.feed_source_id).first()
    
    from .. import tasks
    try:
        tasks.trigger_rss_update_single_user_feed(sub.id, current_user.id)
        return {"message": f"Feed fetch initiated for '{feed_source.name if feed_source else 'Unknown'}'"}
    except Exception as e:
        logger.error(f"Error triggering feed fetch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not trigger feed fetch")


@router.get("/users/settings", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Returns the current user's settings.
    """
    settings = db.query(database.UserSettings).filter(
        database.UserSettings.user_id == current_user.id
    ).first()
    
    if not settings:
        settings = database.UserSettings(user_id=current_user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return settings


@router.put("/users/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    request: UpdateSettingsRequest,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Updates the current user's settings.
    """
    logger.info(f"API: Updating settings for user {current_user.id}")
    
    settings = db.query(database.UserSettings).filter(
        database.UserSettings.user_id == current_user.id
    ).first()
    
    if not settings:
        settings = database.UserSettings(user_id=current_user.id)
        db.add(settings)
    
    if request.page_size is not None and request.page_size > 0:
        settings.page_size = request.page_size
    if request.fetch_interval_minutes is not None and request.fetch_interval_minutes > 0:
        settings.fetch_interval_minutes = request.fetch_interval_minutes
    if request.summary_prompt is not None:
        settings.summary_prompt = request.summary_prompt
    if request.chat_prompt is not None:
        settings.chat_prompt = request.chat_prompt
    if request.tag_prompt is not None:
        settings.tag_prompt = request.tag_prompt
    
    db.commit()
    db.refresh(settings)
    
    return settings