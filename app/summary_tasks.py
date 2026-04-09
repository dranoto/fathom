# app/summary_tasks.py
import asyncio
import logging
from typing import Optional

from sqlalchemy.orm import joinedload

from . import database
from . import settings_database
from . import scraper
from . import summarizer
from . import config as app_config
from . import tag_utils
from .routers.article_helpers import SCRAPING_ERROR_PREFIX, CONTENT_ERROR_PREFIX
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document as LangchainDocument
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

SUMMARY_SEMAPHORE = asyncio.Semaphore(20)
DB_LOCK = asyncio.Lock()

_article_locks: dict[int, asyncio.Lock] = {}


def get_article_lock(article_id: int) -> asyncio.Lock:
    if article_id not in _article_locks:
        _article_locks[article_id] = asyncio.Lock()
    return _article_locks[article_id]


def is_article_summary_running(article_id: int) -> bool:
    lock = _article_locks.get(article_id)
    return lock is not None and lock.locked()


async def run_summary_job(
    article_id: int,
    user_id: int,
    custom_prompt: Optional[str],
    regenerate_tags: bool,
    llm_summary: ChatOpenAI,
    llm_tag: ChatOpenAI,
    db_session_factory,
    settings_db_session_factory
):
    article_lock = get_article_lock(article_id)
    
    async with article_lock:
        async with SUMMARY_SEMAPHORE:
            logger.info(f"SummaryTask: Starting summary job for article {article_id}, user {user_id}")
            
            db = db_session_factory()
            settings_db = settings_db_session_factory()
            
            try:
                min_word_count_threshold = int(settings_database.get_setting(
                    settings_db, "minimum_word_count", str(app_config.DEFAULT_MINIMUM_WORD_COUNT)
                ))
            except (ValueError, TypeError):
                min_word_count_threshold = app_config.DEFAULT_MINIMUM_WORD_COUNT
            
            article_db = db.query(database.Article).options(
                joinedload(database.Article.tags),
                joinedload(database.Article.feed_source)
            ).filter(database.Article.id == article_id).first()
            
            if not article_db:
                logger.error(f"SummaryTask: Article {article_id} not found")
                return
            
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
                logger.info(f"SummaryTask: Content for Article ID {article_id} requires re-scraping.")
                scraped_docs_list_regen: list[LangchainDocument] = await scraper.scrape_urls([str(article_db.url)])
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
                        logger.info(f"SummaryTask: Successfully re-scrapped content for Article ID {article_id}.")
                    else:
                        scraper_error_msg_regen = scraper_error_msg_regen or "Failed to re-scrape content (regen)"
                        article_db.scraped_text_content = f"{SCRAPING_ERROR_PREFIX} {scraper_error_msg_regen}"
                        article_db.full_html_content = None
                        article_db.word_count = 0
                        current_text_content = article_db.scraped_text_content
                        db.add(article_db)
                        logger.error(f"SummaryTask: Failed to re-scrape for Article ID {article_id}: {scraper_error_msg_regen}")
                        return
                else:
                    scraper_error_msg_regen = "Failed to re-scrape: No document returned."
                    article_db.scraped_text_content = f"{SCRAPING_ERROR_PREFIX} {scraper_error_msg_regen}"
                    article_db.full_html_content = None
                    article_db.word_count = 0
                    current_text_content = article_db.scraped_text_content
                    db.add(article_db)
                    logger.error(f"SummaryTask: Failed to re-scrape for Article ID {article_id}: {scraper_error_msg_regen}")
                    return
            
            if not current_text_content or current_text_content.startswith(SCRAPING_ERROR_PREFIX) or (current_word_count is not None and current_word_count < min_word_count_threshold):
                logger.error(f"SummaryTask: Article text content for ID {article_id} is still invalid or too short.")
                return
            
            lc_doc_for_summary_regen = LangchainDocument(
                page_content=current_text_content,
                metadata={
                    "source": str(article_db.url),
                    "id": article_db.id,
                    "full_html_content": article_db.full_html_content,
                }
            )
            prompt_to_use = custom_prompt if custom_prompt and custom_prompt.strip() else settings_database.get_setting(
                settings_db, "summary_prompt", app_config.DEFAULT_SUMMARY_PROMPT
            )
            
            try:
                new_summary_text = await summarizer.summarize_document_content(lc_doc_for_summary_regen, llm_summary, prompt_to_use)
            except summarizer.SummarizationError as e:
                logger.warning(f"SummaryTask: Summarization failed for Article ID {article_id}: {e}")
                return
            
            db.query(database.Summary).filter(
                database.Summary.user_id == user_id,
                database.Summary.article_id == article_id
            ).delete(synchronize_session=False)
            
            model_name = settings_database.get_setting(settings_db, "summary_model_name", app_config.DEFAULT_SUMMARY_MODEL_NAME)
            new_summary_db_obj = database.Summary(
                user_id=user_id,
                article_id=article_id,
                summary_text=new_summary_text,
                prompt_used=prompt_to_use,
                model_used=model_name
            )
            db.add(new_summary_db_obj)
            
            if regenerate_tags and llm_tag and current_text_content and not current_text_content.startswith(SCRAPING_ERROR_PREFIX):
                logger.info(f"SummaryTask: Regenerating tags for user {user_id}, Article ID {article_id}")
                db.execute(
                    database.article_tag_association.delete().where(
                        database.article_tag_association.c.user_id == user_id,
                        database.article_tag_association.c.article_id == article_id
                    )
                )
                
                existing_tags = db.query(database.Tag).filter(
                    database.Tag.user_id == user_id
                ).all()
                existing_normalized_names = [t.normalized_name or tag_utils.normalize_tag_name(t.name) for t in existing_tags]
                
                tag_names_generated = await summarizer.generate_tags_for_text(
                    current_text_content, llm_tag,
                    settings_database.get_setting(settings_db, "tag_prompt", app_config.DEFAULT_TAG_GENERATION_PROMPT)
                )
                
                logger.info(f"SummaryTask: Generated tag names: {tag_names_generated}")
                
                if tag_names_generated:
                    processed_tags = tag_utils.process_ai_tags_with_fuzzy_matching(tag_names_generated, existing_normalized_names)
                    
                    for tag_name_cleaned in processed_tags:
                        if not tag_name_cleaned:
                            continue
                        tag_db_obj = db.query(database.Tag).filter(
                            database.Tag.normalized_name == tag_name_cleaned,
                            database.Tag.user_id == user_id
                        ).first()
                        if not tag_db_obj:
                            try:
                                original_tag = next((t for t in tag_names_generated if tag_utils.normalize_tag_name(t) == tag_name_cleaned), tag_name_cleaned)
                                tag_db_obj = database.Tag(
                                    name=original_tag.strip().title() if original_tag else tag_name_cleaned,
                                    normalized_name=tag_name_cleaned,
                                    user_id=user_id
                                )
                                db.add(tag_db_obj)
                                db.flush()
                            except IntegrityError:
                                db.rollback()
                                tag_db_obj = db.query(database.Tag).filter(
                                    database.Tag.normalized_name == tag_name_cleaned,
                                    database.Tag.user_id == user_id
                                ).first()
                        if tag_db_obj:
                            existing = db.query(database.article_tag_association).filter(
                                database.article_tag_association.c.user_id == user_id,
                                database.article_tag_association.c.article_id == article_id,
                                database.article_tag_association.c.tag_id == tag_db_obj.id
                            ).first()
                            if not existing:
                                stmt = database.article_tag_association.insert().values(
                                    user_id=user_id,
                                    article_id=article_id,
                                    tag_id=tag_db_obj.id
                                )
                                db.execute(stmt)
            
            try:
                db.commit()
                db.refresh(article_db)
                logger.info(f"SummaryTask: Successfully committed all changes for Article ID {article_id}.")
            except Exception as e:
                db.rollback()
                logger.error(f"SummaryTask: Error committing changes for Article ID {article_id}: {e}", exc_info=True)
            finally:
                db.close()
                settings_db.close()


async def run_chat_job(
    article_id: int,
    user_id: int,
    question: str,
    chat_history: Optional[list],
    chat_prompt: Optional[str],
    llm_chat: ChatOpenAI,
    db_session_factory,
    settings_db_session_factory
):
    article_lock = get_article_lock(article_id)
    
    async with article_lock:
        async with SUMMARY_SEMAPHORE:
            logger.info(f"ChatTask: Starting chat job for article {article_id}, user {user_id}")
            
            db = db_session_factory()
            settings_db = settings_db_session_factory()
            
            article_db = db.query(database.Article).filter(
                database.Article.id == article_id
            ).first()
            
            if not article_db:
                logger.error(f"ChatTask: Article {article_id} not found")
                return
            
            article_text_for_chat = article_db.scraped_text_content or ""
            
            error_detail_for_chat: str | None = None
            if not article_text_for_chat or article_text_for_chat.startswith("Error:") or article_text_for_chat.startswith("Content Error:") or not article_db.full_html_content:
                logger.info(f"ChatTask: Article {article_db.id} content requires re-scraping for chat.")
                scraped_docs = await scraper.scrape_urls([str(article_db.url)], app_config.PATH_TO_EXTENSION, app_config.USE_HEADLESS_BROWSER)
                if scraped_docs and scraped_docs[0]:
                    doc_item = scraped_docs[0]
                    if not doc_item.metadata.get("error") and doc_item.page_content and doc_item.page_content.strip():
                        article_text_for_chat = doc_item.page_content
                        article_db.scraped_text_content = article_text_for_chat
                        article_db.full_html_content = doc_item.metadata.get('full_html_content')
                        db.add(article_db)
                        try:
                            db.commit()
                            db.refresh(article_db)
                            logger.info(f"ChatTask: Successfully re-scraped and saved content for article {article_db.id}")
                        except Exception as e_commit:
                            db.rollback()
                            logger.error(f"ChatTask: Error committing re-scraped content for article {article_db.id}: {e_commit}", exc_info=True)
                            error_detail_for_chat = "Failed to save re-scraped content."
                            article_text_for_chat = ""
                    else:
                        error_detail_for_chat = doc_item.metadata.get("error", "Re-scraped content was empty or had an error.")
                        article_text_for_chat = ""
                        article_db.scraped_text_content = f"Scraping Error (chat attempt): {error_detail_for_chat}"
                        article_db.full_html_content = None
                        db.add(article_db)
                        db.commit()
                        db.refresh(article_db)
                else:
                    error_detail_for_chat = "Failed to re-scrape article for chat (no document returned)."
                    article_text_for_chat = ""
                    article_db.scraped_text_content = f"Scraping Error (chat attempt): {error_detail_for_chat}"
                    article_db.full_html_content = None
                    db.add(article_db)
                    db.commit()
                    db.refresh(article_db)
                
                if error_detail_for_chat:
                    logger.warning(f"ChatTask: Error on re-scrape for Article {article_db.id}: {error_detail_for_chat}")
            
            effective_chat_prompt = chat_prompt if chat_prompt else settings_database.get_setting(
                settings_db, "chat_prompt", app_config.DEFAULT_CHAT_PROMPT
            )
            
            answer = await summarizer.get_chat_response(
                llm_instance=llm_chat,
                article_text=article_text_for_chat,
                question=question,
                chat_history=chat_history,
                custom_chat_prompt_str=effective_chat_prompt
            )
            logger.debug(f"ChatTask: LLM Answer for article {article_db.id} (first 100 chars): '{answer[:100]}'")
            
            final_error_message_for_response = error_detail_for_chat
            is_llm_error = answer.startswith("Error getting answer from AI:") or answer == "AI returned an empty answer."
            logger.debug(f"ChatTask: Determined is_llm_error: {is_llm_error} for article {article_db.id}")
            
            if is_llm_error:
                current_llm_error = answer
                if final_error_message_for_response:
                    final_error_message_for_response = f"{final_error_message_for_response} | LLM: {current_llm_error}"
                else:
                    final_error_message_for_response = f"LLM: {current_llm_error}"
            
            if not is_llm_error:
                logger.info(f"ChatTask: Attempting to save chat turn for user {user_id}, article {article_db.id}")
                try:
                    new_chat_item_db = database.ChatHistory(
                        user_id=user_id,
                        article_id=article_db.id,
                        question=question,
                        answer=answer,
                        prompt_used=effective_chat_prompt,
                        model_used=settings_database.get_setting(settings_db, "chat_model_name", app_config.DEFAULT_CHAT_MODEL_NAME)
                    )
                    db.add(new_chat_item_db)
                    logger.debug(f"ChatTask: ChatHistory object created for user {user_id}, article {article_db.id}, attempting commit.")
                    db.commit()
                    db.refresh(new_chat_item_db)
                    logger.info(f"ChatTask: Successfully saved new chat turn (ID {new_chat_item_db.id}) for user {user_id}, article {article_db.id}")
                except Exception as e_save_chat:
                    db.rollback()
                    logger.error(f"ChatTask: Error saving new chat turn to DB for user {user_id}, article {article_db.id}: {e_save_chat}", exc_info=True)
            else:
                logger.warning(f"ChatTask: Skipping save of chat turn for user {user_id}, article {article_db.id} due to is_llm_error being True.")
            
            logger.info(f"ChatTask: Chat task completed for user {user_id}, article {article_db.id}. Answer starts: '{answer[:60]}...'")
            
            db.close()
            settings_db.close()
