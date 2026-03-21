# app/tasks.py
import asyncio
import logging

# Relative imports for modules within the 'app' directory
from . import database # For db_session_scope
from . import rss_client # For update_all_subscribed_feeds function

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Create a lock to ensure that the RSS update process doesn't run concurrently
# if multiple triggers (e.g., scheduler, manual trigger) happen close together.
rss_update_lock = asyncio.Lock()

def is_rss_update_locked():
    """
    Checks if the RSS update lock is currently held.
    Returns True if the lock is held, False otherwise.
    """
    return rss_update_lock.locked()

async def trigger_rss_update_all_feeds():
    """
    Asynchronously triggers the update of all subscribed RSS feeds.

    This function acquires a lock to prevent concurrent execution. If the lock
    is already held, it means an update is in progress, and this run will be skipped.
    It uses a dedicated database session scope for its operations.
    """
    if rss_update_lock.locked():
        logger.info("TASK: RSS update lock is currently held. Skipping this trigger_rss_update_all_feeds run as an update is likely already in progress.")
        return

    async with rss_update_lock:
        logger.info("TASK: Acquired RSS update lock. Starting update_all_subscribed_feeds process.")
        try:
            # Use db_session_scope to ensure proper session management for this background task
            with database.db_session_scope() as db:
                # The rss_client.update_all_subscribed_feeds function handles the core logic
                # of fetching, parsing, and storing new articles from all feed sources.
                await rss_client.update_all_subscribed_feeds(db)
            logger.info("TASK: update_all_subscribed_feeds process finished successfully.")
        except Exception as e:
            # Catch any broad exceptions during the feed update process for robust logging
            logger.error(f"TASK: Exception during update_all_subscribed_feeds: {e}", exc_info=True)
        # The lock is automatically released when exiting the 'async with' block.
    logger.info("TASK: Released RSS update lock.")

async def trigger_rss_update_single_feed(feed_id: int):
    """
    Asynchronously triggers the update of a single RSS feed by its ID.
    Used for manual refresh of a specific feed.
    """
    if rss_update_lock.locked():
        logger.info(f"TASK: RSS update lock is currently held. Skipping single feed update for feed ID {feed_id}.")
        return

    async with rss_update_lock:
        logger.info(f"TASK: Acquired RSS update lock. Starting single feed update for feed ID {feed_id}.")
        try:
            with database.db_session_scope() as db:
                await rss_client.update_single_feed(db, feed_id)
            logger.info(f"TASK: Single feed update for feed ID {feed_id} finished successfully.")
        except Exception as e:
            logger.error(f"TASK: Exception during single feed update for feed ID {feed_id}: {e}", exc_info=True)
    logger.info(f"TASK: Released RSS update lock for single feed ID {feed_id}.")

async def trigger_rss_update_single_user_feed(feed_id: int, user_id: int):
    """
    Asynchronously triggers the update of a single user's RSS feed by feed ID and user ID.
    Used for manual refresh of a specific user's feed.
    """
    if rss_update_lock.locked():
        logger.info(f"TASK: RSS update lock is currently held. Skipping user feed update for feed ID {feed_id}, user {user_id}.")
        return

    async with rss_update_lock:
        logger.info(f"TASK: Acquired RSS update lock. Starting user feed update for feed ID {feed_id}, user {user_id}.")
        try:
            with database.db_session_scope() as db:
                await rss_client.update_single_user_feed(db, feed_id, user_id)
            logger.info(f"TASK: User feed update for feed ID {feed_id}, user {user_id} finished successfully.")
        except Exception as e:
            logger.error(f"TASK: Exception during user feed update for feed ID {feed_id}, user {user_id}: {e}", exc_info=True)
    logger.info(f"TASK: Released RSS update lock for user feed ID {feed_id}, user {user_id}.")

# Example of how this task might be called by a scheduler (actual scheduling setup will be in main_api.py):
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
# from apscheduler.triggers.interval import IntervalTrigger
# from .config import DEFAULT_RSS_FETCH_INTERVAL_MINUTES # Assuming this config exists
#
# async def schedule_rss_updates():
#     scheduler = AsyncIOScheduler(timezone="UTC")
#     scheduler.add_job(
#         trigger_rss_update_all_feeds,
#         trigger=IntervalTrigger(minutes=DEFAULT_RSS_FETCH_INTERVAL_MINUTES),
#         id="update_all_feeds_job",
#         name="Periodic RSS Feed Update",
#         replace_existing=True,
#         max_instances=1,
#         coalesce=True
#     )
#     scheduler.start()
#     logger.info(f"Scheduler started. RSS feeds will be checked every {DEFAULT_RSS_FETCH_INTERVAL_MINUTES} minutes.")
#
# This scheduling logic would typically reside in your main application setup (e.g., main_api.py's startup event).
