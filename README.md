# AI News Today

**AI News Today** is a self-hostable, AI-powered news aggregator and summarizer. It fetches articles from your favorite RSS feeds, uses a Large Language Model (LLM) to generate concise summaries and relevant tags, and presents them in a clean, easy-to-navigate web interface.

This project is designed for users who want to stay informed but are overwhelmed by the volume of online content. It allows you to create a personalized news digest, chat with articles to gain deeper insights, and even view the full, scraped content of an article without leaving the application.

## Key Features

*   **RSS Aggregation:** Add and manage multiple RSS feeds to create a personalized news stream.
*   **AI-Powered Summarization:** Automatically generates concise, easy-to-read summaries for each article.
*   **AI-Powered Tagging:** Automatically generates relevant tags for each article, allowing for easy filtering and discovery.
*   **Article Chat:** Engage in a conversation with an article's content to ask specific questions and get detailed answers.
*   **Full Content Scraping:** View the full, cleaned content of articles directly within the application.
*   **Comprehensive Configuration:** A dedicated "Setup" page in the UI allows you to manage RSS feeds, customize AI prompts, select different AI models, and configure application settings.
*   **Search and Filtering:** Search for articles by keyword or filter by AI-generated tags.
*   **Dockerized Deployment:** Comes with a `Dockerfile` for easy, one-command deployment.
*   **Background Updates:** Automatically fetches new articles in the background.

## Tech Stack

*   **Backend:** Python 3.11, FastAPI, Uvicorn
*   **AI Integration:** Google Gemini, LangChain (`langchain-google-genai`)
*   **Database:** SQLAlchemy, SQLite (by default)
*   **Web Scraping:** Playwright, BeautifulSoup4, Unstructured
*   **RSS Parsing:** `feedparser`
*   **Background Jobs:** APScheduler
*   **Frontend:** Vanilla JavaScript (ESM), HTML5, CSS3
*   **Deployment:** Docker

## Getting Started

Follow these instructions to get the application running on your local machine.

### Prerequisites

*   **Docker:** You must have Docker installed and running on your system. You can find installation instructions for your OS on the [official Docker website](https://docs.docker.com/get-docker/).
*   **Google Gemini API Key:** The application uses the Google Gemini API for its AI features. You will need to obtain an API key from the [Google AI Studio](https://aistudio.google.com/app/apikey).

### Configuration

1.  **Create a `.env` file:** In the root directory of the project, create a file named `.env`.

2.  **Add your API Key:** Open the `.env` file and add your Google Gemini API key as shown below:

    ```env
    # .env
    GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
    ```

3.  **(Optional) Add Initial RSS Feeds:** You can add a comma-separated list of RSS feed URLs to the `.env` file. These feeds will be added to the database on the first run.

    ```env
    # .env
    GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
    RSS_FEED_URLS=https://www.wired.com/feed/category/business/latest/rss,https://www.technologyreview.com/feed/
    ```

### Running the Application

Once you have completed the configuration steps, you can launch the application with a single command:

```bash
docker build -t ai-news-today . && docker run -p 8000:8000 --rm --name ai-news-today-container -v $(pwd)/data:/app/data --env-file .env ai-news-today
```

This command will:
1.  Build the Docker image.
2.  Run the container, exposing the application on port 8000 of your local machine.
3.  Mount a local `data` directory to persist the SQLite database.
4.  Pass the environment variables from your `.env` file to the container.

Once the container is running, you can access the application by opening your web browser and navigating to `http://localhost:8000`.

## Usage

Once the application is running, you can start exploring its features:

*   **Main Feed:** The main feed will initially be empty.
*   **Adding Feeds:** Navigate to the "Setup" page to add your first RSS feed. The application will immediately start fetching and summarizing articles from that feed.
*   **Interacting with Articles:**
    *   Click on an article's title to read the AI-generated summary.
    *   Click on the "Chat" button to open a chat interface and ask questions about the article.
    *   Click on the "Read Full Content" button to view the full, scraped content of the article.
    *   Click on the AI-generated tags to filter the feed by that topic.
*   **Configuration:** Use the "Setup" page to further customize the application, such as adding more feeds, changing AI prompts, or selecting different AI models.

## API Overview

The application exposes a RESTful API for programmatic interaction. The full, interactive API documentation (provided by FastAPI and Swagger UI) is available at `http://localhost:8000/docs` when the application is running.

Some of the key endpoints include:

*   `POST /api/articles/summaries`: Fetch paginated, summarized articles.
*   `POST /api/chat-with-article/{article_id}`: Chat with a specific article.
*   `GET /api/feeds`: Get a list of all RSS feeds in the database.
*   `POST /api/feeds`: Add a new RSS feed.

## Responsible Use

The content scraping feature of this application is intended to provide a better reading experience by consolidating content. However, it is crucial to use this feature responsibly.

*   **Respect Terms of Service:** Do not use this tool to scrape websites that prohibit automated access in their terms of service.
*   **Be Mindful of Copyright:** All content remains the property of its original publisher. This tool is for personal, informational use only.
*   **Do Not Overload Servers:** Be considerate of the websites you are scraping. The default settings are designed to be respectful, but you should not abuse this feature.

The developers of this application are not responsible for any misuse of this tool.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
