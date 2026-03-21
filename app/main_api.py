# app/main_api.py
import logging
import json
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import httpx
from langchain_openai import ChatOpenAI

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import database, settings_database
from . import config as app_config
from . import summarizer
from . import rss_client
from . import tasks

from .routers import (
    config_routes,
    feed_routes,
    article_routes,
    chat_routes,
    admin_routes,
    content_routes,
    debug_routes,
    auth_routes,
    user_routes,
    tag_routes
)
from .intelligence import router as intelligence_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

llm_summary_instance_global: ChatOpenAI | None = None
llm_chat_instance_global: ChatOpenAI | None = None
llm_tag_instance_global: ChatOpenAI | None = None

scheduler = AsyncIOScheduler(timezone="UTC")

app = FastAPI(
    title="News Summarizer API & Frontend (Refactored)",
    version="2.3.0",
    description="API for fetching, summarizing, tagging, chatting with, and viewing full content of news articles."
)

@app.on_event("startup")
async def startup_event():
    global llm_summary_instance_global, llm_chat_instance_global, llm_tag_instance_global, scheduler
    logger.info("MAIN_API: Application startup sequence initiated...")

    logger.info("MAIN_API: Initializing databases...")
    try:
        database.create_db_and_tables()
        logger.info("MAIN_API: Main article database tables checked/created successfully.")

        settings_database.create_settings_db_and_tables()
        logger.info("MAIN_API: Settings database tables checked/created successfully.")
    except Exception as e:
        logger.critical(f"MAIN_API: CRITICAL ERROR during database initialization: {e}", exc_info=True)

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

    logger.info("MAIN_API: Attempting to initialize LLM instances from settings DB...")
    if not app_config.OPENAI_API_KEY:
        logger.critical("MAIN_API: CRITICAL ERROR - OPENAI_API_KEY not found. LLM features will be disabled.")
    else:
        try:
            with settings_database.db_session_scope() as settings_db:
                all_settings = settings_database.get_all_settings(settings_db)
                summary_model_name = all_settings.get("summary_model_name", app_config.DEFAULT_SUMMARY_MODEL_NAME)
                chat_model_name = all_settings.get("chat_model_name", app_config.DEFAULT_CHAT_MODEL_NAME)
                tag_model_name = all_settings.get("tag_model_name", app_config.DEFAULT_TAG_MODEL_NAME)

            def override_gemini_models(model_name: str, default_name: str) -> str:
                if model_name and "gemini" in model_name.lower():
                    logger.warning(f"MAIN_API: Stored model '{model_name}' contains 'gemini' which is no longer supported. Using default: {default_name}")
                    return default_name
                return model_name

            summary_model_name = override_gemini_models(summary_model_name, app_config.DEFAULT_SUMMARY_MODEL_NAME)
            chat_model_name = override_gemini_models(chat_model_name, app_config.DEFAULT_CHAT_MODEL_NAME)
            tag_model_name = override_gemini_models(tag_model_name, app_config.DEFAULT_TAG_MODEL_NAME)

            llm_summary_instance_global = summarizer.initialize_llm(
                api_key=app_config.OPENAI_API_KEY,
                base_url=app_config.OPENAI_BASE_URL,
                model_name=summary_model_name,
                temperature=app_config.SUMMARY_LLM_TEMPERATURE,
                max_tokens=app_config.SUMMARY_MAX_OUTPUT_TOKENS
            )
            app.state.llm_summary_instance = llm_summary_instance_global
            if app.state.llm_summary_instance:
                logger.info(f"MAIN_API: Summarization LLM ({summary_model_name}) initialized.")
            else:
                logger.error(f"MAIN_API: Summarization LLM ({summary_model_name}) FAILED to initialize.")

            llm_chat_instance_global = summarizer.initialize_llm(
                api_key=app_config.OPENAI_API_KEY,
                base_url=app_config.OPENAI_BASE_URL,
                model_name=chat_model_name,
                temperature=app_config.CHAT_LLM_TEMPERATURE,
                max_tokens=app_config.CHAT_MAX_OUTPUT_TOKENS
            )
            app.state.llm_chat_instance = llm_chat_instance_global
            if app.state.llm_chat_instance:
                logger.info(f"MAIN_API: Chat LLM ({chat_model_name}) initialized.")
            else:
                logger.error(f"MAIN_API: Chat LLM ({chat_model_name}) FAILED to initialize.")

            llm_tag_instance_global = summarizer.initialize_llm(
                api_key=app_config.OPENAI_API_KEY,
                base_url=app_config.OPENAI_BASE_URL,
                model_name=tag_model_name,
                temperature=app_config.TAG_LLM_TEMPERATURE,
                max_tokens=app_config.TAG_MAX_OUTPUT_TOKENS
            )
            app.state.llm_tag_instance = llm_tag_instance_global
            if app.state.llm_tag_instance:
                logger.info(f"MAIN_API: Tag Generation LLM ({tag_model_name}) initialized.")
            else:
                logger.error(f"MAIN_API: Tag Generation LLM ({tag_model_name}) FAILED to initialize.")

            app.state.available_models = []
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
                        with settings_database.db_session_scope() as settings_db:
                            settings_database.set_cached_models(settings_db, available)
                        app.state.available_models = available
                        logger.info(f"MAIN_API: Fetched {len(available)} available models from API.")
                    else:
                        logger.warning(f"MAIN_API: Failed to fetch models from API: {response.status_code}")
                        cached = settings_database.get_cached_models(settings_db)
                        app.state.available_models = cached if cached else []
                        logger.info(f"MAIN_API: Using cached models: {app.state.available_models}")
            except Exception as e:
                logger.warning(f"MAIN_API: Could not fetch available models from API: {e}")
                cached = settings_database.get_cached_models(settings_db)
                app.state.available_models = cached if cached else []
                logger.info(f"MAIN_API: Using cached models: {app.state.available_models}")

        except Exception as e:
            logger.critical(f"MAIN_API: A critical error occurred during LLM Initialization: {e}", exc_info=True)
            app.state.llm_summary_instance = None
            app.state.llm_chat_instance = None
            app.state.llm_tag_instance = None

    if not scheduler.running:
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

logger.info("MAIN_API: Including API routers...")
app.include_router(config_routes.router)
app.include_router(feed_routes.router)
app.include_router(article_routes.router)
app.include_router(chat_routes.router)
app.include_router(admin_routes.router)
app.include_router(content_routes.router)
app.include_router(debug_routes.router)
app.include_router(auth_routes.router)
app.include_router(user_routes.router)
app.include_router(tag_routes.router)
app.include_router(intelligence_router)
logger.info("MAIN_API: All API routers included.")

import os
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
frontend_path = os.path.normpath(frontend_path)

try:
    app.mount("/static", StaticFiles(directory=frontend_path), name="static_frontend_files")
    logger.info(f"MAIN_API: Static files mounted from '{frontend_path}' at '/static'.")
except RuntimeError as e:
    logger.error(f"MAIN_API: Error mounting static files. Ensure 'frontend' directory exists at the project root. Details: {e}", exc_info=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
FRONTEND_DIR = os.path.normpath(FRONTEND_DIR)

@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_index_html():
    index_html_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_html_path):
        logger.error(f"MAIN_API: index.html not found at '{index_html_path}'. Ensure it exists.")
    return FileResponse(index_html_path)

@app.get("/admin", response_class=FileResponse, include_in_schema=False)
async def serve_admin_html():
    admin_html_path = os.path.join(FRONTEND_DIR, "admin.html")
    if not os.path.exists(admin_html_path):
        logger.error(f"MAIN_API: admin.html not found at '{admin_html_path}'. Ensure it exists.")
    return FileResponse(admin_html_path)

@app.get("/setup", response_class=FileResponse, include_in_schema=False)
async def serve_setup_html():
    setup_html_path = os.path.join(FRONTEND_DIR, "setup.html")
    if not os.path.exists(setup_html_path):
        logger.error(f"MAIN_API: setup.html not found at '{setup_html_path}'. Ensure it exists.")
    return FileResponse(setup_html_path)

logger.info("MAIN_API: FastAPI application initialized and configured.")
