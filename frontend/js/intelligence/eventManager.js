// frontend/js/intelligence/eventManager.js
import * as eventApi from './eventApiService.js';
import * as uiManager from '../uiManager.js';
import * as state from '../state.js';

let currentEvent = null;
let eventList = [];
let eventChatHistory = [];

let settingsEventId = null;
let settingsCurrentArticles = [];

export async function initIntelligenceView() {
    console.log('Intelligence: Initializing...');
    await loadEventList();
    setupIntelligenceEventListeners();
    setupArticleEventListeners();
}

async function loadEventList() {
    try {
        eventList = await eventApi.fetchEvents();
        renderEventList();
    } catch (error) {
        console.error('Intelligence: Error loading events:', error);
        uiManager.showToast('Error loading events', 'error');
    }
}

function renderEventList() {
    const eventListEl = document.getElementById('event-list');
    if (!eventListEl) return;
    
    eventListEl.innerHTML = '';
    
    if (eventList.length === 0) {
        eventListEl.innerHTML = '<p class="no-events">No events yet. Create one to start tracking!</p>';
        return;
    }
    
    eventList.forEach(event => {
        const eventItem = document.createElement('div');
        eventItem.className = 'event-list-item';
        eventItem.dataset.eventId = event.id;
        eventItem.innerHTML = `
            <span class="event-status-dot ${event.status === 'active' ? 'active' : ''}"></span>
            <span class="event-name">${event.name}</span>
            <span class="event-count">${event.article_count || 0}</span>
        `;
        eventItem.addEventListener('click', () => selectEvent(event.id));
        eventListEl.appendChild(eventItem);
    });
}

async function selectEvent(eventId) {
    try {
        eventChatHistory = [];
        currentEvent = await eventApi.getEvent(eventId);
        renderCurrentEvent();
        updateEventListSelection(eventId);
    } catch (error) {
        console.error('Intelligence: Error selecting event:', error);
        uiManager.showToast('Error loading event details', 'error');
    }
}

function updateEventListSelection(eventId) {
    const items = document.querySelectorAll('.event-list-item');
    items.forEach(item => {
        item.classList.toggle('selected', parseInt(item.dataset.eventId) === eventId);
    });
}

let articlesCollapsed = true;

function renderCurrentEvent() {
    if (!currentEvent) return;
    
    const headerEl = document.getElementById('intelligence-event-header');
    const timelineEl = document.getElementById('intelligence-timeline');
    const summaryEl = document.getElementById('intelligence-summary');
    const chatEl = document.getElementById('intelligence-chat');
    const articlesSection = document.getElementById('intelligence-articles-section');
    const articlesCountEl = document.getElementById('articles-count');
    
    if (headerEl) {
        headerEl.innerHTML = `
            <h2>${currentEvent.name}</h2>
            <div class="event-meta">
                <span>${currentEvent.articles?.length || 0} articles</span>
                <span>•</span>
                <span>${currentEvent.status}</span>
            </div>
            <div class="event-actions">
                ${currentEvent.latest_summary ? `<button class="btn-update-summary" onclick="window.intelligenceManager.updateSummary()">Update Summary</button>` : ''}
                <button class="btn-regenerate-summary" onclick="window.intelligenceManager.regenerateSummary()">Regenerate</button>
                <button class="btn-event-settings" onclick="window.intelligenceManager.openEventSettings()">⚙️</button>
            </div>
        `;
    }
    
    if (articlesCountEl) {
        articlesCountEl.textContent = currentEvent.articles?.length || 0;
    }
    
    if (articlesSection) {
        articlesSection.classList.toggle('collapsed', articlesCollapsed);
    }
    
    if (timelineEl) {
        renderTimeline(timelineEl, currentEvent.articles || []);
    }
    
    if (summaryEl) {
        renderSummary(summaryEl, currentEvent.latest_summary);
    }
    
    if (chatEl) {
        chatEl.innerHTML = `
            <div class="chat-header">Chat about this event</div>
            <div class="chat-messages" id="event-chat-messages"></div>
            <div class="chat-input-container">
                <input type="text" id="event-chat-input" placeholder="Ask about ${currentEvent.name}..." />
                <button id="event-chat-send-btn">Send</button>
            </div>
        `;
        
        const chatInput = document.getElementById('event-chat-input');
        const sendBtn = document.getElementById('event-chat-send-btn');
        if (chatInput) {
            chatInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    sendBtn.click();
                }
            });
        }
        if (sendBtn) {
            sendBtn.addEventListener('click', () => window.intelligenceManager.sendChatMessage());
        }
    }
}

export function toggleArticlesList() {
    articlesCollapsed = !articlesCollapsed;
    const articlesSection = document.getElementById('intelligence-articles-section');
    const toggleIcon = document.getElementById('articles-toggle-icon');
    
    if (articlesSection) {
        articlesSection.classList.toggle('collapsed', articlesCollapsed);
    }
    if (toggleIcon) {
        toggleIcon.textContent = articlesCollapsed ? '▶' : '▼';
    }
}

function renderTimeline(container, articles) {
    if (!articles || articles.length === 0) {
        container.innerHTML = '<p class="no-articles">No articles in this event yet.</p>';
        return;
    }
    
    const summaryArticleIds = currentEvent?.latest_summary?.article_ids || [];
    const summaryArticleIdSet = new Set(summaryArticleIds);
    
    const timelineHtml = articles.map(article => {
        const date = article.published_date ? new Date(article.published_date).toLocaleDateString() : 'Unknown date';
        const isNew = !summaryArticleIdSet.has(article.id);
        return `
            <div class="timeline-item" data-article-id="${article.id}">
                <div class="timeline-date">${date}</div>
                <div class="timeline-content">
                    ${isNew ? '<span class="article-new-badge">NEW</span>' : ''}
                    <a href="${article.url}" target="_blank" class="timeline-title">${article.title || 'Untitled'}</a>
                    <div class="timeline-source">${article.publisher_name || 'Unknown source'}</div>
                </div>
            </div>
        `;
    }).join('');
    
    container.innerHTML = timelineHtml;
}

function renderSummary(container, summary) {
    if (!summary) {
        container.innerHTML = `
            <div class="summary-section">
                <h3>Major Summary</h3>
                <p class="no-summary">No summary yet. Add articles and click "Regenerate Summary".</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = `
        <div class="summary-section">
            <h3>Timeline Narrative</h3>
            <p>${summary.timeline_narrative || 'Not available'}</p>
        </div>
        <div class="summary-section">
            <h3>Cross-Source Synthesis</h3>
            <p>${summary.cross_source_synthesis || 'Not available'}</p>
        </div>
        <div class="summary-section">
            <h3>What's New</h3>
            <p>${summary.progressive_summary || 'Not available'}</p>
        </div>
        ${summary.key_developments && summary.key_developments.length > 0 ? `
        <div class="summary-section">
            <h3>Key Developments</h3>
            <ul class="key-developments">
                ${summary.key_developments.map(d => `<li>${d}</li>`).join('')}
            </ul>
        </div>
        ` : ''}
    `;
}

export async function regenerateSummary() {
    if (!currentEvent) return;
    
    const btns = document.querySelectorAll('.btn-regenerate-summary, .btn-update-summary');
    btns.forEach(btn => {
        btn.disabled = true;
        btn.textContent = 'Generating...';
    });
    
    try {
        uiManager.showToast('Generating major summary...', 'info');
        const result = await eventApi.generateEventSummary(currentEvent.id);
        currentEvent.latest_summary = result.summary_json;
        currentEvent.latest_summary.article_ids = result.article_ids;
        renderCurrentEvent();
        uiManager.showToast('Summary regenerated!', 'success');
    } catch (error) {
        console.error('Intelligence: Error generating summary:', error);
        uiManager.showToast('Failed to generate summary', 'error');
    } finally {
        btns.forEach(btn => {
            btn.disabled = false;
            btn.textContent = btn.classList.contains('btn-update-summary') ? 'Update Summary' : 'Regenerate';
        });
    }
}

export async function updateSummary() {
    if (!currentEvent) return;
    
    const btns = document.querySelectorAll('.btn-regenerate-summary, .btn-update-summary');
    btns.forEach(btn => {
        btn.disabled = true;
        btn.textContent = 'Updating...';
    });
    
    try {
        uiManager.showToast('Updating summary with new articles...', 'info');
        const result = await eventApi.updateEventSummary(currentEvent.id);
        currentEvent.latest_summary = result.summary_json;
        currentEvent.latest_summary.article_ids = result.article_ids;
        renderCurrentEvent();
        uiManager.showToast('Summary updated!', 'success');
    } catch (error) {
        console.error('Intelligence: Error updating summary:', error);
        uiManager.showToast('Failed to update summary', 'error');
    } finally {
        btns.forEach(btn => {
            btn.disabled = false;
            btn.textContent = btn.classList.contains('btn-update-summary') ? 'Update Summary' : 'Regenerate';
        });
    }
}

export async function sendChatMessage() {
    if (!currentEvent) return;
    
    const input = document.getElementById('event-chat-input');
    const messagesContainer = document.getElementById('event-chat-messages');
    const question = input?.value.trim();
    
    if (!question) return;
    
    if (messagesContainer) {
        messagesContainer.innerHTML += `<div class="chat-message user">${question}</div>`;
    }
    
    eventChatHistory.push({ role: 'user', content: question });
    input.value = '';
    
    try {
        const response = await eventApi.chatAboutEvent(currentEvent.id, question, eventChatHistory);
        eventChatHistory.push({ role: 'assistant', content: response.answer });
        if (messagesContainer) {
            messagesContainer.innerHTML += `<div class="chat-message ai">${response.answer}</div>`;
        }
    } catch (error) {
        console.error('Intelligence: Error sending chat:', error);
        uiManager.showToast('Failed to get response', 'error');
    }
}

export function openAddEventModal() {
    const modal = document.getElementById('add-event-modal');
    if (modal) {
        modal.style.display = 'block';
        setupAddEventModal();
    }
}

export function closeAddEventModal() {
    const modal = document.getElementById('add-event-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function setupAddEventModal() {
    const searchInput = document.getElementById('event-article-search');
    const resultsContainer = document.getElementById('event-search-results');
    const eventNameInput = document.getElementById('event-name-input');
    const eventDescInput = document.getElementById('event-desc-input');
    
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(async () => {
                const keyword = searchInput.value.trim();
                if (keyword.length < 2) {
                    resultsContainer.innerHTML = '';
                    return;
                }
                try {
                    const results = await eventApi.searchArticlesForEvent(keyword);
                    renderSearchResults(results);
                } catch (error) {
                    console.error('Intelligence: Error searching articles:', error);
                }
            }, 300);
        });
    }
}

function renderSearchResults(articles) {
    const container = document.getElementById('event-search-results');
    if (!container) return;
    
    if (articles.length === 0) {
        container.innerHTML = '<p class="no-results">No articles found.</p>';
        return;
    }
    
    container.innerHTML = articles.map(article => {
        const date = article.published_date ? new Date(article.published_date).toLocaleDateString() : '';
        return `
            <div class="search-result-item">
                <label>
                    <input type="checkbox" data-article-id="${article.id}" />
                    <span class="article-title">${article.title || 'Untitled'}</span>
                    <span class="article-date">${date}</span>
                </label>
            </div>
        `;
    }).join('');
}

export async function createEventFromModal() {
    const nameInput = document.getElementById('event-name-input');
    const descInput = document.getElementById('event-desc-input');
    const selectedArticles = document.querySelectorAll('#event-search-results input[type="checkbox"]:checked');
    
    const name = nameInput?.value.trim();
    if (!name) {
        uiManager.showToast('Please enter an event name', 'warning');
        return;
    }
    
    try {
        const event = await eventApi.createEvent(name, descInput?.value.trim() || null);
        
        const articleIds = Array.from(selectedArticles).map(cb => parseInt(cb.dataset.articleId));
        if (articleIds.length > 0) {
            await eventApi.addArticlesToEvent(event.id, articleIds);
        }
        
        closeAddEventModal();
        await loadEventList();
        await selectEvent(event.id);
        uiManager.showToast('Event created!', 'success');
        
        if (articleIds.length > 0) {
            uiManager.showToast('Generating summary...', 'info');
            await regenerateSummary();
        }
    } catch (error) {
        console.error('Intelligence: Error creating event:', error);
        uiManager.showToast('Failed to create event', 'error');
    }
}

export function openEventSettings() {
    if (!currentEvent) return;
    console.log('Intelligence: Opening settings for event', currentEvent.id);
    
    settingsEventId = currentEvent.id;
    settingsCurrentArticles = currentEvent.articles ? [...currentEvent.articles] : [];
    
    document.getElementById('settings-event-id').value = currentEvent.id;
    document.getElementById('settings-event-name').value = currentEvent.name || '';
    document.getElementById('settings-event-desc').value = currentEvent.description || '';
    
    renderCurrentArticlesList();
    
    document.getElementById('settings-article-search').value = '';
    document.getElementById('settings-search-results').innerHTML = '';
    
    const modal = document.getElementById('event-settings-modal');
    if (modal) {
        modal.style.display = 'block';
    }
}

export function closeEventSettings() {
    settingsEventId = null;
    settingsCurrentArticles = [];
    
    const modal = document.getElementById('event-settings-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function renderCurrentArticlesList() {
    const listEl = document.getElementById('current-articles-list');
    const countEl = document.getElementById('current-article-count');
    
    if (!listEl || !countEl) return;
    
    countEl.textContent = settingsCurrentArticles.length;
    
    if (settingsCurrentArticles.length === 0) {
        listEl.innerHTML = '<div class="no-articles-message">No articles in this event yet.</div>';
        return;
    }
    
    listEl.innerHTML = settingsCurrentArticles.map(article => `
        <div class="article-list-item" data-article-id="${article.id}">
            <span class="article-title" title="${escapeHtml(article.title || '')}">${escapeHtml(article.title || 'Untitled')}</span>
            <button class="remove-btn" onclick="window.intelligenceManager.removeArticleFromEventUI(${article.id})">Remove</button>
        </div>
    `).join('');
}

export async function removeArticleFromEventUI(articleId) {
    if (!settingsEventId) return;
    
    try {
        await eventApi.removeArticleFromEvent(settingsEventId, articleId);
        
        settingsCurrentArticles = settingsCurrentArticles.filter(a => a.id !== articleId);
        renderCurrentArticlesList();
        
        uiManager.showToast('Article removed', 'success');
    } catch (error) {
        console.error('Intelligence: Error removing article:', error);
        uiManager.showToast('Failed to remove article', 'error');
    }
}

export async function saveEventMetadata() {
    if (!settingsEventId) return;
    
    const name = document.getElementById('settings-event-name').value.trim();
    const description = document.getElementById('settings-event-desc').value.trim();
    
    if (!name) {
        uiManager.showToast('Event name is required', 'error');
        return;
    }
    
    try {
        await eventApi.updateEvent(settingsEventId, { name, description });
        
        currentEvent.name = name;
        currentEvent.description = description;
        
        const headerEl = document.getElementById('intelligence-event-header');
        if (headerEl) {
            const titleEl = headerEl.querySelector('h2');
            if (titleEl) titleEl.textContent = name;
        }
        
        uiManager.showToast('Event saved', 'success');
    } catch (error) {
        console.error('Intelligence: Error saving event:', error);
        uiManager.showToast('Failed to save event', 'error');
    }
}

export async function searchArticlesForSettings() {
    const keyword = document.getElementById('settings-article-search').value.trim();
    
    if (!keyword) {
        uiManager.showToast('Enter a search term', 'error');
        return;
    }
    
    const resultsEl = document.getElementById('settings-search-results');
    resultsEl.innerHTML = '<div class="no-results-message">Searching...</div>';
    
    try {
        const results = await eventApi.searchArticlesForEvent(keyword, 20);
        
        const currentArticleIds = new Set(settingsCurrentArticles.map(a => a.id));
        const filtered = results.filter(a => !currentArticleIds.has(a.id));
        
        if (filtered.length === 0) {
            resultsEl.innerHTML = '<div class="no-results-message">No articles found (or all matching articles are already in this event).</div>';
            return;
        }
        
        resultsEl.innerHTML = filtered.map(article => `
            <div class="search-result-item" data-article-id="${article.id}" data-article-title="${escapeHtml(article.title || '')}">
                <span class="article-title" title="${escapeHtml(article.title || '')}">${escapeHtml(article.title || 'Untitled')}</span>
                <button class="add-btn" onclick="window.intelligenceManager.addArticleToEventUI(${article.id})">Add</button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Intelligence: Error searching articles:', error);
        resultsEl.innerHTML = '<div class="no-results-message">Search failed.</div>';
        uiManager.showToast('Failed to search articles', 'error');
    }
}

export async function addArticleToEventUI(articleId) {
    if (!settingsEventId) return;
    
    const resultEl = document.querySelector(`.search-result-item[data-article-id="${articleId}"]`);
    const title = resultEl ? resultEl.dataset.articleTitle : 'Unknown';
    const article = { id: articleId, title: title };
    
    try {
        await eventApi.addArticlesToEvent(settingsEventId, [articleId]);
        
        settingsCurrentArticles.push(article);
        renderCurrentArticlesList();
        
        if (resultEl) {
            resultEl.remove();
        }
        
        const remainingResults = document.querySelectorAll('.search-result-item');
        if (remainingResults.length === 0) {
            document.getElementById('settings-search-results').innerHTML = 
                '<div class="no-results-message">No more articles to add.</div>';
        }
        
        uiManager.showToast('Article added', 'success');
    } catch (error) {
        console.error('Intelligence: Error adding article:', error);
        uiManager.showToast('Failed to add article', 'error');
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function setupArticleEventListeners() {
    window.addEventListener('event:articleAdded', async (e) => {
        const { eventId } = e.detail;
        if (currentEvent && currentEvent.id === eventId) {
            const updatedEvent = await eventApi.getEvent(eventId);
            currentEvent = updatedEvent;
            renderCurrentEvent();
            renderEventList();
        }
    });
    
    window.addEventListener('event:articleRemoved', async (e) => {
        const { eventId } = e.detail;
        if (currentEvent && currentEvent.id === eventId) {
            const updatedEvent = await eventApi.getEvent(eventId);
            currentEvent = updatedEvent;
            renderCurrentEvent();
            renderEventList();
        }
    });
}

function setupIntelligenceEventListeners() {
    const addEventBtn = document.getElementById('btn-add-event');
    if (addEventBtn) {
        addEventBtn.addEventListener('click', openAddEventModal);
    }
    
    const closeModalBtn = document.getElementById('close-add-event-modal');
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', closeAddEventModal);
    }
    
    const createEventBtn = document.getElementById('btn-create-event');
    if (createEventBtn) {
        createEventBtn.addEventListener('click', createEventFromModal);
    }
    
    const cancelEventBtn = document.getElementById('btn-cancel-event');
    if (cancelEventBtn) {
        cancelEventBtn.addEventListener('click', closeAddEventModal);
    }
    
    const closeSettingsBtn = document.getElementById('close-event-settings');
    if (closeSettingsBtn) {
        closeSettingsBtn.addEventListener('click', closeEventSettings);
    }
    
    const saveMetaBtn = document.getElementById('btn-save-event-meta');
    if (saveMetaBtn) {
        saveMetaBtn.addEventListener('click', saveEventMetadata);
    }
    
    const searchBtn = document.getElementById('btn-search-settings-articles');
    if (searchBtn) {
        searchBtn.addEventListener('click', searchArticlesForSettings);
    }
    
    const searchInput = document.getElementById('settings-article-search');
    if (searchInput) {
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                searchArticlesForSettings();
            }
        });
    }
    
    const settingsModal = document.getElementById('event-settings-modal');
    if (settingsModal) {
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) {
                closeEventSettings();
            }
        });
    }
}

window.intelligenceManager = {
    regenerateSummary,
    updateSummary,
    sendChatMessage,
    openEventSettings,
    openAddEventModal,
    closeAddEventModal,
    createEventFromModal,
    initIntelligenceView,
    removeArticleFromEventUI,
    addArticleToEventUI,
    toggleArticlesList
};
