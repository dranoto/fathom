// frontend/js/uiManager.js
import * as state from './state.js';
import * as apiService from './apiService.js'; 
import * as chatHandler from './chatHandler.js';
import * as eventApi from './intelligence/eventApiService.js';

/**
 * This module is responsible for all direct UI manipulations,
 * such as rendering articles, updating filter displays, managing loading indicators,
 * and controlling section/modal visibility.
 */

// --- Muuri Grid Instance ---
let muuriGrid = null;

/**
 * Initializes the Muuri grid for article layout.
 */
export function initMuuriGrid() {
    if (muuriGrid) {
        console.log("UIManager: Muuri grid already initialized, returning existing.");
        return muuriGrid;
    }
    
    console.log("UIManager: Initializing Muuri grid...");
    const container = document.getElementById('results-container');
    if (!container) {
        console.error("UIManager: results-container not found for Muuri initialization.");
        return null;
    }
    
    console.log("UIManager: Creating new Muuri grid on .results-grid");
    muuriGrid = new Muuri('.results-grid', {
        layoutOnInit: true,
        layoutOnResize: 150,
        layoutDuration: 300,
        layoutEasing: 'ease',
        dragEnabled: false,
        showDuration: 200,
        hideDuration: 200,
    });
    
    console.log("UIManager: Muuri grid initialized successfully.");
    return muuriGrid;
}

/**
 * Gets the Muuri grid instance.
 */
export function getMuuriGrid() {
    return muuriGrid;
}

/**
 * Triggers a Muuri layout refresh.
 */
export function refreshMuuriLayout() {
    if (muuriGrid) {
        requestAnimationFrame(() => {
            muuriGrid.refreshItems();
            muuriGrid.layout();
        });
    }
}

/**
 * Refreshes a specific Muuri item after its content changes.
 */
export function refreshMuuriItem(articleCard) {
    if (muuriGrid && articleCard) {
        const muuriItemEl = articleCard.closest('.muuri-item');
        if (muuriItemEl) {
            const muuriItem = muuriGrid.getItem(muuriItemEl);
            if (muuriItem) {
                muuriGrid.refreshItems([muuriItem]);
                muuriGrid.layout();
            } else {
                muuriGrid.refreshItems();
                muuriGrid.layout();
            }
        } else {
            muuriGrid.refreshItems();
            muuriGrid.layout();
        }
    }
}

// --- Toast Notifications ---
let toastContainer = null;

export function showToast(message, type = 'info', duration = 3000) {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-message">${message}</span>
        <button class="toast-close" aria-label="Close">&times;</button>
    `;

    toastContainer.appendChild(toast);

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => removeToast(toast));

    if (duration > 0) {
        setTimeout(() => removeToast(toast), duration);
    }

    return toast;
}

function removeToast(toast) {
    if (!toast.classList.contains('toast-exit')) {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 300);
    }
}

// --- DOM Element References ---
let resultsContainer, loadingIndicator, loadingText, infiniteScrollLoadingIndicator,
    activeTagFiltersDisplay, mobileActiveTagFiltersDisplay,
    mainFeedSection, setupSection, navMainBtn, navFavoritesBtn, navDeletedBtn, navSettingsBtn,
    navInEventsBtn, navIntelligenceBtn,
    regenerateSummaryModal, closeRegenerateModalBtn, modalArticleIdInput, modalSummaryPromptInput, modalUseDefaultPromptBtn,
    fullArticleModal, closeFullArticleModalBtn, fullArticleModalTitle, fullArticleModalBody, fullArticleModalOriginalLink;


/**
 * Handles read/unread toggle for an article.
 */
async function handleReadToggle(articleId, readBtn, articleCard) {
    const isCurrentlyRead = readBtn.classList.contains('is-read');
    
    try {
        if (isCurrentlyRead) {
            await apiService.markArticleUnread(articleId);
            readBtn.classList.remove('is-read');
            articleCard.classList.remove('is-read');
            readBtn.title = "Mark as read";
        } else {
            await apiService.markArticleRead(articleId);
            readBtn.classList.add('is-read');
            articleCard.classList.add('is-read');
            readBtn.title = "Mark as unread";
        }
        // Trigger Muuri layout after read state change (card height changes)
        if (muuriGrid) {
            const muuriItemEl = articleCard.closest('.muuri-item');
            if (muuriItemEl) {
                const muuriItem = muuriGrid.getItem(muuriItemEl);
                if (muuriItem) {
                    muuriGrid.refreshItems([muuriItem]);
                    muuriGrid.layout();
                } else {
                    console.warn('Muuri: Could not get item for read toggle');
                    muuriGrid.refreshItems();
                    muuriGrid.layout();
                }
            }
        }
    } catch (error) {
        console.error('Error toggling read state:', error);
        showToast('Error updating read state', 'error');
    }
}

/**
 * Handles archive for an article.
 */
async function handleArchiveArticle(articleId, articleCard) {
    try {
        await apiService.archiveArticle(articleId);
        console.log('Archive: API succeeded, hiding card', articleCard.id);
        
        if (muuriGrid) {
            console.log('Archive: muuriGrid exists, finding .muuri-item parent');
            const muuriItemEl = articleCard.closest('.muuri-item');
            console.log('Archive: muuriItemEl found:', muuriItemEl);
            if (muuriItemEl) {
                const muuriItem = muuriGrid.getItem(muuriItemEl);
                console.log('Archive: muuriItem (via getItem):', muuriItem);
                if (muuriItem) {
                    console.log('Archive: Calling muuriGrid.hide([muuriItem])');
                    muuriGrid.hide([muuriItem]);
                    console.log('Archive: hide() returned, waiting for animation then layout');
                    setTimeout(() => {
                        muuriGrid.layout();
                        console.log('Archive: layout() called after delay');
                    }, 250);
                } else {
                    console.error('Archive: muuriGrid.getItem() returned null');
                }
            } else {
                console.log('Archive: .muuri-item NOT found on card. Card classes:', articleCard.className);
                console.log('Archive: Card parent:', articleCard.parentElement);
            }
        } else {
            console.log('Archive: muuriGrid is NOT initialized');
        }
    } catch (error) {
        console.error('Error archiving article:', error);
    }
}


/**
 * Truncates text to a specified word limit.
 * @param {string} text - The text to truncate.
 * @param {number} wordLimit - The maximum number of words.
 * @returns {string} The truncated text with an ellipsis if it was shortened.
 */
function truncateText(text, wordLimit) {
    if (!text) return "";
    const words = text.trim().split(/\s+/);
    if (words.length <= wordLimit) {
        return text.trim();
    }
    return words.slice(0, wordLimit).join(" ") + "...";
}

/**
 * Initializes DOM references for UI elements.
 */
export function initializeUIDOMReferences() {
    resultsContainer = document.getElementById('results-container');
    loadingIndicator = document.getElementById('loading-indicator');
    loadingText = document.getElementById('loading-text');
    infiniteScrollLoadingIndicator = document.getElementById('infinite-scroll-loading-indicator');
    activeTagFiltersDisplay = document.getElementById('active-tag-filters-display');
    mobileActiveTagFiltersDisplay = document.getElementById('mobile-active-tag-filters-display');
    mainFeedSection = document.getElementById('main-feed-section');
    setupSection = document.getElementById('setup-section');
    navMainBtn = document.getElementById('nav-main-btn');
    navFavoritesBtn = document.getElementById('nav-favorites-btn');
    navDeletedBtn = document.getElementById('nav-deleted-btn');
    navSettingsBtn = document.getElementById('nav-settings-btn');
    navInEventsBtn = document.getElementById('nav-in-events-btn');
    navIntelligenceBtn = document.getElementById('nav-intelligence-btn');

    regenerateSummaryModal = document.getElementById('regenerate-summary-modal');
    closeRegenerateModalBtn = document.getElementById('close-regenerate-modal-btn');
    modalArticleIdInput = document.getElementById('modal-article-id-input'); 
    modalSummaryPromptInput = document.getElementById('modal-summary-prompt-input'); 
    modalUseDefaultPromptBtn = document.getElementById('modal-use-default-prompt-btn');

    fullArticleModal = document.getElementById('full-article-modal');
    closeFullArticleModalBtn = document.getElementById('close-full-article-modal-btn');
    fullArticleModalTitle = document.getElementById('full-article-modal-title');
    fullArticleModalBody = document.getElementById('full-article-modal-body');
    fullArticleModalOriginalLink = document.getElementById('full-article-modal-original-link');

    console.log("UIManager: DOM references initialized.");
    if (!resultsContainer) console.error("UIManager: results-container not found!");
    if (!fullArticleModal) console.warn("UIManager: full-article-modal not found!");
}

/**
 * Shows or hides the main loading indicator.
 */
export function showLoadingIndicator(show, message = "Loading...") {
    if (loadingIndicator && loadingText) {
        loadingText.textContent = message;
        loadingIndicator.style.display = show ? 'flex' : 'none';
    } else {
        console.warn("UIManager: Main loading indicator elements not found.");
    }
}

/**
 * Shows or hides the infinite scroll loading indicator.
 */
export function showInfiniteScrollLoadingIndicator(show) {
    if (infiniteScrollLoadingIndicator) {
        infiniteScrollLoadingIndicator.style.display = show ? 'flex' : 'none';
    } else {
        console.warn("UIManager: Infinite scroll loading indicator not found.");
    }
}

/**
 * Opens the Full Article Content modal and fetches/displays content.
 */
export async function openAndLoadFullArticleModal(articleId, articleTitle, originalUrl) {
    if (!fullArticleModal || !fullArticleModalTitle || !fullArticleModalBody || !fullArticleModalOriginalLink) {
        console.error("UIManager: Full article modal elements not found. Cannot open.");
        return;
    }

    fullArticleModalTitle.textContent = articleTitle || "Full Article";
    fullArticleModalBody.innerHTML = '<p class="loading-text-modal">Loading full article content...</p>'; 
    fullArticleModalOriginalLink.href = originalUrl || "#";
    fullArticleModalOriginalLink.textContent = "View Original on Publisher's Site";

    fullArticleModal.style.display = "block";
    console.log(`UIManager: Opening full article modal for article ID: ${articleId}`);

    try {
        const contentData = await apiService.fetchSanitizedArticleContent(articleId);
        fullArticleModalBody.innerHTML = ''; // Clear loading message
        if (contentData.error_message) {
            const errorP = document.createElement('p');
            errorP.classList.add('error-message');
            errorP.textContent = contentData.error_message;
            fullArticleModalBody.appendChild(errorP);
            console.warn(`UIManager: Error fetching sanitized content for article ${articleId}: ${contentData.error_message}`);
        } else if (contentData.sanitized_html_content) {
            // Assuming sanitized_html_content is already sanitized by the backend
            fullArticleModalBody.innerHTML = contentData.sanitized_html_content;
        } else {
            fullArticleModalBody.textContent = "Full article content could not be loaded or is empty.";
        }
        if(contentData.title) fullArticleModalTitle.textContent = contentData.title;
        if(contentData.original_url) fullArticleModalOriginalLink.href = contentData.original_url;

    } catch (error) {
        console.error(`UIManager: Failed to fetch or display sanitized content for article ${articleId}:`, error);
        fullArticleModalBody.innerHTML = ''; // Clear loading message
        const errorP = document.createElement('p');
        errorP.classList.add('error-message');
        errorP.textContent = `Error loading content: ${error.message}`;
        fullArticleModalBody.appendChild(errorP);
    }
}

/**
 * Closes the Full Article Content modal.
 */
export function closeFullArticleModal() {
    if (fullArticleModal) {
        fullArticleModal.style.display = "none";
        if(fullArticleModalBody) fullArticleModalBody.innerHTML = ''; 
    }
    console.log("UIManager: Full article modal closed.");
}


/**
 * Displays article results in the results container.
 */
export function displayArticleResults(articles, clearPrevious, onTagClickCallback, onRegenerateClickCallback, onFavoriteClickCallback, onSummarizeClickCallback) {
    if (!resultsContainer) {
        console.error("UIManager: resultsContainer is null! Cannot display articles.");
        return;
    }
    if (clearPrevious) {
        if (muuriGrid) {
            muuriGrid.remove(muuriGrid.getItems(), { removeElements: true });
        } else {
            resultsContainer.innerHTML = '';
        }
    }

    if (!articles || articles.length === 0) {
        console.log("UIManager: No new articles to display.");
        return;
    }

    const filteredArticles = articles.filter(article => {
        if (!article.is_summarizable) return false;
        if (state.activeView === 'favorites' && !article.is_favorite) return false;
        if (state.activeView === 'in_events' && article.event_ids && article.event_ids.length > 0) return false;
        return true;
    });

    filteredArticles.forEach((article) => {
        const articleCard = document.createElement('div');
        articleCard.classList.add('article-card');
        articleCard.setAttribute('id', `article-db-${article.id}`);
        
        if (article.is_read) {
            articleCard.classList.add('is-read');
        }

        // --- ICON PLACEMENT FIX ---
        // All card action buttons in one neat row
        const actionsRow = document.createElement('div');
        actionsRow.classList.add('card-actions-row');

        // Regenerate Summary button
        const regenButton = document.createElement('button');
        regenButton.classList.add('regenerate-summary-btn');
        regenButton.title = "Regenerate Summary";
        regenButton.onclick = () => {
            if (onRegenerateClickCallback && typeof onRegenerateClickCallback === 'function') {
                onRegenerateClickCallback(article.id);
            }
        };
        if (!article.is_summarizable) {
            regenButton.disabled = true;
            regenButton.title = "Not enough content to summarize";
        }
        actionsRow.appendChild(regenButton);

        // Direct Link icon
        const directLinkIcon = document.createElement('a');
        directLinkIcon.href = article.url;
        directLinkIcon.target = "_blank";
        directLinkIcon.rel = "noopener noreferrer";
        directLinkIcon.classList.add('direct-link-icon');
        directLinkIcon.title = "View Original Article";
        directLinkIcon.innerHTML = "&#128279;";
        actionsRow.appendChild(directLinkIcon);

        // Read checkbox button
        const readBtn = document.createElement('button');
        readBtn.classList.add('read-checkbox-btn');
        readBtn.title = article.is_read ? "Mark as unread" : "Mark as read";
        if (article.is_read) {
            readBtn.classList.add('is-read');
        }
        readBtn.onclick = (e) => {
            e.stopPropagation();
            handleReadToggle(article.id, readBtn, articleCard);
        };
        actionsRow.appendChild(readBtn);

        // Delete button
        const deleteBtn = document.createElement('button');
        deleteBtn.classList.add('delete-article-btn');
        deleteBtn.title = "Archive";
        deleteBtn.innerHTML = '📦';
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            handleArchiveArticle(article.id, articleCard);
        };
        actionsRow.appendChild(deleteBtn);

        // Favorite button
        const favoriteBtn = document.createElement('button');
        favoriteBtn.classList.add('favorite-btn');
        if (article.is_favorite) {
            favoriteBtn.classList.add('is-favorite');
        }
        favoriteBtn.title = article.is_favorite ? "Remove from favorites" : "Add to favorites";
        favoriteBtn.innerHTML = '&#9733;';
        favoriteBtn.onclick = (e) => {
            e.stopPropagation();
            if (onFavoriteClickCallback && typeof onFavoriteClickCallback === 'function') {
                onFavoriteClickCallback(article.id, favoriteBtn);
            }
        };
        actionsRow.appendChild(favoriteBtn);

        // Add to Event button
        const addToEventBtn = document.createElement('button');
        addToEventBtn.classList.add('add-to-event-btn');
        addToEventBtn.title = "Add to Event";
        addToEventBtn.innerHTML = '&#9978;';
        addToEventBtn.onclick = (e) => {
            e.stopPropagation();
            showAddToEventDropdown(article.id, addToEventBtn, article.event_ids || []);
        };
        actionsRow.appendChild(addToEventBtn);

        if (article.event_ids?.length > 0) {
            const eventCount = article.event_ids.length;
            const eventIndicator = document.createElement('span');
            eventIndicator.classList.add('event-indicator');
            if (eventCount === 1 && article.event_names?.[0]) {
                eventIndicator.textContent = article.event_names[0];
            } else if (eventCount >= 2) {
                eventIndicator.textContent = '2+ events';
            }
            actionsRow.appendChild(eventIndicator);
        }

        articleCard.appendChild(actionsRow);

        const titleRow = document.createElement('div');
        titleRow.classList.add('article-title-row');

        const titleEl = document.createElement('h3');
        titleEl.textContent = article.title || 'No Title Provided';
        titleEl.style.cursor = 'pointer';
        titleEl.onclick = () => {
            if (articleCard.classList.contains('is-read')) {
                handleReadToggle(article.id, readBtn, articleCard);
            }
        };
        titleRow.appendChild(titleEl);

        const collapsedDeleteBtn = document.createElement('button');
        collapsedDeleteBtn.classList.add('collapsed-delete-btn');
        collapsedDeleteBtn.title = "Archive";
        collapsedDeleteBtn.innerHTML = '📦';
        collapsedDeleteBtn.onclick = (e) => {
            e.stopPropagation();
            handleArchiveArticle(article.id, articleCard);
        };
        titleRow.appendChild(collapsedDeleteBtn);

        articleCard.appendChild(titleRow);

        const metaInfo = document.createElement('div');
        metaInfo.classList.add('article-meta-info');
        if (article.publisher) {
            const p = document.createElement('span');
            p.classList.add('article-publisher');
            p.textContent = `Source: ${article.publisher}`;
            metaInfo.appendChild(p);
        }
        if (article.published_date) {
            const d = document.createElement('span');
            d.classList.add('article-published-date');
            try {
                d.textContent = `Published: ${new Date(article.published_date).toLocaleString(undefined, { year: 'numeric', month: 'long', day: 'numeric', hour: 'numeric', minute: 'numeric' })}`;
            } catch (e) {
                d.textContent = `Published: ${article.published_date}`;
            }
            metaInfo.appendChild(d);
        }
        if (metaInfo.hasChildNodes()) articleCard.appendChild(metaInfo);

        const readFullArticleBtn = document.createElement('button');
        let buttonText = 'Read Full Article (In-App)';
        // As an informational feature, display word count if available
        if (article.word_count != null) {
            buttonText = `Read Full Article (${article.word_count} words)`;
        }
        readFullArticleBtn.textContent = buttonText;
        readFullArticleBtn.classList.add('read-full-article-btn');
        readFullArticleBtn.onclick = () => openAndLoadFullArticleModal(article.id, article.title, article.url);
        articleCard.appendChild(readFullArticleBtn);

        const summaryContainer = document.createElement('div');
        summaryContainer.classList.add('summary');
        summaryContainer.setAttribute('id', `summary-text-${article.id}`);

        if (article.summary) {
            summaryContainer.innerHTML = (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined')
                ? DOMPurify.sanitize(marked.parse(article.summary))
                : article.summary;
        } else {
            const descriptionP = document.createElement('p');
            descriptionP.classList.add('content-snippet'); // Re-using class for styling
            const truncatedDescription = truncateText(article.rss_description, 100);
            descriptionP.textContent = truncatedDescription || "No summary or description available.";
            summaryContainer.appendChild(descriptionP);

            const summarizeBtn = document.createElement('button');
            summarizeBtn.textContent = 'Summarize with AI';
            summarizeBtn.classList.add('summarize-ai-btn');
            summarizeBtn.onclick = () => {
                // Use the new, specific callback for this button
                if (onSummarizeClickCallback && typeof onSummarizeClickCallback === 'function') {
                    onSummarizeClickCallback(article.id);
                }
            };
            if (!article.is_summarizable) {
                summarizeBtn.disabled = true;
            }
            summaryContainer.appendChild(summarizeBtn);
        }
        articleCard.appendChild(summaryContainer);

        // Always create the tags container for future updates
        const tagsContainer = document.createElement('div');
        tagsContainer.classList.add('article-tags-container');
        tagsContainer.setAttribute('id', `tags-container-${article.id}`);
        articleCard.appendChild(tagsContainer);

        if (article.tags && article.tags.length > 0) {
            article.tags.forEach(tag => {
                const tagEl = document.createElement('span');
                tagEl.classList.add('article-tag');
                tagEl.textContent = tag.name;
                tagEl.setAttribute('data-tag-id', tag.id.toString());
                tagEl.setAttribute('data-tag-name', tag.name);
                if (state.activeTagFilterIds.some(activeTag => activeTag.id === tag.id)) {
                    tagEl.classList.add('active-filter-tag');
                }
                tagEl.onclick = () => {
                    if (onTagClickCallback && typeof onTagClickCallback === 'function') {
                        onTagClickCallback(tag.id, tag.name);
                    }
                };
                tagsContainer.appendChild(tagEl);
            });
        }

        if (article.error_message && !article.summary) {
            const err = document.createElement('p');
            err.classList.add('error-message');
            if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                err.innerHTML = DOMPurify.sanitize(marked.parse(article.error_message));
            } else {
                err.textContent = article.error_message; // Safe fallback
            }
            articleCard.appendChild(err);
        }

        const openChatBtn = document.createElement('button');
        openChatBtn.classList.add('open-chat-modal-btn');
        openChatBtn.textContent = 'Chat about this article';
        if (article.has_chat_history) {
            openChatBtn.classList.add('has-chat-history');
            openChatBtn.title = 'You have chatted about this article before';
        }
        openChatBtn.onclick = () => chatHandler.openArticleChatModal(article);
        if (!article.is_summarizable) {
            openChatBtn.disabled = true;
        }
        articleCard.appendChild(openChatBtn);

        // Wrap in Muuri structure
        const itemWrapper = document.createElement('div');
        itemWrapper.classList.add('muuri-item');
        itemWrapper.setAttribute('data-id', article.id);

        const contentWrapper = document.createElement('div');
        contentWrapper.classList.add('muuri-item-content');

        itemWrapper.appendChild(contentWrapper);
        contentWrapper.appendChild(articleCard);

        if (muuriGrid) {
            muuriGrid.add(itemWrapper, { layout: false });
        } else {
            resultsContainer.appendChild(itemWrapper);
        }
    });
    
    // After all cards are added, trigger a layout
    if (muuriGrid) {
        muuriGrid.layout();
    }
}

let feedFilterSelect = null;

export function initializeFeedFilterDropdown() {
    feedFilterSelect = document.getElementById('feed-filter-select');
    return feedFilterSelect;
}

export function populateFeedFilterDropdown() {
    if (!feedFilterSelect) {
        feedFilterSelect = initializeFeedFilterDropdown();
    }
    if (!feedFilterSelect) return;

    feedFilterSelect.innerHTML = '<option value="">Select a feed...</option>';
    
    const userFeedSourceIds = new Set(state.userFeeds?.map(uf => uf.feed_source_id) || []);
    
    state.dbFeedSources.forEach(feed => {
        if (!userFeedSourceIds.has(feed.id)) return;
        
        const option = document.createElement('option');
        option.value = feed.id.toString();
        const userFeed = state.userFeeds?.find(uf => uf.feed_source_id === feed.id);
        const customName = userFeed?.custom_name;
        let displayName = customName || feed.name || (feed.url ? feed.url.split('/')[2]?.replace(/^www\./, '') : 'Unknown Feed');
        if (displayName.length > 40) displayName = displayName.substring(0, 37) + "...";
        option.textContent = displayName;
        option.title = feed.url;
        feedFilterSelect.appendChild(option);
    });
}

export function updateFeedFilterDropdownSelection() {
    if (!feedFilterSelect) {
        feedFilterSelect = initializeFeedFilterDropdown();
    }
    if (!feedFilterSelect) return;
    feedFilterSelect.value = '';
}

export function updateFeedFilterButtonStyles() {
    // Deprecated - feed filter now uses dropdown, no button styles to update
}

/**
 * Updates the visual style of the main navigation buttons (Main, Favorites, Deleted, Settings).
 */
export function updateNavButtonStyles() {
    const buttons = [navMainBtn, navFavoritesBtn, navDeletedBtn, navSettingsBtn, navInEventsBtn, navIntelligenceBtn];
    
    buttons.forEach(btn => {
        if (btn) btn.classList.remove('active');
    });

    const currentVisibleSection = document.querySelector('.content-section.active');
    if (currentVisibleSection) {
        if (currentVisibleSection.id === 'setup-section') {
            if (navSettingsBtn) navSettingsBtn.classList.add('active');
            return;
        }
        if (currentVisibleSection.id === 'admin-section') {
            if (navSettingsBtn) navSettingsBtn.classList.add('active');
            return;
        }
        if (currentVisibleSection.id === 'intelligence-section') {
            if (navIntelligenceBtn) navIntelligenceBtn.classList.add('active');
            return;
        }
    }

    if (state.activeView === 'main') {
        if (navMainBtn) navMainBtn.classList.add('active');
    } else if (state.activeView === 'favorites') {
        if (navFavoritesBtn) navFavoritesBtn.classList.add('active');
    } else if (state.activeView === 'deleted') {
        if (navDeletedBtn) navDeletedBtn.classList.add('active');
    } else if (state.activeView === 'in_events') {
        if (navInEventsBtn) navInEventsBtn.classList.add('active');
    } else if (state.activeView === 'intelligence') {
        if (navIntelligenceBtn) navIntelligenceBtn.classList.add('active');
    }
}


/**
 * Updates the UI to display active tag filters.
 */
export function updateActiveTagFiltersUI(onRemoveTagFilterCallback, onClearAllFiltersCallback) {
    if (!activeTagFiltersDisplay) {
        console.warn("UIManager: activeTagFiltersDisplay element not found.");
        return;
    }
    activeTagFiltersDisplay.innerHTML = '';
    if (mobileActiveTagFiltersDisplay) {
        mobileActiveTagFiltersDisplay.innerHTML = '';
    }
    
    if (state.activeTagFilterIds.length === 0) {
        activeTagFiltersDisplay.style.display = 'none';
        if (mobileActiveTagFiltersDisplay) {
            mobileActiveTagFiltersDisplay.style.display = 'none';
        }
        return;
    }
    
    const createFilterContent = (container) => {
        const heading = document.createElement('span');
        heading.textContent = 'Filtered by: ';
        heading.style.fontWeight = 'bold';
        container.appendChild(heading);
        
        state.activeTagFilterIds.forEach(tagObj => {
            const tagSpan = document.createElement('span');
            tagSpan.classList.add('active-tag-filter');
            tagSpan.textContent = tagObj.name;
            const removeBtn = document.createElement('span');
            removeBtn.classList.add('remove-tag-filter-btn');
            removeBtn.textContent = '×';
            removeBtn.title = `Remove filter: ${tagObj.name}`;
            removeBtn.onclick = () => {
                if (onRemoveTagFilterCallback && typeof onRemoveTagFilterCallback === 'function') {
                    onRemoveTagFilterCallback(tagObj.id);
                }
            };
            tagSpan.appendChild(removeBtn);
            container.appendChild(tagSpan);
        });
        
        if (state.activeTagFilterIds.length > 1) {
            const clearAllBtn = document.createElement('button');
            clearAllBtn.classList.add('clear-all-filters-btn');
            clearAllBtn.textContent = 'Clear all';
            clearAllBtn.style.marginLeft = '10px';
            clearAllBtn.style.padding = '3px 8px';
            clearAllBtn.style.fontSize = '0.85em';
            clearAllBtn.style.cursor = 'pointer';
            clearAllBtn.onclick = () => {
                if (onClearAllFiltersCallback && typeof onClearAllFiltersCallback === 'function') {
                    onClearAllFiltersCallback();
                }
            };
            container.appendChild(clearAllBtn);
        }
    };
    
    activeTagFiltersDisplay.style.display = 'block';
    createFilterContent(activeTagFiltersDisplay);
    
    if (mobileActiveTagFiltersDisplay) {
        mobileActiveTagFiltersDisplay.style.display = 'flex';
        createFilterContent(mobileActiveTagFiltersDisplay);
    }
}

/**
 * Shows a specific section.
 */
export function showSection(sectionId) {
    document.querySelectorAll('.content-section').forEach(section => {
        section.classList.remove('active');
    });

    const sectionToShow = document.getElementById(sectionId);
    if (sectionToShow) {
        sectionToShow.classList.add('active');
    } else {
        console.error(`UIManager: Section with ID '${sectionId}' not found.`);
        if (mainFeedSection) mainFeedSection.classList.add('active');
    }

    updateNavButtonStyles();
    console.log(`UIManager: Switched to section: ${sectionId}`);
}

/**
 * Opens the regenerate summary modal.
 */
export function openRegenerateSummaryModal(articleId) {
    if (!regenerateSummaryModal || !modalArticleIdInput || !modalSummaryPromptInput) {
        console.error("UIManager: Regenerate summary modal elements not found. Cannot open.");
        return;
    }
    modalArticleIdInput.value = articleId.toString();
    modalSummaryPromptInput.value = state.currentSummaryPrompt || state.defaultSummaryPrompt;
    regenerateSummaryModal.style.display = "block";
    console.log(`UIManager: Opened regenerate summary modal for article ID: ${articleId}`);
}

/**
 * Closes the regenerate summary modal.
 */
export function closeRegenerateSummaryModal() {
    if (regenerateSummaryModal) {
        regenerateSummaryModal.style.display = "none";
    }
    console.log("UIManager: Regenerate summary modal closed.");
}

/**
 * Sets up basic event listeners for UI elements managed by UIManager.
 */
export function setupUIManagerEventListeners(onRegenerateModalUseDefaultPrompt) {
    if (closeRegenerateModalBtn) {
        closeRegenerateModalBtn.onclick = closeRegenerateSummaryModal;
    }
    if (modalUseDefaultPromptBtn && typeof onRegenerateModalUseDefaultPrompt === 'function') {
        modalUseDefaultPromptBtn.onclick = onRegenerateModalUseDefaultPrompt;
    }
    window.addEventListener('click', function(event) {
        if (regenerateSummaryModal && event.target === regenerateSummaryModal) {
            closeRegenerateSummaryModal();
        }
        if (fullArticleModal && event.target === fullArticleModal) {
            closeFullArticleModal();
        }
    });
    if (closeFullArticleModalBtn) {
        closeFullArticleModalBtn.onclick = closeFullArticleModal;
    }
    // The main nav buttons are now handled in script.js
    console.log("UIManager: Basic event listeners set up.");
}

/**
 * Updates a specific article card with new data (summary and tags).
 * This is more efficient than re-rendering the whole feed.
 * @param {object} article - The updated article object from the API.
 * @param {function} onTagClickCallback - The callback function to handle tag clicks.
 */
export function updateArticleCard(article, onTagClickCallback) {
    if (!article || !article.id) {
        console.error("UIManager: updateArticleCard called with invalid article data.");
        return;
    }

    const articleCard = document.getElementById(`article-db-${article.id}`);
    if (!articleCard) {
        console.warn(`UIManager: Could not find article card with ID article-db-${article.id} to update.`);
        return;
    }

    // Update Summary
    const summaryContainer = articleCard.querySelector(`#summary-text-${article.id}`);
    if (summaryContainer) {
        if (article.summary) {
            summaryContainer.innerHTML = (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined')
                ? DOMPurify.sanitize(marked.parse(article.summary))
                : article.summary;
        } else {
            // If the summary is empty after regeneration, show an error or a message.
            summaryContainer.innerHTML = `<p class="error-message">Could not generate a summary.</p>`;
        }
        if (article.error_message) {
            const errorP = document.createElement('p');
            errorP.classList.add('error-message');
            if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                errorP.innerHTML = DOMPurify.sanitize(marked.parse(article.error_message));
            } else {
                errorP.textContent = article.error_message; // Safe fallback
            }
            summaryContainer.appendChild(errorP);
        }
    }

    // Update Tags
    const tagsContainer = articleCard.querySelector(`#tags-container-${article.id}`);
    if (tagsContainer) {
        tagsContainer.innerHTML = ''; // Clear existing tags
        if (article.tags && article.tags.length > 0) {
            article.tags.forEach(tag => {
                const tagEl = document.createElement('span');
                tagEl.classList.add('article-tag');
                tagEl.textContent = tag.name;
                tagEl.setAttribute('data-tag-id', tag.id.toString());
                tagEl.setAttribute('data-tag-name', tag.name);
                if (state.activeTagFilterIds.some(activeTag => activeTag.id === tag.id)) {
                    tagEl.classList.add('active-filter-tag');
                }
                tagEl.onclick = () => {
                    if (onTagClickCallback && typeof onTagClickCallback === 'function') {
                        onTagClickCallback(tag.id, tag.name);
                    }
                };
                tagsContainer.appendChild(tagEl);
            });
        }
    }

    console.log(`UIManager: Successfully updated article card for ID ${article.id}.`);
}


/**
 * Sets the content of the results container.
 */
export function setResultsContainerContent(htmlContent) {
    if (resultsContainer) {
        resultsContainer.innerHTML = htmlContent;
    } else {
        console.error("UIManager: resultsContainer not found, cannot set content.");
    }
}

let activeAddToEventDropdown = null;
let activeDropdownArticleId = null;
let activeDropdownButtonElement = null;
let activeDropdownEventIds = null;

export async function showAddToEventDropdown(articleId, buttonElement, articleEventIds = []) {
    closeAddToEventDropdown();
    activeDropdownArticleId = articleId;
    activeDropdownButtonElement = buttonElement;
    activeDropdownEventIds = articleEventIds || [];

    try {
        const events = await eventApi.fetchEvents();

        const dropdown = document.createElement('div');
        dropdown.className = 'add-to-event-dropdown';
        dropdown.innerHTML = '<div class="dropdown-header">Add to Event</div>';

        if (events.length === 0) {
            dropdown.innerHTML += '<div class="dropdown-empty">No events yet. Create one in Intelligence.</div>';
        } else {
            events.forEach(event => {
                const isInEvent = activeDropdownEventIds.includes(event.id);
                const item = document.createElement('div');
                item.className = 'dropdown-item' + (isInEvent ? ' checked' : '');
                item.innerHTML = (isInEvent ? '✓ ' : '+ ') + event.name;
                item.onclick = async () => {
                    try {
                        if (isInEvent) {
                            await eventApi.removeArticleFromEvent(event.id, articleId);
                            showToast(`Removed from "${event.name}"`, 'success');
                            activeDropdownEventIds = activeDropdownEventIds.filter(id => id !== event.id);
                            if (activeDropdownEventIds.length === 0 && activeDropdownButtonElement) {
                                activeDropdownButtonElement.classList.remove('has-events');
                            }
                        } else {
                            await eventApi.addArticlesToEvent(event.id, [articleId]);
                            showToast(`Added to "${event.name}"`, 'success');
                            activeDropdownEventIds.push(event.id);
                            if (activeDropdownButtonElement) {
                                activeDropdownButtonElement.classList.add('has-events');
                            }
                        }
                        updateArticleCardEventIds(articleId, activeDropdownEventIds);
                    } catch (error) {
                        console.error('Error updating article event:', error);
                        showToast('Failed to update article event', 'error');
                    }
                    closeAddToEventDropdown();
                };
                dropdown.appendChild(item);
            });
        }

        const rect = buttonElement.getBoundingClientRect();
        dropdown.style.position = 'absolute';
        dropdown.style.top = `${rect.bottom + window.scrollY + 5}px`;
        dropdown.style.left = `${rect.left + window.scrollX}px`;
        dropdown.style.zIndex = '1000';

        document.body.appendChild(dropdown);
        activeAddToEventDropdown = dropdown;

        setTimeout(() => {
            document.addEventListener('click', closeAddToEventDropdownOnClickOutside, { once: true });
        }, 0);

    } catch (error) {
        console.error('Error fetching events for dropdown:', error);
        showToast('Failed to load events', 'error');
    }
}

function updateArticleCardEventIds(articleId, eventIds) {
    const articleCard = document.getElementById(`article-db-${articleId}`);
    if (articleCard) {
        articleCard.dataset.eventIds = JSON.stringify(eventIds);
    }
}

function closeAddToEventDropdownOnClickOutside(event) {
    const dropdown = document.querySelector('.add-to-event-dropdown');
    if (dropdown && !dropdown.contains(event.target) && !event.target.classList.contains('add-to-event-btn')) {
        closeAddToEventDropdown();
    }
}

export function closeAddToEventDropdown() {
    if (activeAddToEventDropdown) {
        activeAddToEventDropdown.remove();
        activeAddToEventDropdown = null;
    }
}

console.log("frontend/js/uiManager.js: Module loaded.");
