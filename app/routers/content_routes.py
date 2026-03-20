# app/routers/content_routes.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session as SQLAlchemySession

from .. import database
from .. import security
from .. import sanitizer
from ..schemas import SanitizedArticleContentResponse
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/articles",
    tags=["article content"]
)

@router.get("/{article_id}/content", response_model=SanitizedArticleContentResponse)
async def get_sanitized_article_content(
    article_id: int = Path(..., title="The ID of the article to retrieve content for", ge=1),
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Retrieves the full HTML content of an article by its ID,
    sanitizes it using bleach, and returns the sanitized HTML.
    """
    logger.info(f"API Call: Get sanitized content for Article ID: {article_id}")
    
    article_db = security.verify_article_access(db, article_id, current_user.id)

    if not article_db.full_html_content:
        logger.info(f"API Info: Article ID {article_id} has no full_html_content stored.")
        return SanitizedArticleContentResponse(
            article_id=article_db.id,
            original_url=article_db.url,
            title=article_db.title,
            sanitized_html_content=None, 
            error_message="Full HTML content not found for this article in the database."
        )

    try:
        sanitized_content = sanitizer.sanitize_html_content(article_db.full_html_content)
    except Exception as e:
        logger.error(f"API Error: Failed to sanitize HTML content for Article ID {article_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process article content: {str(e)}")

    return SanitizedArticleContentResponse(
        article_id=article_db.id,
        original_url=article_db.url,
        title=article_db.title,
        sanitized_html_content=sanitized_content
    )
