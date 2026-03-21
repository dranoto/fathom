# app/routers/config_routes.py
import logging
import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session as SQLAlchemySession
from typing import List, Dict, Any

# Updated imports to use the new settings_database
from .. import database, settings_database
from .. import config as app_config
from .. import summarizer
from ..schemas import (
    InitialConfigResponse,
    UpdateAppSettingsRequest,
    UpdateAppSettingsResponse,
    AppSettings
)
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["configuration"]
)

@router.get("/initial-config", response_model=InitialConfigResponse)
async def get_initial_config_endpoint(
    request: Request,
    current_user: database.User = Depends(get_current_user),
    main_db: SQLAlchemySession = Depends(database.get_db),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db)
):
    """
    Endpoint to fetch the initial configuration for the frontend.
    This now separates settings from other app data like feed sources.
    """
    logger.info("API Call: Fetching initial configuration.")

    # 1. Fetch all feed sources from the main database
    db_feeds = main_db.query(database.FeedSource).order_by(database.FeedSource.name).all()
    db_feed_sources_response: List[Dict[str, Any]] = [
        {"id": feed.id, "url": feed.url, "name": feed.name, "fetch_interval_minutes": feed.fetch_interval_minutes}
        for feed in db_feeds
    ]
    logger.debug(f"Found {len(db_feed_sources_response)} feed sources in the main database.")

    # 2. Fetch all settings from the settings database
    all_settings = settings_database.get_all_settings(settings_db)

    # 3. Construct the AppSettings Pydantic model with robust type casting
    try:
        articles_per_page = int(all_settings.get("articles_per_page"))
    except (ValueError, TypeError):
        articles_per_page = app_config.DEFAULT_PAGE_SIZE
        logger.warning(f"Invalid 'articles_per_page' value in settings DB. Falling back to default: {articles_per_page}")

    try:
        rss_fetch_interval_minutes = int(all_settings.get("rss_fetch_interval_minutes"))
    except (ValueError, TypeError):
        rss_fetch_interval_minutes = app_config.DEFAULT_RSS_FETCH_INTERVAL_MINUTES
        logger.warning(f"Invalid 'rss_fetch_interval_minutes' value in settings DB. Falling back to default: {rss_fetch_interval_minutes}")

    try:
        minimum_word_count = int(all_settings.get("minimum_word_count"))
    except (ValueError, TypeError):
        minimum_word_count = app_config.DEFAULT_MINIMUM_WORD_COUNT
        logger.warning(f"Invalid 'minimum_word_count' value in settings DB. Falling back to default: {minimum_word_count}")

    app_settings = AppSettings(
        summary_model_name=all_settings.get("summary_model_name"),
        chat_model_name=all_settings.get("chat_model_name"),
        tag_model_name=all_settings.get("tag_model_name"),
        articles_per_page=articles_per_page,
        rss_fetch_interval_minutes=rss_fetch_interval_minutes,
        summary_prompt=all_settings.get("summary_prompt"),
        chat_prompt=all_settings.get("chat_prompt"),
        tag_generation_prompt=all_settings.get("tag_generation_prompt"),
        minimum_word_count=minimum_word_count,
    )

    # 4. Construct and return the main response object
    response_data = InitialConfigResponse(
        settings=app_settings,
        default_rss_feeds=app_config.RSS_FEED_URLS, # This remains from env/config
        all_db_feed_sources=db_feed_sources_response,
        path_to_extension=app_config.PATH_TO_EXTENSION,
        use_headless_browser=app_config.USE_HEADLESS_BROWSER,
        available_models=request.app.state.available_models
    )
    logger.info("Successfully prepared initial configuration response.")
    return response_data

@router.put("/config", response_model=UpdateAppSettingsResponse)
async def update_app_settings_endpoint(
    request: Request,
    config_update: UpdateAppSettingsRequest,
    current_user: database.User = Depends(get_current_user),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db)
):
    """
    Endpoint to update all application settings.
    Receives a single object with all settings and saves them to the settings database.
    """
    logger.info("API Call: Updating application settings.")

    try:
        # 1. Save all settings to the settings database
        with settings_database.db_session_scope() as db_session:
            settings_dict = config_update.settings.model_dump()
            settings_database.set_multiple_settings(db_session, settings_dict)

        logger.info("Successfully saved settings to the database.")

        # 2. Re-initialize LLMs with the new model names
        app = request.app
        updated_settings = config_update.settings

        def override_gemini_models(model_name: str, default_name: str) -> str:
            if model_name and "gemini" in model_name.lower():
                logger.warning(f"CONFIG_ROUTES: Model '{model_name}' contains 'gemini' which is no longer supported. Using default: {default_name}")
                return default_name
            return model_name

        summary_model = override_gemini_models(updated_settings.summary_model_name, app_config.DEFAULT_SUMMARY_MODEL_NAME)
        chat_model = override_gemini_models(updated_settings.chat_model_name, app_config.DEFAULT_CHAT_MODEL_NAME)
        tag_model = override_gemini_models(updated_settings.tag_model_name, app_config.DEFAULT_TAG_MODEL_NAME)

        # Initialize Summary LLM
        summary_llm = summarizer.initialize_llm(
            api_key=app_config.OPENAI_API_KEY,
            base_url=app_config.OPENAI_BASE_URL,
            model_name=summary_model,
            temperature=app_config.SUMMARY_LLM_TEMPERATURE, max_tokens=app_config.SUMMARY_MAX_OUTPUT_TOKENS
        )
        if summary_llm:
            app.state.llm_summary_instance = summary_llm

        # Initialize Chat LLM
        chat_llm = summarizer.initialize_llm(
            api_key=app_config.OPENAI_API_KEY,
            base_url=app_config.OPENAI_BASE_URL,
            model_name=chat_model,
            temperature=app_config.CHAT_LLM_TEMPERATURE, max_tokens=app_config.CHAT_MAX_OUTPUT_TOKENS
        )
        if chat_llm:
            app.state.llm_chat_instance = chat_llm

        # Initialize Tag LLM
        tag_llm = summarizer.initialize_llm(
            api_key=app_config.OPENAI_API_KEY,
            base_url=app_config.OPENAI_BASE_URL,
            model_name=tag_model,
            temperature=app_config.TAG_LLM_TEMPERATURE, max_tokens=app_config.TAG_MAX_OUTPUT_TOKENS
        )
        if tag_llm:
            app.state.llm_tag_instance = tag_llm

        logger.info("Successfully re-initialized AI models.")

        # 3. Return a success response with the updated settings
        return UpdateAppSettingsResponse(
            message="Settings updated successfully.",
            settings=updated_settings
        )

    except Exception as e:
        logger.error(f"Error updating application settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update settings.")

@router.post("/config/refresh-models")
async def refresh_available_models_endpoint(
    request: Request,
    current_user: database.User = Depends(get_current_user),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db)
):
    """Fetches available models from OpenAI API and updates cache."""
    logger.info("API Call: Refreshing available models from OpenAI API.")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{app_config.OPENAI_BASE_URL}/v1/models",
                headers={"Authorization": f"Bearer {app_config.OPENAI_API_KEY}"},
                timeout=10.0
            )
        if response.status_code == 200:
            models_data = response.json()
            available = [m["id"] for m in models_data.get("data", [])]
            with settings_database.db_session_scope() as db:
                settings_database.set_cached_models(db, available)
            request.app.state.available_models = available
            logger.info(f"CONFIG_ROUTES: Refreshed {len(available)} available models from API.")
            return {"message": "Models refreshed successfully", "models": available}
        else:
            logger.error(f"CONFIG_ROUTES: Failed to fetch models from API: {response.status_code}")
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch models from API")
    except httpx.RequestError as e:
        logger.error(f"CONFIG_ROUTES: Request error while fetching models: {e}")
        raise HTTPException(status_code=500, detail="Request error while fetching models.")
    except Exception as e:
        logger.error(f"CONFIG_ROUTES: Error refreshing models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error refreshing models.")
