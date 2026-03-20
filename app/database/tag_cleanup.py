# app/database/tag_cleanup.py
import logging
import re
import sys
from difflib import SequenceMatcher
from sqlalchemy import text

from .models import engine

logger = logging.getLogger(__name__)

DEFAULT_MERGE_THRESHOLD = 0.75


def normalize_tag_name(tag_name: str) -> str:
    if not tag_name:
        return ""
    normalized = tag_name.strip().lower()
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


def get_similarity(str1: str, str2: str) -> float:
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1, str2).ratio()


def find_similar_tag_pairs(tags, threshold: float):
    pairs = []
    n = len(tags)
    for i in range(n):
        for j in range(i + 1, n):
            sim = get_similarity(tags[i]['normalized'], tags[j]['normalized'])
            if sim >= threshold:
                pairs.append((tags[i], tags[j], sim))
    return pairs


def merge_similar_tags(connection, user_id: int, threshold: float):
    logger.info(f"Starting tag cleanup for user {user_id} with threshold {threshold}")
    
    result = connection.execute(
        text("SELECT id, name, normalized_name FROM tags WHERE user_id = :uid"),
        {"uid": user_id}
    )
    all_tags = [{'id': row[0], 'name': row[1], 'normalized': row[2] or normalize_tag_name(row[1])} for row in result.fetchall()]
    logger.info(f"Found {len(all_tags)} tags for user {user_id}")
    
    if not all_tags:
        return {"merged": [], "deleted": []}
    
    pairs = find_similar_tag_pairs(all_tags, threshold)
    logger.info(f"Found {len(pairs)} similar tag pairs")
    
    for tag1, tag2, sim in pairs:
        logger.info(f"Similar pair: '{tag1['name']}' <-> '{tag2['name']}' (similarity: {sim:.2f})")
    
    merged_tags = set()
    deleted_tag_ids = []
    merge_log = []
    
    for tag1, tag2, sim in pairs:
        if tag1['id'] in merged_tags or tag2['id'] in merged_tags:
            continue
        
        keep = max([tag1, tag2], key=lambda t: len(t['name']))
        discard = tag1 if keep == tag2 else tag2
        
        logger.info(f"Merging '{discard['name']}' (id={discard['id']}) into '{keep['name']}' (id={keep['id']})")
        
        connection.execute(
            text("""
                UPDATE article_tag_association 
                SET tag_id = :keep_id 
                WHERE user_id = :uid AND tag_id = :discard_id
            """),
            {"keep_id": keep['id'], "uid": user_id, "discard_id": discard['id']}
        )
        
        connection.execute(
            text("DELETE FROM tags WHERE id = :id AND user_id = :uid"),
            {"id": discard['id'], "uid": user_id}
        )
        
        merged_tags.add(keep['id'])
        merged_tags.add(discard['id'])
        deleted_tag_ids.append(discard['id'])
        merge_log.append({
            "kept": {"id": keep['id'], "name": keep['name']},
            "discarded": {"id": discard['id'], "name": discard['name']},
            "similarity": sim
        })
        logger.info(f"Successfully merged and deleted tag {discard['id']}")
    
    return {"merged": merge_log, "deleted": deleted_tag_ids}


def run_tag_cleanup(threshold: float = DEFAULT_MERGE_THRESHOLD):
    logger.info("=" * 60)
    logger.info("TAG CLEANUP: Starting one-time tag cleanup migration")
    logger.info(f"Threshold: {threshold}")
    logger.info("=" * 60)
    
    total_merged = 0
    total_deleted = 0
    
    with engine.begin() as connection:
        result = connection.execute(text("SELECT DISTINCT user_id FROM tags"))
        user_ids = [row[0] for row in result.fetchall()]
        
        for user_id in user_ids:
            result = merge_similar_tags(connection, user_id, threshold)
            total_merged += len(result['merged'])
            total_deleted += len(result['deleted'])
            logger.info(f"User {user_id}: merged {len(result['merged'])} pairs, deleted {len(result['deleted'])} tags")
    
    logger.info("=" * 60)
    logger.info(f"TAG CLEANUP: Complete. Total merged: {total_merged}, deleted: {total_deleted}")
    logger.info("=" * 60)
    
    return {"total_merged": total_merged, "total_deleted": total_deleted}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    threshold = DEFAULT_MERGE_THRESHOLD
    if len(sys.argv) > 1:
        try:
            threshold = float(sys.argv[1])
        except ValueError:
            logger.error(f"Invalid threshold: {sys.argv[1]}")
            sys.exit(1)
    
    run_tag_cleanup(threshold)
