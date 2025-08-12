# app/routers/config_routes.py
import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session as SQLAlchemySession
from typing import List, Dict, Any # For type hinting

# Relative imports for modules within the 'app' directory
from .. import database # To access get_db and ORM models like RSSFeedSource
from .. import config as app_config # To access application-level configurations
from .. import summarizer
from ..schemas import InitialConfigResponse, UpdateConfigRequest, UpdateConfigResponse # To use the Pydantic model for the response

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Create an APIRouter instance for these configuration-related routes
# - prefix: a common path prefix for all routes defined in this router
# - tags: used for grouping routes in the OpenAPI documentation (Swagger UI)
router = APIRouter(
    prefix="/api",
    tags=["configuration"]
)

@router.get("/initial-config", response_model=InitialConfigResponse)
async def get_initial_config_endpoint(request: Request, db: SQLAlchemySession = Depends(database.get_db)):
    """
    Endpoint to fetch the initial configuration for the frontend.
    This includes default RSS feeds, all feed sources from the database,
    default application settings like articles per page, prompts, and
    details about the browser extension and headless mode.
    """
    logger.info("API Call: Fetching initial configuration.")

    # Query the database for all RSSFeedSource records, ordered by name
    db_feeds = db.query(database.RSSFeedSource).order_by(database.RSSFeedSource.name).all()

    # Format the database feed sources into the structure expected by the frontend/Pydantic model
    db_feed_sources_response: List[Dict[str, Any]] = [
        {"id": feed.id, "url": feed.url, "name": feed.name, "fetch_interval_minutes": feed.fetch_interval_minutes}
        for feed in db_feeds
    ]
    logger.debug(f"Found {len(db_feed_sources_response)} feed sources in the database.")

    summary_model_name = database.get_setting(db, "summary_model_name", app_config.DEFAULT_SUMMARY_MODEL_NAME)
    chat_model_name = database.get_setting(db, "chat_model_name", app_config.DEFAULT_CHAT_MODEL_NAME)
    tag_model_name = database.get_setting(db, "tag_model_name", app_config.DEFAULT_TAG_MODEL_NAME)

    # Construct and return the InitialConfigResponse object
    # This uses values from the application's configuration (app_config)
    # and the data retrieved from the database.
    response_data = InitialConfigResponse(
        default_rss_feeds=app_config.RSS_FEED_URLS,
        all_db_feed_sources=db_feed_sources_response,
        default_articles_per_page=app_config.DEFAULT_PAGE_SIZE,
        default_summary_prompt=app_config.DEFAULT_SUMMARY_PROMPT,
        default_chat_prompt=app_config.DEFAULT_CHAT_PROMPT,
        default_tag_generation_prompt=app_config.DEFAULT_TAG_GENERATION_PROMPT,
        default_rss_fetch_interval_minutes=app_config.DEFAULT_RSS_FETCH_INTERVAL_MINUTES,
        path_to_extension=app_config.PATH_TO_EXTENSION,
        use_headless_browser=app_config.USE_HEADLESS_BROWSER,
        summary_model_name=summary_model_name,
        chat_model_name=chat_model_name,
        tag_model_name=tag_model_name,
        available_models=request.app.state.available_models
    )
    logger.info("Successfully prepared initial configuration response.")
    return response_data

@router.put("/config", response_model=UpdateConfigResponse)
async def update_config_endpoint(request: Request, config_update: UpdateConfigRequest, db: SQLAlchemySession = Depends(database.get_db)):
    with database.db_session_scope() as db_session:
        database.set_setting(db_session, "summary_model_name", config_update.summary_model_name)
        database.set_setting(db_session, "chat_model_name", config_update.chat_model_name)
        database.set_setting(db_session, "tag_model_name", config_update.tag_model_name)

    # Re-initialize LLMs
    try:
        app = request.app
        summary_llm = summarizer.initialize_llm(
            api_key=app_config.GEMINI_API_KEY,
            model_name=config_update.summary_model_name,
            temperature=0.2, max_output_tokens=app_config.SUMMARY_MAX_OUTPUT_TOKENS
        )
        if summary_llm:
            app.state.llm_summary_instance = summary_llm

        chat_llm = summarizer.initialize_llm(
            api_key=app_config.GEMINI_API_KEY,
            model_name=config_update.chat_model_name,
            temperature=0.5, max_output_tokens=app_config.CHAT_MAX_OUTPUT_TOKENS
        )
        if chat_llm:
            app.state.llm_chat_instance = chat_llm

        tag_llm = summarizer.initialize_llm(
            api_key=app_config.GEMINI_API_KEY,
            model_name=config_update.tag_model_name,
            temperature=0.1, max_output_tokens=app_config.TAG_MAX_OUTPUT_TOKENS
        )
        if tag_llm:
            app.state.llm_tag_instance = tag_llm

        return UpdateConfigResponse(
            summary_model_name=config_update.summary_model_name,
            chat_model_name=config_update.chat_model_name,
            tag_model_name=config_update.tag_model_name
        )
    except Exception as e:
        logger.error(f"Error re-initializing LLMs after config update: {e}")
        raise HTTPException(status_code=500, detail="Failed to re-initialize AI models.")
