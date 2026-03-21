// frontend/js/apiService.js
let SUMMARIES_API_ENDPOINT = '/api/articles/summaries';
let CHAT_API_ENDPOINT_BASE = '/api';

const AUTH_TOKEN_KEY = 'auth_token';
const USER_DATA_KEY = 'user_data';

export function setApiEndpoints(summariesEndpoint, chatBaseEndpoint) {
    if (summariesEndpoint) SUMMARIES_API_ENDPOINT = summariesEndpoint;
    if (chatBaseEndpoint) CHAT_API_ENDPOINT_BASE = chatBaseEndpoint;
    console.log(`API Service Endpoints Updated: SUMMARIES -> ${SUMMARIES_API_ENDPOINT}, CHAT_BASE -> ${CHAT_API_ENDPOINT_BASE}`);
}

function getAuthToken() {
    return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setAuthToken(token) {
    if (token) {
        localStorage.setItem(AUTH_TOKEN_KEY, token);
    } else {
        localStorage.removeItem(AUTH_TOKEN_KEY);
    }
}

function setUserData(userData) {
    if (userData) {
        localStorage.setItem(USER_DATA_KEY, JSON.stringify(userData));
    } else {
        localStorage.removeItem(USER_DATA_KEY);
    }
}

export function getUserData() {
    const data = localStorage.getItem(USER_DATA_KEY);
    return data ? JSON.parse(data) : null;
}

export function isLoggedIn() {
    return !!getAuthToken();
}

async function handleFetch(url, options = {}) {
    const token = getAuthToken();
    const headers = {
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    if (!(options.body instanceof FormData) && headers['Content-Type'] !== 'multipart/form-data') {
        if (!headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }
    }
    
    const finalOptions = {
        ...options,
        headers
    };
    
    console.log(`API Service: Fetching ${url} with options:`, options.method || 'GET', options.body ? 'with body' : 'no body');
    try {
        const response = await fetch(url, finalOptions);
        
        if (response.status === 401) {
            setAuthToken(null);
            setUserData(null);
            window.dispatchEvent(new CustomEvent('auth:logout'));
            throw new Error('Unauthorized - please log in again');
        }
        
        if (!response.ok) {
            let errorDetail = `HTTP error! status: ${response.status}`;
            try {
                const errorData = await response.json();
                errorDetail = errorData.detail || JSON.stringify(errorData) || errorDetail;
            } catch (e) {
                // Ignore JSON parse errors for error responses
            }
            throw new Error(errorDetail);
        }
        
        if (response.status === 204) {
            return null;
        }
        
        return await response.json();
    } catch (error) {
        if (error.message === 'Unauthorized - please log in again') {
            throw error;
        }
        console.error(`API Service Error for ${url}:`, error);
        throw error;
    }
}

export { handleFetch as fetchWithAuth };

export async function login(email, password) {
    const response = await handleFetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    setAuthToken(response.access_token);
    setUserData({ id: response.user_id, email: response.email, is_admin: response.is_admin || false });
    return response;
}

export async function register(email, password) {
    const response = await handleFetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    setAuthToken(response.access_token);
    setUserData({ id: response.user_id, email: response.email, is_admin: response.is_admin || false });
    return response;
}

export async function logout() {
    setAuthToken(null);
    setUserData(null);
}

export async function getCurrentUser() {
    return handleFetch('/api/auth/me');
}

export async function deleteAccount(confirm) {
    const response = await handleFetch('/api/auth/delete-account', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm })
    });
    setAuthToken(null);
    setUserData(null);
    return response;
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

export async function refreshAvailableModels() {
    return handleFetch('/api/config/refresh-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
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

export async function fetchPublicFeeds() {
    return handleFetch('/api/feeds/public');
}

export async function fetchUserFeeds() {
    return handleFetch('/api/users/feeds');
}

export async function addUserFeed(feedData) {
    return handleFetch('/api/users/feeds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(feedData)
    });
}

export async function deleteUserFeed(feedId) {
    return handleFetch(`/api/users/feeds/${feedId}`, {
        method: 'DELETE'
    });
}

export async function updateUserFeed(feedId, feedData) {
    return handleFetch(`/api/users/feeds/${feedId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(feedData)
    });
}

export async function triggerUserFeedFetch(feedId) {
    return handleFetch(`/api/users/feeds/${feedId}/trigger-fetch`, {
        method: 'POST'
    });
}

export async function fetchUserSettings() {
    return handleFetch('/api/users/settings');
}

export async function updateUserSettings(settings) {
    return handleFetch('/api/users/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
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

export async function refreshSingleFeed(feedId) {
    return handleFetch(`/api/feeds/${feedId}/refresh`, {
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
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/article/${articleId}/chat-history`); 
}

export async function postChatMessage(payload) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/chat-with-article`, { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
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

export async function markArticleRead(articleId) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/${articleId}/mark-read`, {
        method: 'POST'
    });
}

export async function markArticleUnread(articleId) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/${articleId}/mark-unread`, {
        method: 'POST'
    });
}

export async function archiveArticle(articleId) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/${articleId}/archive`, {
        method: 'POST'
    });
}

export async function restoreArticle(articleId) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/${articleId}/restore`, {
        method: 'POST'
    });
}

export async function permanentlyDeleteArticle(articleId) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/${articleId}/permanent-delete`, {
        method: 'POST'
    });
}

export async function bulkMarkRead(articleIds) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/bulk-mark-read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(articleIds)
    });
}

export async function fetchArchivedArticles(page = 1, pageSize = 12) {
    return handleFetch(`${CHAT_API_ENDPOINT_BASE}/articles/archived?page=${page}&page_size=${pageSize}`);
}

export async function fetchUserTags() {
    return handleFetch('/api/tags');
}

export async function searchTags(query) {
    return handleFetch(`/api/tags/search?q=${encodeURIComponent(query)}`);
}

export async function fetchDebugStatus() {
    return handleFetch('/api/debug/status');
}

export async function testScrapeUrl(url) {
    return handleFetch(`/api/debug/test-scrape?url=${encodeURIComponent(url)}`, {
        method: 'POST'
    });
}

export async function fetchScrapeHistory(limit = 20) {
    return handleFetch(`/api/debug/scrape-history?limit=${limit}`);
}

export async function clearScrapeHistory() {
    return handleFetch('/api/debug/clear-history', {
        method: 'POST'
    });
}

export async function getAdminUsers() {
    return handleFetch('/api/admin/users');
}

export async function deleteAdminUser(userId) {
    return handleFetch(`/api/admin/users/${userId}`, {
        method: 'DELETE'
    });
}

export async function getAdminFeeds() {
    return handleFetch('/api/admin/feeds');
}

export async function addAdminFeed(feedData) {
    return handleFetch('/api/admin/feeds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(feedData)
    });
}

export async function deleteAdminFeed(feedId) {
    return handleFetch(`/api/admin/feeds/${feedId}`, {
        method: 'DELETE'
    });
}

export async function updateAdminFeed(feedId, feedData) {
    return handleFetch(`/api/admin/feeds/${feedId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(feedData)
    });
}

export async function getAdminSettings() {
    return handleFetch('/api/admin/settings/global');
}

export async function updateAdminSettings(settingsData) {
    return handleFetch('/api/admin/settings/global', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsData)
    });
}

export async function deleteOldData(daysOld) {
    return handleFetch(`/api/admin/cleanup-old-data?days_old=${daysOld}`, {
        method: 'DELETE'
    });
}

console.log("frontend/js/apiService.js: Module loaded.");