# app/tag_utils.py
import re
import logging
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

FUZZY_MATCH_THRESHOLD = 0.80


def normalize_tag_name(tag_name: str) -> str:
    if not tag_name:
        return ""
    normalized = tag_name.strip().lower()
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


def get_normalized_similarity(str1: str, str2: str) -> float:
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1, str2).ratio()


def fuzzy_match_tag(
    normalized_input: str,
    existing_tags: List[str]
) -> Optional[str]:
    if not normalized_input or not existing_tags:
        return None
    
    best_match: Optional[str] = None
    best_score: float = 0.0
    
    for existing_tag in existing_tags:
        score = get_normalized_similarity(normalized_input, existing_tag)
        if score > best_score:
            best_score = score
            best_match = existing_tag
    
    if best_score >= FUZZY_MATCH_THRESHOLD:
        logger.info(f"Tag fuzzy match: '{normalized_input}' matched to '{best_match}' (score: {best_score:.2f})")
        return best_match
    
    return None


def find_similar_tags(
    normalized_input: str,
    existing_tags: List[str],
    threshold: float = FUZZY_MATCH_THRESHOLD,
    limit: int = 5
) -> List[Tuple[str, float]]:
    if not normalized_input or not existing_tags:
        return []
    
    scored: List[Tuple[str, float]] = []
    for existing_tag in existing_tags:
        score = get_normalized_similarity(normalized_input, existing_tag)
        if score >= threshold:
            scored.append((existing_tag, score))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def process_ai_tags_with_fuzzy_matching(
    raw_tags: List[str],
    existing_normalized_tags: List[str]
) -> List[str]:
    matched_tags: List[str] = []
    
    for raw_tag in raw_tags:
        normalized = normalize_tag_name(raw_tag)
        if not normalized:
            continue
        
        if normalized in existing_normalized_tags:
            matched_tags.append(normalized)
            continue
        
        fuzzy_match = fuzzy_match_tag(normalized, existing_normalized_tags)
        if fuzzy_match:
            matched_tags.append(fuzzy_match)
        else:
            matched_tags.append(normalized)
    
    return matched_tags