# AGENTS.md - AI News Today

## Project Overview
Python 3.11 FastAPI app with SQLite, OpenAI-compatible LLM API (via LangChain), Playwright scraping. Vanilla JS frontend.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main_api:app --host 0.0.0.0 --port 9000 --reload

# Install browser for scraping
playwright install chromium

# Docker
docker build -t ai-news-today . && docker run -p 9000:9000 --rm \
  -v $(pwd)/data:/app/data --env-file .env ai-news-today
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
├── main_api.py      # FastAPI entry
├── config.py        # Environment config
├── database/        # SQLAlchemy models
├── schemas.py       # Pydantic models
├── dependencies.py  # FastAPI dependencies
├── routers/         # API endpoints (article_, feed_, user_, chat_, config_, debug_)
├── scraper.py       # Playwright scraping
├── summarizer.py    # LLM summarization (via LangChain ChatOpenAI)
├── rss_client.py    # RSS parsing
├── tasks.py         # APScheduler background jobs
frontend/js/         # ES modules (state, apiService, uiManager, feedHandler...)
```

## Key Conventions

1. **No comments** - Self-documenting code only
2. **Logging over print** - Use `logger` from `logging.getLogger(__name__)`
3. **Environment config** - All settings via `.env`, never hardcoded
4. **Graceful degradation** - LLM failures log error and return meaningful message, don't crash
5. **Database migrations** - Handle missing columns gracefully

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
