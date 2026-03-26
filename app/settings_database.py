# app/settings_database.py
import os
import json
from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession, declarative_base
from sqlalchemy.sql import func
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any, List

from . import config

# --- Database Configuration for Settings ---
SETTINGS_DATABASE_URL = config.SETTINGS_DATABASE_URL

# Ensure the directory for the SQLite database exists
if SETTINGS_DATABASE_URL.startswith("sqlite:///./"):
    db_file_path = SETTINGS_DATABASE_URL.replace("sqlite:///./", "")
    db_dir = os.path.dirname(db_file_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

engine = create_engine(
    SETTINGS_DATABASE_URL,
    connect_args={"check_same_thread": False} if SETTINGS_DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- Context Manager for DB Sessions ---
@contextmanager
def db_session_scope() -> Generator[SQLAlchemySession, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_db() -> Generator[SQLAlchemySession, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Settings Database Model ---
class Configuration(Base):
    __tablename__ = "configuration"
    key = Column(String, primary_key=True, index=True, nullable=False)
    value = Column(String, nullable=False)

    def __repr__(self):
        return f"<Configuration(key='{self.key}', value='{self.value}')>"

# --- Default Settings ---
DEFAULT_SETTINGS: Dict[str, str] = {
    "summary_model_name": config.DEFAULT_SUMMARY_MODEL_NAME,
    "chat_model_name": config.DEFAULT_CHAT_MODEL_NAME,
    "tag_model_name": config.DEFAULT_TAG_MODEL_NAME,
    "summary_temperature": str(config.SUMMARY_LLM_TEMPERATURE),
    "chat_temperature": str(config.CHAT_LLM_TEMPERATURE),
    "tag_temperature": str(config.TAG_LLM_TEMPERATURE),
    "summary_max_output_tokens": str(config.SUMMARY_MAX_OUTPUT_TOKENS),
    "chat_max_output_tokens": str(config.CHAT_MAX_OUTPUT_TOKENS),
    "tag_max_output_tokens": str(config.TAG_MAX_OUTPUT_TOKENS),
    "articles_per_page": str(config.DEFAULT_PAGE_SIZE),
    "rss_fetch_interval_minutes": str(config.DEFAULT_RSS_FETCH_INTERVAL_MINUTES),
    "summary_prompt": config.DEFAULT_SUMMARY_PROMPT,
    "chat_prompt": config.DEFAULT_CHAT_PROMPT,
    "tag_prompt": config.DEFAULT_TAG_GENERATION_PROMPT,
    "minimum_word_count": str(config.DEFAULT_MINIMUM_WORD_COUNT),
    "cached_available_models": "[]",
    "debug_level": config.DEBUG_LEVEL,
    "show_scrape_progress": "true",
    "show_extension_status": "true",
    "log_scraper_details": "true",
    "log_feed_refresh_details": "true",
}

# --- Helper functions for Configuration ---
def get_setting(db: SQLAlchemySession, key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Retrieves a setting value from the database.
    Returns the default value if the key is not found.
    """
    setting = db.query(Configuration).filter(Configuration.key == key).first()
    return setting.value if setting else default

def set_setting(db: SQLAlchemySession, key: str, value: str):
    """
    Creates or updates a setting in the database.
    """
    setting = db.query(Configuration).filter(Configuration.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = Configuration(key=key, value=value)
        db.add(setting)

def get_all_settings(db: SQLAlchemySession) -> Dict[str, str]:
    """
    Retrieves all settings from the database.
    """
    settings = db.query(Configuration).all()
    # Ensure default settings are considered if not in DB
    result = {k: v for k, v in DEFAULT_SETTINGS.items()}
    for setting in settings:
        result[setting.key] = setting.value
    return result

def set_multiple_settings(db: SQLAlchemySession, settings_to_update: Dict[str, Any]):
    """
    Updates multiple settings in the database from a dictionary.
    """
    for key, value in settings_to_update.items():
        if value is None:
            set_setting(db, key, "")
        else:
            set_setting(db, key, str(value))

def get_cached_models(db: SQLAlchemySession) -> List[str]:
    """
    Retrieves cached available models list from the database.
    Returns an empty list if not cached.
    """
    cached = get_setting(db, "cached_available_models", "[]")
    try:
        return json.loads(cached) if cached else []
    except json.JSONDecodeError:
        return []

def set_cached_models(db: SQLAlchemySession, models: List[str]):
    """
    Caches the available models list in the database.
    """
    set_setting(db, "cached_available_models", json.dumps(models))

# --- Database Initialization ---
def create_settings_db_and_tables():
    """
    Creates the database and the configuration table.
    Populates the table with default settings if they don't exist.
    """
    print("SETTINGS_DB: Attempting to create settings database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("SETTINGS_DB: Settings database tables checked/created successfully.")

        with db_session_scope() as db:
            for key, value in DEFAULT_SETTINGS.items():
                existing_setting = db.query(Configuration).filter(Configuration.key == key).first()
                if not existing_setting:
                    print(f"SETTINGS_DB: Initializing default setting for '{key}'.")
                    new_setting = Configuration(key=key, value=str(value))
                    db.add(new_setting)
            print("SETTINGS_DB: Default settings checked and initialized.")
    except Exception as e:
        print(f"SETTINGS_DB: Error during settings database setup: {e}")
