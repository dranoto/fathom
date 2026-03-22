// frontend/js/intelligence/eventApiService.js
import { fetchWithAuth } from '../apiService.js';

export async function fetchEvents() {
    return fetchWithAuth('/api/events');
}

export async function createEvent(name, description = null) {
    return fetchWithAuth('/api/events', {
        method: 'POST',
        body: JSON.stringify({ name, description })
    });
}

export async function getEvent(eventId) {
    return fetchWithAuth(`/api/events/${eventId}`);
}

export async function updateEvent(eventId, data) {
    return fetchWithAuth(`/api/events/${eventId}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
}

export async function deleteEvent(eventId) {
    return fetchWithAuth(`/api/events/${eventId}`, {
        method: 'DELETE'
    });
}

export async function getEventArticles(eventId) {
    return fetchWithAuth(`/api/events/${eventId}/articles`);
}

export async function addArticlesToEvent(eventId, articleIds) {
    return fetchWithAuth(`/api/events/${eventId}/articles`, {
        method: 'POST',
        body: JSON.stringify({ article_ids: articleIds })
    });
}

export async function removeArticleFromEvent(eventId, articleId) {
    return fetchWithAuth(`/api/events/${eventId}/articles/${articleId}`, {
        method: 'DELETE'
    });
}

export async function generateEventSummary(eventId) {
    return fetchWithAuth(`/api/events/${eventId}/summary`, {
        method: 'POST'
    });
}

export async function updateEventSummary(eventId) {
    return fetchWithAuth(`/api/events/${eventId}/summary/update`, {
        method: 'POST'
    });
}

export async function getEventSummary(eventId) {
    return fetchWithAuth(`/api/events/${eventId}/summary`);
}

export async function searchArticlesForEvent(keyword, limit = 20) {
    return fetchWithAuth(`/api/events/search/articles?keyword=${encodeURIComponent(keyword)}&limit=${limit}`);
}

export async function chatAboutEvent(eventId, question, chatHistory = null) {
    const body = { question };
    if (chatHistory) {
        body.chat_history = chatHistory;
    }
    return fetchWithAuth(`/api/events/${eventId}/chat`, {
        method: 'POST',
        body: JSON.stringify(body)
    });
}
