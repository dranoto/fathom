# app/config.py
import os
from dotenv import load_dotenv
import json

load_dotenv() # Load environment variables from .env file

# --- Database Configuration ---
SQLITE_DB_SUBDIR = "data"
SQLITE_DB_FILE = "newsai.db"
SETTINGS_DB_FILE = "settings.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///./{SQLITE_DB_SUBDIR}/{SQLITE_DB_FILE}")
SETTINGS_DATABASE_URL = os.getenv("SETTINGS_DATABASE_URL", f"sqlite:///./{SQLITE_DB_SUBDIR}/{SETTINGS_DB_FILE}")

# --- LLM Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_SUMMARY_MODEL_NAME = os.getenv("DEFAULT_SUMMARY_MODEL_NAME", "gpt-4o-mini")
DEFAULT_CHAT_MODEL_NAME = os.getenv("DEFAULT_CHAT_MODEL_NAME", "gpt-4o-mini")
DEFAULT_TAG_MODEL_NAME = os.getenv("DEFAULT_TAG_MODEL_NAME", "gpt-4o-mini")

# Max output tokens for different LLM tasks
SUMMARY_MAX_OUTPUT_TOKENS = int(os.getenv("SUMMARY_MAX_OUTPUT_TOKENS", 1024))
CHAT_MAX_OUTPUT_TOKENS = int(os.getenv("CHAT_MAX_OUTPUT_TOKENS", 4096))
TAG_MAX_OUTPUT_TOKENS = int(os.getenv("TAG_MAX_OUTPUT_TOKENS", 100))

# --- RSS Feed Configuration ---
rss_feeds_env_str = os.getenv("RSS_FEED_URLS", "")
if rss_feeds_env_str.strip().startswith("[") and rss_feeds_env_str.strip().endswith("]"):
    try:
        RSS_FEED_URLS = json.loads(rss_feeds_env_str)
        if not isinstance(RSS_FEED_URLS, list):
            print("Warning: RSS_FEED_URLS from .env (JSON) did not parse as a list. Falling back.")
            RSS_FEED_URLS = []
    except json.JSONDecodeError:
        print(f"Warning: RSS_FEED_URLS in .env ('{rss_feeds_env_str}') is not valid JSON. Falling back to empty list.")
        RSS_FEED_URLS = []
elif rss_feeds_env_str:
    RSS_FEED_URLS = [url.strip() for url in rss_feeds_env_str.split(',') if url.strip()]
else:
    RSS_FEED_URLS = []

# --- Application Behavior Defaults ---
try:
    DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", 6))
except ValueError:
    print("Warning: Invalid DEFAULT_PAGE_SIZE in .env. Using default 6.")
    DEFAULT_PAGE_SIZE = 6

try:
    MAX_ARTICLES_PER_INDIVIDUAL_FEED = int(os.getenv("MAX_ARTICLES_PER_INDIVIDUAL_FEED", 15))
except ValueError:
    print("Warning: Invalid MAX_ARTICLES_PER_INDIVIDUAL_FEED in .env. Using default 15.")
    MAX_ARTICLES_PER_INDIVIDUAL_FEED = 15

try:
    DEFAULT_RSS_FETCH_INTERVAL_MINUTES = int(os.getenv("DEFAULT_RSS_FETCH_INTERVAL_MINUTES", 60))
except ValueError:
    print("Warning: Invalid DEFAULT_RSS_FETCH_INTERVAL_MINUTES in .env. Using default 60.")
    DEFAULT_RSS_FETCH_INTERVAL_MINUTES = 60


# --- Scraper Configuration ---
USER_AGENT = os.getenv("PLAYWRIGHT_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))

# --- Playwright specific settings ---
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "60000"))
PLAYWRIGHT_PAGE_WAIT_MS = int(os.getenv("PLAYWRIGHT_PAGE_WAIT_MS", "3000"))
SCRAPE_REQUEST_DELAY_SEC = int(os.getenv("SCRAPE_REQUEST_DELAY_SEC", "1"))

# Path to the browser extension directory
# Auto-detect: Docker (/app/scraper_assistant) if exists, otherwise local project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_docker_extension_path = "/app/scraper_assistant"
_local_extension_path = os.path.join(PROJECT_ROOT, "scraper_assistant")

if os.getenv("PATH_TO_EXTENSION"):
    PATH_TO_EXTENSION = os.getenv("PATH_TO_EXTENSION")
elif os.path.isdir(_docker_extension_path):
    PATH_TO_EXTENSION = _docker_extension_path
else:
    PATH_TO_EXTENSION = _local_extension_path
# Whether to run the Playwright browser in headless mode
USE_HEADLESS_BROWSER = os.getenv("USE_HEADLESS_BROWSER", "True").lower() in ('true', '1', 't')

# --- Content Threshold ---
DEFAULT_MINIMUM_WORD_COUNT = int(os.getenv("DEFAULT_MINIMUM_WORD_COUNT", "100"))

# --- LLM Temperature Configuration ---
SUMMARY_LLM_TEMPERATURE = float(os.getenv("SUMMARY_LLM_TEMPERATURE", "0.2"))
CHAT_LLM_TEMPERATURE = float(os.getenv("CHAT_LLM_TEMPERATURE", "0.5"))
TAG_LLM_TEMPERATURE = float(os.getenv("TAG_LLM_TEMPERATURE", "0.1"))

# --- Debug Configuration ---
# Options: minimal, standard, verbose, trace
DEBUG_LEVEL = os.getenv("DEBUG_LEVEL", "standard").lower()
DEBUG_LEVELS = {"minimal": 0, "standard": 1, "verbose": 2, "trace": 3}

def is_debug_level(level_name: str) -> bool:
    return DEBUG_LEVELS.get(DEBUG_LEVEL, 1) >= DEBUG_LEVELS.get(level_name, 0)


# --- Default AI Prompts ---
DEFAULT_SUMMARY_PROMPT = os.getenv("DEFAULT_SUMMARY_PROMPT", """Task:Generate a concise, narrative summary of the following article. The output must be Markdown-formatted and meticulously optimized for scannability, readability, and minimal cognitive load. (Note: The article title will be provided separately).
Format & Content:

Key Takeaways (1-3 Labeled Bullets):
Present the most critical facts using * bullets.
Prefix each bullet with a bold semantic label (choose from: Who:, What:, Where:, When:, Why:, How:, Impact:, Context:, Next: - use the most relevant 1-3 labels).
Keep the bullet text concise (max 10-15 words).
Use bold Markdown on the most crucial 1-3 words within the bullet text itself.
Example: * **Impact:** This **challenges existing models**.
Narrative Context (3-5 Sentences):
Follow with a single, coherent paragraph.
The first sentence must immediately set the scene or state the primary significance.
This paragraph must connect the key takeaways, providing narrative flow, context, or deeper meaning.
It must build upon, not just repeat, the bullets by explaining how events unfolded or why they matter.
Use italics sparingly for emphasis if needed.
Style & Principles:

Clarity: Use active voice, strong verbs, and simple, direct language. Avoid or explain jargon.
Structure: Ensure short sentences and the defined format enhance scannability.
Markdown: Use **bold** and *italics* strategically to guide the eye, not overwhelm it.
Storytelling: Weave a clear, engaging narrative within the paragraph.
Tone: Maintain an objective, professional, yet compelling tone.

Article:{text}
Summary:""")

DEFAULT_CHAT_PROMPT = os.getenv("DEFAULT_CHAT_PROMPT", """Persona & Goal:You are an insightful AI analyst and conversational partner. Your purpose is to help the user explore the provided article's content in greater depth, moving beyond the initial summary. Aim to provide rich, multi-faceted answers that synthesize information, offer context, and encourage further thought.
Context:The user has likely seen a concise V5 summary and is now asking a specific question ({question}) about the article ({article_text}). They are looking for more than just a surface-level answer.
Instructions for Answering:
Ground in the Article: Base your core answer firmly on the provided {article_text}. Reference or quote specific points where it adds clarity. If the article doesn't cover the question, state so explicitly.
Synthesize & Enrich: Go beyond simple extraction. Connect ideas within the article and enrich the answer with relevant general knowledge.
Integrate Perspectives (Where Appropriate): Add significant value by briefly incorporating insights or analytical lenses from fields such as:Psychology/Behavior: (e.g., Why might people react this way? What biases could be at play?)
Neurology/Cognition: (e.g., How might this information be processed? Are there cognitive implications?)
Systems Thinking: (e.g., How does this fit into a larger system? What are the feedback loops?)
Leadership/Strategy: (e.g., What are the strategic implications or leadership lessons?)
(Use these lenses judiciously, only when they genuinely add relevant depth to the specific question asked).
Structure for Clarity: Present your answer clearly. Use Markdown (like **bolding** for key terms or * bullet points for lists) to enhance readability and minimize cognitive load.
Maintain Tone: Respond in a professional, objective, yet supportive and conversational tone.
Encourage Dialogue: Crucially, end your response by inviting further interaction. Ask a follow-up question, suggest a related area to explore, or check if your answer fully addressed their need. (e.g., "Does that help clarify the issue, or would you be interested in how this compares to X?" or "What are your thoughts on that particular aspect?")
Input:Article:{article_text}
Question: {question}
Answer:""")

CHAT_NO_ARTICLE_PROMPT = os.getenv("CHAT_NO_ARTICLE_PROMPT", """You are a helpful AI assistant. The user is asking a question, but unfortunately, the content of the article could not be loaded.
Politely inform the user that you cannot answer their question without the article content.

User's Question: {question}

Response:""")

DEFAULT_TAG_GENERATION_PROMPT = os.getenv("DEFAULT_TAG_GENERATION_PROMPT", """Given the following article text, generate a list of 3-5 relevant keywords or tags.
These tags should capture the main topics, entities, or themes of the article.
Return the tags as a comma-separated list. For example: "Technology,Artificial Intelligence,Startups,Venture Capital,Innovation"

Article:
{text}

Tags:""")


DEFAULT_MAJOR_SUMMARY_PROMPT = os.getenv("DEFAULT_MAJOR_SUMMARY_PROMPT", """Given a collection of articles about {event_name}, analyze them and return a JSON response with three subsections:

Return EXACTLY this JSON structure (no markdown, no extra text):
{{
  "timeline_narrative": "Chronological narrative of key developments, organized by date. Highlight the most significant moments.",
  "cross_source_synthesis": "How do different sources cover this story differently? Note any conflicting angles, unique insights from specific outlets, or notable patterns in coverage.",
  "progressive_summary": "What is NEW since the last summary (or if no previous summary, what are the most recent developments)? Focus on what the user most needs to know right now.",
  "article_count": <total number of articles analyzed>,
  "feed_count": <number of unique feeds>,
  "date_range": "<earliest date> - <latest date>",
  "key_developments": ["Milestone 1", "Milestone 2", "Milestone 3"]
}}

Articles to analyze:
{article_texts}

Return the JSON now:""")


if not OPENAI_API_KEY:
    print("WARNING: OPENAI_API_KEY environment variable is not set. LLM features will be impaired.")

print(f"CONFIG LOADED: DATABASE_URL: {DATABASE_URL}")
print(f"CONFIG LOADED: OPENAI_API_KEY Set: {'Yes' if OPENAI_API_KEY else 'NO'}")
print(f"CONFIG LOADED: OPENAI_BASE_URL: {OPENAI_BASE_URL}")
print(f"CONFIG LOADED: DEFAULT_SUMMARY_MODEL_NAME: {DEFAULT_SUMMARY_MODEL_NAME}")
print(f"CONFIG LOADED: DEFAULT_CHAT_MODEL_NAME: {DEFAULT_CHAT_MODEL_NAME}")
print(f"CONFIG LOADED: DEFAULT_TAG_MODEL_NAME: {DEFAULT_TAG_MODEL_NAME}")
print(f"CONFIG LOADED: SUMMARY_MAX_OUTPUT_TOKENS: {SUMMARY_MAX_OUTPUT_TOKENS}")
print(f"CONFIG LOADED: CHAT_MAX_OUTPUT_TOKENS: {CHAT_MAX_OUTPUT_TOKENS}")
print(f"CONFIG LOADED: TAG_MAX_OUTPUT_TOKENS: {TAG_MAX_OUTPUT_TOKENS}")
print(f"CONFIG LOADED: SUMMARY_LLM_TEMPERATURE: {SUMMARY_LLM_TEMPERATURE}")
print(f"CONFIG LOADED: CHAT_LLM_TEMPERATURE: {CHAT_LLM_TEMPERATURE}")
print(f"CONFIG LOADED: TAG_LLM_TEMPERATURE: {TAG_LLM_TEMPERATURE}")
print(f"CONFIG LOADED: RSS_FEED_URLS count: {len(RSS_FEED_URLS)}")
print(f"CONFIG LOADED: DEFAULT_PAGE_SIZE: {DEFAULT_PAGE_SIZE}")
print(f"CONFIG LOADED: MAX_ARTICLES_PER_INDIVIDUAL_FEED: {MAX_ARTICLES_PER_INDIVIDUAL_FEED}")
print(f"CONFIG LOADED: DEFAULT_RSS_FETCH_INTERVAL_MINUTES: {DEFAULT_RSS_FETCH_INTERVAL_MINUTES}")
print(f"CONFIG LOADED: DEFAULT_MINIMUM_WORD_COUNT: {DEFAULT_MINIMUM_WORD_COUNT}")
print(f"CONFIG LOADED: PLAYWRIGHT_TIMEOUT: {PLAYWRIGHT_TIMEOUT}")
print(f"CONFIG LOADED: PLAYWRIGHT_PAGE_WAIT_MS: {PLAYWRIGHT_PAGE_WAIT_MS}")
print(f"CONFIG LOADED: SCRAPE_REQUEST_DELAY_SEC: {SCRAPE_REQUEST_DELAY_SEC}")
print(f"CONFIG LOADED: REQUEST_TIMEOUT: {REQUEST_TIMEOUT}")
print(f"CONFIG LOADED: USE_HEADLESS_BROWSER: {USE_HEADLESS_BROWSER}")
print(f"CONFIG LOADED: DEBUG_LEVEL: {DEBUG_LEVEL}")
