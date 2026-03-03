const { ipcRenderer } = require('electron');

// Settings state
let settings = {
    masterEnabled: true,
    humanizeEnabled: false,
    autoInjectEnabled: false,
    liveModeEnabled: false,
    codingModeEnabled: false,
    ultraHumanEnabled: false,
    darkMode: true,
    ghostModeEnabled: true  // default ON = hidden from screen share
};

// DOM Elements
let masterToggle;
let darkModeToggle;
let humanizeToggle;
let autoInjectToggle;
let liveModeToggle;
let codingModeToggle;
let ultraHumanToggle;
let ghostModeToggle;
let closeBtn;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    masterToggle = document.getElementById('master-toggle');
    darkModeToggle = document.getElementById('dark-mode-toggle');
    humanizeToggle = document.getElementById('humanize-toggle');
    autoInjectToggle = document.getElementById('auto-inject-toggle');
    liveModeToggle = document.getElementById('live-mode-toggle');
    codingModeToggle = document.getElementById('coding-mode-toggle');
    ultraHumanToggle = document.getElementById('ultra-human-toggle');
    ghostModeToggle = document.getElementById('ghost-mode-toggle');
    closeBtn = document.getElementById('close-btn');

    await loadSettings();
    setupEventListeners();
    setupSidebarNavigation();
    updateUI();
    initProviderUI();
});

function setupEventListeners() {
    // Master toggle
    masterToggle.addEventListener('change', () => {
        settings.masterEnabled = masterToggle.checked;
        saveSettings();
        ipcRenderer.send('settings-master-toggle', settings.masterEnabled);
        updateDisabledState();
    });

    // Dark mode toggle
    darkModeToggle.addEventListener('change', () => {
        settings.darkMode = darkModeToggle.checked;
        saveSettings();
        applyTheme();
    });

    // Human-like typing toggle
    humanizeToggle.addEventListener('change', () => {
        settings.humanizeEnabled = humanizeToggle.checked;
        saveSettings();
        ipcRenderer.send('settings-humanize-toggle', settings.humanizeEnabled);
    });

    // Auto-inject toggle
    autoInjectToggle.addEventListener('change', () => {
        settings.autoInjectEnabled = autoInjectToggle.checked;
        saveSettings();
        ipcRenderer.invoke('set-auto-inject', settings.autoInjectEnabled);
    });

    // Live mode toggle
    liveModeToggle.addEventListener('change', () => {
        settings.liveModeEnabled = liveModeToggle.checked;
        saveSettings();
        ipcRenderer.send('settings-live-mode-toggle', settings.liveModeEnabled);
    });

    // Coding mode toggle
    codingModeToggle.addEventListener('change', () => {
        settings.codingModeEnabled = codingModeToggle.checked;
        saveSettings();
        ipcRenderer.send('settings-coding-mode-toggle', settings.codingModeEnabled);
    });

    // Ultra Human typing toggle
    ultraHumanToggle.addEventListener('change', () => {
        settings.ultraHumanEnabled = ultraHumanToggle.checked;
        saveSettings();
        ipcRenderer.send('settings-ultra-human-toggle', settings.ultraHumanEnabled);
    });

    // Ghost mode toggle
    ghostModeToggle.addEventListener('change', () => {
        settings.ghostModeEnabled = ghostModeToggle.checked;
        saveSettings();
        ipcRenderer.send('settings-ghost-mode-toggle', settings.ghostModeEnabled);
    });

    // Close button
    closeBtn.addEventListener('click', () => {
        ipcRenderer.send('close-settings-window');
    });
}

async function loadSettings() {
    // Load from localStorage
    try {
        const saved = localStorage.getItem('ghosttype-settings');
        if (saved) {
            const parsed = JSON.parse(saved);
            settings = { ...settings, ...parsed };
        }
    } catch (e) {
        console.error('Failed to load settings from localStorage:', e);
    }

    // Push saved settings to main first (so humanize etc. persist after paste/escape or restart)
    try {
        ipcRenderer.send('settings-init-sync', settings);
    } catch (e) {
        console.error('Failed to push settings to main:', e);
    }
    // Then sync from main (so we show current runtime state)
    try {
        const mainState = await ipcRenderer.invoke('get-settings-state');
        if (mainState) {
            settings.masterEnabled = mainState.masterEnabled;
            settings.autoInjectEnabled = mainState.autoInjectEnabled;
            settings.humanizeEnabled = mainState.humanizeEnabled;
            settings.liveModeEnabled = mainState.liveModeEnabled;
            settings.codingModeEnabled = mainState.codingModeEnabled;
            settings.ultraHumanEnabled = mainState.ultraHumanEnabled;
            if (mainState.ghostModeEnabled !== undefined) settings.ghostModeEnabled = mainState.ghostModeEnabled;
        }
    } catch (e) {
        console.error('Failed to sync settings with main process:', e);
    }
}

function saveSettings() {
    try {
        localStorage.setItem('ghosttype-settings', JSON.stringify(settings));
    } catch (e) {
        console.error('Failed to save settings:', e);
    }
}

function updateUI() {
    masterToggle.checked = settings.masterEnabled;
    darkModeToggle.checked = settings.darkMode;
    humanizeToggle.checked = settings.humanizeEnabled;
    autoInjectToggle.checked = settings.autoInjectEnabled;
    liveModeToggle.checked = settings.liveModeEnabled;
    codingModeToggle.checked = settings.codingModeEnabled;
    ultraHumanToggle.checked = settings.ultraHumanEnabled;
    ghostModeToggle.checked = settings.ghostModeEnabled;
    applyTheme();
    updateDisabledState();
}

function updateDisabledState() {
    // Disable other toggles when master is off
    const isEnabled = settings.masterEnabled;
    humanizeToggle.disabled = !isEnabled;
    autoInjectToggle.disabled = !isEnabled;
    liveModeToggle.disabled = !isEnabled;
    codingModeToggle.disabled = !isEnabled;
    ultraHumanToggle.disabled = !isEnabled;

    // Visual feedback
    const behaviorItems = document.querySelectorAll('.setting-item');
    behaviorItems.forEach((item, index) => {
        // Skip master toggle (index 0) and dark mode (index 1)
        if (index > 1) {
            item.style.opacity = isEnabled ? '1' : '0.5';
        }
    });
}

function applyTheme() {
    const body = document.body;

    if (settings.darkMode) {
        body.classList.remove('light-mode');
    } else {
        body.classList.add('light-mode');
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// PROVIDER MANAGEMENT UI
// ══════════════════════════════════════════════════════════════════════════════

const PROVIDER_NAMES = {
    'GROQ_API_KEY': 'Groq',
    'MISTRAL_API_KEY': 'Mistral',
    'DEEPSEEK_API_KEY': 'DeepSeek',
    'ANTHROPIC_API_KEY': 'Anthropic',
    'OPENAI_API_KEY': 'OpenAI',
    'GEMINI_API_KEY': 'Gemini',
    'XAI_API_KEY': 'xAI (Grok)',
    'TOGETHERAI_API_KEY': 'Together AI',
    'PERPLEXITYAI_API_KEY': 'Perplexity',
    'COHERE_API_KEY': 'Cohere',
    'REPLICATE_API_TOKEN': 'Replicate',
};

// Models for each provider (for testing)
const PROVIDER_TEST_MODELS = {
    'GROQ_API_KEY': 'groq/llama-3.3-70b-versatile',
    'MISTRAL_API_KEY': 'mistral/mistral-small-latest',
    'DEEPSEEK_API_KEY': 'deepseek/deepseek-chat',
    'ANTHROPIC_API_KEY': 'anthropic/claude-sonnet-4-20250514',
    'OPENAI_API_KEY': 'openai/gpt-4o-mini',
    'GEMINI_API_KEY': 'gemini/gemini-2.0-flash',
    'XAI_API_KEY': 'xai/grok-2-latest',
    'TOGETHERAI_API_KEY': 'together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo',
    'PERPLEXITYAI_API_KEY': 'perplexity/sonar-pro',
    'COHERE_API_KEY': 'cohere_chat/command-r-plus',
    'REPLICATE_API_TOKEN': 'replicate/meta/meta-llama-3.1-405b-instruct',
};

async function initProviderUI() {
    const saveKeyBtn = document.getElementById('save-key-btn');
    const keyStatus = document.getElementById('key-status');

    if (saveKeyBtn) {
        saveKeyBtn.addEventListener('click', async () => {
            const providerSelect = document.getElementById('new-key-provider');
            const keyInput = document.getElementById('new-key-input');
            const provider = providerSelect.value;
            const key = keyInput.value.trim();

            if (!provider) {
                keyStatus.textContent = 'Select a provider';
                keyStatus.className = 'key-status error';
                return;
            }
            if (!key) {
                keyStatus.textContent = 'Enter an API key';
                keyStatus.className = 'key-status error';
                return;
            }

            try {
                const result = await ipcRenderer.invoke('save-api-key', provider, key);
                if (result.success) {
                    keyStatus.textContent = 'Key saved! Restart AI backend to apply.';
                    keyStatus.className = 'key-status success';
                    keyInput.value = '';
                    providerSelect.value = '';
                    // Refresh provider cards
                    await refreshProviderCards();
                } else {
                    keyStatus.textContent = 'Error: ' + (result.error || 'Unknown error');
                    keyStatus.className = 'key-status error';
                }
            } catch (e) {
                keyStatus.textContent = 'Error: ' + e.message;
                keyStatus.className = 'key-status error';
            }
        });
    }

    await refreshProviderCards();
}

async function refreshProviderCards() {
    const container = document.getElementById('provider-cards');
    if (!container) return;

    try {
        const providers = await ipcRenderer.invoke('get-providers');
        container.innerHTML = '';

        const configured = providers.filter(p => p.configured);
        if (configured.length === 0) {
            container.innerHTML = '<div style="padding: 12px 20px; font-size: 13px; color: var(--text-secondary);">No providers configured. Add an API key below.</div>';
            return;
        }

        for (const p of configured) {
            const name = PROVIDER_NAMES[p.envVar] || p.envVar;
            const card = document.createElement('div');
            card.className = 'provider-card';
            card.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span class="status-badge active"></span>
                    <span class="provider-name">${name}</span>
                </div>
                <div class="provider-actions">
                    <button class="test-btn" data-env="${p.envVar}">Test</button>
                    <button class="remove-btn" data-env="${p.envVar}" title="Remove key">×</button>
                </div>
            `;
            container.appendChild(card);
        }

        // Attach event listeners
        container.querySelectorAll('.test-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const envVar = btn.dataset.env;
                const model = PROVIDER_TEST_MODELS[envVar];
                if (!model) return;

                btn.textContent = '...';
                btn.className = 'test-btn testing';

                try {
                    const result = await ipcRenderer.invoke('test-provider', model);
                    if (result.success) {
                        btn.textContent = 'Pass';
                        btn.className = 'test-btn pass';
                    } else {
                        btn.textContent = 'Fail';
                        btn.className = 'test-btn fail';
                        btn.title = result.message || 'Test failed';
                    }
                } catch (e) {
                    btn.textContent = 'Fail';
                    btn.className = 'test-btn fail';
                }

                // Reset after 3 seconds
                setTimeout(() => {
                    btn.textContent = 'Test';
                    btn.className = 'test-btn';
                    btn.title = '';
                }, 3000);
            });
        });

        container.querySelectorAll('.remove-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const envVar = btn.dataset.env;
                try {
                    await ipcRenderer.invoke('save-api-key', envVar, '');
                    await refreshProviderCards();
                } catch (e) {
                    console.error('Failed to remove key:', e);
                }
            });
        });

        // Update default provider dropdown
        const defaultSelect = document.getElementById('default-provider');
        if (defaultSelect) {
            const currentVal = defaultSelect.value;
            defaultSelect.innerHTML = '<option value="auto">Auto</option>';
            for (const p of configured) {
                const name = PROVIDER_NAMES[p.envVar] || p.envVar;
                const opt = document.createElement('option');
                opt.value = PROVIDER_TEST_MODELS[p.envVar] || p.envVar;
                opt.textContent = name;
                defaultSelect.appendChild(opt);
            }
            defaultSelect.value = currentVal;
        }
    } catch (e) {
        console.error('Failed to refresh provider cards:', e);
    }
}

// Sidebar navigation setup
function setupSidebarNavigation() {
    const sidebarItems = document.querySelectorAll('.sidebar-item');
    const sections = document.querySelectorAll('.section');

    sidebarItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove active class from all items and sections
            sidebarItems.forEach(i => i.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active-section'));

            // Add active class to clicked item
            item.classList.add('active');

            // Show corresponding section
            const sectionId = item.dataset.section + '-section';
            const section = document.getElementById(sectionId);
            if (section) {
                section.classList.add('active-section');
            }
        });
    });

    // Set initial active section
    const initialSection = document.querySelector('.sidebar-item.active');
    if (initialSection) {
        const sectionId = initialSection.dataset.section + '-section';
        const section = document.getElementById(sectionId);
        if (section) {
            section.classList.add('active-section');
        }
    }
}

// Listen for settings sync from main process
ipcRenderer.on('sync-settings', (event, newSettings) => {
    if (newSettings.masterEnabled !== undefined) {
        settings.masterEnabled = newSettings.masterEnabled;
    }
    if (newSettings.humanizeEnabled !== undefined) {
        settings.humanizeEnabled = newSettings.humanizeEnabled;
    }
    if (newSettings.autoInjectEnabled !== undefined) {
        settings.autoInjectEnabled = newSettings.autoInjectEnabled;
    }
    if (newSettings.liveModeEnabled !== undefined) {
        settings.liveModeEnabled = newSettings.liveModeEnabled;
    }
    if (newSettings.codingModeEnabled !== undefined) {
        settings.codingModeEnabled = newSettings.codingModeEnabled;
    }
    if (newSettings.ultraHumanEnabled !== undefined) {
        settings.ultraHumanEnabled = newSettings.ultraHumanEnabled;
    }
    if (newSettings.ghostModeEnabled !== undefined) {
        settings.ghostModeEnabled = newSettings.ghostModeEnabled;
    }
    if (newSettings.darkMode !== undefined) {
        settings.darkMode = newSettings.darkMode;
    }
    updateUI();
});

// Add cancel button functionality for API key input
function setupCancelButton() {
    const cancelBtn = document.getElementById('cancel-key-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            document.getElementById('new-key-provider').value = '';
            document.getElementById('new-key-input').value = '';
            document.getElementById('key-status').textContent = '';
        });
    }
}

// Call this after DOM is loaded
setTimeout(setupCancelButton, 100);
