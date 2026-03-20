# app/routers/tag_routes.py
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as SQLAlchemySession

from .. import database
from ..schemas import ArticleTagResponse
from ..tag_utils import normalize_tag_name, get_normalized_similarity
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=List[ArticleTagResponse])
async def get_user_tags(
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    logger.info(f"API: Fetching all tags for user {current_user.id}")
    tags = db.query(database.Tag).filter(
        database.Tag.user_id == current_user.id
    ).order_by(database.Tag.name).all()
    return [ArticleTagResponse(id=t.id, name=t.name) for t in tags]


@router.get("/search", response_model=List[ArticleTagResponse])
async def search_tags(
    q: str = Query(..., min_length=2, description="Search query (minimum 2 characters)"),
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    logger.info(f"API: Searching tags for user {current_user.id} with query: {q}")
    normalized_query = normalize_tag_name(q)
    query_words = set(normalized_query.split())
    
    user_tags = db.query(database.Tag).filter(
        database.Tag.user_id == current_user.id
    ).all()
    
    if not user_tags:
        return []
    
    exact_matches = []
    starts_with_matches = []
    substring_matches = []
    all_words_match = []
    fuzzy_matches = []
    
    for tag in user_tags:
        tag_normalized = tag.normalized_name or normalize_tag_name(tag.name)
        tag_words = set(tag_normalized.split())
        
        if tag_normalized == normalized_query:
            exact_matches.append((tag, 1.0))
        elif tag_normalized.startswith(normalized_query):
            starts_with_matches.append((tag, 1.0 + len(normalized_query) / len(tag_normalized)))
        elif normalized_query in tag_normalized:
            substring_matches.append((tag, len(normalized_query) / len(tag_normalized)))
        elif query_words and query_words.issubset(tag_words):
            all_words_match.append((tag, len(query_words) / len(tag_words)))
        else:
            score = get_normalized_similarity(normalized_query, tag_normalized)
            if score >= 0.5:
                fuzzy_matches.append((tag, score))
    
    starts_with_matches.sort(key=lambda x: x[1], reverse=True)
    substring_matches.sort(key=lambda x: x[1], reverse=True)
    all_words_match.sort(key=lambda x: x[1], reverse=True)
    fuzzy_matches.sort(key=lambda x: x[1], reverse=True)
    
    results = []
    for tag, score in exact_matches:
        results.append(ArticleTagResponse(id=tag.id, name=tag.name))
    for tag, score in starts_with_matches:
        if len(results) < 10:
            results.append(ArticleTagResponse(id=tag.id, name=tag.name))
    for tag, score in substring_matches:
        if len(results) < 10:
            results.append(ArticleTagResponse(id=tag.id, name=tag.name))
    for tag, score in all_words_match:
        if len(results) < 10:
            results.append(ArticleTagResponse(id=tag.id, name=tag.name))
    for tag, score in fuzzy_matches:
        if len(results) < 10:
            results.append(ArticleTagResponse(id=tag.id, name=tag.name))
    
    return results[:10]