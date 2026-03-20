# app/routers/article_helpers.py
import logging
from typing import Optional

from sqlalchemy.orm import Session as SQLAlchemySession

from .. import database
from ..schemas import ArticleTagResponse, ArticleResult

logger = logging.getLogger(__name__)

SCRAPING_ERROR_PREFIX = "Scraping Error:"
CONTENT_ERROR_PREFIX = "Content Error:"


async def _should_attempt_scrape(article_db_obj: database.Article, min_word_count_threshold: int) -> bool:
    if article_db_obj.scraped_text_content and article_db_obj.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX):
        logger.info(f"Article ID {article_db_obj.id} previously had a scraping error ('{article_db_obj.scraped_text_content[:50]}...'). Skipping automatic re-scrape.")
        return False

    if article_db_obj.word_count is not None and article_db_obj.word_count < min_word_count_threshold:
        logger.info(f"Article ID {article_db_obj.id} has a word count ({article_db_obj.word_count}) below threshold ({min_word_count_threshold}). Skipping automatic re-scrape.")
        return False

    if article_db_obj.word_count is None and article_db_obj.scraped_text_content and \
       not article_db_obj.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX) and \
       len(article_db_obj.scraped_text_content) < (min_word_count_threshold * 5) and \
       article_db_obj.full_html_content is not None:
        logger.warning(f"Article ID {article_db_obj.id} has null word_count, falling back to char count. It has short text content from a previous successful scrape. Skipping automatic re-scrape.")
        return False

    if not article_db_obj.scraped_text_content or not article_db_obj.full_html_content:
        logger.info(f"Article ID {article_db_obj.id} needs scraping: text_content or full_html_content is missing/invalid and not a known failure.")
        return True
    return False


def _create_article_result(
    article_db_obj: database.Article,
    db: SQLAlchemySession,
    min_word_count_threshold: int,
    user_id: int,
    summary_text: Optional[str] = None,
    error_message: Optional[str] = None
) -> ArticleResult:
    """
    Creates an ArticleResult Pydantic model from an Article database object.
    Uses user_article_states for read/favorite/deleted status.
    """
    user_state = db.query(database.UserArticleState).filter(
        database.UserArticleState.user_id == user_id,
        database.UserArticleState.article_id == article_db_obj.id
    ).first()

    is_favorite = user_state.is_favorite if user_state else False
    is_read = user_state.is_read if user_state else False
    is_deleted = user_state.is_deleted if user_state else False

    if summary_text is None:
        latest_summary = db.query(database.Summary).filter(
            database.Summary.user_id == user_id,
            database.Summary.article_id == article_db_obj.id
        ).order_by(database.Summary.created_at.desc()).first()
        summary_text = latest_summary.summary_text if latest_summary else None

    is_summarizable = (
        article_db_obj.scraped_text_content and
        not article_db_obj.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX) and
        (article_db_obj.word_count is None or article_db_obj.word_count >= min_word_count_threshold)
    )

    has_chat_history = db.query(database.ChatHistory).filter(
        database.ChatHistory.user_id == user_id,
        database.ChatHistory.article_id == article_db_obj.id
    ).count() > 0

    user_tags = db.query(database.Tag).join(
        database.article_tag_association,
        database.Tag.id == database.article_tag_association.c.tag_id
    ).filter(
        database.article_tag_association.c.user_id == user_id,
        database.article_tag_association.c.article_id == article_db_obj.id
    ).all()

    tags = [ArticleTagResponse(id=tag.id, name=tag.name) for tag in user_tags]

    return ArticleResult(
        id=article_db_obj.id,
        title=article_db_obj.title,
        url=article_db_obj.url,
        summary=summary_text,
        publisher=article_db_obj.feed_source.name if article_db_obj.feed_source else article_db_obj.publisher_name,
        published_date=article_db_obj.published_date,
        created_at=article_db_obj.created_at,
        source_feed_url=article_db_obj.feed_source.url if article_db_obj.feed_source else None,
        tags=tags,
        is_favorite=is_favorite,
        is_read=is_read,
        is_deleted=is_deleted,
        is_summarizable=is_summarizable,
        error_message=error_message,
        rss_description=article_db_obj.rss_description,
        word_count=article_db_obj.word_count,
        has_chat_history=has_chat_history
    )