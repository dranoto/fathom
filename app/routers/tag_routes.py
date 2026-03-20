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
    query_words = normalized_query.split()
    
    feed_source_ids = db.query(database.UserFeedSubscription.feed_source_id).filter(
        database.UserFeedSubscription.user_id == current_user.id
    ).all()
    feed_source_id_set = {f[0] for f in feed_source_ids}
    
    deleted_article_ids = set()
    deleted_result = db.query(database.UserArticleState.article_id).filter(
        database.UserArticleState.user_id == current_user.id,
        database.UserArticleState.is_deleted == True
    ).all()
    deleted_article_ids = {r[0] for r in deleted_result}
    
    user_tags = db.query(database.Tag).filter(
        database.Tag.user_id == current_user.id
    ).all()
    
    if not user_tags:
        return []
    
    def tag_has_active_article(tag_id):
        articles_with_tag = db.query(
            database.article_tag_association.c.article_id
        ).join(
            database.Article,
            database.article_tag_association.c.article_id == database.Article.id
        ).filter(
            database.article_tag_association.c.user_id == current_user.id,
            database.article_tag_association.c.tag_id == tag_id,
            database.Article.feed_source_id.in_(feed_source_id_set)
        ).all()
        
        for (article_id,) in articles_with_tag:
            if article_id not in deleted_article_ids:
                return True
        return False
    
    exact_matches = []
    starts_with_matches = []
    substring_matches = []
    word_prefix_matches = []
    fuzzy_matches = []
    
    def word_prefix_match(query_words_list, tag_words_set):
        if not query_words_list:
            return False
        return all(
            any(qw == tw or tw.startswith(qw) or qw.startswith(tw) for tw in tag_words_set)
            for qw in query_words_list if len(qw) >= 2
        )
    
    for tag in user_tags:
        if not tag_has_active_article(tag.id):
            continue
            
        tag_normalized = tag.normalized_name or normalize_tag_name(tag.name)
        tag_words = tag_normalized.split()
        tag_words_set = set(tag_words)
        
        if tag_normalized == normalized_query:
            exact_matches.append((tag, 1.0))
        elif tag_normalized.startswith(normalized_query):
            starts_with_matches.append((tag, 1.0 + len(normalized_query) / len(tag_normalized)))
        elif normalized_query in tag_normalized:
            substring_matches.append((tag, len(normalized_query) / len(tag_normalized)))
        elif len(normalized_query) >= 3 and word_prefix_match(query_words, tag_words_set):
            word_prefix_matches.append((tag, 0.9))
        else:
            score = get_normalized_similarity(normalized_query, tag_normalized)
            if score >= 0.5:
                fuzzy_matches.append((tag, score))
    
    starts_with_matches.sort(key=lambda x: x[1], reverse=True)
    substring_matches.sort(key=lambda x: x[1], reverse=True)
    word_prefix_matches.sort(key=lambda x: x[1], reverse=True)
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
    for tag, score in word_prefix_matches:
        if len(results) < 10:
            results.append(ArticleTagResponse(id=tag.id, name=tag.name))
    for tag, score in fuzzy_matches:
        if len(results) < 10:
            results.append(ArticleTagResponse(id=tag.id, name=tag.name))
    
    return results[:10]