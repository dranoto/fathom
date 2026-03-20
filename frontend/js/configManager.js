// frontend/js/configManager.js
import * as state from './state.js';
import * as apiService from './apiService.js';

/**
 * This module handles loading, saving, and applying application configurations.
 */

// --- DOM Element References for the Setup Tab ---
let numArticlesSetupInput, currentNumArticlesDisplay,
    summaryPromptInput, currentSummaryPromptDisplay,
    tagGenerationPromptInput, currentTagGenerationPromptDisplay,
    chatPromptInput, currentChatPromptDisplay,
    contentPrefsForm, aiPromptsForm, resetPromptsBtn;

/**
 * Initializes the configuration manager by fetching DOM elements.
 */
export function initializeDOMReferences() {
    numArticlesSetupInput = document.getElementById('num_articles_setup');
    currentNumArticlesDisplay = document.getElementById('current-num-articles-display');
    summaryPromptInput = document.getElementById('summary-prompt-input');
    currentSummaryPromptDisplay = document.getElementById('current-summary-prompt-display');
    tagGenerationPromptInput = document.getElementById('tag-generation-prompt-input');
    currentTagGenerationPromptDisplay = document.getElementById('current-tag-generation-prompt-display');
    chatPromptInput = document.getElementById('chat-prompt-input');
    currentChatPromptDisplay = document.getElementById('current-chat-prompt-display');

    contentPrefsForm = document.getElementById('content-prefs-form');
    aiPromptsForm = document.getElementById('ai-prompts-form');
    resetPromptsBtn = document.getElementById('reset-prompts-btn');

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

    state.setArticlesPerPage(settings.articles_per_page);

    state.setDefaultPrompts(settings.summary_prompt, settings.chat_prompt, settings.tag_generation_prompt);
    state.setCurrentPrompts(settings.summary_prompt, settings.chat_prompt, settings.tag_generation_prompt);

    updateSetupUI();
    console.log("ConfigManager: Configurations loaded and UI updated.");
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

    if (summaryPromptInput) summaryPromptInput.value = state.currentSummaryPrompt;
    if (currentSummaryPromptDisplay) currentSummaryPromptDisplay.textContent = state.currentSummaryPrompt;
    if (tagGenerationPromptInput) tagGenerationPromptInput.value = state.currentTagGenerationPrompt;
    if (currentTagGenerationPromptDisplay) currentTagGenerationPromptDisplay.textContent = state.currentTagGenerationPrompt;
    if (chatPromptInput) chatPromptInput.value = state.currentChatPrompt;
    if (currentChatPromptDisplay) currentChatPromptDisplay.textContent = state.currentChatPrompt;

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
            summary_prompt: state.currentSummaryPrompt,
            chat_prompt: state.currentChatPrompt,
            tag_generation_prompt: state.currentTagGenerationPrompt,
        };

        const response = await apiService.updateConfig({ settings: settingsToSave });

        console.log("ConfigManager: Save successful.", response);
        alert('Settings saved successfully!');

    } catch (error) {
        console.error('Failed to save configuration:', error);
        alert('Error saving settings. Please check the console for details and refresh the page.');
    }
}

/**
 * Saves the content preference settings (articles per page).
 */
export async function saveContentPreferences(articlesPerPage, callback) {
    const newArticlesPerPage = parseInt(articlesPerPage);

    if (isNaN(newArticlesPerPage) || newArticlesPerPage < 1 || newArticlesPerPage > 50) {
        alert('Please enter a number of articles per page between 1 and 50.');
        return;
    }

    const hasChanged = newArticlesPerPage !== state.articlesPerPage;
    if (!hasChanged) {
        console.log("ConfigManager: No changes detected in content preferences. Skipping save.");
        return;
    }

    state.setArticlesPerPage(newArticlesPerPage);
    updateSetupUI();

    await saveConfiguration();

    state.setCurrentPage(1);
    if (callback && typeof callback === 'function') {
        await callback();
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
    saveConfiguration();
}

/**
 * Resets AI prompts to their default values from the initial config.
 */
export function resetAiPromptsToDefaults() {
    if (confirm("Are you sure you want to reset prompts to their default values?")) {
        state.setCurrentPrompts(state.defaultSummaryPrompt, state.defaultChatPrompt, state.defaultTagGenerationPrompt);
        updateSetupUI();
        saveConfiguration();
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
    contentPrefsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveContentPreferences(numArticlesSetupInput.value, callbacks.onArticlesPerPageChange);
    });
    aiPromptsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        saveAiPrompts(summaryPromptInput.value, chatPromptInput.value, tagGenerationPromptInput.value);
    });
    resetPromptsBtn.addEventListener('click', resetAiPromptsToDefaults);
    console.log("ConfigManager: Setup form event listeners attached.");
}

console.log("frontend/js/configManager.js: Module loaded.");
