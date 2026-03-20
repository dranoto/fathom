// frontend/js/feedHandler.js
import * as state from './state.js';
import * as apiService from './apiService.js';

let addRssFeedForm, rssFeedUrlInput, rssFeedNameInput, rssFeedsListUI;
let publicFeedsSelect, addFromDropdownBtn;
let refreshMainFeedFilterButtonsCallback;

export function initializeFeedHandlerDOMReferences(refreshFiltersCb) {
    addRssFeedForm = document.getElementById('add-rss-feed-form');
    rssFeedUrlInput = document.getElementById('rss-feed-url-input');
    rssFeedNameInput = document.getElementById('rss-feed-name-input');
    rssFeedsListUI = document.getElementById('user-feeds-list');
    publicFeedsSelect = document.getElementById('public-feeds-select');
    addFromDropdownBtn = document.getElementById('add-from-dropdown-btn');

    if (typeof refreshFiltersCb === 'function') {
        refreshMainFeedFilterButtonsCallback = refreshFiltersCb;
    }

    console.log("FeedHandler: DOM references initialized.");
}

async function loadPublicFeedsDropdown() {
    console.log("FeedHandler: loadPublicFeedsDropdown called");
    const publicFeedsSelectEl = document.getElementById('public-feeds-select');
    if (!publicFeedsSelectEl) {
        console.warn("FeedHandler: public-feeds-select element not found in DOM");
        return;
    }
    
    try {
        console.log("FeedHandler: Fetching public feeds...");
        const publicFeeds = await apiService.fetchPublicFeeds();
        console.log("FeedHandler: Got", publicFeeds?.length, "public feeds");
        publicFeedsSelectEl.innerHTML = '<option value="">-- Select a feed to add --</option>';
        
        if (!publicFeeds || publicFeeds.length === 0) {
            console.log("FeedHandler: No public feeds returned");
            return;
        }
        
        publicFeeds.forEach(feed => {
            const option = document.createElement('option');
            option.value = feed.url;
            option.textContent = `${feed.custom_name || feed.name || feed.url} (${feed.url})`;
            publicFeedsSelectEl.appendChild(option);
        });
        console.log("FeedHandler: Loaded", publicFeeds.length, "public feeds into dropdown");
    } catch (error) {
        console.error("FeedHandler: Error loading public feeds:", error);
    }
}

function renderUserFeedsList() {
    if (!rssFeedsListUI) {
        console.error("FeedHandler: userFeedsListUI element not found.");
        return;
    }
    rssFeedsListUI.innerHTML = '';

    if (state.userFeeds.length === 0) {
        rssFeedsListUI.innerHTML = '<p>No feeds added yet. Add one from the dropdown or enter a new URL above.</p>';
        return;
    }

    state.userFeeds.forEach((feed) => {
        const tag = document.createElement('div');
        tag.classList.add('user-feed-tag');
        
        const nameSpan = document.createElement('span');
        nameSpan.classList.add('feed-name');
        nameSpan.textContent = feed.custom_name || feed.name || feed.url;
        tag.appendChild(nameSpan);

        const editBtn = document.createElement('button');
        editBtn.classList.add('edit-feed-btn');
        editBtn.textContent = '✎';
        editBtn.title = 'Edit feed name';
        editBtn.onclick = () => {
            const currentName = feed.custom_name || feed.name || '';
            const newName = prompt('Enter a custom name for this feed:', currentName);
            if (newName === null) return;
            if (newName === feed.custom_name) return;
            (async () => {
                try {
                    await apiService.updateUserFeed(feed.id, { custom_name: newName || null });
                    await loadUserFeeds();
                    if (refreshMainFeedFilterButtonsCallback) refreshMainFeedFilterButtonsCallback();
                } catch (error) {
                    console.error("FeedHandler: Error updating feed:", error);
                    alert(`Error updating feed: ${error.message}`);
                }
            })();
        };
        tag.appendChild(editBtn);

        const removeBtn = document.createElement('button');
        removeBtn.classList.add('remove-feed-btn');
        removeBtn.textContent = '×';
        removeBtn.onclick = async () => {
            if (!confirm(`Remove feed "${feed.name || feed.url}"?`)) return;
            try {
                await apiService.deleteUserFeed(feed.id);
                await loadUserFeeds();
                if (refreshMainFeedFilterButtonsCallback) refreshMainFeedFilterButtonsCallback();
            } catch (error) {
                console.error("FeedHandler: Error removing feed:", error);
                alert(`Error removing feed: ${error.message}`);
            }
        };
        tag.appendChild(removeBtn);
        rssFeedsListUI.appendChild(tag);
    });
}

export async function loadUserFeeds() {
    try {
        const feeds = await apiService.fetchUserFeeds();
        state.setUserFeeds(feeds || []);
        renderUserFeedsList();
        await loadPublicFeedsDropdown();
    } catch (error) {
        console.error("FeedHandler: Error loading user feeds:", error);
        state.setUserFeeds([]);
        renderUserFeedsList();
    }
}

async function handleAddFromDropdown() {
    const publicFeedsSelectEl = document.getElementById('public-feeds-select');
    if (!publicFeedsSelectEl) return;
    
    const selectedUrl = publicFeedsSelectEl.value;
    if (!selectedUrl) {
        alert('Please select a feed from the dropdown');
        return;
    }

    try {
        await apiService.addUserFeed({ url: selectedUrl });
        await loadUserFeeds();
        if (refreshMainFeedFilterButtonsCallback) refreshMainFeedFilterButtonsCallback();
    } catch (error) {
        console.error("FeedHandler: Error adding feed from dropdown:", error);
        alert(`Error adding feed: ${error.message}`);
    }
}

async function handleAddNewFeed(event) {
    event.preventDefault();
    if (!rssFeedUrlInput) return;

    const url = rssFeedUrlInput.value.trim();
    const name = rssFeedNameInput?.value.trim();

    if (!url) {
        alert('Feed URL is required');
        return;
    }

    try {
        new URL(url);
    } catch (_) {
        alert('Invalid URL format');
        return;
    }

    try {
        await apiService.addUserFeed({ url, custom_name: name || null });
        rssFeedUrlInput.value = '';
        if (rssFeedNameInput) rssFeedNameInput.value = '';
        await loadUserFeeds();
        if (refreshMainFeedFilterButtonsCallback) refreshMainFeedFilterButtonsCallback();
    } catch (error) {
        console.error("FeedHandler: Error adding new feed:", error);
        alert(`Error adding feed: ${error.message}`);
    }
}

export async function renderFeedsFromState() {
    console.log("FeedHandler: Rendering feeds from state...");
    await loadUserFeeds();
}

export async function fetchAndRenderDbFeeds() {
    console.log("FeedHandler: Fetching and rendering user feeds...");
    await loadUserFeeds();
}

export function setupFeedHandlerEventListeners() {
    console.log("FeedHandler: setupFeedHandlerEventListeners called");
    const addRssFeedFormEl = document.getElementById('add-rss-feed-form');
    const addFromDropdownBtnEl = document.getElementById('add-from-dropdown-btn');
    
    if (addRssFeedFormEl) {
        addRssFeedFormEl.addEventListener('submit', handleAddNewFeed);
        console.log("FeedHandler: add-rss-feed-form submit listener attached");
    }
    
    if (addFromDropdownBtnEl) {
        addFromDropdownBtnEl.addEventListener('click', handleAddFromDropdown);
        console.log("FeedHandler: add-from-dropdown-btn click listener attached");
    }

    console.log("FeedHandler: Event listeners set up.");
}

console.log("frontend/js/feedHandler.js: Module loaded.");