// frontend/js/state.js

/**
 * This module holds the shared frontend state for the NewsAI application.
 * Exported variables are 'live bindings' but should generally be modified
 * via exported setter functions to maintain clarity and control.
 */

// --- Core Application State ---
export let dbFeedSources = []; 
export let userFeeds = [];
export let articlesPerPage = 6;
export let currentPage = 1; 
export let totalPages = 1; 
export let totalArticlesAvailable = 0; 
export let isLoadingMoreArticles = false; 
export let currentArticleForChat = null; 
export let currentChatHistory = []; 

// For polling
export let lastKnownLatestArticleTimestamp = null; // Stores ISO string

// --- Prompts (Defaults and Current Values) ---
export let defaultSummaryPrompt = "Task:Generate a concise, narrative summary of the following article. The output must be Markdown-formatted, engaging, and suitable for a news digest. Focus on the key information, main actors, outcomes, and any significant implications. Ensure the summary flows well and captures the essence of the article. Avoid overly technical jargon unless essential and explained. Structure with a clear beginning, middle, and end. {text}";
export let defaultChatPrompt = "Persona & Goal:You are an insightful AI analyst and conversational partner. Your purpose is to help the user explore the provided article's content in greater depth, moving beyond the initial summary. Engage with their questions thoughtfully, provide detailed explanations, clarify complexities, and offer different perspectives based *only* on the article text. If the user asks for information outside the article, politely state that you can only discuss the provided text. Formatting: Use Markdown for all responses, including bolding, italics, bullet points, and numbered lists where appropriate to enhance readability and structure. Ensure your answers are well-organized and easy to follow. Task: Given the article text below, and the user's question, provide a comprehensive and helpful answer. Article Text: {article_text} Question: {question} Answer (in Markdown):";
export let defaultTagGenerationPrompt = "Given the following article text, generate a list of 3-5 relevant keywords or tags. These tags should be concise, lowercase, and accurately reflect the main topics, entities, or themes of the article. Output them as a comma-separated list. For example: 'ukraine, military aid, international relations, defense policy, us politics'. Article: {text} Tags:";

export let currentSummaryPrompt = defaultSummaryPrompt;
export let currentChatPrompt = defaultChatPrompt;
export let currentTagGenerationPrompt = defaultTagGenerationPrompt;

// --- Locally tracked favorited articles (to hide from main page) ---
export let locallyFavoritedArticleIds = new Set();

// --- Filters ---
export let activeFeedFilterIds = []; 
export let activeTagFilterIds = []; 
export let currentKeywordSearch = null; 
export let activeView = 'main'; // 'main' or 'favorites'

// --- Tag Search ---
export let tagSearchQuery = '';
export let tagSearchResults = [];
export let isTagSearchOpen = false;

// --- Utility functions to update state ---

export function setDbFeedSources(sources) {
    dbFeedSources = Array.isArray(sources) ? sources : [];
}

export function setUserFeeds(feeds) {
    userFeeds = Array.isArray(feeds) ? feeds : [];
}

export function setArticlesPerPage(count) {
    const numCount = parseInt(count);
    if (!isNaN(numCount) && numCount > 0) {
        articlesPerPage = numCount;
    }
}

export function setCurrentPage(page) {
    const numPage = parseInt(page);
    if (!isNaN(numPage) && numPage > 0) {
        currentPage = numPage;
    }
}

export function setTotalPages(pages) {
    const numPages = parseInt(pages);
    if (!isNaN(numPages) && numPages >= 0) {
        totalPages = numPages;
    }
}

export function setTotalArticlesAvailable(count) {
    const numCount = parseInt(count);
    if (!isNaN(numCount) && numCount >= 0) {
        totalArticlesAvailable = numCount;
    }
}

export function setIsLoadingMoreArticles(isLoading) {
    isLoadingMoreArticles = !!isLoading; 
}

export function setCurrentArticleForChat(article) {
    currentArticleForChat = article; 
}

export function setCurrentChatHistory(history) {
    currentChatHistory = Array.isArray(history) ? history : [];
}

export function setDefaultPrompts(summary, chat, tag) {
    if (summary) defaultSummaryPrompt = summary;
    if (chat) defaultChatPrompt = chat;
    if (tag) defaultTagGenerationPrompt = tag;
}

export function setCurrentPrompts(summary, chat, tag) {
    currentSummaryPrompt = summary || defaultSummaryPrompt;
    currentChatPrompt = chat || defaultChatPrompt;
    currentTagGenerationPrompt = tag || defaultTagGenerationPrompt;
}

export function setActiveFeedFilterIds(ids) {
    activeFeedFilterIds = Array.isArray(ids) ? ids.map(id => parseInt(id)).filter(id => !isNaN(id)) : [];
}

export function setActiveTagFilterIds(tagObjects) {
    activeTagFilterIds = Array.isArray(tagObjects) ? tagObjects.filter(t => t && typeof t.id === 'number' && typeof t.name === 'string') : [];
}
export function addActiveTagFilter(tagObj) {
    if (tagObj && typeof tagObj.id === 'number' && typeof tagObj.name === 'string' && !activeTagFilterIds.some(t => t.id === tagObj.id)) {
        activeTagFilterIds.push(tagObj);
    }
}
export function removeActiveTagFilter(tagId) {
    const numTagId = parseInt(tagId);
    if (!isNaN(numTagId)) {
        activeTagFilterIds = activeTagFilterIds.filter(t => t.id !== numTagId);
    }
}

export function setCurrentKeywordSearch(keyword) {
    currentKeywordSearch = typeof keyword === 'string' ? keyword.trim() : null;
}

export function setActiveView(view) {
    if (view === 'main' || view === 'favorites' || view === 'deleted' || view === 'settings' || view === 'admin' || view === 'intelligence' || view === 'in_events') {
        activeView = view;
    } else {
        console.warn(`State: Invalid view '${view}' provided to setActiveView.`);
    }
}

export function setLastKnownLatestArticleTimestamp(timestamp) {
    if (timestamp && typeof timestamp === 'string') {
        try {
            new Date(timestamp); 
            lastKnownLatestArticleTimestamp = timestamp;
        } catch (e) {
            console.error("State: Invalid timestamp provided for lastKnownLatestArticleTimestamp", timestamp, e);
        }
    } else if (timestamp === null) {
        lastKnownLatestArticleTimestamp = null;
    } else {
        console.warn("State: Attempted to set invalid lastKnownLatestArticleTimestamp", timestamp);
    }
}

export function addLocallyFavoritedArticle(articleId) {
    locallyFavoritedArticleIds.add(articleId);
}

export function removeLocallyFavoritedArticle(articleId) {
    locallyFavoritedArticleIds.delete(articleId);
}

export function isLocallyFavorited(articleId) {
    return locallyFavoritedArticleIds.has(articleId);
}

export function setTagSearchQuery(query) {
    tagSearchQuery = typeof query === 'string' ? query.trim() : '';
}

export function setTagSearchResults(results) {
    tagSearchResults = Array.isArray(results) ? results : [];
}

export function setIsTagSearchOpen(isOpen) {
    isTagSearchOpen = !!isOpen;
}

export function clearTagSearch() {
    tagSearchQuery = '';
    tagSearchResults = [];
    isTagSearchOpen = false;
}

console.log("frontend/js/state.js: Module loaded and state initialized.");
