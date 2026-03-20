# app/summarizer.py
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from typing import Optional, List, Dict
from . import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SummarizationError(Exception):
    """Custom exception for errors during summarization."""
    pass

def initialize_llm(
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float = 0.3,
    max_tokens: int = 1024
):
    """
    Initializes a ChatOpenAI LLM instance for OpenAI-compatible endpoints.
    """
    try:
        llm = ChatOpenAI(
            model=model_name,
            openai_api_key=api_key,  # type: ignore - LangChain accepts via kwargs
            openai_api_base=base_url,  # type: ignore - LangChain accepts via kwargs
            temperature=temperature,
            max_tokens=max_tokens,  # type: ignore - LangChain accepts via kwargs
        )
        logger.info(f"Successfully initialized LLM: {model_name} at {base_url} with max_tokens: {max_tokens}")
        return llm
    except Exception as e:
        logger.error(f"Error initializing LLM {model_name}: {e}")
        return None

def get_summarization_prompt_template(custom_prompt_str: Optional[str] = None) -> PromptTemplate:
    """
    Returns the PromptTemplate for summarization.
    Uses custom_prompt_str if provided and valid, otherwise defaults to config.DEFAULT_SUMMARY_PROMPT.
    """
    template_str = custom_prompt_str if custom_prompt_str and "{text}" in custom_prompt_str else config.DEFAULT_SUMMARY_PROMPT
    if custom_prompt_str and "{text}" not in custom_prompt_str:
        logger.warning(f"Custom summary prompt was provided but is missing '{{text}}' placeholder. Using default prompt.")
        
    return PromptTemplate(template=template_str, input_variables=["text"])

async def summarize_document_content(
    doc: Document,
    llm_instance: ChatOpenAI,
    custom_prompt_str: Optional[str] = None
) -> str:
    """
    Summarizes the content of a Document using the provided LLM instance.
    If plain text content (doc.page_content) is too short, 
    it attempts to use HTML content from doc.metadata.get('full_html_content').
    """
    if not llm_instance:
        logger.error("Summarization LLM not available.")
        raise SummarizationError("Summarization LLM not available.")

    current_content_to_summarize = doc.page_content
    content_source_description = "plain text"
    MIN_CONTENT_LENGTH = 50

    if not current_content_to_summarize or len(current_content_to_summarize.strip()) < MIN_CONTENT_LENGTH:
        plain_text_len = len(current_content_to_summarize.strip()) if current_content_to_summarize else 0
        logger.info(
            f"Plain text content from '{doc.metadata.get('source', 'Unknown')}' is too short "
            f"(length: {plain_text_len}). "
            f"Attempting to use HTML content."
        )
        html_content = doc.metadata.get('full_html_content')
        
        if html_content and len(html_content.strip()) >= MIN_CONTENT_LENGTH:
            current_content_to_summarize = html_content
            content_source_description = "HTML"
            logger.info(
                f"Using HTML content for '{doc.metadata.get('source', 'Unknown')}' for summarization. "
                f"HTML length: {len(current_content_to_summarize.strip())}."
            )
        else:
            plain_len = len(doc.page_content.strip()) if doc.page_content else 0
            html_len = len(html_content.strip()) if html_content else 0
            logger.warning(
                f"HTML content for '{doc.metadata.get('source', 'Unknown')}' is also too short or unavailable. "
                f"Plain text length: {plain_len}, "
                f"HTML length: {html_len}."
            )
            
    if not current_content_to_summarize or len(current_content_to_summarize.strip()) < MIN_CONTENT_LENGTH:
        content_len = len(current_content_to_summarize.strip()) if current_content_to_summarize else 0
        logger.warning(
            f"Selected content ({content_source_description}) for '{doc.metadata.get('source', 'Unknown')}' "
            f"is still too short (length: {content_len}) or empty to summarize."
        )
        raise SummarizationError("Content too short or empty to summarize.")

    try:
        prompt_template = get_summarization_prompt_template(custom_prompt_str)
        
        logger.info(
            f"Attempting to summarize URL: {doc.metadata.get('source', 'Unknown URL')} "
            f"(using {content_source_description}, length: {len(current_content_to_summarize.strip())}) "
            f"with prompt: \"{prompt_template.template[:100]}...\""
        )
        
        chain = prompt_template | llm_instance | StrOutputParser()
        summary = await chain.ainvoke({"text": current_content_to_summarize})
        summary = summary.strip() if summary else ""

        if not summary:
            logger.warning(
                f"Empty summary received from LLM for URL: {doc.metadata.get('source', 'Unknown URL')} "
                f"(summarized from {content_source_description})."
            )
            raise SummarizationError("Summary generation resulted in empty output.")
        
        logger.info(
            f"Successfully summarized URL: {doc.metadata.get('source', 'Unknown URL')} "
            f"(from {content_source_description}). Summary length: {len(summary)}"
        )
        return summary
    except Exception as e:
        logger.error(
            f"ERROR during summarization for doc '{doc.metadata.get('source', 'Unknown URL')}' "
            f"(using {content_source_description}): {e}", exc_info=True
        )
        raise SummarizationError(f"Error generating summary: {str(e)}") from e

def get_tag_generation_prompt_template(custom_prompt_str: Optional[str] = None) -> PromptTemplate:
    """
    Returns the PromptTemplate for tag generation.
    Uses custom_prompt_str if provided and valid, otherwise defaults to config.DEFAULT_TAG_GENERATION_PROMPT.
    """
    template_str = custom_prompt_str if custom_prompt_str and "{text}" in custom_prompt_str else config.DEFAULT_TAG_GENERATION_PROMPT
    if custom_prompt_str and "{text}" not in custom_prompt_str:
        logger.warning(f"Custom tag generation prompt was provided but is missing '{{text}}' placeholder. Using default prompt.")
    return PromptTemplate(template=template_str, input_variables=["text"])

async def generate_tags_for_text(
    text_content: str,
    llm_instance: ChatOpenAI,
    custom_prompt_str: Optional[str] = None
) -> List[str]:
    """
    Generates a list of tags for the given text_content using the provided LLM instance.
    """
    if not llm_instance:
        logger.error("Error: Tag generation LLM not available.")
        return []
    if not text_content or len(text_content.strip()) < 20:
        logger.info(f"Content too short for tag generation. Length: {len(text_content.strip())}")
        return []

    try:
        prompt_template = get_tag_generation_prompt_template(custom_prompt_str)
        formatted_prompt = await prompt_template.aformat(text=text_content)
        
        logger.info(f"Attempting to generate tags with prompt (first 150 chars): \"{formatted_prompt[:150]}...\"")
        
        response_obj = await llm_instance.ainvoke(formatted_prompt)
        raw_content = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
        if isinstance(raw_content, list):
            raw_content = ' '.join(str(c) for c in raw_content)
        tags_string = raw_content.strip() if isinstance(raw_content, str) else str(raw_content)

        if not tags_string:
            logger.warning("Empty tag string received from LLM.")
            return []

        tags_list = [tag.strip() for tag in tags_string.split(',') if tag.strip()]
        
        logger.info(f"Successfully generated tags: {tags_list}. Raw string: '{tags_string}'")
        return tags_list
    except Exception as e:
        logger.error(f"ERROR during tag generation: {e}", exc_info=True)
        return []


async def get_chat_response(
    llm_instance: ChatOpenAI,
    article_text: str,
    question: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    custom_chat_prompt_str: Optional[str] = None
) -> str:
    """
    Generates a chat response based on article text, a question, and optional chat history.
    """
    if not llm_instance:
        return "Error: Chat LLM not available."

    history_str_parts = []
    if chat_history:
        for entry in chat_history:
            if isinstance(entry, dict):
                role = entry.get("role", "unknown").capitalize()
                content = entry.get("content", "")
            else:
                role = getattr(entry, "role", "unknown")
                if role:
                    role = role.capitalize()
                content = getattr(entry, "content", "") or ""
            history_str_parts.append(f"{role}: {content}")
    full_history_str = "\n".join(history_str_parts)

    base_prompt_template_str: str
    input_variables_for_template = ["question"]

    if not article_text or len(article_text.strip()) < 20:
        base_prompt_template_str = custom_chat_prompt_str if custom_chat_prompt_str and "{question}" in custom_chat_prompt_str else config.CHAT_NO_ARTICLE_PROMPT
        if "{question}" not in base_prompt_template_str:
            base_prompt_template_str = "I'm sorry, but the article content could not be loaded, so I cannot answer your question about it."
            input_variables_for_template = []
    else:
        if custom_chat_prompt_str:
            base_prompt_template_str = custom_chat_prompt_str
            if "{article_text}" in base_prompt_template_str and "{question}" in base_prompt_template_str:
                input_variables_for_template = ["article_text", "question"]
            elif "{question}" in base_prompt_template_str:
                input_variables_for_template = ["question"]
            else:
                logger.warning("Custom chat prompt is missing required placeholders ({article_text} and/or {question}). Using default.")
                base_prompt_template_str = config.DEFAULT_CHAT_PROMPT
                input_variables_for_template = ["article_text", "question"]
        else:
            base_prompt_template_str = config.DEFAULT_CHAT_PROMPT
            input_variables_for_template = ["article_text", "question"]

    final_prompt_parts = []
    try:
        current_prompt_text = base_prompt_template_str

        if not input_variables_for_template:
            final_prompt_parts.append(current_prompt_text)
        else:
            if "{article_text}" in current_prompt_text and "article_text" in input_variables_for_template:
                current_prompt_text = current_prompt_text.replace("{article_text}", article_text)
            
            question_placeholder = "{question}"
            if question_placeholder in current_prompt_text:
                parts = current_prompt_text.split(question_placeholder, 1)
                final_prompt_parts.append(parts[0])
                
                if full_history_str:
                    final_prompt_parts.append(full_history_str)
                    final_prompt_parts.append("\n")
                
                final_prompt_parts.append(f"User: {question}")
                
                if len(parts) > 1:
                    final_prompt_parts.append(parts[1])
                else:
                    final_prompt_parts.append("\nAI:")
            else:
                logger.warning("Chat prompt expected {question} placeholder but it was missing. Appending history and question to the formatted prompt.")
                final_prompt_parts.append(current_prompt_text)
                if full_history_str:
                    final_prompt_parts.append("\n" + full_history_str)
                final_prompt_parts.append(f"\nUser: {question}\nAI:")

    except Exception as e:
        logger.error(f"Error formatting chat prompt: {e}. Using basic fallback prompt with history.", exc_info=True)
        final_prompt_parts.append(f"Article: {article_text}\n")
        if full_history_str:
            final_prompt_parts.append(full_history_str + "\n")
        final_prompt_parts.append(f"User: {question}\nAI:")

    final_formatted_prompt = "".join(final_prompt_parts)

    logger.info(f"Attempting chat with final prompt (length: {len(final_formatted_prompt)}). First 200 chars: \"{final_formatted_prompt[:200]}...\"")

    try:
        response_obj = await llm_instance.ainvoke(final_formatted_prompt)
        raw_answer = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
        if isinstance(raw_answer, list):
            raw_answer = ' '.join(str(c) for c in raw_answer)
        answer = raw_answer.strip() if isinstance(raw_answer, str) else str(raw_answer)
        
        logger.info(f"Chat LLM returned answer (length: {len(answer)}). First 100 chars: '{answer[:100]}...'")
        if not answer:
            logger.warning("Empty answer received from chat LLM.")
            return "AI returned an empty answer."
        return answer
    except Exception as e:
        logger.error(f"ERROR getting answer from AI for chat: {e}", exc_info=True)
        return f"Error getting answer from AI: {str(e)}"
