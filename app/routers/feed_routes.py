# app/routers/feed_routes.py
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy.exc import IntegrityError
from typing import List

from .. import database
from .. import config as app_config
from ..schemas import FeedSourceResponse, AddFeedRequest, UpdateFeedRequest, RefreshStatusResponse
from .. import tasks
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["feeds"]
)


def require_admin(current_user: database.User = Depends(get_current_user)):
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.post("/feeds", response_model=FeedSourceResponse, status_code=201)
async def add_new_feed_source(
    feed_request: AddFeedRequest,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """
    Adds a new RSS feed source to the database. Admin only.
    """
    logger.info(f"API Call: Admin {admin_user.id} adding new feed source with URL: {feed_request.url}")
    existing_feed = db.query(database.FeedSource).filter(database.FeedSource.url == str(feed_request.url)).first()
    if existing_feed:
        raise HTTPException(status_code=409, detail="Feed URL already exists in the database.")

    feed_name = feed_request.name
    if not feed_name:
        try:
            feed_name = str(feed_request.url).split('/')[2].replace("www.","")
        except IndexError:
            feed_name = str(feed_request.url)
    
    new_feed = database.FeedSource(
        url=str(feed_request.url),
        name=feed_name,
        fetch_interval_minutes=feed_request.fetch_interval_minutes or app_config.DEFAULT_RSS_FETCH_INTERVAL_MINUTES
    )
    db.add(new_feed)
    try:
        db.commit()
        db.refresh(new_feed)
        logger.info(f"Successfully added new feed source: ID {new_feed.id}, URL {new_feed.url}")
        return new_feed
    except IntegrityError:
        db.rollback()
        logger.error(f"Database IntegrityError while adding feed {feed_request.url}.")
        raise HTTPException(status_code=409, detail="Feed URL already exists.")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error adding feed {feed_request.url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not add feed.")


@router.get("/feeds", response_model=List[FeedSourceResponse])
async def get_all_feed_sources(
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """
    Retrieves all RSS feed sources from the database, ordered by name. Admin only.
    """
    logger.info("API Call: Fetching all feed sources.")
    feeds = db.query(database.FeedSource).order_by(database.FeedSource.name).all()
    logger.debug(f"Retrieved {len(feeds)} feed sources from the database.")
    return feeds


@router.put("/feeds/{feed_id}", response_model=FeedSourceResponse)
async def update_feed_source_settings(
    feed_id: int,
    feed_update: UpdateFeedRequest,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """
    Updates the settings (name and/or fetch interval) for an existing RSS feed source. Admin only.
    """
    logger.info(f"API Call: Admin {admin_user.id} attempting to update feed source ID: {feed_id}")
    feed_db = db.query(database.FeedSource).filter(database.FeedSource.id == feed_id).first()
    if not feed_db:
        raise HTTPException(status_code=404, detail="Feed source not found.")

    updated_fields = False
    if feed_update.name is not None:
        feed_db.name = feed_update.name
        updated_fields = True
    if feed_update.fetch_interval_minutes is not None:
        if feed_update.fetch_interval_minutes > 0:
            feed_db.fetch_interval_minutes = feed_update.fetch_interval_minutes
            updated_fields = True
        else:
            raise HTTPException(status_code=400, detail="Fetch interval must be positive.")

    if updated_fields:
        try:
            db.add(feed_db)
            db.commit()
            db.refresh(feed_db)
            logger.info(f"Successfully updated feed source ID {feed_id}.")
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating feed source ID {feed_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Could not update feed settings.")
    else:
        logger.info(f"No changes requested for feed source ID {feed_id}.")
        
    return feed_db


@router.delete("/feeds/{feed_id}", status_code=204)
async def delete_feed_source(
    feed_id: int,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """
    Deletes an RSS feed source. Cascade deletes all user subscriptions. Admin only.
    """
    logger.info(f"API Call: Admin {admin_user.id} attempting to delete feed source ID: {feed_id}")
    
    feed_db = db.query(database.FeedSource).filter(database.FeedSource.id == feed_id).first()
    if not feed_db:
        raise HTTPException(status_code=404, detail="Feed source not found.")
    
    user_count = db.query(database.UserFeedSubscription).filter(
        database.UserFeedSubscription.feed_source_id == feed_id
    ).count()
    
    try:
        db.delete(feed_db)
        db.commit()
        logger.info(f"Successfully deleted feed source ID {feed_id} and {user_count} subscriptions (via cascade).")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting feed source ID {feed_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not delete feed source.")
    
    return None


@router.post("/trigger-rss-refresh", status_code=202)
async def manual_trigger_rss_refresh(
    background_tasks: BackgroundTasks,
    admin_user: database.User = Depends(require_admin)
):
    """
    Manually triggers the background task to refresh all RSS feeds. Admin only.
    """
    logger.info(f"API Call: Admin {admin_user.id} triggering manual RSS refresh.")
    try:
        background_tasks.add_task(tasks.trigger_rss_update_all_feeds)
        logger.info("RSS feed refresh process has been successfully scheduled in the background.")
        return {"message": "RSS feed refresh process has been initiated in the background."}
    except AttributeError:
        logger.critical("Configuration Error: 'tasks.trigger_rss_update_all_feeds' not found.")
        raise HTTPException(status_code=500, detail="RSS refresh task is not configured correctly.")
    except Exception as e:
        logger.error(f"Error scheduling manual RSS refresh: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not schedule RSS refresh.")


@router.get("/feeds/refresh-status", response_model=RefreshStatusResponse)
async def get_rss_refresh_status(
    admin_user: database.User = Depends(require_admin)
):
    """
    Checks if an RSS feed refresh task is currently in progress. Admin only.
    """
    logger.info("API Call: Checking RSS refresh status.")
    is_locked = tasks.is_rss_update_locked()
    return {"is_refreshing": is_locked}


@router.post("/feeds/{feed_id}/refresh", status_code=202)
async def refresh_single_feed(
    feed_id: int,
    background_tasks: BackgroundTasks,
    db: SQLAlchemySession = Depends(database.get_db),
    admin_user: database.User = Depends(require_admin)
):
    """
    Triggers refresh of a single specific feed. Admin only.
    """
    logger.info(f"API Call: Admin {admin_user.id} triggering RSS refresh for feed ID: {feed_id}")
    feed_db = db.query(database.FeedSource).filter(database.FeedSource.id == feed_id).first()
    if not feed_db:
        raise HTTPException(status_code=404, detail="Feed source not found.")
    
    try:
        background_tasks.add_task(tasks.trigger_rss_update_single_feed, feed_id)
        logger.info(f"RSS feed refresh for feed ID {feed_id} has been scheduled in the background.")
        return {"message": f"RSS feed refresh for '{feed_db.name}' has been initiated.", "feed_id": feed_id}
    except AttributeError:
        logger.critical("Configuration Error: 'tasks.trigger_rss_update_single_feed' not found.")
        raise HTTPException(status_code=500, detail="Single feed refresh task is not configured correctly.")
    except Exception as e:
        logger.error(f"Error scheduling single feed RSS refresh for feed ID {feed_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not schedule RSS refresh.")