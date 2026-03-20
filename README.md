# AI News Today

**AI News Today** is a self-hostable, AI-powered news aggregator and summarizer. It fetches articles from RSS feeds, uses AI to generate concise summaries and relevant tags, and presents them in a clean, mobile-friendly web interface with PWA support.

## Features

- **RSS Aggregation**: Add and manage multiple RSS feeds
- **AI Summarization**: Automatic concise summaries via Google Gemini
- **AI Tagging**: Automatic relevant tags for filtering and discovery
- **Article Chat**: Ask questions about any article's content
- **Full Content Scraping**: View complete article content without leaving the app
- **Search**: Filter articles by keyword or AI-generated tags
- **Favorites & Archive**: Save articles and track read status
- **PWA Support**: Install on Android for native-like experience
- **Mobile Responsive**: Full-featured mobile interface
- **Background Updates**: Automatic RSS fetching on a configurable schedule

## Tech Stack

- **Backend**: Python 3.11, FastAPI, Uvicorn, SQLAlchemy, SQLite
- **AI**: Google Gemini via LangChain
- **Web Scraping**: Playwright, BeautifulSoup4
- **Background Jobs**: APScheduler
- **Frontend**: Vanilla JavaScript (ESM), CSS3, PWA
- **Deployment**: Docker

## Quick Start

### Prerequisites

- Docker
- Google Gemini API key ([Get one here](https://aistudio.google.com/app/apikey))

### Configuration

Create a `.env` file:

```env
GEMINI_API_KEY=your_api_key_here
RSS_FEED_URLS=https://example.com/feed1,https://example.com/feed2
```

### Running

```bash
docker build -t ai-news-today . && docker run -p 9000:9000 --rm \
  --name ai-news-today-container \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  ai-news-today
```

Access at `http://localhost:9000`

### Local Development

```bash
pip install -r requirements.txt
source .venv/bin/activate
uvicorn app.main_api:app --host 0.0.0.0 --port 9000 --reload
playwright install chromium
```

## Usage

### Navigation

- **Main Feed**: Default view showing all articles
- **Favorites**: Saved articles (click star icon on article)
- **Archived**: Deleted articles (soft delete, can restore)
- **Feed Dropdown**: Filter by specific feed
- **Tag Search**: Find and filter by AI-generated tags
- **Keyword Search**: Search article titles and content

### Article Actions

- **Title**: Expand article card with summary
- **Chat Button**: Ask questions about the article
- **Regenerate**: Create new summary or tags
- **Star**: Add to favorites
- **Archive**: Remove from main feed

### PWA Installation (Android)

1. Open in Chrome on Android
2. Tap menu → "Add to Home Screen"
3. App will update automatically when new code is deployed

## API

Full API docs at `/docs` when running.

Key endpoints:
- `POST /api/articles/summaries` - Fetch paginated articles
- `POST /api/articles/{id}/regenerate-summary` - Regenerate summary/tags
- `POST /api/chat-with-article` - Chat with article content
- `GET /api/users/feeds` - User's subscribed feeds
- `POST /api/users/feeds` - Subscribe to a feed

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | (required) | Google Gemini API key |
| `DATABASE_URL` | `sqlite:///./data/newsai.db` | Database connection |
| `RSS_FEED_URLS` | | Comma-separated initial feeds |
| `DEFAULT_PAGE_SIZE` | 6 | Articles per page |
| `DEFAULT_RSS_FETCH_INTERVAL_MINUTES` | 60 | Background refresh interval |
| `MAX_ARTICLES_PER_INDIVIDUAL_FEED` | 15 | Max articles per feed on fetch |
| `PLAYWRIGHT_TIMEOUT` | 60000 | Scraping timeout (ms) |
| `DEBUG_LEVEL` | `standard` | Logging level |

## Project Structure

```
├── app/
│   ├── main_api.py          # FastAPI entry point
│   ├── config.py            # Environment config
│   ├── database/            # SQLAlchemy models
│   ├── routers/             # API endpoints
│   ├── scraper.py           # Playwright content extraction
│   ├── summarizer.py         # LLM summarization
│   ├── rss_client.py        # RSS parsing
│   └── tasks.py             # APScheduler jobs
├── frontend/
│   ├── index.html           # Main HTML
│   ├── admin.html           # Admin panel
│   ├── js/                  # ES modules
│   │   ├── state.js         # State management
│   │   ├── apiService.js    # API calls
│   │   ├── uiManager.js     # UI logic
│   │   └── chatHandler.js   # Article chat
│   └── css/                 # Stylesheets
├── requirements.txt
├── Dockerfile
└── README.md
```

## License

MIT License