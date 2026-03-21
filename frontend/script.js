// frontend/script.js (Main Orchestrator)
import * as state from './js/state.js';
import * as apiService from './js/apiService.js';
import * as configManager from './js/configManager.js';
import * as uiManager from './js/uiManager.js';
import * as chatHandler from './js/chatHandler.js';
import * as feedHandler from './js/feedHandler.js';
import { initDebugManager, showDebugPanel } from './js/debugManager.js';
import * as eventManager from './js/intelligence/eventManager.js';

/**
 * Main script for the NewsAI frontend.
 * Orchestrates all modules and handles core application logic.
 */

// --- DOM Element References (for elements directly handled by this main script) ---
let refreshNewsBtn, keywordSearchInput, keywordSearchBtn,
    regeneratePromptForm;

// --- Auth DOM References ---
let loginModal, registerModal, deleteAccountModal,
    navLoginBtn, navRegisterBtn, logoutBtn, deleteAccountBtn,
    authButtons, userMenu, userEmail,
    loginForm, registerForm, deleteAccountForm;

// --- Polling Configuration ---
const POLLING_INTERVAL_MS = 120000; // Check for new articles every 2 minutes (120,000 ms)
let pollingIntervalId = null;

// --- Main Application Logic ---

async function fetchAndDisplaySummaries(forceBackendRssRefresh = false, page = state.currentPage, keyword = state.currentKeywordSearch, isPollRefresh = false) {
    console.log(`MainScript: fetchAndDisplaySummaries called. Page: ${page}, Keyword: ${keyword}, IsPoll: ${isPollRefresh}, FeedFilters: ${JSON.stringify(state.activeFeedFilterIds)}, TagFilters: ${JSON.stringify(state.activeTagFilterIds.map(t=>t.id))}`);
    
    if (page === 1) { 
        state.setCurrentPage(1); 
    }
    state.setIsLoadingMoreArticles(true);

    const loadingMessageParts = [];
    if (state.activeFeedFilterIds.length > 0) {
        const feedNames = state.activeFeedFilterIds.map(id => {
            const feed = state.dbFeedSources.find(f => f.id === id);
            const userFeed = state.userFeeds?.find(uf => uf.feed_source_id === id);
            const customName = userFeed?.custom_name;
            return customName || (feed ? (feed.name || feed.url.split('/')[2]?.replace(/^www\./, '')) : `ID ${id}`);
        }).join(', ');
        loadingMessageParts.push(`Feeds: ${feedNames}`);
    }
    if (state.activeTagFilterIds.length > 0) {
        loadingMessageParts.push(`Tags: ${state.activeTagFilterIds.map(t => t.name).join(', ')}`);
    }
    if (keyword) {
        loadingMessageParts.push(`Keyword: "${keyword}"`);
    }
    const activeFilterDisplay = loadingMessageParts.length > 0 ? loadingMessageParts.join(' & ') : "All Articles";
    
    if (page === 1 && !isPollRefresh) { 
        uiManager.showLoadingIndicator(true, `Fetching page ${state.currentPage} for ${activeFilterDisplay}...`);
    } else if (page > 1) {
        uiManager.showInfiniteScrollLoadingIndicator(true);
    }

    const payload = {
        page: state.currentPage,
        page_size: state.articlesPerPage,
        feed_source_ids: state.activeFeedFilterIds.length > 0 ? state.activeFeedFilterIds : null,
        tag_ids: state.activeTagFilterIds.length > 0 ? state.activeTagFilterIds.map(t => t.id) : null,
        keyword: keyword || null,
        summary_prompt: (state.currentSummaryPrompt !== state.defaultSummaryPrompt) ? state.currentSummaryPrompt : null,
        tag_generation_prompt: (state.currentTagGenerationPrompt !== state.defaultTagGenerationPrompt) ? state.currentTagGenerationPrompt : null,
        favorites_only: state.activeView === 'favorites',
    };

    try {
        // apiService.fetchNewsSummaries will use state.SUMMARIES_API_ENDPOINT which is set by configManager
        const data = await apiService.fetchNewsSummaries(payload); 
        console.log("MainScript: Received data from fetchNewsSummaries:", data);

        if (page === 1) { 
            state.setTotalArticlesAvailable(data.total_articles_available); 
        }
        state.setTotalPages(data.total_pages);

        uiManager.displayArticleResults(
            data.processed_articles_on_page,
            page === 1,
            handleArticleTagClick,
            uiManager.openRegenerateSummaryModal,
            handleFavoriteClick,
            handleDirectSummarize // Pass the new handler
        );

        if (page === 1 && data.processed_articles_on_page && data.processed_articles_on_page.length > 0) {
            const newestArticleInBatch = data.processed_articles_on_page.reduce((latest, article) => {
                if (!article.created_at) return latest; 
                const articleDate = new Date(article.created_at);
                return (latest === null || articleDate > latest) ? articleDate : latest;
            }, null);
            if (newestArticleInBatch) {
                if (!state.lastKnownLatestArticleTimestamp || newestArticleInBatch > new Date(state.lastKnownLatestArticleTimestamp)) {
                    state.setLastKnownLatestArticleTimestamp(newestArticleInBatch.toISOString());
                    console.log("MainScript: Updated lastKnownLatestArticleTimestamp to:", state.lastKnownLatestArticleTimestamp);
                }
            }
        }

        if (page === 1 && data.processed_articles_on_page.length === 0 && data.total_articles_available === 0) {
            let noResultsMessage = `<div class="empty-state"><span class="empty-state-icon">📰</span><p>No articles found for the current filter (${activeFilterDisplay}).</p></div>`;
            if (state.dbFeedSources.length === 0 && state.activeTagFilterIds.length === 0 && !keyword) {
                noResultsMessage = `<div class="empty-state"><span class="empty-state-icon">📡</span><p>No RSS feeds configured.</p><p><a href="#" onclick="document.getElementById('nav-settings-btn').click(); return false;">Add your first feed in Settings</a></p></div>`;
            }
            uiManager.setResultsContainerContent(noResultsMessage);
        }
        
        if (isPollRefresh && page === 1 && data.processed_articles_on_page.length > 0) {
            console.log("MainScript: New articles loaded via polling.");
        }

    } catch (error) {
        console.error('MainScript: Error fetching or displaying summaries:', error);
        if (page === 1 && !isPollRefresh) {
            const errorP = document.createElement('p');
            errorP.classList.add('error-message');
            errorP.textContent = `Error fetching summaries: ${error.message}.`;
            const resultsContainer = document.getElementById('results-container');
            if (resultsContainer) {
                resultsContainer.innerHTML = '';
                resultsContainer.appendChild(errorP);
            }
        } else if (page > 1) {
            const resultsContainer = document.getElementById('results-container');
            if (resultsContainer) {
                const errorP = document.createElement('p');
                errorP.classList.add('error-message');
                errorP.textContent = `Error fetching more articles: ${error.message}`;
                resultsContainer.appendChild(errorP);
            }
        }
        state.setTotalPages(state.currentPage); 
    } finally {
        state.setIsLoadingMoreArticles(false);
        if (!isPollRefresh || page > 1) { 
            uiManager.showLoadingIndicator(false);
        }
        uiManager.showInfiniteScrollLoadingIndicator(false);
        console.log("MainScript: fetchAndDisplaySummaries finished.");
    }
}

async function pollForNewArticles() {
    console.log("MainScript: Polling for new articles. Last known timestamp:", state.lastKnownLatestArticleTimestamp);
    try {
        const pollData = await apiService.checkNewArticles(state.lastKnownLatestArticleTimestamp);
        console.log("MainScript: Poll response:", pollData);
        if (pollData.new_articles_available) {
            console.log(`MainScript: New articles available (Count: ${pollData.article_count}). New server latest_article_timestamp: ${pollData.latest_article_timestamp}. Refreshing view.`);
            // When new articles are found via polling, refresh the view starting from page 1,
            // clearing current keyword search to show all new articles.
            // Pass 'true' for isPollRefresh to potentially alter UI feedback (e.g., no full-page loader).
            if (keywordSearchInput) keywordSearchInput.value = ''; // Clear search UI
            state.setCurrentKeywordSearch(null); // Clear keyword state
            await fetchAndDisplaySummaries(false, 1, null, true); 
        } else {
            console.log("MainScript: No new articles detected by polling. Current server latest_article_timestamp:", pollData.latest_article_timestamp);
        }
        // Always update our knowledge of the server's latest timestamp
        if (pollData.latest_article_timestamp) {
             if (!state.lastKnownLatestArticleTimestamp || new Date(pollData.latest_article_timestamp) > new Date(state.lastKnownLatestArticleTimestamp)) {
                state.setLastKnownLatestArticleTimestamp(pollData.latest_article_timestamp);
                console.log("MainScript: Polling updated lastKnownLatestArticleTimestamp to server's latest:", state.lastKnownLatestArticleTimestamp);
            }
        }
    } catch (error) {
        console.error("MainScript: Error during polling:", error);
    }
}

async function initializeAppSettings() {
    console.log("MainScript: Initializing application settings...");
    initializeAllDOMReferences();
    uiManager.initMuuriGrid();
    uiManager.showLoadingIndicator(true, "Initializing application...");
    try {
        const initialBackendConfig = await apiService.fetchInitialConfigData();
        console.log("MainScript: Initial backend config fetched:", initialBackendConfig);
        
        // configManager.loadConfigurations now handles setting API endpoints in apiService
        configManager.loadConfigurations(initialBackendConfig); 
        
        state.setDbFeedSources(initialBackendConfig.all_db_feed_sources || []);

        // With feeds loaded from initial-config, we can now render them directly from state
        // without another API call. This is part of the fix for the disappearing articles bug.
        await feedHandler.renderFeedsFromState();
        uiManager.populateFeedFilterDropdown();
        uiManager.initializeFeedFilterDropdown();

        uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters); 
        uiManager.showSection('main-feed-section'); 

        if (state.dbFeedSources.length > 0 || state.activeTagFilterIds.length > 0 || state.currentKeywordSearch) {
            await fetchAndDisplaySummaries(false, 1, state.currentKeywordSearch);
        } else {
            uiManager.setResultsContainerContent('<div class="empty-state"><span class="empty-state-icon">📡</span><p>No RSS feeds configured.</p><p><a href="#" onclick="document.getElementById(\'nav-settings-btn\').click(); return false;">Add your first feed in Settings</a></p></div>');
        }

        if (pollingIntervalId) clearInterval(pollingIntervalId); 
        await pollForNewArticles(); // Initial poll immediately after setup
        pollingIntervalId = setInterval(pollForNewArticles, POLLING_INTERVAL_MS);
        console.log(`MainScript: Started polling for new articles every ${POLLING_INTERVAL_MS / 1000} seconds.`);

    } catch (error) { 
        console.error("MainScript: Error during application initialization:", error);
        const errorP = document.createElement('p');
        errorP.classList.add('error-message');
        errorP.textContent = `Failed to initialize application: ${error.message}`;
        const resultsContainer = document.getElementById('results-container');
        if (resultsContainer) {
            resultsContainer.innerHTML = '';
            resultsContainer.appendChild(errorP);
        }
    }
    finally { uiManager.showLoadingIndicator(false); }
    console.log("MainScript: Application settings initialization finished.");
}

function handleArticleTagClick(tagId, tagName) {
    console.log(`MainScript: Tag clicked - ID: ${tagId}, Name: ${tagName}`);
    const tagIndex = state.activeTagFilterIds.findIndex(t => t.id === tagId);
    if (tagIndex > -1) { state.removeActiveTagFilter(tagId); } 
    else { state.addActiveTagFilter({ id: tagId, name: tagName }); }
    state.setActiveFeedFilterIds([]);
    state.setCurrentKeywordSearch(null);
    state.setActiveView('main');
    const keywordInput = document.getElementById('keyword-search-input'); // Get ref here
    if(keywordInput) keywordInput.value = ''; 
    uiManager.updateFeedFilterButtonStyles();
    uiManager.updateNavButtonStyles();
    uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters); 
    state.setCurrentPage(1);
    fetchAndDisplaySummaries(false, 1, null); 
}

function handleRemoveTagFilter(tagIdToRemove) {
    console.log(`MainScript: Removing tag filter for ID: ${tagIdToRemove}`);
    state.removeActiveTagFilter(tagIdToRemove);
    uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters); 
    document.querySelectorAll(`.article-tag[data-tag-id='${tagIdToRemove}']`).forEach(el => el.classList.remove('active-filter-tag'));
    state.setCurrentPage(1);
    fetchAndDisplaySummaries(false, 1, state.currentKeywordSearch);
}

function handleClearAllFilters() {
    console.log('MainScript: Clearing all filters');
    state.activeTagFilterIds = [];
    state.activeFeedFilterIds = [];
    state.setCurrentKeywordSearch(null);
    state.setActiveView('main');
    
    const keywordInput = document.getElementById('keyword-search-input');
    if (keywordInput) keywordInput.value = '';
    
    const tagSearchInput = document.getElementById('tag-search-input');
    if (tagSearchInput) tagSearchInput.value = '';
    
    document.querySelectorAll('.article-tag.active-filter-tag').forEach(el => el.classList.remove('active-filter-tag'));
    
    uiManager.updateFeedFilterButtonStyles();
    uiManager.updateFeedFilterDropdownSelection();
    uiManager.updateNavButtonStyles();
    uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters);
    state.setCurrentPage(1);
    fetchAndDisplaySummaries(false, 1, null);
}

function handleTagSearchSelect(tagId, tagName) {
    console.log(`MainScript: Tag search selected - ID: ${tagId}, Name: ${tagName}`);
    const tagSearchInput = document.getElementById('tag-search-input');
    const tagSearchResults = document.getElementById('tag-search-results');
    
    if (tagSearchInput) tagSearchInput.value = '';
    if (tagSearchResults) {
        tagSearchResults.classList.remove('visible');
        tagSearchResults.innerHTML = '';
    }
    state.clearTagSearch();
    
    state.addActiveTagFilter({ id: tagId, name: tagName });
    state.setActiveFeedFilterIds([]);
    state.setCurrentKeywordSearch(null);
    state.setActiveView('main');
    
    const keywordInput = document.getElementById('keyword-search-input');
    if (keywordInput) keywordInput.value = '';
    
    uiManager.updateFeedFilterButtonStyles();
    uiManager.updateFeedFilterDropdownSelection();
    uiManager.updateNavButtonStyles();
    uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters);
    state.setCurrentPage(1);
    fetchAndDisplaySummaries(false, 1, null);
}

function getSelectedFeedNamesForRefresh() {
    if (state.activeFeedFilterIds.length === 0) return "ALL feeds";
    return state.activeFeedFilterIds
        .map(id => {
            const feed = state.dbFeedSources.find(f => f.id === id);
            const userFeed = state.userFeeds?.find(uf => uf.feed_source_id === id);
            const customName = userFeed?.custom_name;
            return customName || (feed ? (feed.name || feed.url.split('/')[2]?.replace(/^www\./, '')) : `Feed ${id}`);
        })
        .join(', ');
}

function updateRefreshButtonText() {
    if (!refreshNewsBtn) return;
    
    if (state.activeFeedFilterIds.length === 0) {
        refreshNewsBtn.textContent = "Refresh All Feeds";
    } else if (state.activeFeedFilterIds.length === 1) {
        const feedId = state.activeFeedFilterIds[0];
        const feed = state.dbFeedSources.find(f => f.id === feedId);
        const userFeed = state.userFeeds?.find(uf => uf.feed_source_id === feedId);
        const customName = userFeed?.custom_name;
        const feedName = customName || (feed ? (feed.name || feed.url.split('/')[2]?.replace(/^www\./, '')) : 'this feed');
        refreshNewsBtn.textContent = `Refresh ${feedName}`;
    } else {
        refreshNewsBtn.textContent = `Refresh ${state.activeFeedFilterIds.length} Feeds`;
    }
}

function handleFeedFilterClick(feedId) {
    console.log(`MainScript: Feed filter clicked for ID: ${feedId}`);
    if (state.activeFeedFilterIds.includes(feedId)) { state.setActiveFeedFilterIds([]); } 
    else { state.setActiveFeedFilterIds([feedId]); }
    state.setActiveTagFilterIds([]);
    state.setCurrentKeywordSearch(null);
    state.setActiveView('main');
    const keywordInput = document.getElementById('keyword-search-input');
    if(keywordInput) keywordInput.value = '';
    uiManager.updateFeedFilterButtonStyles();
    uiManager.updateFeedFilterDropdownSelection();
    uiManager.updateNavButtonStyles();
    uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters);
    state.setCurrentPage(1);
    updateRefreshButtonText();
    fetchAndDisplaySummaries(false, 1, null); 
}

function handleAllFeedsClick() {
    console.log("MainScript: 'All Feeds' button clicked.");
    if (state.activeFeedFilterIds.length === 0 && state.activeTagFilterIds.length === 0 && !state.currentKeywordSearch) return; 
    state.setActiveFeedFilterIds([]);
    uiManager.updateFeedFilterButtonStyles();
    uiManager.updateFeedFilterDropdownSelection();
    state.setCurrentPage(1);
    updateRefreshButtonText();
    fetchAndDisplaySummaries(false, 1, state.currentKeywordSearch); 
}

async function handleFavoriteClick(articleId, favoriteButtonElement) {
    console.log(`MainScript: Favorite clicked for Article ID: ${articleId}`);
    const wasFavorite = favoriteButtonElement.classList.contains('is-favorite');
    const isFavoritesView = state.activeView === 'favorites';

    const articleCard = favoriteButtonElement.closest('.article-card');
    console.log('Favorite: articleCard found:', articleCard?.id, articleCard?.className);
    const muuriItemEl = articleCard?.closest('.muuri-item');
    console.log('Favorite: muuriItemEl found:', muuriItemEl);
    const muuriGrid = uiManager.getMuuriGrid();
    console.log(`Favorite: wasFavorite=${wasFavorite}, isFavoritesView=${isFavoritesView}, hasMuuriGrid=${!!muuriGrid}`);

    try {
        const updatedArticle = await apiService.toggleFavoriteStatus(articleId);
        console.log("MainScript: Favorite status updated via API:", updatedArticle.is_favorite);

        if (updatedArticle.is_favorite) {
            favoriteButtonElement.classList.add('is-favorite');
            favoriteButtonElement.title = "Remove from favorites";
            state.addLocallyFavoritedArticle(articleId);
            // When favoriting in main feed, hide from grid
            if (!isFavoritesView && muuriItemEl && muuriGrid) {
                const muuriItem = muuriGrid.getItem(muuriItemEl);
                console.log('Favorite: muuriItem (via getItem):', muuriItem);
                if (muuriItem) {
                    console.log('Favorite: Adding to favorites, hiding from main feed');
                    muuriGrid.hide([muuriItem]);
                    setTimeout(() => {
                        muuriGrid.layout();
                    }, 250);
                }
            }
        } else {
            favoriteButtonElement.classList.remove('is-favorite');
            favoriteButtonElement.title = "Add to favorites";
            state.removeLocallyFavoritedArticle(articleId);
            // When unfavoriting in favorites view, hide from grid
            if (isFavoritesView && muuriItemEl && muuriGrid) {
                const muuriItem = muuriGrid.getItem(muuriItemEl);
                console.log('Favorite: muuriItem (via getItem):', muuriItem);
                if (muuriItem) {
                    console.log('Favorite: Removing from favorites');
                    muuriGrid.hide([muuriItem]);
                    setTimeout(() => {
                        muuriGrid.layout();
                    }, 250);
                }
            }
        }
    } catch (error) {
        console.error("MainScript: Error toggling favorite status:", error);
        uiManager.showToast(`Failed to update favorite status: ${error.message}`, 'error');
    }
}

async function handleRegenerateSummaryFormSubmit(event) {
    event.preventDefault();
    const articleIdEl = document.getElementById('modal-article-id-input');
    const customPromptEl = document.getElementById('modal-summary-prompt-input');
    if (!articleIdEl || !customPromptEl) { uiManager.showToast("Error: Could not find modal elements.", 'error'); return; }
    const articleId = articleIdEl.value;
    let customPrompt = customPromptEl.value.trim();
    if (!articleId) { uiManager.showToast("Error: Article ID not found for regeneration.", 'error'); return; }
    if (customPrompt && !customPrompt.includes("{text}")) { uiManager.showToast("The custom prompt must include the placeholder {text}.", 'error'); return; }
    if (!customPrompt) customPrompt = null;

    uiManager.closeRegenerateSummaryModal();
    await summarizeArticle(articleId, customPrompt);
}

async function handleDirectSummarize(articleId) {
    console.log(`MainScript: Direct summarization triggered for Article ID: ${articleId}`);
    await summarizeArticle(articleId, null); // Pass null to use the default prompt
}

async function summarizeArticle(articleId, customPrompt) {
    const summaryElement = document.getElementById(`summary-text-${articleId}`);
    const articleCardElement = document.getElementById(`article-db-${articleId}`);
    const regenButtonOnCard = articleCardElement ? articleCardElement.querySelector('.regenerate-summary-btn') : null;
    const summarizeButton = articleCardElement ? articleCardElement.querySelector('.summarize-ai-btn') : null;

    if (summaryElement) {
        summaryElement.innerHTML = (typeof marked !== 'undefined' ? marked.parse("Regenerating summary...") : "Regenerating summary...");
    }
    if (regenButtonOnCard) regenButtonOnCard.disabled = true;
    if (summarizeButton) summarizeButton.disabled = true;

    try {
        const updatedArticle = await apiService.regenerateSummary(articleId, { custom_prompt: customPrompt });
        uiManager.updateArticleCard(updatedArticle, handleArticleTagClick);
        // Refresh Muuri item after card content changes (summary added/changed)
        uiManager.refreshMuuriItem(articleCardElement);
    } catch (error) {
        console.error("MainScript: Error regenerating summary:", error);
        if (summaryElement) {
            summaryElement.innerHTML = '';
            const errorP = document.createElement('p');
            errorP.classList.add('error-message');
            errorP.textContent = `Error: ${error.message}`;
            summaryElement.appendChild(errorP);
        }
        uiManager.showToast(`Failed to regenerate summary: ${error.message}`, 'error');
    } finally {
        if (regenButtonOnCard) regenButtonOnCard.disabled = false;
        if (summarizeButton) summarizeButton.disabled = false;
    }
}

function handleRegenerateModalUseDefaultPrompt() {
    const modalSummaryPromptInput = document.getElementById('modal-summary-prompt-input');
    if (modalSummaryPromptInput) {
        modalSummaryPromptInput.value = state.defaultSummaryPrompt;
    }
}

let isGlobalEventListenersInitialized = false;

function setupGlobalEventListeners() {
    if (isGlobalEventListenersInitialized) return;
    isGlobalEventListenersInitialized = true;
    console.log("MainScript: Setting up global event listeners...");

    const navMainBtn = document.getElementById('nav-main-btn');
    const navFavoritesBtn = document.getElementById('nav-favorites-btn');

    if (navMainBtn) {
        navMainBtn.addEventListener('click', async () => {
            if (state.activeView === 'main' && 
                document.getElementById('main-feed-section').classList.contains('active') && 
                state.activeFeedFilterIds.length === 0 && 
                !state.currentKeywordSearch &&
                state.activeTagFilterIds.length === 0) return;

            uiManager.showSection('main-feed-section');
            state.setActiveView('main');
            state.setActiveFeedFilterIds([]);
            state.setActiveTagFilterIds([]);
            state.setCurrentKeywordSearch(null);
            state.setCurrentPage(1);
            uiManager.updateFeedFilterDropdownSelection();
            uiManager.updateNavButtonStyles();
            const keywordInput = document.getElementById('keyword-search-input');
            if (keywordInput) keywordInput.value = '';
            await fetchAndDisplaySummaries(false, 1, null);
        });
    }

    if (navFavoritesBtn) {
        navFavoritesBtn.addEventListener('click', () => {
            console.log('Favorites button clicked, current view:', state.activeView);
            if (state.activeView === 'favorites') {
                state.setActiveView('main');
                const mainSectionTitle = document.querySelector('#main-feed-section h2');
                if(mainSectionTitle) mainSectionTitle.textContent = 'Latest Summaries';
                state.setActiveFeedFilterIds([]);
                state.setActiveTagFilterIds([]);
                state.setCurrentKeywordSearch(null);
                const keywordInput = document.getElementById('keyword-search-input');
                if(keywordInput) keywordInput.value = '';
                state.setCurrentPage(1);
                uiManager.showSection('main-feed-section');
                uiManager.updateNavButtonStyles();
                fetchAndDisplaySummaries(false, 1, null);
            } else {
                state.setActiveView('favorites');
                state.setActiveFeedFilterIds([]);
                state.setActiveTagFilterIds([]);
                state.setCurrentKeywordSearch(null);
                const keywordInput = document.getElementById('keyword-search-input');
                if(keywordInput) keywordInput.value = '';
                state.setCurrentPage(1);
                uiManager.showSection('main-feed-section');
                const mainSectionTitle = document.querySelector('#main-feed-section h2');
                if(mainSectionTitle) mainSectionTitle.textContent = 'Favorites';
                uiManager.updateNavButtonStyles();
                fetchAndDisplaySummaries(false, 1, null);
            }
        });
    }

    const navDeletedBtn = document.getElementById('nav-deleted-btn');
    if (navDeletedBtn) {
        navDeletedBtn.addEventListener('click', () => {
            console.log('Archived button clicked, current view:', state.activeView);
            if (state.activeView === 'deleted') {
                state.setActiveView('main');
                const mainSectionTitle = document.querySelector('#main-feed-section h2');
                if(mainSectionTitle) mainSectionTitle.textContent = 'Latest Summaries';
                state.setActiveFeedFilterIds([]);
                state.setCurrentPage(1);
                uiManager.showSection('main-feed-section');
                uiManager.updateNavButtonStyles();
                fetchAndDisplaySummaries(false, 1, null);
            } else {
                state.setActiveView('deleted');
                uiManager.showSection('deleted-section');
                uiManager.updateNavButtonStyles();
                loadArchivedArticles();
            }
        });
    }

    const navIntelligenceBtn = document.getElementById('nav-intelligence-btn');
    if (navIntelligenceBtn) {
        navIntelligenceBtn.addEventListener('click', async () => {
            console.log('Intelligence button clicked');
            state.setActiveView('intelligence');
            uiManager.showSection('intelligence-section');
            uiManager.updateNavButtonStyles();
            await eventManager.initIntelligenceView();
        });
    }

    const navSettingsBtn = document.getElementById('nav-settings-btn');
    if (navSettingsBtn) {
        navSettingsBtn.addEventListener('click', async () => {
            uiManager.showSection('setup-section');
            state.setActiveView('settings');
            uiManager.updateNavButtonStyles();
            feedHandler.loadUserFeeds();
        });
    }

    const navAdminBtn = document.getElementById('nav-admin-btn');
    if (navAdminBtn) {
        navAdminBtn.addEventListener('click', async () => {
            uiManager.showSection('admin-section');
            state.setActiveView('admin');
            uiManager.updateNavButtonStyles();
            adminLoadUsers();
        });
    }

    // DOM elements like keywordSearchInput are now initialized at the top of this file or within this function.
    keywordSearchInput = document.getElementById('keyword-search-input'); 
    keywordSearchBtn = document.getElementById('keyword-search-btn');

    if (keywordSearchBtn && keywordSearchInput) {
        keywordSearchBtn.addEventListener('click', () => {
            const searchTerm = keywordSearchInput.value.trim();
            state.setCurrentKeywordSearch(searchTerm || null);
            state.setActiveFeedFilterIds([]);
            state.setActiveTagFilterIds([]);
            state.setActiveView('main');
            uiManager.updateFeedFilterButtonStyles();
            uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters);
            uiManager.updateNavButtonStyles();
            state.setCurrentPage(1);
            fetchAndDisplaySummaries(false, 1, state.currentKeywordSearch);
        });
        keywordSearchInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') { event.preventDefault(); keywordSearchBtn.click(); }
        });
    } else { console.warn("MainScript: Keyword search elements not found."); }

    const mobileSearchInput = document.getElementById('mobile-search-input');
    const mobileSearchBtn = document.getElementById('mobile-search-btn');
    if (mobileSearchBtn && mobileSearchInput) {
        mobileSearchBtn.addEventListener('click', () => {
            const searchTerm = mobileSearchInput.value.trim();
            state.setCurrentKeywordSearch(searchTerm || null);
            state.setActiveFeedFilterIds([]);
            state.setActiveTagFilterIds([]);
            state.setActiveView('main');
            uiManager.updateFeedFilterButtonStyles();
            uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters);
            uiManager.updateNavButtonStyles();
            state.setCurrentPage(1);
            fetchAndDisplaySummaries(false, 1, state.currentKeywordSearch);
        });
        mobileSearchInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') { event.preventDefault(); mobileSearchBtn.click(); }
        });
    }

    const feedFilterSelect = document.getElementById('feed-filter-select');
    if (feedFilterSelect) {
        feedFilterSelect.addEventListener('change', () => {
            const selectedValue = feedFilterSelect.value;
            const selectedId = selectedValue ? parseInt(selectedValue) : null;
            
            if (selectedId) {
                state.setActiveFeedFilterIds([selectedId]);
            } else {
                state.setActiveFeedFilterIds([]);
            }
            state.setActiveTagFilterIds([]);
            state.setCurrentKeywordSearch(null);
            state.setActiveView('main');
            const keywordInput = document.getElementById('keyword-search-input');
            if(keywordInput) keywordInput.value = '';
            const mainSectionTitle = document.querySelector('#main-feed-section h2');
            if(mainSectionTitle) mainSectionTitle.textContent = 'Latest Summaries';
            uiManager.updateFeedFilterButtonStyles();
            uiManager.updateNavButtonStyles();
            uiManager.updateActiveTagFiltersUI(handleRemoveTagFilter, handleClearAllFilters);
            state.setCurrentPage(1);
            fetchAndDisplaySummaries(false, 1, null);
        });
    }

    refreshNewsBtn = document.getElementById('refresh-news-btn');
    if (refreshNewsBtn) {
        updateRefreshButtonText();
        refreshNewsBtn.addEventListener('click', async () => {
            const selectedFeedNames = getSelectedFeedNamesForRefresh();
            const confirmMsg = state.activeFeedFilterIds.length === 0
                ? `This will refresh ${selectedFeedNames}. This might take a moment. Continue?`
                : `This will refresh ${selectedFeedNames}. Continue?`;
            if (!confirm(confirmMsg)) return;

            uiManager.showLoadingIndicator(true, `Refreshing ${selectedFeedNames}...`);

            try {
                if (state.activeFeedFilterIds.length === 1) {
                    await apiService.refreshSingleFeed(state.activeFeedFilterIds[0]);
                } else {
                    await apiService.triggerRssRefresh();
                }
                pollForRefreshCompletion();
            } catch (error) {
                console.error("MainScript: Error triggering RSS refresh:", error);
                uiManager.showToast(`Error triggering refresh: ${error.message}`, 'error');
                uiManager.showLoadingIndicator(false);
            }
        });
    } else { console.warn("MainScript: Refresh news button not found."); }

    regeneratePromptForm = document.getElementById('regenerate-prompt-form');
    if (regeneratePromptForm) {
        regeneratePromptForm.addEventListener('submit', handleRegenerateSummaryFormSubmit);
    } else { console.warn("MainScript: Regenerate summary form not found."); }

    window.addEventListener('scroll', () => {
        if ((window.innerHeight + window.scrollY) >= (document.body.offsetHeight - 300) && !state.isLoadingMoreArticles && state.currentPage < state.totalPages) {
            console.log("MainScript: Reached bottom of page, loading more articles...");
            state.setCurrentPage(state.currentPage + 1);
            fetchAndDisplaySummaries(false, state.currentPage, state.currentKeywordSearch);
        }
    });

    const tagSearchInput = document.getElementById('tag-search-input');
    const tagSearchResults = document.getElementById('tag-search-results');
    
    if (tagSearchInput && tagSearchResults) {
        let tagSearchDebounceTimer = null;
        
        tagSearchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            state.setTagSearchQuery(query);
            
            if (tagSearchDebounceTimer) clearTimeout(tagSearchDebounceTimer);
            
            if (query.length < 2) {
                state.setTagSearchResults([]);
                state.setIsTagSearchOpen(false);
                tagSearchResults.classList.remove('visible');
                tagSearchResults.innerHTML = '';
                return;
            }
            
            tagSearchDebounceTimer = setTimeout(async () => {
                try {
                    const results = await apiService.searchTags(query);
                    state.setTagSearchResults(results);
                    
                    if (results.length === 0) {
                        tagSearchResults.innerHTML = '<div class="tag-search-no-results">No matching tags found</div>';
                        state.setIsTagSearchOpen(true);
                        tagSearchResults.classList.add('visible');
                    } else {
                        tagSearchResults.innerHTML = results.map(tag => 
                            `<div class="tag-search-result-item" data-tag-id="${tag.id}" data-tag-name="${tag.name}">${tag.name}</div>`
                        ).join('');
                        state.setIsTagSearchOpen(true);
                        tagSearchResults.classList.add('visible');
                        
                        tagSearchResults.querySelectorAll('.tag-search-result-item').forEach(item => {
                            item.addEventListener('click', () => {
                                const tagId = parseInt(item.dataset.tagId);
                                const tagName = item.dataset.tagName;
                                handleTagSearchSelect(tagId, tagName);
                            });
                        });
                    }
                } catch (error) {
                    console.error('Error searching tags:', error);
                    state.setTagSearchResults([]);
                }
            }, 300);
        });
        
        tagSearchInput.addEventListener('blur', () => {
            setTimeout(() => {
                state.setIsTagSearchOpen(false);
                tagSearchResults.classList.remove('visible');
            }, 200);
        });
        
        tagSearchInput.addEventListener('focus', () => {
            if (state.tagSearchResults.length > 0) {
                state.setIsTagSearchOpen(true);
                tagSearchResults.classList.add('visible');
            }
        });
    }
    
    const mobileTagSearchInput = document.getElementById('mobile-tag-search-input');
    const mobileTagSearchResults = document.getElementById('mobile-tag-search-results');
    
    if (mobileTagSearchInput && mobileTagSearchResults) {
        let mobileTagSearchDebounceTimer = null;
        
        mobileTagSearchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            state.setTagSearchQuery(query);
            
            if (mobileTagSearchDebounceTimer) clearTimeout(mobileTagSearchDebounceTimer);
            
            if (query.length < 2) {
                state.setTagSearchResults([]);
                state.setIsTagSearchOpen(false);
                mobileTagSearchResults.classList.remove('visible');
                mobileTagSearchResults.innerHTML = '';
                return;
            }
            
            mobileTagSearchDebounceTimer = setTimeout(async () => {
                try {
                    const results = await apiService.searchTags(query);
                    state.setTagSearchResults(results);
                    
                    if (results.length === 0) {
                        mobileTagSearchResults.innerHTML = '<div class="tag-search-no-results">No matching tags found</div>';
                        state.setIsTagSearchOpen(true);
                        mobileTagSearchResults.classList.add('visible');
                    } else {
                        mobileTagSearchResults.innerHTML = results.map(tag => 
                            `<div class="tag-search-result-item" data-tag-id="${tag.id}" data-tag-name="${tag.name}">${tag.name}</div>`
                        ).join('');
                        state.setIsTagSearchOpen(true);
                        mobileTagSearchResults.classList.add('visible');
                        
                        mobileTagSearchResults.querySelectorAll('.tag-search-result-item').forEach(item => {
                            item.addEventListener('click', () => {
                                const tagId = parseInt(item.dataset.tagId);
                                const tagName = item.dataset.tagName;
                                handleTagSearchSelect(tagId, tagName);
                            });
                        });
                    }
                } catch (error) {
                    console.error('Error searching tags:', error);
                    state.setTagSearchResults([]);
                }
            }, 300);
        });
        
        mobileTagSearchInput.addEventListener('blur', () => {
            setTimeout(() => {
                state.setIsTagSearchOpen(false);
                mobileTagSearchResults.classList.remove('visible');
            }, 200);
        });
        
        mobileTagSearchInput.addEventListener('focus', () => {
            if (state.tagSearchResults.length > 0) {
                state.setIsTagSearchOpen(true);
                mobileTagSearchResults.classList.add('visible');
            }
        });
    }
    
    console.log("MainScript: Global event listeners set up.");
}

function pollForRefreshCompletion() {
    const pollInterval = 3000; // 3 seconds
    const maxPollTime = 120000; // 2 minutes
    let timeWaited = 0;

    uiManager.showLoadingIndicator(true, 'Feeds are refreshing. Please wait...');

    const intervalId = setInterval(async () => {
        try {
            const status = await apiService.fetchRefreshStatus();
            if (!status.is_refreshing) {
                clearInterval(intervalId);
                uiManager.showLoadingIndicator(true, 'Refresh complete. Fetching new articles...');
                state.setCurrentPage(1);
                fetchAndDisplaySummaries(false, 1, state.currentKeywordSearch).finally(() => {
                    uiManager.showLoadingIndicator(false);
                });
            } else {
                timeWaited += pollInterval;
                if (timeWaited >= maxPollTime) {
                    clearInterval(intervalId);
                    uiManager.showToast("The refresh is taking longer than expected. The process will continue in the background.", 'warning');
                    uiManager.showLoadingIndicator(false);
                }
            }
        } catch (error) {
            clearInterval(intervalId);
            console.error("MainScript: Error polling for refresh completion:", error);
            uiManager.showToast("An error occurred while checking the refresh status.", 'error');
            uiManager.showLoadingIndicator(false);
        }
    }, pollInterval);
}

document.addEventListener('DOMContentLoaded', async () => {
    console.log("MainScript: DOMContentLoaded event fired. Script execution starting...");

    setupAuthEventListeners();
    
    if (!apiService.isLoggedIn()) {
        console.log("MainScript: User not logged in, showing login prompt");
        const resultsContainer = document.getElementById('results-container');
        if (resultsContainer) {
            resultsContainer.innerHTML = '<p>Please <a href="#" id="auth-prompt-login">login</a> or <a href="#" id="auth-prompt-register">register</a> to continue.</p>';
            document.getElementById('auth-prompt-login')?.addEventListener('click', (e) => { e.preventDefault(); openLoginModal(); });
            document.getElementById('auth-prompt-register')?.addEventListener('click', (e) => { e.preventDefault(); openRegisterModal(); });
        }
        return;
    }

    // Initialize DOM references for all modules first
    uiManager.initializeUIDOMReferences();
    configManager.initializeDOMReferences();
    chatHandler.initializeChatDOMReferences();
    feedHandler.initializeFeedHandlerDOMReferences(() => {
        uiManager.populateFeedFilterDropdown();
    });

    // Then setup event listeners for modules that depend on these DOM elements
    uiManager.setupUIManagerEventListeners(handleRegenerateModalUseDefaultPrompt);
    configManager.setupFormEventListeners({
        onArticlesPerPageChange: () => { 
            state.setCurrentPage(1);
            fetchAndDisplaySummaries(false, 1, state.currentKeywordSearch);
        }
    });
    chatHandler.setupChatModalEventListeners();
    feedHandler.setupFeedHandlerEventListeners();
    
    // Setup event listeners handled directly by this main script
    setupGlobalEventListeners(); 
    
    // Initialize application settings and load initial data
    await initializeAppSettings(); 
    
    // Initialize debug manager (hidden by default, press Ctrl+Shift+D to show)
    initDebugManager();
    
    console.log("MainScript: Full application initialization complete.");
});

let archivedArticlesPage = 1;
let archivedArticlesTotal = 0;
let archivedArticlesPageSize = 12;

async function loadArchivedArticles(page = 1) {
    const archivedList = document.getElementById('deleted-articles-list');
    
    if (!archivedList) return;
    
    archivedArticlesPage = page;
    archivedList.innerHTML = '<p>Loading archived articles...</p>';
    
    try {
        const response = await apiService.fetchArchivedArticles(page, archivedArticlesPageSize);
        const articles = response.items || [];
        archivedArticlesTotal = response.total || 0;
        
        if (articles.length === 0 && page === 1) {
            archivedList.innerHTML = '<p>No archived articles.</p>';
            return;
        }
        
        if (articles.length === 0) {
            archivedList.innerHTML = '<p>No more archived articles.</p>';
            return;
        }
        
        archivedList.innerHTML = '';
        articles.forEach(article => {
            const item = document.createElement('div');
            item.className = 'deleted-article-item';
            item.innerHTML = `
                <div class="deleted-article-info">
                    <strong>${article.title || 'No Title'}</strong>
                    <br>
                    <small>Archived ${formatTimeAgo(article.archived_at)}</small>
                </div>
                <div class="deleted-article-actions">
                    <button class="restore-btn" data-id="${article.id}">Restore</button>
                </div>
            `;
            archivedList.appendChild(item);
            
            item.querySelector('.restore-btn').addEventListener('click', async (e) => {
                const id = e.target.dataset.id;
                try {
                    await apiService.restoreArticle(parseInt(id));
                    await loadArchivedArticles(archivedArticlesPage);
                } catch (error) {
                    uiManager.showToast('Error restoring article', 'error');
                }
            });
        });
        
        const totalPages = Math.ceil(archivedArticlesTotal / archivedArticlesPageSize);
        if (totalPages > 1) {
            const paginationDiv = document.createElement('div');
            paginationDiv.className = 'archived-pagination';
            paginationDiv.style.cssText = 'margin-top: 20px; display: flex; gap: 10px; align-items: center; justify-content: center;';
            
            if (page > 1) {
                const prevBtn = document.createElement('button');
                prevBtn.textContent = 'Previous';
                prevBtn.onclick = () => loadArchivedArticles(page - 1);
                paginationDiv.appendChild(prevBtn);
            }
            
            const pageInfo = document.createElement('span');
            pageInfo.textContent = `Page ${page} of ${totalPages} (${archivedArticlesTotal} total)`;
            paginationDiv.appendChild(pageInfo);
            
            if (page < totalPages) {
                const nextBtn = document.createElement('button');
                nextBtn.textContent = 'Next';
                nextBtn.onclick = () => loadArchivedArticles(page + 1);
                paginationDiv.appendChild(nextBtn);
            }
            
            archivedList.appendChild(paginationDiv);
        }
        
    } catch (error) {
        console.error('Error loading archived articles:', error);
        archivedList.innerHTML = '<p>Error loading archived articles.</p>';
    }
}

function formatTimeAgo(dateStr) {
    if (!dateStr) return 'unknown';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'yesterday';
    return `${diffDays} days ago`;
}

function updateAuthUI() {
    const loggedIn = apiService.isLoggedIn();
    const userData = apiService.getUserData();
    const navAdminBtn = document.getElementById('nav-admin-btn');
    
    if (loggedIn && userData) {
        if (authButtons) authButtons.style.display = 'none';
        if (userMenu) userMenu.style.display = 'flex';
        if (userEmail) userEmail.textContent = userData.email;
        if (navAdminBtn) navAdminBtn.style.display = userData.is_admin ? 'inline-block' : 'none';
    } else {
        if (authButtons) authButtons.style.display = 'flex';
        if (userMenu) userMenu.style.display = 'none';
        if (navAdminBtn) navAdminBtn.style.display = 'none';
    }
}

function openLoginModal() {
    if (loginModal) loginModal.style.display = 'block';
}

function closeLoginModal() {
    if (loginModal) loginModal.style.display = 'none';
}

function openRegisterModal() {
    if (registerModal) registerModal.style.display = 'block';
}

function closeRegisterModal() {
    if (registerModal) registerModal.style.display = 'none';
}

function openDeleteAccountModal() {
    if (deleteAccountModal) deleteAccountModal.style.display = 'block';
}

function closeDeleteAccountModal() {
    if (deleteAccountModal) deleteAccountModal.style.display = 'none';
    const confirmInput = document.getElementById('delete-account-confirm');
    if (confirmInput) confirmInput.value = '';
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    const email = document.getElementById('login-email')?.value;
    const password = document.getElementById('login-password')?.value;
    
    if (!email || !password) {
        uiManager.showToast('Please enter email and password', 'warning');
        return;
    }
    
    try {
        await apiService.login(email, password);
        closeLoginModal();
        updateAuthUI();
        initializeAllDOMReferences();
        await initializeAppSettings();
    } catch (error) {
        uiManager.showToast(`Login failed: ${error.message}`, 'error');
    }
}

async function handleRegisterSubmit(event) {
    event.preventDefault();
    const email = document.getElementById('register-email')?.value;
    const password = document.getElementById('register-password')?.value;
    const passwordConfirm = document.getElementById('register-password-confirm')?.value;
    
    if (!email || !password) {
        uiManager.showToast('Please enter email and password', 'warning');
        return;
    }
    
    if (password !== passwordConfirm) {
        uiManager.showToast('Passwords do not match', 'warning');
        return;
    }
    
    try {
        await apiService.register(email, password);
        closeRegisterModal();
        updateAuthUI();
        initializeAllDOMReferences();
        await initializeAppSettings();
    } catch (error) {
        uiManager.showToast(`Registration failed: ${error.message}`, 'error');
    }
}

let isDOMInitialized = false;

function initializeAllDOMReferences() {
    if (isDOMInitialized) return;
    
    uiManager.initializeUIDOMReferences();
    configManager.initializeDOMReferences();
    chatHandler.initializeChatDOMReferences();
    feedHandler.initializeFeedHandlerDOMReferences(() => {
        uiManager.populateFeedFilterDropdown();
    });
    uiManager.setupUIManagerEventListeners(handleRegenerateModalUseDefaultPrompt);
    configManager.setupFormEventListeners({
        onArticlesPerPageChange: () => { 
            state.setCurrentPage(1);
            fetchAndDisplaySummaries(false, 1, state.currentKeywordSearch);
        }
    });
    chatHandler.setupChatModalEventListeners();
    feedHandler.setupFeedHandlerEventListeners();
    setupGlobalEventListeners();
    isDOMInitialized = true;
}

async function handleLogout() {
    try {
        await apiService.logout();
        updateAuthUI();
        window.location.reload();
    } catch (error) {
        console.error('Logout error:', error);
    }
}

async function handleDeleteAccountSubmit(event) {
    event.preventDefault();
    const confirm = document.getElementById('delete-account-confirm')?.value;
    
    if (confirm !== 'DELETE') {
        uiManager.showToast('Please type DELETE to confirm', 'warning');
        return;
    }
    
    try {
        await apiService.deleteAccount(confirm);
        closeDeleteAccountModal();
        updateAuthUI();
        uiManager.showToast('Account deleted successfully', 'success');
        window.location.reload();
    } catch (error) {
        uiManager.showToast(`Failed to delete account: ${error.message}`, 'error');
    }
}

function setupAuthEventListeners() {
    navLoginBtn = document.getElementById('nav-login-btn');
    navRegisterBtn = document.getElementById('nav-register-btn');
    logoutBtn = document.getElementById('logout-btn');
    deleteAccountBtn = document.getElementById('delete-account-btn');
    loginModal = document.getElementById('login-modal');
    registerModal = document.getElementById('register-modal');
    deleteAccountModal = document.getElementById('delete-account-modal');
    authButtons = document.getElementById('auth-buttons');
    userMenu = document.getElementById('user-menu');
    userEmail = document.getElementById('user-email');
    loginForm = document.getElementById('login-form');
    registerForm = document.getElementById('register-form');
    deleteAccountForm = document.getElementById('delete-account-form');
    
    if (navLoginBtn) navLoginBtn.addEventListener('click', openLoginModal);
    if (navRegisterBtn) navRegisterBtn.addEventListener('click', openRegisterModal);
    if (logoutBtn) logoutBtn.addEventListener('click', handleLogout);
    if (deleteAccountBtn) deleteAccountBtn.addEventListener('click', openDeleteAccountModal);
    
    if (loginForm) loginForm.addEventListener('submit', handleLoginSubmit);
    if (registerForm) registerForm.addEventListener('submit', handleRegisterSubmit);
    if (deleteAccountForm) deleteAccountForm.addEventListener('submit', handleDeleteAccountSubmit);
    
    const closeLoginBtn = document.getElementById('close-login-modal-btn');
    const closeRegisterBtn = document.getElementById('close-register-modal-btn');
    const closeDeleteAccountBtn = document.getElementById('close-delete-account-modal-btn');
    
    if (closeLoginBtn) closeLoginBtn.addEventListener('click', closeLoginModal);
    if (closeRegisterBtn) closeRegisterBtn.addEventListener('click', closeRegisterModal);
    if (closeDeleteAccountBtn) closeDeleteAccountBtn.addEventListener('click', closeDeleteAccountModal);
    
    window.addEventListener('auth:logout', () => {
        updateAuthUI();
    });
    
    updateAuthUI();
}

// Admin Panel Functions
window.adminShowTab = function(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById('admin' + tabName.charAt(0).toUpperCase() + tabName.slice(1) + 'Tab').style.display = 'block';
    event.target.classList.add('active');
    
    if (tabName === 'users') {
        adminLoadUsers();
    } else if (tabName === 'feeds') {
        adminLoadFeeds();
    } else if (tabName === 'settings') {
        adminLoadSettings();
    }
};

function adminShowAlert(message, type = 'success') {
    const container = document.getElementById('admin-alert-container');
    container.innerHTML = `<div class="alert alert-${type}" style="padding: 15px; border-radius: 5px; margin-bottom: 15px; background: ${type === 'success' ? '#d4edda' : '#f8d7da'}; color: ${type === 'success' ? '#155724' : '#721c24'}; border: 1px solid ${type === 'success' ? '#c3e6cb' : '#f5c6cb'};">${message}</div>`;
    setTimeout(() => container.innerHTML = '', 5000);
}

async function adminLoadUsers() {
    try {
        const users = await apiService.getAdminUsers();
        const container = document.getElementById('admin-users-list');
        
        if (users.length === 0) {
            container.innerHTML = '<p style="padding: 20px;">No users found.</p>';
            return;
        }
        
        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Admin</th>
                        <th>Created</th>
                        <th>Feeds</th>
                        <th>Article States</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${users.map(u => `
                        <tr>
                            <td>${u.email}</td>
                            <td>${u.is_admin ? 'Yes' : 'No'}</td>
                            <td>${u.created_at ? new Date(u.created_at).toLocaleDateString() : 'N/A'}</td>
                            <td>${u.feed_count}</td>
                            <td>${u.article_state_count}</td>
                            <td>
                                ${u.is_admin ? '<em>Cannot delete</em>' : 
                                    `<button class="nav-button" style="padding: 6px 12px; background: #e74c3c; border-color: #e74c3c; color: white;" onclick="adminDeleteUser(${u.id}, '${u.email.replace(/'/g, "\\'")}')">Delete</button>`}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        document.getElementById('admin-users-list').innerHTML = 
            `<p style="color: #e74c3c; padding: 20px;">Error loading users: ${error.message}</p>`;
    }
}

window.adminDeleteUser = async function(userId, email) {
    if (!confirm(`Delete user "${email}"? This will delete all their data.`)) {
        return;
    }
    try {
        await apiService.deleteAdminUser(userId);
        adminShowAlert(`User ${email} deleted`);
        adminLoadUsers();
    } catch (error) {
        adminShowAlert('Error deleting user: ' + error.message, 'error');
    }
};

async function adminLoadFeeds() {
    try {
        const feeds = await apiService.getAdminFeeds();
        document.getElementById('admin-total-feeds').textContent = feeds.length;
        document.getElementById('admin-total-articles').textContent = 
            feeds.reduce((sum, f) => sum + f.article_count, 0);
        
        const container = document.getElementById('admin-feeds-list');
        
        if (feeds.length === 0) {
            container.innerHTML = '<p style="padding: 20px;">No feeds found.</p>';
            return;
        }
        
        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>URL</th>
                        <th>Users</th>
                        <th>Articles</th>
                        <th>Interval</th>
                        <th>Last Fetch</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${feeds.map(f => `
                        <tr>
                            <td>${f.name}</td>
                            <td><code style="font-size: 0.85em;">${f.url}</code></td>
                            <td>${f.user_count}</td>
                            <td>${f.article_count}</td>
                            <td>${f.fetch_interval_minutes}m</td>
                            <td>${f.last_fetch_at ? new Date(f.last_fetch_at).toLocaleString() : 'Never'}</td>
                            <td>
                                <button class="nav-button" style="padding: 6px 12px;" onclick="adminRefreshSingleFeed(${f.id}, '${f.name.replace(/'/g, "\\'")}')">🔄</button>
                                <button class="nav-button" style="padding: 6px 12px;" onclick="adminOpenEditModal(${f.id}, '${f.name.replace(/'/g, "\\'")}', '${f.url}', ${f.fetch_interval_minutes})">Edit</button>
                                ${f.user_count > 0 ? 
                                    `<em style="color: #7f8c8d;">Has users</em>` : 
                                    `<button class="nav-button" style="padding: 6px 12px; background: #e74c3c; border-color: #e74c3c; color: white;" onclick="adminDeleteFeed(${f.id}, '${f.name.replace(/'/g, "\\'")}')">Delete</button>`}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        document.getElementById('admin-feeds-list').innerHTML = 
            `<p style="color: #e74c3c; padding: 20px;">Error loading feeds: ${error.message}</p>`;
    }
}

window.adminAddFeed = async function(event) {
    event.preventDefault();
    const url = document.getElementById('admin-feed-url').value;
    const name = document.getElementById('admin-feed-name').value || null;
    const interval = parseInt(document.getElementById('admin-feed-interval').value) || 60;
    
    try {
        await apiService.addAdminFeed({ url, name, fetch_interval_minutes: interval });
        adminShowAlert('Feed added successfully');
        document.getElementById('admin-add-feed-form').reset();
        document.getElementById('admin-feed-interval').value = 60;
        adminLoadFeeds();
    } catch (error) {
        adminShowAlert('Error adding feed: ' + error.message, 'error');
    }
};

window.adminDeleteFeed = async function(feedId, feedName) {
    if (!confirm(`Delete feed "${feedName}"? All articles will be deleted.`)) {
        return;
    }
    try {
        await apiService.deleteAdminFeed(feedId);
        adminShowAlert(`Feed ${feedName} deleted`);
        adminLoadFeeds();
    } catch (error) {
        adminShowAlert('Error deleting feed: ' + error.message, 'error');
    }
};

window.adminOpenEditModal = function(feedId, name, url, interval) {
    document.getElementById('admin-edit-feed-id').value = feedId;
    document.getElementById('admin-edit-feed-name').value = name;
    document.getElementById('admin-edit-feed-url').value = url;
    document.getElementById('admin-edit-feed-interval').value = interval;
    document.getElementById('admin-edit-feed-modal').style.display = 'flex';
};

window.adminCloseEditModal = function() {
    document.getElementById('admin-edit-feed-modal').style.display = 'none';
};

window.adminSaveEditedFeed = async function(event) {
    event.preventDefault();
    const feedId = document.getElementById('admin-edit-feed-id').value;
    const name = document.getElementById('admin-edit-feed-name').value;
    const interval = parseInt(document.getElementById('admin-edit-feed-interval').value);
    
    try {
        await apiService.updateAdminFeed(feedId, { name, fetch_interval_minutes: interval });
        adminShowAlert('Feed updated successfully');
        adminCloseEditModal();
        adminLoadFeeds();
    } catch (error) {
        adminShowAlert('Error updating feed: ' + error.message, 'error');
    }
};

window.adminRefreshAllFeeds = async function() {
    const statusEl = document.getElementById('admin-refresh-status');
    const btn = document.getElementById('admin-refresh-all-btn');
    try {
        btn.disabled = true;
        statusEl.textContent = 'Refreshing...';
        await apiService.refreshAllFeeds();
        statusEl.textContent = 'Refresh initiated';
        setTimeout(() => { statusEl.textContent = ''; btn.disabled = false; }, 3000);
    } catch (error) {
        statusEl.textContent = 'Error: ' + error.message;
        btn.disabled = false;
    }
};

window.adminRefreshSingleFeed = async function(feedId, feedName) {
    try {
        await apiService.refreshSingleFeed(feedId);
        adminShowAlert(`Refresh initiated for "${feedName}"`);
    } catch (error) {
        adminShowAlert('Error: ' + error.message, 'error');
    }
};

async function adminLoadSettings() {
    try {
        const settings = await apiService.getAdminSettings();
        const container = document.getElementById('admin-settings-form');
        
        container.innerHTML = `
            <div class="settings-grid">
                <div class="settings-section">
                    <h3>Models</h3>
                    <div class="model-row">
                        <label style="width: 120px;">Summary:</label>
                        <input type="text" id="admin-summary-model" value="${settings.summary_model || ''}">
                        <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c;" onclick="adminUpdateSetting('summary_model', document.getElementById('admin-summary-model').value)">Update</button>
                    </div>
                    <div class="model-row">
                        <label style="width: 120px;">Chat:</label>
                        <input type="text" id="admin-chat-model" value="${settings.chat_model || ''}">
                        <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c;" onclick="adminUpdateSetting('chat_model', document.getElementById('admin-chat-model').value)">Update</button>
                    </div>
                    <div class="model-row">
                        <label style="width: 120px;">Tag:</label>
                        <input type="text" id="admin-tag-model" value="${settings.tag_model || ''}">
                        <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c;" onclick="adminUpdateSetting('tag_model', document.getElementById('admin-tag-model').value)">Update</button>
                    </div>
                </div>
                <div class="settings-section">
                    <h3>Max Output Tokens</h3>
                    <div class="model-row">
                        <label style="width: 120px;">Summary:</label>
                        <input type="number" id="admin-summary-tokens" value="${settings.summary_max_output_tokens || '1024'}">
                        <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c;" onclick="adminUpdateSetting('summary_max_output_tokens', document.getElementById('admin-summary-tokens').value)">Update</button>
                    </div>
                    <div class="model-row">
                        <label style="width: 120px;">Chat:</label>
                        <input type="number" id="admin-chat-tokens" value="${settings.chat_max_output_tokens || '4096'}">
                        <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c;" onclick="adminUpdateSetting('chat_max_output_tokens', document.getElementById('admin-chat-tokens').value)">Update</button>
                    </div>
                    <div class="model-row">
                        <label style="width: 120px;">Tag:</label>
                        <input type="number" id="admin-tag-tokens" value="${settings.tag_max_output_tokens || '100'}">
                        <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c;" onclick="adminUpdateSetting('tag_max_output_tokens', document.getElementById('admin-tag-tokens').value)">Update</button>
                    </div>
                </div>
                <div class="settings-section">
                    <h3>System Settings</h3>
                    <div class="model-row">
                        <label style="width: 180px;">Min Word Count:</label>
                        <input type="number" id="admin-min-word-count" value="${settings.minimum_word_count || '100'}" min="0" max="1000" style="width: 80px;">
                        <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c;" onclick="adminUpdateSetting('minimum_word_count', document.getElementById('admin-min-word-count').value)">Update</button>
                    </div>
                    <p style="font-size: 0.85em; color: #7f8c8d; margin-top: 5px;">Articles with fewer words will be hidden from feeds.</p>
                    <div class="model-row" style="margin-top: 15px;">
                        <label style="width: 180px;">RSS Interval (min):</label>
                        <input type="number" id="admin-rss-interval" value="${settings.default_rss_fetch_interval_minutes || '60'}" min="5" max="1440" style="width: 80px;">
                        <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c;" onclick="adminUpdateSetting('default_rss_fetch_interval_minutes', document.getElementById('admin-rss-interval').value)">Update</button>
                    </div>
                </div>
            </div>
            <div class="settings-section" style="margin-top: 25px;">
                <h3>Default Prompts</h3>
                <div class="form-group">
                    <label>Summary Prompt</label>
                    <textarea id="admin-summary-prompt" rows="3">${(settings.summary_prompt || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</textarea>
                    <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c; margin-top: 8px;" onclick="adminUpdateSetting('summary_prompt', document.getElementById('admin-summary-prompt').value)">Update</button>
                </div>
                <div class="form-group">
                    <label>Chat Prompt</label>
                    <textarea id="admin-chat-prompt" rows="3">${(settings.chat_prompt || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</textarea>
                    <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c; margin-top: 8px;" onclick="adminUpdateSetting('chat_prompt', document.getElementById('admin-chat-prompt').value)">Update</button>
                </div>
                <div class="form-group">
                    <label>Tag Generation Prompt</label>
                    <textarea id="admin-tag-prompt" rows="3">${(settings.tag_prompt || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</textarea>
                    <button class="nav-button" style="background: #1abc9c; color: white; border-color: #1abc9c; margin-top: 8px;" onclick="adminUpdateSetting('tag_prompt', document.getElementById('admin-tag-prompt').value)">Update</button>
                </div>
            </div>
            <div class="settings-section" style="margin-top: 25px;">
                <h3>Data Management</h3>
                <div class="form-group">
                    <label for="admin-days-old-input">Delete articles older than (days):</label>
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <input type="number" id="admin-days-old-input" value="30" min="1" max="3650" style="width: 100px;">
                        <button class="nav-button" style="background: #e74c3c; border-color: #e74c3c; color: white;" onclick="adminDeleteOldData()">Delete Old Articles</button>
                    </div>
                    <p id="admin-delete-status" style="margin-top: 10px; font-size: 0.9em;"></p>
                </div>
            </div>
        `;
    } catch (error) {
        document.getElementById('admin-settings-form').innerHTML = 
            `<p style="color: #e74c3c; padding: 20px;">Error loading settings: ${error.message}</p>`;
    }
}

window.adminUpdateSetting = async function(key, value) {
    try {
        await apiService.updateAdminSettings({ [key]: value });
        adminShowAlert('Setting updated');
    } catch (error) {
        adminShowAlert('Error updating setting: ' + error.message, 'error');
    }
};

window.adminDeleteOldData = async function() {
    const days = parseInt(document.getElementById('admin-days-old-input').value);
    const statusEl = document.getElementById('admin-delete-status');
    if (isNaN(days) || days < 1) {
        statusEl.textContent = 'Please enter a valid number of days.';
        statusEl.style.color = '#e74c3c';
        return;
    }
    if (!confirm(`Delete all articles older than ${days} days? This cannot be undone.`)) return;
    statusEl.textContent = 'Deleting...';
    statusEl.style.color = 'inherit';
    try {
        const result = await apiService.deleteOldData(days);
        statusEl.textContent = result.message || 'Done';
        statusEl.style.color = '#27ae60';
    } catch (error) {
        statusEl.textContent = 'Error: ' + error.message;
        statusEl.style.color = '#e74c3c';
    }
};
