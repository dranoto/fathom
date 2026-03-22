# app/intelligence/routes.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy import or_, desc, func
from typing import List, Optional

from app import database, settings_database
from app import config as app_config
from app.routers.auth_routes import get_current_user
from app.security import get_user_feed_source_ids
from app.dependencies import get_llm_summary, get_llm_chat
from app.intelligence.models import Event, ArticleEvent, EventSummary
from app.intelligence.schemas import (
    EventCreate, EventUpdate, EventResponse, EventDetailResponse,
    ArticleInEvent, ArticleSearchResult, ArticleEventAdd,
    EventSummaryResponse, EventSummaryData, EventChatRequest, EventChatResponse
)
from app.intelligence.summarizer import generate_major_summary
from app import summarizer as chat_summarizer

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/events",
    tags=["intelligence"]
)


def get_event_or_404(db: SQLAlchemySession, event_id: int, user_id: int) -> Event:
    event = db.query(Event).filter(
        Event.id == event_id,
        Event.user_id == user_id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("", response_model=List[EventResponse])
async def list_events(
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    events = db.query(Event).filter(Event.user_id == current_user.id).order_by(desc(Event.created_at)).all()
    
    if not events:
        return []
    
    event_ids = [e.id for e in events]
    
    article_counts = dict(
        db.query(ArticleEvent.event_id, func.count(ArticleEvent.article_id))
        .filter(ArticleEvent.event_id.in_(event_ids))
        .group_by(ArticleEvent.event_id)
        .all()
    )
    
    feed_counts = dict(
        db.query(ArticleEvent.event_id, func.count(func.distinct(database.Article.feed_source_id)))
        .join(database.Article, ArticleEvent.article_id == database.Article.id)
        .filter(
            ArticleEvent.event_id.in_(event_ids),
            database.Article.feed_source_id.isnot(None)
        )
        .group_by(ArticleEvent.event_id)
        .all()
    )
    
    result = []
    for event in events:
        result.append(EventResponse(
            id=event.id,
            user_id=event.user_id,
            name=event.name,
            description=event.description,
            status=event.status,
            created_at=event.created_at,
            article_count=article_counts.get(event.id, 0),
            feed_count=feed_counts.get(event.id, 0)
        ))
    
    return result


@router.post("", response_model=EventResponse)
async def create_event(
    event_data: EventCreate,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    event = Event(
        user_id=current_user.id,
        name=event_data.name,
        description=event_data.description
    )
    db.add(event)
    
    try:
        db.commit()
        db.refresh(event)
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create event")
    
    return EventResponse(
        id=event.id,
        user_id=event.user_id,
        name=event.name,
        description=event.description,
        status=event.status,
        created_at=event.created_at,
        article_count=0,
        feed_count=0
    )
    

@router.get("/search/articles", response_model=List[ArticleSearchResult])
async def search_articles_for_event(
    keyword: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    user_feed_source_ids = get_user_feed_source_ids(db, current_user.id)
    
    if not user_feed_source_ids:
        return []
    
    search_term = f"%{keyword}%"
    
    articles = db.query(database.Article).filter(
        database.Article.feed_source_id.in_(user_feed_source_ids),
        or_(
            database.Article.title.ilike(search_term),
            database.Article.scraped_text_content.ilike(search_term),
            database.Article.rss_description.ilike(search_term)
        )
    ).order_by(desc(database.Article.published_date)).limit(limit).all()
    
    return [
        ArticleSearchResult(
            id=a.id,
            title=a.title,
            publisher_name=a.publisher_name,
            published_date=a.published_date,
            url=a.url,
            word_count=a.word_count
        )
        for a in articles
    ]


@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(
    event_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    event = get_event_or_404(db, event_id, current_user.id)
    
    article_events = (
        db.query(ArticleEvent, database.Article)
        .join(database.Article, ArticleEvent.article_id == database.Article.id)
        .filter(ArticleEvent.event_id == event_id)
        .order_by(desc(database.Article.published_date))
        .all()
    )
    
    articles = []
    for ae, article in article_events:
        articles.append(ArticleInEvent(
            id=article.id,
            title=article.title,
            publisher_name=article.publisher_name,
            published_date=article.published_date,
            url=article.url,
            word_count=article.word_count,
            added_at=ae.added_at
        ))
    
    latest_summary = db.query(EventSummary).filter(
        EventSummary.event_id == event_id
    ).order_by(desc(EventSummary.generated_at)).first()
    
    summary_data = None
    if latest_summary:
        summary_json = latest_summary.summary_json.copy() if latest_summary.summary_json else {}
        summary_json["article_ids"] = latest_summary.article_ids or []
        summary_data = EventSummaryData(**summary_json)
    
    return EventDetailResponse(
        id=event.id,
        user_id=event.user_id,
        name=event.name,
        description=event.description,
        status=event.status,
        created_at=event.created_at,
        articles=articles,
        latest_summary=summary_data
    )


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: int,
    event_data: EventUpdate,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    event = get_event_or_404(db, event_id, current_user.id)
    
    if event_data.name is not None:
        event.name = event_data.name
    if event_data.description is not None:
        event.description = event_data.description
    if event_data.status is not None:
        event.status = event_data.status
    
    try:
        db.commit()
        db.refresh(event)
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update event")
    
    article_count = db.query(func.count(ArticleEvent.article_id)).filter(
        ArticleEvent.event_id == event_id
    ).scalar() or 0
    
    feed_count = db.query(func.count(func.distinct(database.Article.feed_source_id))).join(
        ArticleEvent, ArticleEvent.article_id == database.Article.id
    ).filter(
        ArticleEvent.event_id == event_id,
        database.Article.feed_source_id.isnot(None)
    ).scalar() or 0
    
    return EventResponse(
        id=event.id,
        user_id=event.user_id,
        name=event.name,
        description=event.description,
        status=event.status,
        created_at=event.created_at,
        article_count=article_count,
        feed_count=feed_count
    )


@router.delete("/{event_id}")
async def delete_event(
    event_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    event = get_event_or_404(db, event_id, current_user.id)
    
    try:
        db.delete(event)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete event")
    
    return {"message": "Event deleted successfully"}


@router.get("/{event_id}/articles", response_model=List[ArticleInEvent])
async def get_event_articles(
    event_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    get_event_or_404(db, event_id, current_user.id)
    
    article_events = (
        db.query(ArticleEvent, database.Article)
        .join(database.Article, ArticleEvent.article_id == database.Article.id)
        .filter(ArticleEvent.event_id == event_id)
        .order_by(desc(database.Article.published_date))
        .all()
    )
    
    articles = []
    for ae, article in article_events:
        articles.append(ArticleInEvent(
            id=article.id,
            title=article.title,
            publisher_name=article.publisher_name,
            published_date=article.published_date,
            url=article.url,
            word_count=article.word_count,
            added_at=ae.added_at
        ))
    
    return articles


@router.post("/{event_id}/articles")
async def add_articles_to_event(
    event_id: int,
    article_data: ArticleEventAdd,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    event = get_event_or_404(db, event_id, current_user.id)
    user_feed_source_ids = get_user_feed_source_ids(db, current_user.id)
    
    added_count = 0
    for article_id in article_data.article_ids:
        article = db.query(database.Article).filter(
            database.Article.id == article_id,
            database.Article.feed_source_id.in_(user_feed_source_ids)
        ).first()
        
        if not article:
            continue
        
        existing = db.query(ArticleEvent).filter(
            ArticleEvent.article_id == article_id,
            ArticleEvent.event_id == event_id
        ).first()
        
        if not existing:
            ae = ArticleEvent(article_id=article_id, event_id=event_id)
            db.add(ae)
            added_count += 1
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding articles to event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add articles")
    
    return {"message": f"Added {added_count} articles to event", "added_count": added_count}


@router.delete("/{event_id}/articles/{article_id}")
async def remove_article_from_event(
    event_id: int,
    article_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    get_event_or_404(db, event_id, current_user.id)
    
    ae = db.query(ArticleEvent).filter(
        ArticleEvent.event_id == event_id,
        ArticleEvent.article_id == article_id
    ).first()
    
    if not ae:
        raise HTTPException(status_code=404, detail="Article not in event")
    
    try:
        db.delete(ae)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing article from event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to remove article")
    
    return {"message": "Article removed from event"}


@router.post("/{event_id}/summary", response_model=EventSummaryResponse)
async def generate_event_summary(
    event_id: int,
    request: Request,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    event = get_event_or_404(db, event_id, current_user.id)
    
    article_events = (
        db.query(ArticleEvent, database.Article)
        .join(database.Article, ArticleEvent.article_id == database.Article.id)
        .filter(ArticleEvent.event_id == event_id)
        .order_by(desc(database.Article.published_date))
        .all()
    )
    
    if not article_events:
        raise HTTPException(status_code=400, detail="No articles in event")
    
    articles_data = []
    for ae, article in article_events:
        articles_data.append({
            "id": article.id,
            "title": article.title,
            "publisher_name": article.publisher_name,
            "published_date": article.published_date.isoformat() if article.published_date else None,
            "url": article.url,
            "word_count": article.word_count,
            "scraped_text_content": article.scraped_text_content,
            "rss_description": article.rss_description
        })
    
    prior_summary = db.query(EventSummary).filter(
        EventSummary.event_id == event_id
    ).order_by(desc(EventSummary.generated_at)).first()
    
    prior_json = prior_summary.summary_json if prior_summary else None
    prior_article_ids = prior_summary.article_ids if prior_summary else []
    
    major_summary_prompt = settings_database.get_setting(
        db, "major_summary_prompt", app_config.DEFAULT_MAJOR_SUMMARY_PROMPT
    )
    
    try:
        llm = get_llm_summary(request)
        summary_json = await generate_major_summary(
            event_name=event.name,
            articles=articles_data,
            prompt_template=major_summary_prompt,
            prior_summary_json=prior_json,
            llm=llm
        )
    except Exception as e:
        logger.error(f"Error generating major summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")
    
    article_ids_used = [a["id"] for a in articles_data]
    summary_json["article_ids"] = article_ids_used
    
    new_summary = EventSummary(
        event_id=event_id,
        summary_json=summary_json,
        article_ids=article_ids_used,
        article_count=len(articles_data)
    )
    db.add(new_summary)
    
    try:
        db.commit()
        db.refresh(new_summary)
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving event summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save summary")
    
    return EventSummaryResponse(
        id=new_summary.id,
        event_id=new_summary.event_id,
        summary_json=EventSummaryData(**new_summary.summary_json),
        article_ids=new_summary.article_ids or [],
        generated_at=new_summary.generated_at,
        article_count=new_summary.article_count
    )


@router.get("/{event_id}/summary")
async def get_event_summary(
    event_id: int,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    get_event_or_404(db, event_id, current_user.id)
    
    latest_summary = db.query(EventSummary).filter(
        EventSummary.event_id == event_id
    ).order_by(desc(EventSummary.generated_at)).first()
    
    if not latest_summary:
        return None
    
    return EventSummaryResponse(
        id=latest_summary.id,
        event_id=latest_summary.event_id,
        summary_json=EventSummaryData(**latest_summary.summary_json),
        article_ids=latest_summary.article_ids or [],
        generated_at=latest_summary.generated_at,
        article_count=latest_summary.article_count
    )


@router.post("/{event_id}/summary/update", response_model=EventSummaryResponse)
async def update_event_summary(
    event_id: int,
    request: Request,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    event = get_event_or_404(db, event_id, current_user.id)
    
    prior_summary = db.query(EventSummary).filter(
        EventSummary.event_id == event_id
    ).order_by(desc(EventSummary.generated_at)).first()
    
    if not prior_summary:
        raise HTTPException(status_code=400, detail="No existing summary to update. Use regenerate instead.")
    
    prior_article_ids = set(prior_summary.article_ids or [])
    prior_json = prior_summary.summary_json
    
    article_events = (
        db.query(ArticleEvent, database.Article)
        .join(database.Article, ArticleEvent.article_id == database.Article.id)
        .filter(ArticleEvent.event_id == event_id)
        .order_by(desc(database.Article.published_date))
        .all()
    )
    
    if not article_events:
        raise HTTPException(status_code=400, detail="No articles in event")
    
    articles_data = []
    new_articles = []
    for ae, article in article_events:
        article_dict = {
            "id": article.id,
            "title": article.title,
            "publisher_name": article.publisher_name,
            "published_date": article.published_date.isoformat() if article.published_date else None,
            "url": article.url,
            "word_count": article.word_count,
            "scraped_text_content": article.scraped_text_content,
            "rss_description": article.rss_description
        }
        articles_data.append(article_dict)
        if article.id not in prior_article_ids:
            new_articles.append(article_dict)
    
    major_summary_prompt = settings_database.get_setting(
        db, "major_summary_prompt", app_config.DEFAULT_MAJOR_SUMMARY_PROMPT
    )
    
    try:
        llm = get_llm_summary(request)
        
        if new_articles:
            summary_json = await generate_major_summary(
                event_name=event.name,
                articles=articles_data,
                prompt_template=major_summary_prompt,
                prior_summary_json=prior_json,
                llm=llm
            )
        else:
            summary_json = prior_json.copy() if prior_json else prior_json
            summary_json["progressive_summary"] = "(No new articles since last summary)"
    except Exception as e:
        logger.error(f"Error generating major summary update: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")
    
    article_ids_used = [a["id"] for a in articles_data]
    summary_json["article_ids"] = article_ids_used
    
    new_summary = EventSummary(
        event_id=event_id,
        summary_json=summary_json,
        article_ids=article_ids_used,
        article_count=len(articles_data)
    )
    db.add(new_summary)
    
    try:
        db.commit()
        db.refresh(new_summary)
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving event summary update: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save summary")
    
    return EventSummaryResponse(
        id=new_summary.id,
        event_id=new_summary.event_id,
        summary_json=EventSummaryData(**new_summary.summary_json),
        article_ids=new_summary.article_ids or [],
        generated_at=new_summary.generated_at,
        article_count=new_summary.article_count
    )


@router.post("/{event_id}/chat", response_model=EventChatResponse)
async def chat_about_event(
    event_id: int,
    chat_request: EventChatRequest,
    http_request: Request,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    event = get_event_or_404(db, event_id, current_user.id)
    
    article_events = (
        db.query(ArticleEvent, database.Article)
        .join(database.Article, ArticleEvent.article_id == database.Article.id)
        .filter(ArticleEvent.event_id == event_id)
        .order_by(desc(database.Article.published_date))
        .limit(20)
        .all()
    )
    
    if not article_events:
        raise HTTPException(status_code=400, detail="No articles in event")
    
    articles_data = []
    for ae, article in article_events:
        content = article.scraped_text_content or article.rss_description or ""
        excerpt = content[:3000] + "..." if len(content) > 3000 else content
        articles_data.append({
            "id": article.id,
            "title": article.title,
            "publisher_name": article.publisher_name,
            "url": article.url,
            "content": excerpt
        })
    
    articles_context = "\n\n".join([
        f"--- {a['title']} ({a['publisher_name']}) ---\n{a['content']}"
        for a in articles_data
    ])
    
    try:
        llm_chat = get_llm_chat(http_request)
        answer = await chat_summarizer.get_chat_response(
            llm_instance=llm_chat,
            article_text=articles_context,
            question=chat_request.question,
            chat_history=chat_request.chat_history
        )
    except Exception as e:
        logger.error(f"Error getting chat response for event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate response")
    
    sources = [
        ArticleInEvent(
            id=a["id"],
            title=a["title"],
            publisher_name=a["publisher_name"],
            published_date=None,
            url=a["url"],
            word_count=None,
            added_at=None
        )
        for a in articles_data[:5]
    ]
    
    return EventChatResponse(answer=answer, sources=sources)
