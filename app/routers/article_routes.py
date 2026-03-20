# app/routers/article_routes.py
import logging
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as SQLAlchemySession, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, func as sql_func
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from langchain_core.documents import Document as LangchainDocument
from langchain_openai import ChatOpenAI

from .. import database, settings_database
from .. import scraper
from .. import summarizer
from .. import config as app_config
from .. import security
from ..schemas import (
    PaginatedSummariesAPIResponse,
    NewsPageQuery,
    ArticleResult,
    RegenerateSummaryRequest,
    ArticleTagResponse,
    NewArticleCheckResponse
)
from ..dependencies import get_llm_summary, get_llm_tag
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/articles", tags=["articles"])

SCRAPING_ERROR_PREFIX = "Scraping Error:"
CONTENT_ERROR_PREFIX = "Content Error:"

from . import article_helpers


@router.post("/summaries", response_model=PaginatedSummariesAPIResponse)
async def get_news_summaries_endpoint(
    query: NewsPageQuery,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db),
    llm_summary: ChatOpenAI = Depends(get_llm_summary),
    llm_tag: ChatOpenAI = Depends(get_llm_tag)
):
    if not llm_summary and not llm_tag:
        logger.warning("API Warning: Summarization or Tagging LLM not available.")
    
    logger.info(f"API Call: Get news summaries for user {current_user.id}. Query: {query.model_dump_json(indent=2)}")
    
    feed_source_ids = db.query(database.UserFeedSubscription.feed_source_id).filter(
        database.UserFeedSubscription.user_id == current_user.id
    ).all()
    feed_source_id_set = {f[0] for f in feed_source_ids}
    logger.info(f"DEBUG: feed_source_id_set = {feed_source_id_set}")
    
    if not feed_source_id_set:
        return PaginatedSummariesAPIResponse(
            search_source="No feeds added",
            requested_page=1,
            page_size=query.page_size,
            total_articles_available=0,
            total_pages=0,
            processed_articles_on_page=[]
        )
    
    if not feed_source_id_set:
        return PaginatedSummariesAPIResponse(
            search_source="No matching feed sources found",
            requested_page=1,
            page_size=query.page_size,
            total_articles_available=0,
            total_pages=0,
            processed_articles_on_page=[]
        )
    
    db_query = db.query(database.Article).filter(database.Article.feed_source_id.in_(feed_source_id_set))
    search_source_display_parts = []
    
    if query.tag_ids:
        db_query = db_query.join(
            database.article_tag_association,
            database.Article.id == database.article_tag_association.c.article_id
        ).filter(
            database.article_tag_association.c.user_id == current_user.id,
            database.article_tag_association.c.tag_id.in_(query.tag_ids)
        )
        tag_names_result = db.query(database.Tag.name).join(
            database.article_tag_association,
            database.Tag.id == database.article_tag_association.c.tag_id
        ).filter(
            database.article_tag_association.c.user_id == current_user.id,
            database.Tag.id.in_(query.tag_ids)
        ).all()
        tag_names = [name_tuple[0] for name_tuple in tag_names_result if name_tuple[0]]
        search_source_display_parts.append(f"Tags: {', '.join(tag_names) or 'Selected Tags'}")
    
    if query.keyword:
        keyword_like = f"%{query.keyword}%"
        db_query = db_query.filter(or_(
            database.Article.title.ilike(keyword_like),
            database.Article.scraped_text_content.ilike(keyword_like)
        ))
        search_source_display_parts.append(f"Keyword: '{query.keyword}'")

    user_article_ids_with_state = db.query(database.UserArticleState.article_id).filter(
        database.UserArticleState.user_id == current_user.id
    ).all()
    user_article_ids_set = {a[0] for a in user_article_ids_with_state}
    
    user_deleted_ids = set()
    user_favorite_ids = set()
    user_read_ids = set()
    
    if user_article_ids_set:
        states = db.query(database.UserArticleState).filter(
            database.UserArticleState.user_id == current_user.id,
            database.UserArticleState.article_id.in_(user_article_ids_set)
        ).all()
        
        for state in states:
            if state.is_deleted:
                user_deleted_ids.add(state.article_id)
            if state.is_favorite:
                user_favorite_ids.add(state.article_id)
            if state.is_read:
                user_read_ids.add(state.article_id)

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    if query.favorites_only:
        articles_to_filter = user_favorite_ids
    else:
        effective_feed_ids = feed_source_id_set
        if query.feed_source_ids:
            effective_feed_ids = feed_source_id_set & set(query.feed_source_ids)
            feed_names = db.query(database.FeedSource.name).filter(
                database.FeedSource.id.in_(query.feed_source_ids)
            ).all()
            feed_names_str = ', '.join([f[0] for f in feed_names if f[0]])
            search_source_display_parts.append(f"Feed: {feed_names_str or 'Selected'}")
        
        all_article_ids_in_feed = db.query(database.Article.id).filter(
            database.Article.feed_source_id.in_(effective_feed_ids)
        ).all()
        articles_to_filter = {a[0] for a in all_article_ids_in_feed}
    
    filtered_article_ids = articles_to_filter - user_deleted_ids
    
    if query.read_state == "unread":
        filtered_article_ids = filtered_article_ids - user_read_ids
        search_source_display_parts.append("Unread")
    elif query.read_state == "read":
        filtered_article_ids = filtered_article_ids & user_read_ids
        search_source_display_parts.append("Read")
    
    search_source_display = " & ".join(search_source_display_parts) if search_source_display_parts else "All Articles"
    
    try:
        min_word_count_threshold = int(settings_database.get_setting(settings_db, "minimum_word_count", str(app_config.DEFAULT_MINIMUM_WORD_COUNT)))
    except (ValueError, TypeError):
        min_word_count_threshold = app_config.DEFAULT_MINIMUM_WORD_COUNT

    if not query.keyword:
        db_query = db_query.filter(
            or_(
                database.Article.word_count >= min_word_count_threshold,
                database.Article.word_count.is_(None)
            )
        )
    
    if filtered_article_ids:
        db_query = db_query.filter(database.Article.id.in_(filtered_article_ids))
    else:
        return PaginatedSummariesAPIResponse(
            search_source=search_source_display,
            requested_page=1,
            page_size=query.page_size,
            total_articles_available=0,
            total_pages=0,
            processed_articles_on_page=[]
        )
    
    db_query = db_query.options(
        joinedload(database.Article.tags),
        joinedload(database.Article.feed_source)
    ).order_by(database.Article.published_date.desc().nullslast(), database.Article.id.desc())
    
    total_articles_available = db_query.count()
    total_pages = math.ceil(total_articles_available / query.page_size) if query.page_size > 0 else 0
    current_page_for_slice = max(1, query.page)
    if total_pages > 0:
        current_page_for_slice = min(current_page_for_slice, total_pages)
    offset = (current_page_for_slice - 1) * query.page_size
    articles_from_db = db_query.limit(query.page_size).offset(offset).all()
    
    article_ids_on_page = [article.id for article in articles_from_db]
    
    summaries_map = {}
    if article_ids_on_page:
        all_summaries = db.query(database.Summary).filter(
            database.Summary.user_id == current_user.id,
            database.Summary.article_id.in_(article_ids_on_page)
        ).order_by(database.Summary.created_at.desc()).all()
        
        for summary in all_summaries:
            if summary.article_id not in summaries_map and not summary.summary_text.startswith("Error:"):
                summaries_map[summary.article_id] = summary.summary_text
    
    results_on_page: List[ArticleResult] = []
    articles_needing_ondemand_scrape: List[database.Article] = []
    
    for article_db_obj in articles_from_db:
        error_parts_for_display = []
        needs_on_demand_scrape = await article_helpers._should_attempt_scrape(article_db_obj, min_word_count_threshold)

        if needs_on_demand_scrape:
            articles_needing_ondemand_scrape.append(article_db_obj)
            error_parts_for_display.append("Content pending fresh scrape.")
        elif article_db_obj.scraped_text_content and article_db_obj.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX):
            error_parts_for_display.append(article_db_obj.scraped_text_content)
        elif article_db_obj.word_count is not None and article_db_obj.word_count < min_word_count_threshold:
            error_parts_for_display.append(f"Content previously scraped but found to be very short (word count: {article_db_obj.word_count}).")

        article_result = article_helpers._create_article_result(
            article_db_obj=article_db_obj,
            db=db,
            min_word_count_threshold=min_word_count_threshold,
            user_id=current_user.id,
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
            
            for i, res_art in enumerate(results_on_page):
                if res_art.id == art_db_obj_to_process.id:
                    error_parts_for_display = []
                    if art_db_obj_to_process.scraped_text_content and art_db_obj_to_process.scraped_text_content.startswith(SCRAPING_ERROR_PREFIX):
                        error_parts_for_display.append(art_db_obj_to_process.scraped_text_content)
                    elif art_db_obj_to_process.word_count is not None and art_db_obj_to_process.word_count < min_word_count_threshold:
                        error_parts_for_display.append(f"Content scraped but found to be very short (word count: {art_db_obj_to_process.word_count}).")

                    results_on_page[i] = article_helpers._create_article_result(
                        article_db_obj=art_db_obj_to_process,
                        db=db,
                        min_word_count_threshold=min_word_count_threshold,
                        user_id=current_user.id,
                        summary_text=summaries_map.get(art_db_obj_to_process.id),
                        error_message=" | ".join(error_parts_for_display) if error_parts_for_display else None
                    )
                    break
    
    return PaginatedSummariesAPIResponse(
        search_source=search_source_display,
        requested_page=current_page_for_slice,
        page_size=query.page_size,
        total_articles_available=total_articles_available,
        total_pages=total_pages,
        processed_articles_on_page=results_on_page
    )


@router.post("/{article_id}/favorite", response_model=ArticleResult)
async def toggle_favorite_status(
    article_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db)
):
    """
    Toggles the 'is_favorite' status of a single article for the current user.
    """
    logger.info(f"API Call: Toggle favorite for user {current_user.id}, Article ID {article_id}")

    article_db = security.verify_article_access(db, article_id, current_user.id)
    article_db = db.query(database.Article).options(
        joinedload(database.Article.tags),
        joinedload(database.Article.feed_source)
    ).filter(database.Article.id == article_id).first()

    user_state = db.query(database.UserArticleState).filter(
        database.UserArticleState.user_id == current_user.id,
        database.UserArticleState.article_id == article_id
    ).first()

    if not user_state:
        user_state = database.UserArticleState(
            user_id=current_user.id,
            article_id=article_id,
            is_favorite=True,
            is_read=False,
            is_deleted=False
        )
        db.add(user_state)
    else:
        if user_state.is_deleted and not user_state.is_favorite:
            user_state.is_deleted = False
            user_state.deleted_at = None
            user_state.is_read = False
        user_state.is_favorite = not user_state.is_favorite

    try:
        db.commit()
        logger.info(f"API: Toggled is_favorite={user_state.is_favorite} for user {current_user.id}, Article ID {article_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"API: Error toggling favorite for user {current_user.id}, Article ID {article_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="A database error occurred.")

    min_word_count_threshold = app_config.DEFAULT_MINIMUM_WORD_COUNT

    return article_helpers._create_article_result(
        article_db_obj=article_db,
        db=db,
        min_word_count_threshold=min_word_count_threshold,
        user_id=current_user.id
    )


@router.post("/{article_id}/regenerate-summary", response_model=ArticleResult)
async def regenerate_article_summary(
    article_id: int,
    request_body: RegenerateSummaryRequest,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db),
    llm_summary: ChatOpenAI = Depends(get_llm_summary),
    llm_tag: ChatOpenAI = Depends(get_llm_tag)
):
    if not llm_summary:
        raise HTTPException(status_code=503, detail="Summarization LLM not available.")

    try:
        min_word_count_threshold = int(settings_database.get_setting(settings_db, "minimum_word_count", str(app_config.DEFAULT_MINIMUM_WORD_COUNT)))
    except (ValueError, TypeError):
        min_word_count_threshold = app_config.DEFAULT_MINIMUM_WORD_COUNT

    security.verify_article_access(db, article_id, current_user.id)
    article_db = db.query(database.Article).options(
        joinedload(database.Article.tags),
        joinedload(database.Article.feed_source)
    ).filter(database.Article.id == article_id).first()
    
    logger.info(f"API Call: Regenerate summary for user {current_user.id}, Article ID {article_id}")
    current_text_content = article_db.scraped_text_content
    current_word_count = article_db.word_count
    force_scrape_needed = (
        not current_text_content or
        current_text_content.startswith(SCRAPING_ERROR_PREFIX) or
        current_text_content.startswith(CONTENT_ERROR_PREFIX) or
        (current_word_count is not None and current_word_count < min_word_count_threshold) or
        not article_db.full_html_content
    )
    
    if force_scrape_needed:
        logger.info(f"API Regenerate: Content for Article ID {article_id} requires re-scraping.")
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
                logger.error(f"API Regenerate: Failed to re-scrape for Article ID {article_id}: {scraper_error_msg_regen}")
                raise HTTPException(status_code=500, detail=f"Failed to get valid content for regeneration: {scraper_error_msg_regen}")
        else:
            scraper_error_msg_regen = "Failed to re-scrape: No document returned."
            article_db.scraped_text_content = f"{SCRAPING_ERROR_PREFIX} {scraper_error_msg_regen}"
            article_db.full_html_content = None
            article_db.word_count = 0
            current_text_content = article_db.scraped_text_content
            db.add(article_db)
            logger.error(f"API Regenerate: Failed to re-scrape for Article ID {article_id}: {scraper_error_msg_regen}")
            raise HTTPException(status_code=500, detail=f"Failed to get valid content for regeneration: {scraper_error_msg_regen}")

    if not current_text_content or current_text_content.startswith(SCRAPING_ERROR_PREFIX) or (current_word_count is not None and current_word_count < min_word_count_threshold):
        logger.error(f"API Regenerate: Article text content for ID {article_id} is still invalid or too short.")
        return article_helpers._create_article_result(
            article_db_obj=article_db,
            db=db,
            min_word_count_threshold=min_word_count_threshold,
            user_id=current_user.id,
            error_message=f"Cannot regenerate summary: article content is invalid or too short (word count: {current_word_count})."
        )

    lc_doc_for_summary_regen = LangchainDocument(
        page_content=current_text_content,
        metadata={
            "source": str(article_db.url),
            "id": article_db.id,
            "full_html_content": article_db.full_html_content,
        }
    )
    prompt_to_use = request_body.custom_prompt if request_body.custom_prompt and request_body.custom_prompt.strip() else settings_database.get_setting(settings_db, "summary_prompt", app_config.DEFAULT_SUMMARY_PROMPT)

    try:
        new_summary_text = await summarizer.summarize_document_content(lc_doc_for_summary_regen, llm_summary, prompt_to_use)
    except summarizer.SummarizationError as e:
        logger.warning(f"API Regenerate: Summarization failed for Article ID {article_id}: {e}")
        return article_helpers._create_article_result(
            article_db_obj=article_db,
            db=db,
            min_word_count_threshold=min_word_count_threshold,
            user_id=current_user.id,
            error_message=str(e)
        )

    db.query(database.Summary).filter(
        database.Summary.user_id == current_user.id,
        database.Summary.article_id == article_id
    ).delete(synchronize_session=False)

    model_name = settings_database.get_setting(settings_db, "summary_model_name", app_config.DEFAULT_SUMMARY_MODEL_NAME)
    new_summary_db_obj = database.Summary(
        user_id=current_user.id,
        article_id=article_id,
        summary_text=new_summary_text,
        prompt_used=prompt_to_use,
        model_used=model_name
    )
    db.add(new_summary_db_obj)

    if request_body.regenerate_tags and llm_tag and current_text_content and not current_text_content.startswith(SCRAPING_ERROR_PREFIX):
        logger.info(f"API Regenerate: Regenerating tags for user {current_user.id}, Article ID {article_id}")
        db.execute(
            database.article_tag_association.delete().where(
                database.article_tag_association.c.user_id == current_user.id,
                database.article_tag_association.c.article_id == article_id
            )
        )
        tag_names_generated = await summarizer.generate_tags_for_text(current_text_content, llm_tag, settings_database.get_setting(settings_db, "tag_prompt", app_config.DEFAULT_TAG_GENERATION_PROMPT))
        if tag_names_generated:
            for tag_name in tag_names_generated:
                tag_name_cleaned = tag_name.strip().lower()
                if not tag_name_cleaned:
                    continue
                tag_db_obj = db.query(database.Tag).filter(
                    database.Tag.name == tag_name_cleaned,
                    database.Tag.user_id == current_user.id
                ).first()
                if not tag_db_obj:
                    try:
                        tag_db_obj = database.Tag(name=tag_name_cleaned, user_id=current_user.id)
                        db.add(tag_db_obj)
                        db.flush()
                    except IntegrityError:
                        db.rollback()
                        tag_db_obj = db.query(database.Tag).filter(
                            database.Tag.name == tag_name_cleaned,
                            database.Tag.user_id == current_user.id
                        ).first()
                if tag_db_obj:
                    existing = db.query(database.article_tag_association).filter(
                        database.article_tag_association.c.user_id == current_user.id,
                        database.article_tag_association.c.article_id == article_id,
                        database.article_tag_association.c.tag_id == tag_db_obj.id
                    ).first()
                    if not existing:
                        stmt = database.article_tag_association.insert().values(
                            user_id=current_user.id,
                            article_id=article_id,
                            tag_id=tag_db_obj.id
                        )
                        db.execute(stmt)

    try:
        db.commit()
        db.refresh(article_db)
        logger.info(f"API Regenerate: Successfully committed all changes for Article ID {article_id}.")
    except Exception as e:
        db.rollback()
        logger.error(f"API Regenerate: Error committing changes for Article ID {article_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"A database error occurred while saving changes: {e}")

    return article_helpers._create_article_result(
        article_db_obj=article_db,
        db=db,
        min_word_count_threshold=min_word_count_threshold,
        user_id=current_user.id,
        summary_text=new_summary_text,
        error_message=None if not new_summary_text.startswith("Error:") else new_summary_text
    )


@router.get("/status/new-articles", response_model=NewArticleCheckResponse)
async def check_for_new_articles(
    since_timestamp: Optional[datetime] = Query(None, description="Timestamp to check for articles created after this point (ISO format)."),
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    logger.info(f"API Call: Checking for new articles for user {current_user.id} since_timestamp: {since_timestamp}")
    
    feed_source_ids = db.query(database.UserFeedSubscription.feed_source_id).filter(
        database.UserFeedSubscription.user_id == current_user.id
    ).all()
    feed_source_id_set = {f[0] for f in feed_source_ids}
    
    if not feed_source_id_set:
        return NewArticleCheckResponse(new_articles_available=False, latest_article_timestamp=None, article_count=0)
    
    if not feed_source_id_set:
        return NewArticleCheckResponse(new_articles_available=False, latest_article_timestamp=None, article_count=0)
    
    latest_article_query = db.query(sql_func.max(database.Article.created_at)).filter(
        database.Article.feed_source_id.in_(feed_source_id_set)
    )
    latest_article_db_timestamp = latest_article_query.scalar()
    
    if since_timestamp is None:
        total_article_count = db.query(sql_func.count(database.Article.id)).filter(
            database.Article.feed_source_id.in_(feed_source_id_set)
        ).scalar()
        return NewArticleCheckResponse(
            new_articles_available=total_article_count > 0,
            latest_article_timestamp=latest_article_db_timestamp,
            article_count=total_article_count
        )

    if since_timestamp.tzinfo is None:
        since_timestamp = since_timestamp.replace(tzinfo=timezone.utc)

    new_articles_query = db.query(database.Article).filter(
        database.Article.feed_source_id.in_(feed_source_id_set),
        database.Article.created_at > since_timestamp
    )
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


@router.post("/{article_id}/mark-read")
async def mark_article_read(
    article_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """Mark an article as read for the current user."""
    security.verify_article_access(db, article_id, current_user.id)
    
    user_state = db.query(database.UserArticleState).filter(
        database.UserArticleState.user_id == current_user.id,
        database.UserArticleState.article_id == article_id
    ).first()
    
    if not user_state:
        user_state = database.UserArticleState(
            user_id=current_user.id,
            article_id=article_id,
            is_read=True,
            is_favorite=False,
            is_deleted=False
        )
        db.add(user_state)
    else:
        user_state.is_read = True
    
    db.commit()
    logger.info(f"API: Article {article_id} marked as read for user {current_user.id}")
    return {"message": "Article marked as read", "article_id": article_id}


@router.post("/{article_id}/mark-unread")
async def mark_article_unread(
    article_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """Mark an article as unread for the current user."""
    security.verify_article_access(db, article_id, current_user.id)
    
    user_state = db.query(database.UserArticleState).filter(
        database.UserArticleState.user_id == current_user.id,
        database.UserArticleState.article_id == article_id
    ).first()
    
    if user_state:
        user_state.is_read = False
    
    db.commit()
    logger.info(f"API: Article {article_id} marked as unread for user {current_user.id}")
    return {"message": "Article marked as unread", "article_id": article_id}


@router.post("/{article_id}/delete")
async def soft_delete_article(
    article_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """Soft-delete an article for the current user."""
    security.verify_article_access(db, article_id, current_user.id)
    
    user_state = db.query(database.UserArticleState).filter(
        database.UserArticleState.user_id == current_user.id,
        database.UserArticleState.article_id == article_id
    ).first()
    
    if not user_state:
        user_state = database.UserArticleState(
            user_id=current_user.id,
            article_id=article_id,
            is_read=False,
            is_favorite=False,
            is_deleted=True
        )
        db.add(user_state)
    else:
        user_state.is_deleted = True
        user_state.deleted_at = datetime.now(timezone.utc)
        user_state.is_favorite = False
    
    db.commit()
    logger.info(f"API: Article {article_id} soft-deleted for user {current_user.id}")
    return {"message": "Article moved to deleted", "article_id": article_id}


@router.post("/{article_id}/restore")
async def restore_article(
    article_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """Restore a deleted article for the current user."""
    security.verify_article_access(db, article_id, current_user.id)
    
    user_state = db.query(database.UserArticleState).filter(
        database.UserArticleState.user_id == current_user.id,
        database.UserArticleState.article_id == article_id
    ).first()
    
    if user_state:
        user_state.is_deleted = False
        user_state.deleted_at = None
        user_state.is_read = False
        db.commit()
    
    logger.info(f"API: Article {article_id} restored for user {current_user.id}")
    return {"message": "Article restored", "article_id": article_id}


@router.post("/{article_id}/permanent-delete")
async def permanent_delete_article(
    article_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """Permanently delete user's article state (not the article itself)."""
    security.verify_article_access(db, article_id, current_user.id)
    
    user_state = db.query(database.UserArticleState).filter(
        database.UserArticleState.user_id == current_user.id,
        database.UserArticleState.article_id == article_id
    ).first()
    
    if user_state:
        db.delete(user_state)
        db.commit()
        logger.info(f"API: User {current_user.id} permanently deleted state for article {article_id}")
    
    return {"message": "Article permanently deleted", "article_id": article_id}


@router.post("/bulk-mark-read")
async def bulk_mark_read(
    article_ids: List[int],
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """Mark multiple articles as read for the current user."""
    feed_source_id_set = security.get_user_feed_source_ids(db, current_user.id)
    if not feed_source_id_set:
        return {"message": "No feeds found", "count": 0}
    
    valid_article_ids = db.query(database.Article.id).filter(
        database.Article.id.in_(article_ids),
        database.Article.feed_source_id.in_(feed_source_id_set)
    ).all()
    valid_article_ids_set = {a[0] for a in valid_article_ids}
    
    for article_id in article_ids:
        if article_id not in valid_article_ids_set:
            continue
        user_state = db.query(database.UserArticleState).filter(
            database.UserArticleState.user_id == current_user.id,
            database.UserArticleState.article_id == article_id
        ).first()
        
        if user_state:
            user_state.is_read = True
        else:
            user_state = database.UserArticleState(
                user_id=current_user.id,
                article_id=article_id,
                is_read=True,
                is_favorite=False,
                is_deleted=False
            )
            db.add(user_state)
    
    db.commit()
    logger.info(f"API: Bulk marked {len(article_ids)} articles as read for user {current_user.id}")
    return {"message": f"Marked {len(article_ids)} articles as read", "count": len(article_ids)}


@router.get("/deleted")
async def get_deleted_articles(
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    """Get all deleted articles for the current user."""
    feed_source_ids = db.query(database.UserFeedSubscription.feed_source_id).filter(
        database.UserFeedSubscription.user_id == current_user.id
    ).all()
    feed_source_id_set = {f[0] for f in feed_source_ids}
    
    if not feed_source_id_set:
        return []
    
    deleted_states = db.query(database.UserArticleState).filter(
        database.UserArticleState.user_id == current_user.id,
        database.UserArticleState.is_deleted == True
    ).all()
    
    deleted_article_ids = [s.article_id for s in deleted_states]
    
    if not deleted_article_ids:
        return []
    
    articles = db.query(database.Article).filter(
        database.Article.id.in_(deleted_article_ids),
        database.Article.feed_source_id.in_(feed_source_id_set)
    ).all()
    
    results = []
    for article in articles:
        state = next((s for s in deleted_states if s.article_id == article.id), None)
        results.append({
            "id": article.id,
            "title": article.title,
            "url": article.url,
            "publisher": article.feed_source.name if article.feed_source else article.publisher_name,
            "deleted_at": state.deleted_at.isoformat() if state and state.deleted_at else None,
            "created_at": article.created_at.isoformat() if article.created_at else None,
        })
    
    results.sort(key=lambda x: x.get("deleted_at", ""), reverse=True)
    return results