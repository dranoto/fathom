# app/intelligence/schemas.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class EventSummaryData(BaseModel):
    timeline_narrative: str
    cross_source_synthesis: str
    progressive_summary: str
    article_count: Optional[int] = None
    feed_count: Optional[int] = None
    date_range: Optional[str] = None
    key_developments: Optional[List[str]] = None

    class Config:
        from_attributes = True


class EventCreate(BaseModel):
    name: str
    description: Optional[str] = None


class EventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class EventResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    article_count: Optional[int] = 0
    feed_count: Optional[int] = 0

    class Config:
        from_attributes = True


class EventDetailResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    articles: List["ArticleInEvent"]
    latest_summary: Optional[EventSummaryData]

    class Config:
        from_attributes = True


class ArticleInEvent(BaseModel):
    id: int
    title: Optional[str]
    publisher_name: Optional[str]
    published_date: Optional[datetime]
    url: str
    word_count: Optional[int]
    added_at: datetime

    class Config:
        from_attributes = True


class ArticleSearchResult(BaseModel):
    id: int
    title: Optional[str]
    publisher_name: Optional[str]
    published_date: Optional[datetime]
    url: str
    word_count: Optional[int]
    relevance_score: Optional[float] = None

    class Config:
        from_attributes = True


class ArticleEventAdd(BaseModel):
    article_ids: List[int]


class EventSummaryResponse(BaseModel):
    id: int
    event_id: int
    summary_json: EventSummaryData
    generated_at: datetime
    article_count: int

    class Config:
        from_attributes = True


class EventChatRequest(BaseModel):
    question: str
    chat_history: Optional[List[Dict[str, str]]] = None


class EventChatResponse(BaseModel):
    answer: str
    sources: List[ArticleInEvent]

    class Config:
        from_attributes = True


EventDetailResponse.model_rebuild()
