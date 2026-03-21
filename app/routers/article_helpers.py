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
    error_message: Optional[str] = None,
    user_favorite_ids: Optional[set[int]] = None,
    user_read_ids: Optional[set[int]] = None,
    user_deleted_ids: Optional[set[int]] = None,
    chat_history_article_ids: Optional[set[int]] = None,
    article_tags_map: Optional[dict[int, list[ArticleTagResponse]]] = None
) -> ArticleResult:
    """
    Creates an ArticleResult Pydantic model from an Article database object.
    Uses pre-fetched data to avoid N+1 queries.
    """
    article_id = article_db_obj.id

    is_favorite = article_id in user_favorite_ids if user_favorite_ids else False
    is_read = article_id in user_read_ids if user_read_ids else False
    is_deleted = article_id in user_deleted_ids if user_deleted_ids else False

    if summary_text is None:
        latest_summary = db.query(database.Summary).filter(
            database.Summary.user_id == user_id,
            database.Summary.article_id == article_id
        ).order_by(database.Summary.created_at.desc()).first()
        summary_text = latest_summary.summary_text if latest_summary else None

    is_summarizable = (
        article_db_obj.scraped_text_content and
        not article_db_obj.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX) and
        (article_db_obj.word_count is None or article_db_obj.word_count >= min_word_count_threshold)
    )

    has_chat_history = article_id in chat_history_article_ids if chat_history_article_ids else False

    tags = article_tags_map.get(article_id, []) if article_tags_map else []

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