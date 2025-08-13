# app/settings_database.py
import os
from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession, declarative_base
from sqlalchemy.sql import func
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any

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
    "articles_per_page": str(config.DEFAULT_PAGE_SIZE),
    "rss_fetch_interval_minutes": str(config.DEFAULT_RSS_FETCH_INTERVAL_MINUTES),
    "summary_prompt": config.DEFAULT_SUMMARY_PROMPT,
    "chat_prompt": config.DEFAULT_CHAT_PROMPT,
    "tag_generation_prompt": config.DEFAULT_TAG_GENERATION_PROMPT,
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
        # Ensure value is a string before setting
        str_value = str(value)
        set_setting(db, key, str_value)

# --- Database Initialization ---
def create_settings_db_and_tables():
    """
    Creates the database and the configuration table.
    Populates the table with default settings if they don't exist.
    """
    logger.info("SETTINGS_DB: Attempting to create settings database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("SETTINGS_DB: Settings database tables checked/created successfully.")

        with db_session_scope() as db:
            # Fetch keys that are already in the DB to avoid adding them again
            existing_keys = {s.key for s in db.query(Configuration.key).all()}
            for key, value in DEFAULT_SETTINGS.items():
                if key not in existing_keys:
                    print(f"SETTINGS_DB: Initializing default setting for '{key}'.")
                    new_setting = Configuration(key=key, value=str(value))
                    db.add(new_setting)
            print("SETTINGS_DB: Default settings checked and initialized.")
    except Exception as e:
        print(f"SETTINGS_DB: Error during settings database setup: {e}")
