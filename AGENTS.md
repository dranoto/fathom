# AGENTS.md - Fathom News Intelligence

## Project Overview
Python 3.11 FastAPI app with SQLite, OpenAI-compatible LLM API (via LangChain), Playwright scraping. Vanilla JS frontend with Muuri.js masonry layout.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main_api:app --host 0.0.0.0 --port 9000 --reload

# Install browser for scraping
playwright install chromium

# Docker
docker build -t fathom . && docker run -p 9000:9000 --rm \
  -v $(pwd)/data:/app/data --env-file .env fathom
```

**No formal test framework** - Manual API testing at `http://localhost:9000/docs`

## Code Style Guidelines

### Python

**Imports** (3 sections, blank lines between):
```python
# Standard library
import logging
from datetime import datetime
from typing import List, Optional

# Third-party
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session

# Local application
from .routers import article_routes
```

**Type Hints**: Required for all function parameters and returns.

**Naming**:
- `snake_case` for functions/variables
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- `_leading_underscore` for private members

**Error Handling**:
- Use specific exception types
- Log with `exc_info=True` for stack traces
- Chain exceptions: `raise CustomError(msg) from e`
- Graceful degradation - don't crash on LLM failures
- Always use try/catch around `db.commit()` with rollback on failure

**Logging**:
```python
logger = logging.getLogger(__name__)
logger.info(f"Operation started...", exc_info=True)
```

**Database**: Use context managers for sessions.
**Pydantic**: Use `from_attributes = True` for ORM compatibility.

### JavaScript (ES Modules)

**Naming**: `camelCase` functions/vars, `UPPER_SNAKE_CASE` constants.
**Async/Await**: Prefer over raw Promises.

## Project Structure
```
app/
├── main_api.py       # FastAPI entry point
├── config.py         # Environment config with defaults
├── schemas.py        # Pydantic models
├── database/         # SQLAlchemy models
├── dependencies.py   # FastAPI dependencies (LLM, DB sessions)
├── routers/          # API endpoints
│   ├── article_routes.py
│   ├── article_helpers.py  # Shared article result building
│   └── ...
├── scraper.py        # Playwright scraping
├── summarizer.py     # LLM summarization (LangChain ChatOpenAI)
├── rss_client.py     # RSS parsing
├── tasks.py          # APScheduler background jobs
└── intelligence/      # Intelligence module
    ├── models.py     # Event, ArticleEvent, EventSummary
    ├── schemas.py    # Pydantic models
    ├── routes.py     # Event CRUD, summary, chat endpoints
    └── summarizer.py # Major summary generation

frontend/
├── index.html        # Main HTML entry
├── script.js         # Main orchestrator (imports all modules)
├── css/              # Stylesheets
└── js/
    ├── state.js      # Shared frontend state
    ├── apiService.js # API calls with auth
    ├── uiManager.js  # UI rendering, Muuri grid management
    ├── intelligence/ # Frontend intelligence module
    │   ├── eventApiService.js  # Event API calls
    │   └── eventManager.js     # Event UI logic
    └── ...
```

## Key Conventions

1. **No comments** - Self-documenting code only
2. **Logging over print** - Use `logger` from `logging.getLogger(__name__)`
3. **Environment config** - All settings via `.env`, never hardcoded
4. **Graceful degradation** - LLM failures log error and return meaningful message, don't crash
5. **Database migrations** - Handle missing columns gracefully
6. **Route ordering** - Static routes (e.g., `/search/articles`) must be defined BEFORE parameterized routes (e.g., `/{event_id}`) to avoid matching issues

## Intelligence Module

### Overview
Tracks developing news events across multiple RSS feeds with multi-article summaries, timeline views, and enhanced chat.

### Database Models (`app/intelligence/models.py`)
- **Event** - User's news event (name, description, status)
- **ArticleEvent** - Many-to-many association (article can belong to multiple events)
- **EventSummary** - JSON summary with timeline narrative, cross-source synthesis, progressive summary

### API Endpoints (`app/intelligence/routes.py`)
| Endpoint | Description |
|----------|-------------|
| `GET /api/events` | List user's events |
| `POST /api/events` | Create event |
| `GET /api/events/{id}` | Get event with articles |
| `PUT /api/events/{id}` | Update event |
| `DELETE /api/events/{id}` | Delete event |
| `POST /api/events/{id}/articles` | Add articles to event |
| `DELETE /api/events/{id}/articles/{article_id}` | Remove article |
| `POST /api/events/{id}/summary` | Generate major summary (JSON with 3 sections) |
| `GET /api/events/{id}/chat` | Chat about event with context |
| `GET /api/events/search/articles` | Search articles to add (keyword matching) |

### Major Summary Output Format
```json
{
  "timeline_narrative": "Chronological development of events...",
  "cross_source_synthesis": "Key insights from multiple sources...",
  "progressive_summary": "Updated understanding based on new articles..."
}
```

### Frontend State
- `activeView`: `'main' | 'favorites' | 'deleted' | 'in_events' | 'intelligence'`
- Article cards show event indicators (tent icon with event name or "2+ events")
- "No Events" filter shows orphan articles (not in any event)

## Git Workflow
- **Commits**: Small, frequent. Use prefixes: `Fix:`, `Add:`, `Refactor:`, `Update:`
- **Push**: `git push git@github.com:dranoto/fathom.git main`
- **Gitignore**: `.venv/`, `data/*.db`, `.env`, `scraper_assistant/`, `__pycache__/`

## LLM Configuration

Uses **OpenAI-compatible API** via LangChain's `ChatOpenAI`. Gemini is explicitly not supported and will be rejected.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | API key for LLM provider |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base URL |
| `DEFAULT_SUMMARY_MODEL_NAME` | `gpt-4o-mini` | Model for summarization |
| `DEFAULT_CHAT_MODEL_NAME` | `gpt-4o-mini` | Model for article chat |
| `DEFAULT_TAG_MODEL_NAME` | `gpt-4o-mini` | Model for tag generation |
| `SUMMARY_LLM_TEMPERATURE` | `0.2` | Summary generation temperature |
| `CHAT_LLM_TEMPERATURE` | `0.5` | Chat temperature |
| `TAG_LLM_TEMPERATURE` | `0.1` | Tag generation temperature |

## Other Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/newsai.db` | Main database |
| `SETTINGS_DATABASE_URL` | `sqlite:///./data/settings.db` | Settings DB |
| `RSS_FEED_URLS` | | Comma-separated feeds |
| `DEFAULT_PAGE_SIZE` | 6 | Articles per page |
| `DEFAULT_RSS_FETCH_INTERVAL_MINUTES` | 60 | Refresh interval |
| `DEBUG_LEVEL` | `standard` | `minimal`/`standard`/`verbose`/`trace` |
