# app/routers/chat_routes.py
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as SQLAlchemySession
from typing import List

from .. import database
from .. import scraper
from .. import summarizer
from .. import config as app_config
from .. import settings_database
from .. import security
from ..schemas import (
    ChatHistoryItem,
    ChatQuery,
    ChatResponse
)
from ..dependencies import get_llm_chat
from .auth_routes import get_current_user
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["chat"]
)

@router.get("/article/{article_id}/chat-history", response_model=List[ChatHistoryItem])
async def get_article_chat_history(
    article_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    logger.info(f"API Call: Fetching chat history for user {current_user.id}, Article ID: {article_id}")
    db_history_items = db.query(database.ChatHistory)\
        .filter(
            database.ChatHistory.article_id == article_id,
            database.ChatHistory.user_id == current_user.id
        )\
        .order_by(database.ChatHistory.timestamp.asc())\
        .all()
    if not db_history_items:
        logger.info(f"No chat history found for user {current_user.id}, Article ID: {article_id}")
        return []
    formatted_history: List[ChatHistoryItem] = []
    for item in db_history_items:
        formatted_history.append(ChatHistoryItem(role="user", content=item.question))
        if item.answer:
            formatted_history.append(ChatHistoryItem(role="ai", content=item.answer))
    logger.info(f"Successfully retrieved {len(formatted_history)} items for chat history of user {current_user.id}, Article ID: {article_id}")
    return formatted_history

@router.post("/chat-with-article", response_model=ChatResponse)
async def chat_with_article_endpoint(
    query: ChatQuery,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db),
    settings_db: SQLAlchemySession = Depends(settings_database.get_db),
    llm_chat: ChatOpenAI = Depends(get_llm_chat)
):
    if not llm_chat:
        logger.error("API Error: Chat LLM not available via DI in chat_with_article_endpoint.")
        raise HTTPException(status_code=503, detail="Chat service (LLM) not initialized.")

    logger.info(f"API Call: Chat with user {current_user.id}, Article ID: {query.article_id}. Question: '{query.question[:50]}...'")
    
    article_db = security.verify_article_access(db, query.article_id, current_user.id)
    
    if query.chat_history:
        logger.debug(f"Received chat history with {len(query.chat_history)} turns for Article ID: {query.article_id}")

    article_text_for_chat = article_db.scraped_text_content or ""

    error_detail_for_chat: str | None = None
    if not article_text_for_chat or article_text_for_chat.startswith("Error:") or article_text_for_chat.startswith("Content Error:") or not article_db.full_html_content:
        logger.info(f"CHAT API: Article {article_db.id} content requires re-scraping for chat.")
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
                    logger.info(f"CHAT API: Successfully re-scraped and saved content for article {article_db.id}")
                except Exception as e_commit:
                    db.rollback()
                    logger.error(f"CHAT API: Error committing re-scraped content for article {article_db.id}: {e_commit}", exc_info=True)
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
            logger.warning(f"CHAT API: Error on re-scrape for Article {article_db.id}: {error_detail_for_chat}")

    effective_chat_prompt = query.chat_prompt if query.chat_prompt else settings_database.get_setting(settings_db, "chat_prompt", app_config.DEFAULT_CHAT_PROMPT)
    
    answer = await summarizer.get_chat_response(
        llm_instance=llm_chat,
        article_text=article_text_for_chat,
        question=query.question,
        chat_history=query.chat_history,
        custom_chat_prompt_str=effective_chat_prompt
    )
    logger.debug(f"CHAT API: LLM Answer for article {article_db.id} (first 100 chars): '{answer[:100]}'")

    final_error_message_for_response = error_detail_for_chat
    is_llm_error = answer.startswith("Error getting answer from AI:") or answer == "AI returned an empty answer."
    logger.debug(f"CHAT API: Determined is_llm_error: {is_llm_error} for article {article_db.id}")

    if is_llm_error:
        current_llm_error = answer
        if final_error_message_for_response:
            final_error_message_for_response = f"{final_error_message_for_response} | LLM: {current_llm_error}"
        else:
            final_error_message_for_response = f"LLM: {current_llm_error}"

    if not is_llm_error:
        logger.info(f"CHAT API: Attempting to save chat turn for user {current_user.id}, article {article_db.id}")
        try:
            new_chat_item_db = database.ChatHistory(
                user_id=current_user.id,
                article_id=article_db.id,
                question=query.question,
                answer=answer,
                prompt_used=effective_chat_prompt,
                model_used=settings_database.get_setting(settings_db, "chat_model_name", app_config.DEFAULT_CHAT_MODEL_NAME)
            )
            db.add(new_chat_item_db)
            logger.debug(f"CHAT API: ChatHistory object created for user {current_user.id}, article {article_db.id}, attempting commit.")
            db.commit()
            db.refresh(new_chat_item_db)
            logger.info(f"CHAT API: Successfully saved new chat turn (ID {new_chat_item_db.id}) for user {current_user.id}, article {article_db.id}")
        except Exception as e_save_chat:
            db.rollback()
            logger.error(f"CHAT API: Error saving new chat turn to DB for user {current_user.id}, article {article_db.id}: {e_save_chat}", exc_info=True)
            db_save_error = "Failed to save chat turn to database."
            if final_error_message_for_response:
                final_error_message_for_response = f"{final_error_message_for_response} | DB: {db_save_error}"
            else:
                final_error_message_for_response = f"DB: {db_save_error}"
    else:
        logger.warning(f"CHAT API: Skipping save of chat turn for user {current_user.id}, article {article_db.id} due to is_llm_error being True.")

    logger.info(f"CHAT API: Sending response for user {current_user.id}, article {article_db.id}. Answer starts: '{answer[:60]}...'. Error: {final_error_message_for_response}")
    return ChatResponse(article_id=article_db.id, question=query.question, answer=answer, error_message=final_error_message_for_response)