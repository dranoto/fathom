# app/routers/article_routes.py
import logging
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as SQLAlchemySession, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, func as sql_func
from typing import List, Optional
from datetime import datetime, timezone

from langchain_core.documents import Document as LangchainDocument
from langchain_google_genai import GoogleGenerativeAI

from .. import database, settings_database
from .. import scraper
from .. import summarizer
from .. import config as app_config
from ..schemas import (
    PaginatedSummariesAPIResponse,
    NewsPageQuery,
    ArticleResult,
    RegenerateSummaryRequest,
    ArticleTagResponse,
    NewArticleCheckResponse
)
from ..dependencies import get_llm_summary, get_llm_tag

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/articles", tags=["articles"])

SCRAPING_ERROR_PREFIX = "Scraping Error:"
CONTENT_ERROR_PREFIX = "Content Error:"


async def _should_attempt_scrape(article_db_obj: database.Article, min_word_count_threshold: int) -> bool:
    if article_db_obj.scraped_text_content and article_db_obj.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX):
        logger.info(f"Article ID {article_db_obj.id} previously had a scraping error ('{article_db_obj.scraped_text_content[:50]}...'). Skipping automatic re-scrape.")
        return False

    # New logic using word_count
    if article_db_obj.word_count is not None and article_db_obj.word_count < min_word_count_threshold:
        logger.info(f"Article ID {article_db_obj.id} has a word count ({article_db_obj.word_count}) below threshold ({min_word_count_threshold}). Skipping automatic re-scrape.")
        return False

    # Fallback to old logic only if word_count is somehow null
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
    summary_text: Optional[str] = None,
    error_message: Optional[str] = None
) -> ArticleResult:
    """
    Creates an ArticleResult Pydantic model from an Article database object.
    Centralizes the logic for creating this response model.
    """
    # If a summary is not passed in, fetch the latest one.
    if summary_text is None:
        latest_summary = db.query(database.Summary).filter(
            database.Summary.article_id == article_db_obj.id
        ).order_by(database.Summary.created_at.desc()).first()
        summary_text = latest_summary.summary_text if latest_summary else None

    # Centralize is_summarizable logic
    is_summarizable = (
        article_db_obj.scraped_text_content and
        not article_db_obj.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX) and
        (article_db_obj.word_count is None or article_db_obj.word_count >= min_word_count_threshold)
    )

    return ArticleResult(
        id=article_db_obj.id,
        title=article_db_obj.title,
        url=article_db_obj.url,
        summary=summary_text,
        publisher=article_db_obj.feed_source.name if article_db_obj.feed_source else article_db_obj.publisher_name,
        published_date=article_db_obj.published_date,
        created_at=article_db_obj.created_at,
        source_feed_url=article_db_obj.feed_source.url if article_db_obj.feed_source else None,
        tags=[ArticleTagResponse.from_orm(tag) for tag in article_db_obj.tags],
        is_favorite=bool(article_db_obj.is_favorite),
        is_summarizable=is_summarizable,
        error_message=error_message,
        rss_description=article_db_obj.rss_description,
        word_count=article_db_obj.word_count
    )


@router.post("/summaries", response_model=PaginatedSummariesAPIResponse)
async def get_news_summaries_endpoint(
    query: NewsPageQuery,
    db: SQLAlchemySession = Depends(database.get_db),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db),
    llm_summary: GoogleGenerativeAI = Depends(get_llm_summary),
    llm_tag: GoogleGenerativeAI = Depends(get_llm_tag)
):
    if not llm_summary and not llm_tag:
        logger.warning("API Warning: Summarization or Tagging LLM not available in get_news_summaries_endpoint. AI features will be disabled for this request.")
    logger.info(f"API Call: Get news summaries. Query: {query.model_dump_json(indent=2)}")
    db_query = db.query(database.Article)
    search_source_display_parts = []
    if query.feed_source_ids:
        db_query = db_query.filter(database.Article.feed_source_id.in_(query.feed_source_ids))
        source_names_result = db.query(database.RSSFeedSource.name).filter(database.RSSFeedSource.id.in_(query.feed_source_ids)).all()
        source_names = [name_tuple[0] for name_tuple in source_names_result if name_tuple[0]]
        search_source_display_parts.append(f"Feeds: {', '.join(source_names) or 'Selected Feeds'}")
    if query.tag_ids:
        for tag_id in query.tag_ids: db_query = db_query.filter(database.Article.tags.any(database.Tag.id == tag_id))
        tag_names_result = db.query(database.Tag.name).filter(database.Tag.id.in_(query.tag_ids)).all()
        tag_names = [name_tuple[0] for name_tuple in tag_names_result if name_tuple[0]]
        search_source_display_parts.append(f"Tags: {', '.join(tag_names) or 'Selected Tags'}")
    if query.keyword:
        keyword_like = f"%{query.keyword}%"
        db_query = db_query.filter(or_(database.Article.title.ilike(keyword_like), database.Article.scraped_text_content.ilike(keyword_like)))
        search_source_display_parts.append(f"Keyword: '{query.keyword}'")

    # Add filtering for favorites
    if query.favorites_only:
        db_query = db_query.filter(database.Article.is_favorite == True)
        search_source_display_parts.append("Favorites")

    search_source_display = " & ".join(search_source_display_parts) if search_source_display_parts else "All Articles"
    db_query = db_query.options(joinedload(database.Article.tags), joinedload(database.Article.feed_source)).order_by(database.Article.published_date.desc().nullslast(), database.Article.id.desc())

    # Get the minimum word count threshold from settings.
    try:
        min_word_count_threshold = int(settings_database.get_setting(settings_db, "minimum_word_count", "100"))
    except (ValueError, TypeError):
        min_word_count_threshold = 100

    # Apply the word count filter UNLESS a keyword search is active.
    # A keyword search should be able to find text in any article, regardless of length.
    # This now includes articles where word_count is NULL (i.e., legacy articles)
    if not query.keyword:
        db_query = db_query.filter(
            or_(
                database.Article.word_count >= min_word_count_threshold,
                database.Article.word_count.is_(None)
            )
        )

    total_articles_available = db_query.count()
    total_pages = math.ceil(total_articles_available / query.page_size) if query.page_size > 0 else 0
    current_page_for_slice = max(1, query.page)
    if total_pages > 0: current_page_for_slice = min(current_page_for_slice, total_pages)
    offset = (current_page_for_slice - 1) * query.page_size
    articles_from_db = db_query.limit(query.page_size).offset(offset).all()

    # --- N+1 Query Optimization ---
    # 1. Get all article IDs from the current page
    article_ids_on_page = [article.id for article in articles_from_db]

    # 2. Fetch all latest summaries for these articles in a single query
    summaries_map = {}
    if article_ids_on_page:
        # Query all summaries, ordered by creation date descending
        all_summaries = db.query(database.Summary).filter(database.Summary.article_id.in_(article_ids_on_page)).order_by(database.Summary.created_at.desc()).all()
        # Create a map of article_id -> latest_summary_text
        for summary in all_summaries:
            if summary.article_id not in summaries_map and not summary.summary_text.startswith("Error:"):
                summaries_map[summary.article_id] = summary.summary_text
    # --- End Optimization ---

    results_on_page: List[ArticleResult] = []
    articles_needing_ondemand_scrape: List[database.Article] = []
    for article_db_obj in articles_from_db:
        error_parts_for_display = []
        needs_on_demand_scrape = await _should_attempt_scrape(article_db_obj, min_word_count_threshold)

        if needs_on_demand_scrape:
            articles_needing_ondemand_scrape.append(article_db_obj)
            error_parts_for_display.append("Content pending fresh scrape.")
        elif article_db_obj.scraped_text_content and article_db_obj.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX):
            error_parts_for_display.append(article_db_obj.scraped_text_content)
        elif article_db_obj.word_count is not None and article_db_obj.word_count < min_word_count_threshold:
            error_parts_for_display.append(f"Content previously scraped but found to be very short (word count: {article_db_obj.word_count}).")

        article_result = _create_article_result(
            article_db_obj=article_db_obj,
            db=db,
            min_word_count_threshold=min_word_count_threshold,
            summary_text=summaries_map.get(article_db_obj.id),
            error_message=" | ".join(list(set(error_parts_for_display))) if error_parts_for_display else None
        )
        results_on_page.append(article_result)

    if articles_needing_ondemand_scrape:
        logger.info(f"API: Found {len(articles_needing_ondemand_scrape)} articles for on-demand scraping on current page.")
        for art_db_obj_to_process in articles_needing_ondemand_scrape:
            logger.info(f"API: On-demand scraping for {art_db_obj_to_process.url[:70]}...")
            scraped_docs_list_od: List[LangchainDocument] = await scraper.scrape_urls([str(art_db_obj_to_process.url)])
            scraper_error_msg_od = None
            if scraped_docs_list_od and scraped_docs_list_od[0]:
                sc_doc_od = scraped_docs_list_od[0]
                scraper_error_msg_od = sc_doc_od.metadata.get("error")
                if not scraper_error_msg_od and sc_doc_od.page_content:
                    art_db_obj_to_process.scraped_text_content = sc_doc_od.page_content
                    art_db_obj_to_process.full_html_content = sc_doc_od.metadata.get('full_html_content')
                    art_db_obj_to_process.word_count = sc_doc_od.metadata.get('word_count', 0)
                else:
                    scraper_error_msg_od = scraper_error_msg_od or "On-demand scraper returned no page_content."
                    art_db_obj_to_process.scraped_text_content = f"{SCRAPING_ERROR_PREFIX} {scraper_error_msg_od}"
                    art_db_obj_to_process.full_html_content = None
                    art_db_obj_to_process.word_count = 0
            else:
                scraper_error_msg_od = "On-demand scraping: No document returned."
                art_db_obj_to_process.scraped_text_content = f"{SCRAPING_ERROR_PREFIX} {scraper_error_msg_od}"
                art_db_obj_to_process.full_html_content = None
                art_db_obj_to_process.word_count = 0
            db.add(art_db_obj_to_process)
            try:
                db.commit()
                db.refresh(art_db_obj_to_process)
            except Exception as e:
                db.rollback()
                logger.error(f"Error committing on-demand scrape for article {art_db_obj_to_process.id}: {e}", exc_info=True)
            # Find the index of the result to update
            for i, res_art in enumerate(results_on_page):
                if res_art.id == art_db_obj_to_process.id:
                    error_parts_for_display = []
                    if art_db_obj_to_process.scraped_text_content and art_db_obj_to_process.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX):
                        error_parts_for_display.append(art_db_obj_to_process.scraped_text_content)
                    elif art_db_obj_to_process.word_count is not None and art_db_obj_to_process.word_count < min_word_count_threshold:
                        error_parts_for_display.append(f"Content scraped but found to be very short (word count: {art_db_obj_to_process.word_count}).")

                    # Replace the old result with a new one created by the helper
                    results_on_page[i] = _create_article_result(
                        article_db_obj=art_db_obj_to_process,
                        db=db,
                        min_word_count_threshold=min_word_count_threshold,
                        summary_text=summaries_map.get(art_db_obj_to_process.id), # Re-use summary if it existed
                        error_message=" | ".join(error_parts_for_display) if error_parts_for_display else None
                    )
                    break
    return PaginatedSummariesAPIResponse( search_source=search_source_display, requested_page=current_page_for_slice, page_size=query.page_size, total_articles_available=total_articles_available, total_pages=total_pages, processed_articles_on_page=results_on_page)


@router.post("/{article_id}/favorite", response_model=ArticleResult)
async def toggle_favorite_status(
    article_id: int,
    db: SQLAlchemySession = Depends(database.get_db)
):
    """
    Toggles the 'is_favorite' status of a single article.
    """
    logger.info(f"API Call: Toggle favorite status for Article ID {article_id}")

    # Use joinedload to efficiently fetch related data needed for the response model
    article_db = db.query(database.Article).options(
        joinedload(database.Article.tags),
        joinedload(database.Article.feed_source)
    ).filter(database.Article.id == article_id).first()

    if not article_db:
        raise HTTPException(status_code=404, detail="Article not found.")

    # Toggle the is_favorite status
    article_db.is_favorite = not article_db.is_favorite

    try:
        db.commit()
        db.refresh(article_db)
        logger.info(f"API: Successfully set is_favorite={article_db.is_favorite} for Article ID {article_id}.")
    except Exception as e:
        db.rollback()
        logger.error(f"API: Error committing favorite status for Article ID {article_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="A database error occurred while updating the article.")

    # The summary is not affected by favoriting, so we can pass it from the existing relationship
    # This avoids an extra query. We just need to make sure the summary relationship is loaded or handled.
    # For simplicity, the helper function will query it if not provided.

    # We need a min_word_count_threshold for the helper. Since this endpoint doesn't
    # have access to the settings_db by default, we'll use a sensible default.
    # A better approach might be to add settings_db dependency here if it becomes more complex.
    min_word_count_threshold = 100 # A reasonable default.

    return _create_article_result(
        article_db_obj=article_db,
        db=db,
        min_word_count_threshold=min_word_count_threshold
    )


@router.post("/{article_id}/regenerate-summary", response_model=ArticleResult)
async def regenerate_article_summary(
    article_id: int,
    request_body: RegenerateSummaryRequest,
    db: SQLAlchemySession = Depends(database.get_db),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db),
    llm_summary: GoogleGenerativeAI = Depends(get_llm_summary),
    llm_tag: GoogleGenerativeAI = Depends(get_llm_tag)
):
    if not llm_summary: raise HTTPException(status_code=503, detail="Summarization LLM not available.")

    try:
        min_word_count_threshold = int(settings_database.get_setting(settings_db, "minimum_word_count", "100"))
    except (ValueError, TypeError):
        min_word_count_threshold = 100

    article_db = db.query(database.Article).options(joinedload(database.Article.tags), joinedload(database.Article.feed_source)).filter(database.Article.id == article_id).first()
    if not article_db: raise HTTPException(status_code=404, detail="Article not found.")
    logger.info(f"API Call: Regenerate summary for Article ID {article_id}. Force re-scrape if content is missing/error/short.")
    current_text_content = article_db.scraped_text_content
    current_word_count = article_db.word_count
    force_scrape_needed = (not current_text_content or current_text_content.startswith(SCRAPING_ERROR_PREFIX) or current_text_content.startswith(CONTENT_ERROR_PREFIX) or (current_word_count is not None and current_word_count < min_word_count_threshold) or not article_db.full_html_content)
    if force_scrape_needed:
        logger.info(f"API Regenerate: Content for Article ID {article_id} requires re-scraping for regeneration.")
        scraped_docs_list_regen: List[LangchainDocument] = await scraper.scrape_urls([str(article_db.url)])
        scraper_error_msg_regen = None
        if scraped_docs_list_regen and scraped_docs_list_regen[0]:
            sc_doc_regen = scraped_docs_list_regen[0]
            scraper_error_msg_regen = sc_doc_regen.metadata.get("error")
            if not scraper_error_msg_regen and sc_doc_regen.page_content:
                article_db.scraped_text_content = sc_doc_regen.page_content
                article_db.full_html_content = sc_doc_regen.metadata.get('full_html_content')
                article_db.word_count = sc_doc_regen.metadata.get('word_count', 0)
                current_text_content = article_db.scraped_text_content
                current_word_count = article_db.word_count
                db.add(article_db)
                logger.info(f"API Regenerate: Successfully re-scraped content for Article ID {article_id}.")
            else:
                scraper_error_msg_regen = scraper_error_msg_regen or "Failed to re-scrape content (regen)"
                article_db.scraped_text_content = f"{SCRAPING_ERROR_PREFIX} {scraper_error_msg_regen}"
                article_db.full_html_content = None
                article_db.word_count = 0
                current_text_content = article_db.scraped_text_content
                db.add(article_db)
                # No commit here, let the transaction fail and be handled by FastAPI/Starlette
                logger.error(f"API Regenerate: Failed to re-scrape for Article ID {article_id}: {scraper_error_msg_regen}")
                raise HTTPException(status_code=500, detail=f"Failed to get valid content for regeneration: {scraper_error_msg_regen}")
        else:
            scraper_error_msg_regen = "Failed to re-scrape: No document returned."
            article_db.scraped_text_content = f"{SCRAPING_ERROR_PREFIX} {scraper_error_msg_regen}"
            article_db.full_html_content = None
            article_db.word_count = 0
            current_text_content = article_db.scraped_text_content
            db.add(article_db)
            # No commit here
            logger.error(f"API Regenerate: Failed to re-scrape for Article ID {article_id}: {scraper_error_msg_regen}")
            raise HTTPException(status_code=500, detail=f"Failed to get valid content for regeneration: {scraper_error_msg_regen}")
    if not current_text_content or current_text_content.startswith(SCRAPING_ERROR_PREFIX) or (current_word_count is not None and current_word_count < min_word_count_threshold):
        logger.error(f"API Regenerate: Article text content for ID {article_id} is still invalid or too short (word count: {current_word_count}) after potential re-scrape attempt.")
        error_msg_response = f"Cannot regenerate summary: article content is invalid or too short (word count: {current_word_count})."
        return _create_article_result(
            article_db_obj=article_db,
            db=db,
            min_word_count_threshold=min_word_count_threshold,
            error_message=error_msg_response
        )

    lc_doc_for_summary_regen = LangchainDocument(
        page_content=current_text_content,
        metadata={
            "source": str(article_db.url),
            "id": article_db.id,
            "full_html_content": article_db.full_html_content,
        }
    )
    prompt_to_use = request_body.custom_prompt if request_body.custom_prompt and request_body.custom_prompt.strip() else app_config.DEFAULT_SUMMARY_PROMPT

    try:
        new_summary_text = await summarizer.summarize_document_content(lc_doc_for_summary_regen, llm_summary, prompt_to_use)
    except summarizer.SummarizationError as e:
        logger.warning(f"API Regenerate: Summarization failed for Article ID {article_id}: {e}")
        return _create_article_result(
            article_db_obj=article_db,
            db=db,
            min_word_count_threshold=min_word_count_threshold,
            error_message=str(e)
        )

    # --- Deletion and Creation Logic ---
    # Only delete the old summary if a new one was successfully generated.
    db.query(database.Summary).filter(database.Summary.article_id == article_id).delete(synchronize_session=False)

    model_name = settings_database.get_setting(settings_db, "summary_model_name", app_config.DEFAULT_SUMMARY_MODEL_NAME)
    new_summary_db_obj = database.Summary(article_id=article_id, summary_text=new_summary_text, prompt_used=prompt_to_use, model_used=model_name)
    db.add(new_summary_db_obj)
    if request_body.regenerate_tags and llm_tag and current_text_content and not current_text_content.startswith(SCRAPING_ERROR_PREFIX) and (current_word_count is not None and current_word_count >= min_word_count_threshold):
        logger.info(f"API Regenerate: Regenerating tags for Article ID {article_id}.")
        if article_db.tags:
            article_db.tags.clear()
        tag_names_generated = await summarizer.generate_tags_for_text(current_text_content, llm_tag, None)
        if tag_names_generated:
            for tag_name in tag_names_generated:
                tag_name_cleaned = tag_name.strip().lower()
                if not tag_name_cleaned: continue
                tag_db_obj = db.query(database.Tag).filter(database.Tag.name == tag_name_cleaned).first()
                if not tag_db_obj:
                    try:
                        # Use a nested transaction (SAVEPOINT) to handle potential race conditions
                        # for tag creation without rolling back the entire transaction.
                        with db.begin_nested():
                            tag_db_obj = database.Tag(name=tag_name_cleaned)
                            db.add(tag_db_obj)
                    except IntegrityError:
                        # The nested transaction is automatically rolled back on error.
                        # The main transaction is still active. We can now safely query for the existing tag.
                        tag_db_obj = db.query(database.Tag).filter(database.Tag.name == tag_name_cleaned).first()
                if tag_db_obj and tag_db_obj not in article_db.tags:
                    article_db.tags.append(tag_db_obj)
    try:
        db.commit()
        db.refresh(article_db)
        logger.info(f"API Regenerate: Successfully committed all changes for Article ID {article_id}.")
    except Exception as e:
        db.rollback()
        logger.error(f"API Regenerate: Error committing changes for Article ID {article_id}: {e}", exc_info=True)
        # Decide on what to return or raise. Raising an exception might be more RESTful.
        raise HTTPException(status_code=500, detail=f"A database error occurred while saving changes: {e}")

    return _create_article_result(
        article_db_obj=article_db,
        db=db,
        min_word_count_threshold=min_word_count_threshold,
        summary_text=new_summary_text,
        error_message=None if not new_summary_text.startswith("Error:") else new_summary_text
    )


# NEW POLLING ENDPOINT
@router.get("/status/new-articles", response_model=NewArticleCheckResponse)
async def check_for_new_articles(
    since_timestamp: Optional[datetime] = Query(None, description="Timestamp to check for articles created after this point (ISO format)."),
    db: SQLAlchemySession = Depends(database.get_db)
):
    logger.info(f"API Call: Checking for new articles since_timestamp: {since_timestamp}")
    latest_article_query = db.query(sql_func.max(database.Article.created_at))
    latest_article_db_timestamp = latest_article_query.scalar()
    if since_timestamp is None:
        article_count_query = db.query(sql_func.count(database.Article.id))
        if since_timestamp is None and latest_article_db_timestamp is not None:
             total_article_count = db.query(sql_func.count(database.Article.id)).scalar()
             return NewArticleCheckResponse(
                 new_articles_available= total_article_count > 0,
                 latest_article_timestamp=latest_article_db_timestamp,
                 article_count= total_article_count
             )
        return NewArticleCheckResponse(new_articles_available=False, latest_article_timestamp=None, article_count=0)

    if since_timestamp.tzinfo is None: # Ensure timezone awareness for comparison
        since_timestamp = since_timestamp.replace(tzinfo=timezone.utc)

    new_articles_query = db.query(database.Article).filter(database.Article.created_at > since_timestamp)
    count_new_articles = new_articles_query.count()

    if count_new_articles > 0:
        return NewArticleCheckResponse(
            new_articles_available=True,
            latest_article_timestamp=latest_article_db_timestamp,
            article_count=count_new_articles
        )
    else:
        return NewArticleCheckResponse(
            new_articles_available=False,
            latest_article_timestamp=latest_article_db_timestamp,
            article_count=0
        )
