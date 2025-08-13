# app/main_api.py
import logging
import asyncio 
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Langchain and LLM related imports
from langchain_google_genai import GoogleGenerativeAI
import google.genai as genai

# APScheduler imports
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Relative imports for application modules
from . import database, settings_database # Import settings_database
from . import config as app_config 
from . import summarizer 
from . import rss_client 
from . import tasks 

# Import router modules
from .routers import (
    config_routes,
    feed_routes,
    article_routes,
    chat_routes,
    admin_routes,
    content_routes
)

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global Variables ---
# These are less critical now as app.state is the primary carrier, but can be useful for debugging.
llm_summary_instance_global: GoogleGenerativeAI | None = None
llm_chat_instance_global: GoogleGenerativeAI | None = None
llm_tag_instance_global: GoogleGenerativeAI | None = None

# APScheduler instance
scheduler = AsyncIOScheduler(timezone="UTC")

# FastAPI application instance
app = FastAPI(
    title="News Summarizer API & Frontend (Refactored)",
    version="2.2.0", # Updated version for settings refactor
    description="API for fetching, summarizing, tagging, chatting with, and viewing full content of news articles."
)

# --- Application Lifecycle Events (Startup & Shutdown) ---
@app.on_event("startup")
async def startup_event():
    global llm_summary_instance_global, llm_chat_instance_global, llm_tag_instance_global, scheduler
    logger.info("MAIN_API: Application startup sequence initiated...")

    # 1. Initialize Databases
    logger.info("MAIN_API: Initializing databases...")
    try:
        # Initialize the main article database
        database.create_db_and_tables()
        logger.info("MAIN_API: Main article database tables checked/created successfully.")

        # Initialize the new settings database
        settings_database.create_settings_db_and_tables()
        logger.info("MAIN_API: Settings database tables checked/created successfully.")
    except Exception as e:
        logger.critical(f"MAIN_API: CRITICAL ERROR during database initialization: {e}", exc_info=True)
        # Depending on the error, we might want to exit here.
        # For now, we'll log it as critical and continue.

    # 2. Add Initial RSS Feeds to DB (from env vars, if any)
    if app_config.RSS_FEED_URLS:
        logger.info(f"MAIN_API: Ensuring initial RSS feeds are in DB from config: {app_config.RSS_FEED_URLS}")
        try:
            with database.db_session_scope() as db:
                 rss_client.add_initial_feeds_to_db(db, app_config.RSS_FEED_URLS)
            logger.info("MAIN_API: Initial RSS feeds processed.")
        except Exception as e:
            logger.error(f"MAIN_API: Error processing initial RSS feeds: {e}", exc_info=True)
    else:
        logger.info("MAIN_API: No initial RSS_FEED_URLS configured in app_config to add to DB.")

    # 3. Initialize LLM Instances using settings from the settings DB
    logger.info("MAIN_API: Attempting to initialize LLM instances from settings DB...")
    if not app_config.GEMINI_API_KEY:
        logger.critical("MAIN_API: CRITICAL ERROR - GEMINI_API_KEY not found. LLM features will be disabled.")
    else:
        try:
            # Use the new settings database to get model names
            with settings_database.db_session_scope() as settings_db:
                all_settings = settings_database.get_all_settings(settings_db)
                summary_model_name = all_settings.get("summary_model_name")
                chat_model_name = all_settings.get("chat_model_name")
                tag_model_name = all_settings.get("tag_model_name")

            # Programmatically fetch available models
            try:
                genai.configure(api_key=app_config.GEMINI_API_KEY)
                # Filter for models that support 'generateContent' and are text-based.
                # The 'models/' prefix is common for Gemini models.
                app.state.available_models = sorted([
                    model.name for model in genai.list_models()
                    if 'generateContent' in model.supported_generation_methods and 'models/' in model.name
                ])
                logger.info(f"MAIN_API: Successfully fetched {len(app.state.available_models)} available models from Google AI.")

                # This is a safety net in case the API list changes or a user has an old model name saved.
                # It ensures that any model name already saved in the database is present in the list.
                saved_models = {summary_model_name, chat_model_name, tag_model_name}
                for model_name in sorted(m for m in saved_models if m):
                    if model_name not in app.state.available_models:
                        app.state.available_models.insert(0, model_name)
                        logger.warning(f"MAIN_API: Saved model '{model_name}' not found in fetched list; adding it to the top to ensure availability.")

            except google.api_core.exceptions.GoogleAPICallError as e:
                logger.error(f"MAIN_API: Failed to fetch models from Google AI: {e}. Falling back to a default list.")
                # Fallback to a default list in case of API failure
                app.state.available_models = [
                    "gemini-1.5-flash-latest",
                    "gemini-1.5-pro-latest",
                    "gemini-1.0-pro",
                ]

            llm_summary_instance_global = summarizer.initialize_llm(
                api_key=app_config.GEMINI_API_KEY,
                model_name=summary_model_name,
                temperature=0.2, max_output_tokens=app_config.SUMMARY_MAX_OUTPUT_TOKENS
            )
            app.state.llm_summary_instance = llm_summary_instance_global
            if app.state.llm_summary_instance:
                logger.info(f"MAIN_API: Summarization LLM ({summary_model_name}) initialized.")
            else:
                logger.error(f"MAIN_API: Summarization LLM ({summary_model_name}) FAILED to initialize.")

            llm_chat_instance_global = summarizer.initialize_llm(
                api_key=app_config.GEMINI_API_KEY,
                model_name=chat_model_name,
                temperature=0.5, max_output_tokens=app_config.CHAT_MAX_OUTPUT_TOKENS
            )
            app.state.llm_chat_instance = llm_chat_instance_global
            if app.state.llm_chat_instance:
                logger.info(f"MAIN_API: Chat LLM ({chat_model_name}) initialized.")
            else:
                logger.error(f"MAIN_API: Chat LLM ({chat_model_name}) FAILED to initialize.")

            llm_tag_instance_global = summarizer.initialize_llm(
                api_key=app_config.GEMINI_API_KEY,
                model_name=tag_model_name,
                temperature=0.1, max_output_tokens=app_config.TAG_MAX_OUTPUT_TOKENS
            )
            app.state.llm_tag_instance = llm_tag_instance_global
            if app.state.llm_tag_instance:
                logger.info(f"MAIN_API: Tag Generation LLM ({tag_model_name}) initialized.")
            else:
                logger.error(f"MAIN_API: Tag Generation LLM ({tag_model_name}) FAILED to initialize.")

        except Exception as e:
            logger.critical(f"MAIN_API: CRITICAL ERROR during LLM Initialization: {e}.", exc_info=True)
            app.state.llm_summary_instance = None
            app.state.llm_chat_instance = None
            app.state.llm_tag_instance = None

    # 4. Start APScheduler for RSS Feed Updates
    if not scheduler.running:
        # Get interval from settings DB, fallback to config
        with settings_database.db_session_scope() as settings_db:
            try:
                interval_minutes = int(settings_database.get_setting(
                    settings_db,
                    "rss_fetch_interval_minutes",
                    str(app_config.DEFAULT_RSS_FETCH_INTERVAL_MINUTES)
                ))
            except (ValueError, TypeError):
                interval_minutes = app_config.DEFAULT_RSS_FETCH_INTERVAL_MINUTES
                logger.warning(f"Invalid 'rss_fetch_interval_minutes' in settings DB, falling back to default: {interval_minutes}")

        logger.info(f"MAIN_API: Configuring APScheduler to run RSS feed updates every {interval_minutes} minutes.")
        scheduler.add_job(
            tasks.trigger_rss_update_all_feeds,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="update_all_feeds_job",
            name="Periodic RSS Feed Update",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=15),
            max_instances=1,
            coalesce=True
        )
        try:
            scheduler.start()
            logger.info("MAIN_API: APScheduler started successfully.")
        except Exception as e:
            logger.error(f"MAIN_API: Failed to start APScheduler: {e}", exc_info=True)
    else:
        logger.info("MAIN_API: APScheduler is already running.")

    logger.info("MAIN_API: Application startup sequence complete.")


@app.on_event("shutdown")
def shutdown_event():
    global scheduler 
    logger.info("MAIN_API: Application shutdown sequence initiated...")
    if scheduler.running:
        logger.info("MAIN_API: Shutting down APScheduler...")
        try:
            scheduler.shutdown()
            logger.info("MAIN_API: APScheduler shut down successfully.")
        except Exception as e:
            logger.error(f"MAIN_API: Error shutting down APScheduler: {e}", exc_info=True)
    logger.info("MAIN_API: Application shutdown sequence complete.")

# --- Include Routers ---
logger.info("MAIN_API: Including API routers...")
app.include_router(config_routes.router)
app.include_router(feed_routes.router)
app.include_router(article_routes.router)
app.include_router(chat_routes.router)
app.include_router(admin_routes.router)
app.include_router(content_routes.router)
logger.info("MAIN_API: All API routers included.")

# --- Static Files & Root Endpoint ---
try:
    app.mount("/static", StaticFiles(directory="frontend"), name="static_frontend_files")
    logger.info("MAIN_API: Static files mounted from 'frontend' directory at '/static'.")
except RuntimeError as e:
    logger.error(f"MAIN_API: Error mounting static files. Ensure 'frontend' directory exists at the project root. Details: {e}", exc_info=True)

@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_index_html():
    index_html_path = "frontend/index.html"
    import os
    if not os.path.exists(index_html_path):
        logger.error(f"MAIN_API: index.html not found at '{index_html_path}'. Ensure it exists.")
    return FileResponse(index_html_path)

logger.info("MAIN_API: FastAPI application initialized and configured.")
