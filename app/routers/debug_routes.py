# app/routers/debug_routes.py
import logging
import time
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session as SQLAlchemySession
from typing import List, Dict, Any

from .. import config, settings_database, database
from ..database import db_session_scope
from ..scraper import get_extension_status
from .auth_routes import get_current_user
from .admin_routes import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"])

_recent_scrape_results: List[Dict[str, Any]] = []
_debug_start_time = time.time()

def add_scrape_result(result: Dict[str, Any]):
    _recent_scrape_results.insert(0, result)
    if len(_recent_scrape_results) > 100:
        _recent_scrape_results.pop()

def get_recent_scrape_results(limit: int = 20) -> List[Dict[str, Any]]:
    return _recent_scrape_results[:limit]

def clear_scrape_results():
    _recent_scrape_results.clear()

@router.get("/status")
async def get_debug_status(
    request: Request,
    admin_user: database.User = Depends(require_admin),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db)
) -> Dict[str, Any]:
    debug_level = settings_database.get_setting(settings_db, "debug_level", config.DEBUG_LEVEL)
    
    ext_status = get_extension_status()
    
    uptime_seconds = int(time.time() - _debug_start_time)
    
    recent_scrapes = get_recent_scrape_results(limit=10)
    
    feed_status = []
    with db_session_scope() as db:
        from ..database import FeedSource, Article
        from .. import tasks
        
        feeds = db.query(FeedSource).all()
        for feed in feeds:
            article_count = db.query(Article).filter(Article.feed_source_id == feed.id).count()
            feed_status.append({
                "id": feed.id,
                "name": feed.name,
                "url": feed.url,
                "last_fetched": feed.last_fetched_at.isoformat() if feed.last_fetched_at else None,
                "interval_minutes": feed.fetch_interval_minutes,
                "article_count": article_count,
                "is_refreshing": tasks._is_refreshing if hasattr(tasks, '_is_refreshing') else False
            })
    
    return {
        "debug_level": debug_level,
        "extension_loaded": ext_status["loaded"],
        "extension_path": ext_status["path"] or config.PATH_TO_EXTENSION,
        "service_workers": ext_status["service_workers"],
        "extension_version": ext_status["version"],
        "extension_last_checked": datetime.fromtimestamp(ext_status["last_checked"], tz=timezone.utc).isoformat() if ext_status["last_checked"] else None,
        "uptime_seconds": uptime_seconds,
        "uptime_human": f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m",
        "recent_scrapes": recent_scrapes,
        "feed_status": feed_status,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "config": {
            "headless_browser": config.USE_HEADLESS_BROWSER,
            "playwright_timeout": config.PLAYWRIGHT_TIMEOUT,
            "page_wait_ms": config.PLAYWRIGHT_PAGE_WAIT_MS,
        }
    }

@router.post("/test-scrape")
async def test_scrape(
    url: str,
    request: Request,
    admin_user: database.User = Depends(require_admin),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db)
) -> Dict[str, Any]:
    test_url = url.strip()
    if not test_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL format")
    
    logger.info(f"DEBUG: Test scrape requested for URL: {test_url}")
    
    start_time = time.time()
    extension_active = False
    service_workers = 0
    
    try:
        from ..scraper import scrape_urls
        
        results = await scrape_urls([test_url])
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        if results and len(results) > 0:
            result = results[0]
            extension_active = getattr(request.app.state, 'extension_loaded', False)
            service_workers = getattr(request.app.state, 'service_workers', 0) or 0
            
            scrape_result = {
                "url": test_url,
                "success": result.metadata.get('word_count', 0) > 0 if result.metadata.get('word_count') else False,
                "word_count": result.metadata.get('word_count', 0),
                "html_length": len(result.page_content) if result.page_content else 0,
                "error": result.metadata.get('error'),
                "title": result.metadata.get('title'),
                "extension_active": extension_active,
                "service_workers": service_workers,
                "time_ms": elapsed_ms,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            scrape_result = {
                "url": test_url,
                "success": False,
                "word_count": 0,
                "html_length": 0,
                "error": "No results returned from scraper",
                "title": None,
                "extension_active": extension_active,
                "service_workers": service_workers,
                "time_ms": elapsed_ms,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        add_scrape_result(scrape_result)
        
        return scrape_result
        
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(f"DEBUG: Test scrape failed for {test_url}: {e}", exc_info=True)
        
        error_result = {
            "url": test_url,
            "success": False,
            "word_count": 0,
            "html_length": 0,
            "error": str(e),
            "title": None,
            "extension_active": extension_active,
            "service_workers": service_workers,
            "time_ms": elapsed_ms,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        add_scrape_result(error_result)
        
        raise HTTPException(status_code=500, detail="Failed to scrape URL.")

@router.get("/scrape-history")
async def get_scrape_history(
    limit: int = 20,
    admin_user: database.User = Depends(require_admin),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db)
) -> Dict[str, Any]:
    debug_level = settings_database.get_setting(settings_db, "debug_level", config.DEBUG_LEVEL)
    return {
        "debug_level": debug_level,
        "history": get_recent_scrape_results(limit=limit)
    }

@router.post("/clear-history")
async def clear_history(
    admin_user: database.User = Depends(require_admin)
) -> Dict[str, str]:
    clear_scrape_results()
    return {"message": "Scrape history cleared"}
