# app/routers/tag_routes.py
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as SQLAlchemySession

from .. import database
from ..schemas import ArticleTagResponse
from ..tag_utils import normalize_tag_name, find_similar_tags
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
    
    user_tags = db.query(database.Tag).filter(
        database.Tag.user_id == current_user.id
    ).all()
    
    if not user_tags:
        return []
    
    existing_normalized = [t.normalized_name or normalize_tag_name(t.name) for t in user_tags]
    
    similar = find_similar_tags(normalized_query, existing_normalized, threshold=0.6, limit=5)
    
    similar_normalized = {name for name, score in similar}
    
    results = []
    for tag in user_tags:
        tag_normalized = tag.normalized_name or normalize_tag_name(tag.name)
        if tag_normalized == normalized_query:
            results.insert(0, ArticleTagResponse(id=tag.id, name=tag.name))
        elif tag_normalized in similar_normalized:
            results.append(ArticleTagResponse(id=tag.id, name=tag.name))
    
    return results[:5]