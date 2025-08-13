// frontend/js/configManager.js
import * as state from './state.js';
import * as apiService from './apiService.js';

/**
 * This module handles loading, saving, and applying application configurations.
 * It now exclusively interacts with the backend for settings persistence.
 */

// --- DOM Element References for the Setup Tab ---
let numArticlesSetupInput, currentNumArticlesDisplay,
    minimumWordCountSetupInput, currentMinimumWordCountDisplay,
    summaryPromptInput, currentSummaryPromptDisplay,
    tagGenerationPromptInput, currentTagGenerationPromptDisplay,
    chatPromptInput, currentChatPromptDisplay,
    rssFetchIntervalInput, currentRssFetchIntervalDisplay,
    contentPrefsForm, aiPromptsForm, globalRssSettingsForm, resetPromptsBtn,
    aiModelsForm, summaryModelSelect, chatModelSelect, tagModelSelect;

/**
 * Initializes the configuration manager by fetching DOM elements.
 */
export function initializeDOMReferences() {
    numArticlesSetupInput = document.getElementById('num_articles_setup');
    currentNumArticlesDisplay = document.getElementById('current-num-articles-display');
    minimumWordCountSetupInput = document.getElementById('minimum-word-count-setup');
    currentMinimumWordCountDisplay = document.getElementById('current-minimum-word-count-display');
    summaryPromptInput = document.getElementById('summary-prompt-input');
    currentSummaryPromptDisplay = document.getElementById('current-summary-prompt-display');
    tagGenerationPromptInput = document.getElementById('tag-generation-prompt-input');
    currentTagGenerationPromptDisplay = document.getElementById('current-tag-generation-prompt-display');
    chatPromptInput = document.getElementById('chat-prompt-input');
    currentChatPromptDisplay = document.getElementById('current-chat-prompt-display');
    rssFetchIntervalInput = document.getElementById('rss-fetch-interval-input');
    currentRssFetchIntervalDisplay = document.getElementById('current-rss-fetch-interval-display');

    contentPrefsForm = document.getElementById('content-prefs-form');
    aiPromptsForm = document.getElementById('ai-prompts-form');
    globalRssSettingsForm = document.getElementById('global-rss-settings-form');
    resetPromptsBtn = document.getElementById('reset-prompts-btn');

    aiModelsForm = document.getElementById('ai-models-form');
    summaryModelSelect = document.getElementById('summary-model-select');
    chatModelSelect = document.getElementById('chat-model-select');
    tagModelSelect = document.getElementById('tag-model-select');

    console.log("ConfigManager: DOM references initialized.");
}

/**
 * Loads all configurations from the backend and applies them to the state.
 * @param {object} initialBackendConfig - Config data fetched from the backend.
 */
export function loadConfigurations(initialBackendConfig) {
    console.log("ConfigManager: Loading configurations from backend...");

    if (!initialBackendConfig || !initialBackendConfig.settings) {
        console.error("ConfigManager: Initial backend config is missing or invalid.", initialBackendConfig);
        return;
    }

    const settings = initialBackendConfig.settings;

    // Set state from backend settings
    state.setArticlesPerPage(settings.articles_per_page);
    state.setMinimumWordCount(settings.minimum_word_count);
    state.setGlobalRssFetchInterval(settings.rss_fetch_interval_minutes);

    // Set prompts
    state.setDefaultPrompts(settings.summary_prompt, settings.chat_prompt, settings.tag_generation_prompt);
    state.setCurrentPrompts(settings.summary_prompt, settings.chat_prompt, settings.tag_generation_prompt);

    // Set models
    state.setAvailableModels(initialBackendConfig.available_models);
    state.setDefaultModels(settings.summary_model_name, settings.chat_model_name, settings.tag_model_name);
    state.setCurrentModels(settings.summary_model_name, settings.chat_model_name, settings.tag_model_name);

    updateSetupUI();
    console.log("ConfigManager: Configurations loaded and UI updated.");
}

function populateModelDropdowns() {
    const selects = [
        { el: summaryModelSelect, current: state.currentSummaryModel },
        { el: chatModelSelect, current: state.currentChatModel },
        { el: tagModelSelect, current: state.currentTagModel },
    ];

    selects.forEach(selectInfo => {
        if (selectInfo.el) {
            selectInfo.el.innerHTML = '';
            state.availableModels.forEach(modelName => {
                const option = document.createElement('option');
                option.value = modelName;
                option.textContent = modelName;
                if (modelName === selectInfo.current) {
                    option.selected = true;
                }
                selectInfo.el.appendChild(option);
            });
        }
    });
}

/**
 * Updates the input fields and display elements in the Setup Tab with current configuration values.
 */
export function updateSetupUI() {
    if (!numArticlesSetupInput) {
        console.warn("ConfigManager: updateSetupUI called before DOM references were initialized.");
        initializeDOMReferences();
        if(!numArticlesSetupInput) {
            console.error("ConfigManager: DOM elements for setup UI not found even after re-init.");
            return;
        }
    }

    if (numArticlesSetupInput) numArticlesSetupInput.value = state.articlesPerPage;
    if (currentNumArticlesDisplay) currentNumArticlesDisplay.textContent = state.articlesPerPage;
    if (minimumWordCountSetupInput) minimumWordCountSetupInput.value = state.minimumWordCount;
    if (currentMinimumWordCountDisplay) currentMinimumWordCountDisplay.textContent = state.minimumWordCount;

    if (summaryPromptInput) summaryPromptInput.value = state.currentSummaryPrompt;
    if (currentSummaryPromptDisplay) currentSummaryPromptDisplay.textContent = state.currentSummaryPrompt;
    if (tagGenerationPromptInput) tagGenerationPromptInput.value = state.currentTagGenerationPrompt;
    if (currentTagGenerationPromptDisplay) currentTagGenerationPromptDisplay.textContent = state.currentTagGenerationPrompt;
    if (chatPromptInput) chatPromptInput.value = state.currentChatPrompt;
    if (currentChatPromptDisplay) currentChatPromptDisplay.textContent = state.currentChatPrompt;

    if (rssFetchIntervalInput) rssFetchIntervalInput.value = state.globalRssFetchInterval;
    if (currentRssFetchIntervalDisplay) currentRssFetchIntervalDisplay.textContent = state.globalRssFetchInterval;

    populateModelDropdowns();

    console.log("ConfigManager: Setup UI elements updated.");
}

/**
 * Gathers all current settings from the state and sends them to the backend.
 */
async function saveConfiguration() {
    console.log("ConfigManager: Saving configuration to backend...");
    try {
        const settingsToSave = {
            articles_per_page: state.articlesPerPage,
            minimum_word_count: state.minimumWordCount,
            rss_fetch_interval_minutes: state.globalRssFetchInterval,
            summary_prompt: state.currentSummaryPrompt,
            chat_prompt: state.currentChatPrompt,
            tag_generation_prompt: state.currentTagGenerationPrompt,
            summary_model_name: state.currentSummaryModel,
            chat_model_name: state.currentChatModel,
            tag_model_name: state.currentTagModel,
        };

        const response = await apiService.updateConfig({ settings: settingsToSave });

        // The backend now re-initializes models, so no need to do it here.
        // We can update the state with the confirmed settings from the response if needed,
        // but it should already match the local state.
        console.log("ConfigManager: Save successful.", response);
        alert('Settings saved successfully!');

    } catch (error) {
        console.error('Failed to save configuration:', error);
        alert('Error saving settings. Please check the console for details and refresh the page.');
    }
}

/**
 * Saves the content preference settings (articles per page, min word count).
 */
export function saveContentPreferences(articlesPerPage, minWordCount, callback) {
    const newArticlesPerPage = parseInt(articlesPerPage);
    const newMinWordCount = parseInt(minWordCount);

    if (isNaN(newArticlesPerPage) || newArticlesPerPage < 1 || newArticlesPerPage > 50) {
        alert('Please enter a number of articles per page between 1 and 50.');
        return;
    }
    if (isNaN(newMinWordCount) || newMinWordCount < 0 || newMinWordCount > 1000) {
        alert('Please enter a minimum word count between 0 and 1000.');
        return;
    }

    state.setArticlesPerPage(newArticlesPerPage);
    state.setMinimumWordCount(newMinWordCount);
    updateSetupUI();
    saveConfiguration(); // Persist all settings
    state.setCurrentPage(1);
    if (callback && typeof callback === 'function') {
        callback();
    }
}


/**
 * Saves the custom AI prompt settings.
 */
export function saveAiPrompts(newSummaryPrompt, newChatPrompt, newTagGenerationPrompt) {
    if (newSummaryPrompt && !newSummaryPrompt.includes("{text}")) {
        alert("Summary prompt must contain the placeholder {text}."); return;
    }
    if (newTagGenerationPrompt && !newTagGenerationPrompt.includes("{text}")) {
        alert("Tag Generation prompt must contain the placeholder {text}."); return;
    }
    if (newChatPrompt && !newChatPrompt.includes("{question}")) {
        alert("Chat prompt should ideally include {question}. It's also recommended to include {article_text}.");
    }

    state.setCurrentPrompts(
        newSummaryPrompt.trim() || state.defaultSummaryPrompt,
        newChatPrompt.trim() || state.defaultChatPrompt,
        newTagGenerationPrompt.trim() || state.defaultTagGenerationPrompt
    );
    updateSetupUI();
    saveConfiguration(); // Persist all settings
}

/**
 * Saves the selected AI models.
 */
export async function saveAiModels(summaryModel, chatModel, tagModel) {
    state.setCurrentModels(summaryModel, chatModel, tagModel);
    updateSetupUI();
    await saveConfiguration(); // Persist all settings
}

/**
 * Resets AI prompts to their default values from the initial config.
 */
export function resetAiPromptsToDefaults() {
    if (confirm("Are you sure you want to reset prompts to their default values?")) {
        // We don't have separate defaults anymore, so we need to reload the config.
        // A simpler approach is to just re-set them from the initial defaults,
        // but a full save is better to be consistent.
        state.setCurrentPrompts(state.defaultSummaryPrompt, state.defaultChatPrompt, state.defaultTagGenerationPrompt);
        updateSetupUI();
        saveConfiguration();
    }
}

/**
 * Saves the global RSS fetch interval preference.
 */
export function saveGlobalRssFetchInterval(interval) {
    const newInterval = parseInt(interval);
    if (!isNaN(newInterval) && newInterval >= 5) {
        state.setGlobalRssFetchInterval(newInterval);
        updateSetupUI();
        saveConfiguration();
    } else {
        alert("Please enter a valid interval (minimum 5 minutes).");
    }
}

/**
 * Attaches event listeners to the forms in the Setup Tab.
 */
export function setupFormEventListeners(callbacks = {}) {
    if (!contentPrefsForm) {
        console.warn("ConfigManager: Forms not found, cannot attach event listeners.");
        return;
    }
    contentPrefsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        saveContentPreferences(numArticlesSetupInput.value, minimumWordCountSetupInput.value, callbacks.onArticlesPerPageChange);
    });
    aiPromptsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        saveAiPrompts(summaryPromptInput.value, chatPromptInput.value, tagGenerationPromptInput.value);
    });
    resetPromptsBtn.addEventListener('click', resetAiPromptsToDefaults);
    globalRssSettingsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        saveGlobalRssFetchInterval(rssFetchIntervalInput.value);
    });
    aiModelsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        saveAiModels(summaryModelSelect.value, chatModelSelect.value, tagModelSelect.value);
    });
    console.log("ConfigManager: Setup form event listeners attached.");
}

console.log("frontend/js/configManager.js: Module loaded.");
