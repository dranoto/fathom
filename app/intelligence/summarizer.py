# app/intelligence/summarizer.py
import json
import logging
from typing import List, Dict, Any, Optional
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app import config as app_config, settings_database

logger = logging.getLogger(__name__)


def build_major_summary_prompt(
    event_name: str, 
    article_texts: str, 
    prompt_template: str,
    prior_summary_json: Optional[Dict[str, Any]] = None
) -> str:
    if prior_summary_json:
        prompt_template = prompt_template + "\n\nAlso consider this previous summary for the progressive_summary section:\n" + json.dumps(prior_summary_json, indent=2)
    
    return prompt_template.format(
        event_name=event_name,
        article_texts=article_texts
    )


def parse_major_summary_response(response_content: str) -> Dict[str, Any]:
    try:
        response_content = response_content.strip()
        if response_content.startswith("```json"):
            response_content = response_content[7:]
        if response_content.startswith("```"):
            response_content = response_content[3:]
        if response_content.endswith("```"):
            response_content = response_content[:-3]
        
        response_content = response_content.strip()
        
        return json.loads(response_content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse major summary JSON: {e}. Content: {response_content[:500]}")
        raise ValueError(f"Failed to parse summary response as JSON: {e}")


async def generate_major_summary(
    event_name: str,
    articles: List[Dict[str, Any]],
    prompt_template: str,
    prior_summary_json: Optional[Dict[str, Any]] = None,
    llm: Optional[ChatOpenAI] = None
) -> Dict[str, Any]:
    if not llm:
        raise RuntimeError("Summary LLM not available")
    
    article_texts_parts = []
    seen_urls = set()
    
    for article in articles:
        url = article.get("url", "Unknown URL")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        title = article.get("title", "Untitled")
        publisher = article.get("publisher_name", "Unknown Source")
        published_date = article.get("published_date", "Unknown Date")
        content = article.get("scraped_text_content", article.get("rss_description", "No content available"))
        
        if content:
            excerpt = content[:2000] + "..." if len(content) > 2000 else content
        else:
            excerpt = "No content available"
        
        article_texts_parts.append(
            f"--- Article ---\nTitle: {title}\nSource: {publisher} ({published_date})\nURL: {url}\nContent: {excerpt}\n"
        )
    
    article_texts = "\n".join(article_texts_parts)
    
    prompt = build_major_summary_prompt(event_name, article_texts, prompt_template, prior_summary_json)
    
    try:
        response = await llm.agenerate([[HumanMessage(content=prompt)]])
        response_content = response.generations[0][0].text
        
        summary_data = parse_major_summary_response(response_content)
        
        if prior_summary_json and "progressive_summary" in summary_data:
            summary_data["progressive_summary"] = f"(Updates based on new articles) {summary_data['progressive_summary']}"
        
        return summary_data
        
    except Exception as e:
        logger.error(f"Error generating major summary for event '{event_name}': {e}", exc_info=True)
        raise
