// frontend/js/intelligence/eventManager.js
import * as eventApi from './eventApiService.js';
import * as uiManager from '../uiManager.js';
import * as state from '../state.js';

let currentEvent = null;
let eventList = [];
let eventChatHistory = [];

export async function initIntelligenceView() {
    console.log('Intelligence: Initializing...');
    await loadEventList();
    setupIntelligenceEventListeners();
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

function renderCurrentEvent() {
    if (!currentEvent) return;
    
    const headerEl = document.getElementById('intelligence-event-header');
    const timelineEl = document.getElementById('intelligence-timeline');
    const summaryEl = document.getElementById('intelligence-summary');
    const chatEl = document.getElementById('intelligence-chat');
    
    if (headerEl) {
        headerEl.innerHTML = `
            <h2>${currentEvent.name}</h2>
            <div class="event-meta">
                <span>${currentEvent.articles?.length || 0} articles</span>
                <span>•</span>
                <span>${currentEvent.status}</span>
            </div>
            <div class="event-actions">
                <button class="btn-regenerate-summary" onclick="window.intelligenceManager.regenerateSummary()">Regenerate Summary</button>
                <button class="btn-event-settings" onclick="window.intelligenceManager.openEventSettings()">⚙️</button>
            </div>
        `;
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

function renderTimeline(container, articles) {
    if (!articles || articles.length === 0) {
        container.innerHTML = '<p class="no-articles">No articles in this event yet.</p>';
        return;
    }
    
    const timelineHtml = articles.map(article => {
        const date = article.published_date ? new Date(article.published_date).toLocaleDateString() : 'Unknown date';
        return `
            <div class="timeline-item" data-article-id="${article.id}">
                <div class="timeline-date">${date}</div>
                <div class="timeline-content">
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
    
    const btn = document.querySelector('.btn-regenerate-summary');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Generating...';
    }
    
    try {
        uiManager.showToast('Generating major summary...', 'info');
        const result = await eventApi.generateEventSummary(currentEvent.id);
        currentEvent.latest_summary = result.summary_json;
        renderCurrentEvent();
        uiManager.showToast('Summary regenerated!', 'success');
    } catch (error) {
        console.error('Intelligence: Error generating summary:', error);
        uiManager.showToast('Failed to generate summary', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Regenerate Summary';
        }
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
}

window.intelligenceManager = {
    regenerateSummary,
    sendChatMessage,
    openEventSettings,
    openAddEventModal,
    closeAddEventModal,
    createEventFromModal,
    initIntelligenceView
};
