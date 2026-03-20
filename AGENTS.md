# AGENTS.md - AI News Today Development Guide

## Project Overview

**AI News Today** is a self-hostable, AI-powered news aggregator and summarizer built with:
- **Backend**: Python 3.11, FastAPI, Uvicorn, SQLAlchemy
- **AI**: Google Gemini (via LangChain)
- **Database**: SQLite (articles, settings)
- **Frontend**: Vanilla JavaScript (ESM), HTML5, CSS3
- **Web Scraping**: Playwright, BeautifulSoup4

---

## Build & Run Commands

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (from project root)
uvicorn app.main_api:app --host 0.0.0.0 --port 9000 --reload

# Install Playwright browsers (required for scraping)
playwright install chromium
```

### Docker

```bash
# Build and run
docker build -t ai-news-today . && docker run -p 9000:9000 --rm \
  --name ai-news-today-container \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  ai-news-today
```

### Running with Virtual Environment

```bash
# Activate venv
source .venv/bin/activate

# Run uvicorn
uvicorn app.main_api:app --host 0.0.0.0 --port 9000 --reload
```

---

## Testing

**There is currently no formal test framework configured.**

If adding tests, use `pytest`:

```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/test_article_routes.py

# Run tests matching a pattern
pytest -k "article"

# Run with coverage
pytest --cov=app --cov-report=html
```

Manual API testing is available at `http://localhost:9000/docs` (Swagger UI).

---

## Code Style Guidelines

### Python (Backend)

#### Imports
Organize imports in three sections with blank lines between:
1. Standard library (`datetime`, `logging`, `typing`)
2. Third-party (`fastapi`, `sqlalchemy`, `langchain`)
3. Local application (`.routers`, `.database`, `.config`)

```python
# Standard library
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict

# Third-party
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session

# Local application
from . import database, config
from .routers import article_routes, feed_routes
```

#### Type Hints
Use type hints for all function parameters and return values:

```python
# Good
def get_article_by_id(db: Session, article_id: int) -> Optional[Article]:
    ...

async def summarize_document_content(
    doc: Document,
    llm_instance: ChatOpenAI,
    custom_prompt_str: Optional[str] = None
) -> str:
    ...
```

#### Naming Conventions
- **Functions/variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore`

```python
# Variables and functions
article_id: int
fetch_interval_minutes: int
llm_summary_instance_global: ChatOpenAI | None

# Classes
class RSSFeedSource(Base):
class Article(Base):
class SummarizationError(Exception):

# Constants
DATABASE_URL = "sqlite:///./data/newsai.db"
DEFAULT_PAGE_SIZE = 6
```

#### Error Handling
- Use specific exception types when possible
- Always log errors with context using `exc_info=True` for stack traces
- Chain exceptions using `from e` when re-raising

```python
# Good - specific exception with logging
try:
    database.create_db_and_tables()
except Exception as e:
    logger.critical(f"CRITICAL ERROR during database initialization: {e}", exc_info=True)
    raise

# Good - custom exceptions with chaining
except Exception as e:
    logger.error(f"Error generating summary: {str(e)}", exc_info=True)
    raise SummarizationError(f"Error generating summary: {str(e)}") from e

# Good - graceful degradation
if not llm_instance:
    logger.error("Summarization LLM not available.")
    raise SummarizationError("Summarization LLM not available.")
```

#### Logging
Use `logging` module with `logger = logging.getLogger(__name__)`:

```python
import logging

logger = logging.getLogger(__name__)

# Log levels: debug, info, warning, error, critical
logger.info(f"MAIN_API: Application startup sequence initiated...")
logger.warning(f"Invalid 'rss_fetch_interval_minutes' in settings DB")
logger.error(f"MAIN_API: Error mounting static files: {e}", exc_info=True)
```

#### Database Patterns
Use context managers for database sessions:

```python
@contextmanager
def db_session_scope() -> Generator[SQLAlchemySession, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# Usage
with database.db_session_scope() as db:
    rss_client.add_initial_feeds_to_db(db, app_config.RSS_FEED_URLS)
```

#### SQLAlchemy Models
Use declarative base and relationship patterns:

```python
Base = declarative_base()

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True)
    url = Column(String, unique=True, index=True, nullable=False)

    feed_source = relationship("RSSFeedSource", back_populates="articles")
    summaries = relationship("Summary", back_populates="article", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Article(id={self.id}, title='{self.title[:50] if self.title else ''}...')>"
```

#### Pydantic Schemas
Use `from_attributes = True` for ORM compatibility:

```python
class ArticleResult(BaseModel):
    id: int
    title: Optional[str] = None
    url: str
    tags: List[ArticleTagResponse] = []

    class Config:
        from_attributes = True
```

#### Docstrings
Include docstrings for public functions and complex logic:

```python
async def summarize_document_content(
    doc: Document,
    llm_instance: ChatOpenAI,
    custom_prompt_str: Optional[str] = None
) -> str:
    """
    Summarizes the content of a Document using the provided LLM instance.
    If plain text content is too short, attempts to use HTML content.
    """
    ...
```

---

### JavaScript (Frontend)

#### ES Modules
Use ES module imports/exports:

```javascript
// Imports
import * as state from './js/state.js';
import { fetchNewsSummaries } from './js/apiService.js';

// Exports
export function updateUI(articles) { ... }
export const POLLING_INTERVAL_MS = 120000;
```

#### Naming
- **Variables/functions**: `camelCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Classes**: `PascalCase` (rarely used)

```javascript
const POLLING_INTERVAL_MS = 120000;
let pollingIntervalId = null;

function fetchAndDisplaySummaries() { ... }
```

#### Async/Await
Prefer `async/await` over raw Promises:

```javascript
async function fetchAndDisplaySummaries(forceBackendRssRefresh = false) {
    try {
        const data = await apiService.fetchNewsSummaries(payload);
        uiManager.displayArticleResults(data.processed_articles_on_page);
    } catch (error) {
        console.error('Error fetching summaries:', error);
    }
}
```

---

## Project Structure

```
/home/thankfulcarp/fathom/
├── app/
│   ├── __init__.py
│   ├── main_api.py          # FastAPI app entry point
│   ├── config.py            # Environment configuration
│   ├── database/            # SQLAlchemy models & migrations
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── migrations.py
│   ├── schemas.py           # Pydantic models
│   ├── dependencies.py      # FastAPI dependencies
│   ├── scraper.py           # Web scraping logic
│   ├── summarizer.py        # LLM summarization
│   ├── rss_client.py        # RSS feed handling
│   ├── tasks.py             # Background tasks (APScheduler)
│   ├── settings_database.py # Settings DB operations
│   ├── security.py          # Auth helpers
│   ├── sanitizer.py         # HTML sanitization
│   └── routers/             # API route handlers
│       ├── article_routes.py
│       ├── article_helpers.py
│       ├── feed_routes.py    # Admin-only feed management
│       ├── user_routes.py    # User feed subscriptions
│       ├── chat_routes.py
│       ├── config_routes.py
│       ├── content_routes.py
│       ├── auth_routes.py
│       └── debug_routes.py
├── frontend/
│   ├── index.html
│   ├── admin.html           # Admin panel
│   ├── script.js
│   ├── css/
│   └── js/                  # ES modules
│       ├── state.js
│       ├── apiService.js
│       ├── feedHandler.js
│       ├── uiManager.js
│       ├── configManager.js
│       └── debugManager.js
├── scraper_assistant/        # Chrome extension (gitignored)
├── requirements.txt
├── Dockerfile
├── AGENTS.md
└── .env                      # Environment variables (gitignored)
```

---

## Environment Variables

```env
# Required
GEMINI_API_KEY=your_api_key_here

# Optional
DATABASE_URL=sqlite:///./data/newsai.db
SETTINGS_DATABASE_URL=sqlite:///./data/settings.db
OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_SUMMARY_MODEL_NAME=gpt-4o-mini
DEFAULT_CHAT_MODEL_NAME=gpt-4o-mini
DEFAULT_TAG_MODEL_NAME=gpt-4o-mini
RSS_FEED_URLS=https://feed1.com,https://feed2.com
DEFAULT_PAGE_SIZE=6
MAX_ARTICLES_PER_INDIVIDUAL_FEED=15
DEFAULT_RSS_FETCH_INTERVAL_MINUTES=60
PLAYWRIGHT_TIMEOUT=60000
PLAYWRIGHT_PAGE_WAIT_MS=3000
SCRAPE_REQUEST_DELAY_SEC=1
REQUEST_TIMEOUT=10
PLAYWRIGHT_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
SUMMARY_LLM_TEMPERATURE=0.2
CHAT_LLM_TEMPERATURE=0.5
TAG_LLM_TEMPERATURE=0.1
DEFAULT_MINIMUM_WORD_COUNT=100
USE_HEADLESS_BROWSER=True
PATH_TO_EXTENSION=/app/scraper_assistant
DEBUG_LEVEL=standard
```

---

## Debug System

The application includes a runtime-configurable debug system for troubleshooting scraping and feed issues.

### Debug Levels

| Level | Description |
|-------|-------------|
| `minimal` | Only errors and critical issues |
| `standard` | Key operations logged (default) |
| `verbose` | Every URL scraped, extension status, timing |
| `trace` | Full request/response details, service worker messages |

### Debug Panel UI

Access the debug panel via:
- **Keyboard shortcut**: `Ctrl+Shift+D`
- **URL parameter**: Add `?debug=true` to the URL

The debug panel shows:
- Extension loading status (green/red indicator)
- Number of active service workers
- Extension version and path
- Server uptime
- Feed status with article counts
- Recent scrape history with success/failure
- Test scrape functionality

### Debug API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/debug/status` | GET | Returns full debug status |
| `/api/debug/test-scrape` | POST | Tests scraping a URL, returns detailed results |
| `/api/debug/scrape-history` | GET | Returns recent scrape results |
| `/api/debug/clear-history` | POST | Clears scrape history |

### Debug Settings (Persisted)

These settings are stored in `settings.db`:

| Setting | Default | Description |
|---------|---------|-------------|
| `debug_level` | `standard` | Current debug level |
| `show_scrape_progress` | `true` | Show progress in UI |
| `show_extension_status` | `true` | Show extension status |
| `log_scraper_details` | `true` | Log per-URL scrape results |
| `log_feed_refresh_details` | `true` | Log per-feed refresh status |

---

## Key Conventions

1. **No comments in code** - Write self-documenting code; comments should explain "why", not "what"
2. **Prefer `logging` over `print`** - For any output that may appear in production
3. **Use `exc_info=True`** - When logging exceptions to include stack traces
4. **Graceful degradation** - LLM failures should not crash the app; log errors and return meaningful messages
5. **Database migrations** - Handle missing columns gracefully (see `database.py` for pattern)
6. **Environment variables** - All configuration via `.env`, never hardcoded
7. **Virtual environment** - Use `.venv/` for local development (gitignored)

---

## Git Workflow

### Commits

**Make small, frequent commits** - Each commit should represent a single logical change:

```
# Good commit messages
"Fix: Correct summary regeneration and mobile button functionality"
"Add: Per-user feed subscriptions with custom names"
"Refactor: Centralized feed library with FeedSource table"

# Avoid vague commits
"Updates"
"More changes"
"Fix stuff"
```

**Commit guidelines:**
- Commit early and often - don't wait for "perfect" code
- Each commit should compile and not break functionality
- Write commit messages in present tense: "Add feature" not "Added feature"
- Use prefixes: `Fix:`, `Add:`, `Refactor:`, `Update:`, `Remove:`

**Before committing:**
```bash
git status  # Review what changed
git diff    # Check changes are correct
```

**Push regularly:**
```bash
git push git@github.com:dranoto/fathom.git main
```

### Branching

- Work on `main` branch for this project
- Create feature branches if working on large experimental changes

### Gitignore

The following should always be gitignored:
- `.venv/` - virtual environment
- `data/*.db` - SQLite databases (contain user-specific data)
- `.env` - environment variables with secrets
- `scraper_assistant/` - Chrome extension directory
- `__pycache__/`, `*.pyc` - Python cache
