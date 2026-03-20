// frontend/js/debugManager.js
import * as apiService from './apiService.js';

let debugPanel = null;
let debugToggleBtn = null;
let isPanelVisible = false;
let pollingInterval = null;
let lastDebugData = null;

export function initDebugManager() {
    console.log("DebugManager: Initializing...");
    
    createDebugPanel();
    setupKeyboardShortcut();
    
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('debug') === 'true') {
        showDebugPanel();
    }
    
    console.log("DebugManager: Initialized. Press Ctrl+Shift+D to toggle debug panel.");
}

function createDebugPanel() {
    debugPanel = document.createElement('div');
    debugPanel.id = 'debug-panel';
    debugPanel.innerHTML = `
        <style>
            #debug-panel {
                position: fixed;
                bottom: 10px;
                right: 10px;
                width: 400px;
                max-height: 500px;
                background: #1a1a2e;
                border: 1px solid #00ff88;
                border-radius: 8px;
                color: #e0e0e0;
                font-family: monospace;
                font-size: 12px;
                z-index: 10000;
                display: none;
                flex-direction: column;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
            }
            #debug-panel.visible {
                display: flex;
            }
            #debug-panel .panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px;
                background: #16213e;
                border-radius: 8px 8px 0 0;
                cursor: move;
            }
            #debug-panel .panel-title {
                font-weight: bold;
                color: #00ff88;
            }
            #debug-panel .panel-controls {
                display: flex;
                gap: 8px;
            }
            #debug-panel .panel-controls button {
                background: #0f3460;
                border: 1px solid #00ff88;
                color: #00ff88;
                padding: 4px 8px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 11px;
            }
            #debug-panel .panel-controls button:hover {
                background: #00ff88;
                color: #1a1a2e;
            }
            #debug-panel .panel-content {
                flex: 1;
                overflow-y: auto;
                padding: 10px;
            }
            #debug-panel .status-section {
                margin-bottom: 12px;
                padding-bottom: 12px;
                border-bottom: 1px solid #333;
            }
            #debug-panel .status-section:last-child {
                border-bottom: none;
                margin-bottom: 0;
            }
            #debug-panel .status-header {
                font-weight: bold;
                color: #00ff88;
                margin-bottom: 6px;
            }
            #debug-panel .status-row {
                display: flex;
                justify-content: space-between;
                padding: 2px 0;
            }
            #debug-panel .status-label {
                color: #888;
            }
            #debug-panel .status-value {
                color: #fff;
            }
            #debug-panel .status-value.success {
                color: #00ff88;
            }
            #debug-panel .status-value.error {
                color: #ff6b6b;
            }
            #debug-panel .status-value.warning {
                color: #ffd93d;
            }
            #debug-panel .extension-dot {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 6px;
            }
            #debug-panel .extension-dot.loaded {
                background: #00ff88;
            }
            #debug-panel .extension-dot.not-loaded {
                background: #ff6b6b;
            }
            #debug-panel .scrape-result {
                padding: 6px;
                margin: 4px 0;
                background: #16213e;
                border-radius: 4px;
                font-size: 11px;
            }
            #debug-panel .scrape-result.success {
                border-left: 3px solid #00ff88;
            }
            #debug-panel .scrape-result.error {
                border-left: 3px solid #ff6b6b;
            }
            #debug-panel .test-scrape-input {
                display: flex;
                gap: 6px;
                margin-top: 8px;
            }
            #debug-panel .test-scrape-input input {
                flex: 1;
                background: #0f3460;
                border: 1px solid #333;
                color: #fff;
                padding: 6px;
                border-radius: 4px;
                font-size: 11px;
            }
            #debug-panel .test-scrape-input button {
                background: #00ff88;
                color: #1a1a2e;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 11px;
            }
            #debug-panel .refresh-btn {
                background: #0f3460;
                color: #00ff88;
                border: 1px solid #00ff88;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
                margin-top: 8px;
                width: 100%;
            }
            #debug-panel .refresh-btn:hover {
                background: #00ff88;
                color: #1a1a2e;
            }
        </style>
        <div class="panel-header">
            <span class="panel-title">🔧 Debug Panel</span>
            <div class="panel-controls">
                <button id="debug-refresh-btn" title="Refresh">↻</button>
                <button id="debug-minimize-btn" title="Minimize">−</button>
                <button id="debug-close-btn" title="Close">×</button>
            </div>
        </div>
        <div class="panel-content">
            <div class="status-section">
                <div class="status-header">Extension Status</div>
                <div class="status-row">
                    <span class="status-label">Status:</span>
                    <span class="status-value" id="debug-ext-status">
                        <span class="extension-dot not-loaded"></span>Unknown
                    </span>
                </div>
                <div class="status-row">
                    <span class="status-label">Service Workers:</span>
                    <span class="status-value" id="debug-ext-sw">-</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Version:</span>
                    <span class="status-value" id="debug-ext-version">-</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Path:</span>
                    <span class="status-value" id="debug-ext-path" style="font-size:10px;word-break:break-all;">-</span>
                </div>
            </div>
            
            <div class="status-section">
                <div class="status-header">Server Status</div>
                <div class="status-row">
                    <span class="status-label">Uptime:</span>
                    <span class="status-value" id="debug-uptime">-</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Debug Level:</span>
                    <span class="status-value" id="debug-level">-</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Headless:</span>
                    <span class="status-value" id="debug-headless">-</span>
                </div>
            </div>
            
            <div class="status-section">
                <div class="status-header">Feeds</div>
                <div id="debug-feeds-list">Loading...</div>
            </div>
            
            <div class="status-section">
                <div class="status-header">Test Scrape</div>
                <div class="test-scrape-input">
                    <input type="text" id="debug-test-url" placeholder="Enter URL to test..." value="https://www.nytimes.com/2026/03/19/world/middleeast/trump-iran-south-pars-gas-field.html">
                    <button id="debug-test-scrape-btn">Go</button>
                </div>
            </div>
            
            <div class="status-section">
                <div class="status-header">Recent Scrapes</div>
                <div id="debug-scrapes-list">No recent scrapes</div>
            </div>
            
            <button class="refresh-btn" id="debug-force-refresh-btn">Force Feed Refresh</button>
        </div>
    `;
    
    document.body.appendChild(debugPanel);
    
    debugToggleBtn = document.createElement('button');
    debugToggleBtn.id = 'debug-toggle-btn';
    debugToggleBtn.innerHTML = '🔧';
    debugToggleBtn.title = 'Toggle Debug Panel (Ctrl+Shift+D)';
    debugToggleBtn.style.cssText = `
        position: fixed;
        bottom: 10px;
        right: 10px;
        width: 40px;
        height: 40px;
        background: #1a1a2e;
        border: 1px solid #00ff88;
        border-radius: 50%;
        color: #00ff88;
        font-size: 18px;
        cursor: pointer;
        z-index: 9999;
        display: none;
    `;
    document.body.appendChild(debugToggleBtn);
    
    setupEventListeners();
}

function setupEventListeners() {
    document.getElementById('debug-close-btn').addEventListener('click', hideDebugPanel);
    document.getElementById('debug-minimize-btn').addEventListener('click', hideDebugPanel);
    document.getElementById('debug-refresh-btn').addEventListener('click', refreshDebugStatus);
    debugToggleBtn.addEventListener('click', toggleDebugPanel);
    
    document.getElementById('debug-test-scrape-btn').addEventListener('click', async () => {
        const url = document.getElementById('debug-test-url').value;
        if (url) {
            await testScrape(url);
        }
    });
    
    document.getElementById('debug-force-refresh-btn').addEventListener('click', async () => {
        try {
            await apiService.triggerRssRefresh();
            alert('Feed refresh triggered!');
            setTimeout(refreshDebugStatus, 2000);
        } catch (error) {
            alert('Error triggering refresh: ' + error.message);
        }
    });
}

function setupKeyboardShortcut() {
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key === 'D') {
            e.preventDefault();
            toggleDebugPanel();
        }
    });
}

export function showDebugPanel() {
    if (!debugPanel) return;
    isPanelVisible = true;
    debugPanel.classList.add('visible');
    debugToggleBtn.style.display = 'none';
    startPolling();
    refreshDebugStatus();
}

function hideDebugPanel() {
    if (!debugPanel) return;
    isPanelVisible = false;
    debugPanel.classList.remove('visible');
    debugToggleBtn.style.display = 'block';
    stopPolling();
}

function toggleDebugPanel() {
    if (isPanelVisible) {
        hideDebugPanel();
    } else {
        showDebugPanel();
    }
}

function startPolling() {
    if (pollingInterval) return;
    pollingInterval = setInterval(refreshDebugStatus, 5000);
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

async function refreshDebugStatus() {
    try {
        const data = await apiService.fetchDebugStatus();
        lastDebugData = data;
        updateDebugUI(data);
    } catch (error) {
        console.error('DebugManager: Error fetching status:', error);
    }
}

function updateDebugUI(data) {
    const extDot = document.querySelector('#debug-ext-status .extension-dot');
    const extStatusText = document.getElementById('debug-ext-status');
    if (data.extension_loaded) {
        extDot.className = 'extension-dot loaded';
        extStatusText.innerHTML = '<span class="extension-dot loaded"></span>Loaded';
    } else {
        extDot.className = 'extension-dot not-loaded';
        extStatusText.innerHTML = '<span class="extension-dot not-loaded"></span>Not Loaded';
    }
    
    document.getElementById('debug-ext-sw').textContent = data.service_workers || 0;
    document.getElementById('debug-ext-version').textContent = data.extension_version || '-';
    document.getElementById('debug-ext-path').textContent = data.extension_path || '-';
    document.getElementById('debug-uptime').textContent = data.uptime_human || '-';
    document.getElementById('debug-level').textContent = data.debug_level || '-';
    document.getElementById('debug-headless').textContent = data.config?.headless_browser ? 'Yes' : 'No';
    
    const feedsList = document.getElementById('debug-feeds-list');
    if (data.feed_status && data.feed_status.length > 0) {
        feedsList.innerHTML = data.feed_status.map(feed => `
            <div class="status-row">
                <span>${feed.name}</span>
                <span class="status-value">${feed.article_count} articles</span>
            </div>
        `).join('');
    } else {
        feedsList.innerHTML = '<span class="status-value warning">No feeds configured</span>';
    }
    
    const scrapesList = document.getElementById('debug-scrapes-list');
    if (data.recent_scrapes && data.recent_scrapes.length > 0) {
        scrapesList.innerHTML = data.recent_scrapes.slice(0, 5).map(scrape => {
            const success = scrape.success;
            const wordCount = scrape.word_count || 0;
            const error = scrape.error ? ` - ${scrape.error.substring(0, 50)}` : '';
            return `
                <div class="scrape-result ${success ? 'success' : 'error'}">
                    <div><strong>${success ? '✓' : '✗'}</strong> ${scrape.url?.substring(0, 40)}...</div>
                    <div style="color:#888;">Words: ${wordCount} | Time: ${scrape.time_ms}ms${error}</div>
                </div>
            `;
        }).join('');
    } else {
        scrapesList.innerHTML = '<span style="color:#888;">No recent scrapes</span>';
    }
}

async function testScrape(url) {
    const btn = document.getElementById('debug-test-scrape-btn');
    btn.textContent = 'Testing...';
    btn.disabled = true;
    
    try {
        const result = await apiService.testScrapeUrl(url);
        console.log('Test scrape result:', result);
        alert(`Scrape complete!\nSuccess: ${result.success}\nWord count: ${result.word_count}\nError: ${result.error || 'None'}\nExtension active: ${result.extension_active}`);
        refreshDebugStatus();
    } catch (error) {
        alert('Error testing scrape: ' + error.message);
    } finally {
        btn.textContent = 'Go';
        btn.disabled = false;
    }
}

export function isDebugPanelVisible() {
    return isPanelVisible;
}
