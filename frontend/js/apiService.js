// frontend/js/apiService.js
// apiService.js
let SUMMARIES_API_ENDPOINT = '/api/articles/summaries'; // Default value
let CHAT_API_ENDPOINT_BASE = '/api'; // Default value

export function setApiEndpoints(summariesEndpoint, chatBaseEndpoint) {
    if (summariesEndpoint) SUMMARIES_API_ENDPOINT = summariesEndpoint;
    if (chatBaseEndpoint) CHAT_API_ENDPOINT_BASE = chatBaseEndpoint;
    console.log(`API Service Endpoints Updated: SUMMARIES -> ${SUMMARIES_API_ENDPOINT}, CHAT_BASE -> ${CHAT_API_ENDPOINT_BASE}`);
}

/**
 * This module centralizes all API communication for the NewsAI frontend.
 * Each function corresponds to an API endpoint on the backend.
 * It handles making the fetch request and basic error checking.
 */

async function handleFetch(url, options = {}) {
    console.log(`API Service: Fetching ${url} with options:`, options.method || 'GET', options.body ? 'with body' : 'no body');
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            let errorDetail = `HTTP error! status: ${response.status}`;
            try {
                const errorData = await response.json();
                errorDetail = errorData.detail || JSON.stringify(errorData) || errorDetail;
            } catch (e) {
                try { errorDetail = await response.text() || errorDetail; } catch (e_text) { /* Fallback */ }
            }
            console.error(`API Service: Fetch error for ${url} - ${errorDetail}`);
            throw new Error(errorDetail);
        }
        if (response.status === 204) { 
            console.log(`API Service: Received 204 No Content for ${url}`);
            return null; 
        }
        return response.json();
    } catch (error) {
        console.error(`API Service: Network or unexpected error for ${url}: ${error.message}`, error);
        throw error;
    }
}

export async function fetchInitialConfigData() {
    return handleFetch('/api/initial-config');
}

export async function updateConfig(payload) {
    return handleFetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

export async function toggleFavoriteStatus(articleId) {
    return handleFetch(`/api/articles/${articleId}/favorite`, {
        method: 'POST'
    });
}

export async function fetchNewsSummaries(payload) {
    console.log(`API Service: Fetching news summaries from: ${SUMMARIES_API_ENDPOINT}`);
    return handleFetch(SUMMARIES_API_ENDPOINT, { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

export async function addRssFeed(feedData) {
    return handleFetch('/api/feeds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(feedData)
    });
}

export async function fetchDbFeeds() { 
    return handleFetch('/api/feeds'); 
}

export async function updateRssFeed(feedId, updatePayload) { 
    return handleFetch(`/api/feeds/${feedId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatePayload)
    });
}

export async function deleteRssFeed(feedId) { 
    return handleFetch(`/api/feeds/${feedId}`, {
        method: 'DELETE'
    });
}

export async function triggerRssRefresh() { 
    return handleFetch('/api/trigger-rss-refresh', {
        method: 'POST'
    });
}

export async function fetchRefreshStatus() {
    return handleFetch('/api/feeds/refresh-status');
}

export async function regenerateSummary(articleId, payload) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/${articleId}/regenerate-summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

export async function fetchChatHistory(articleId) {
    // CORRECTED PATH: Removed the extra "s" from "articles"
    // The endpoint is in chat_routes.py with prefix "/api" and route "/article/{id}/chat-history"
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/article/${articleId}/chat-history`); 
}

export async function postChatMessage(payload) {
    // chat_routes.py has prefix="/api" and endpoint "/chat-with-article"
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/chat-with-article`, { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

export async function deleteOldData(daysOld) {
    return handleFetch(`/api/admin/cleanup-old-data?days_old=${daysOld}`, { 
        method: 'DELETE' 
    });
}

export async function fetchSanitizedArticleContent(articleId) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/${articleId}/content`);
}

export async function checkNewArticles(sinceTimestamp) {
    let url = `${CHAT_API_ENDPOINT_BASE}/articles/status/new-articles`; 
    if (sinceTimestamp) {
        url += `?since_timestamp=${encodeURIComponent(sinceTimestamp)}`;
    }
    return handleFetch(url);
}

console.log("frontend/js/apiService.js: Module loaded.");
