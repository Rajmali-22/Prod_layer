const { ipcRenderer } = require('electron');

let promptInput = null;
let generateBtn = null;
let statusDiv = null;
let micBtn = null;
let agentSelect = null;

// Voice recording state
let isRecording = false;

document.addEventListener('DOMContentLoaded', () => {
    promptInput = document.getElementById('prompt-input');
    generateBtn = document.getElementById('generate-btn');
    statusDiv = document.getElementById('status');
    micBtn = document.getElementById('mic-btn');
    agentSelect = document.getElementById('agent-select');

    // Populate agent selector from backend
    populateAgentSelector();

    // Restore last-used agent from localStorage
    try {
        const savedAgent = localStorage.getItem('ghosttype-agent');
        if (savedAgent && agentSelect) {
            agentSelect.value = savedAgent;
        }
    } catch (e) {}

    // Save agent selection on change
    if (agentSelect) {
        agentSelect.addEventListener('change', () => {
            try {
                localStorage.setItem('ghosttype-agent', agentSelect.value);
            } catch (e) {}
            ipcRenderer.send('settings-agent-change', agentSelect.value);
        });
    }

    // Generate button click
    generateBtn.addEventListener('click', handleGenerate);

    // Enter key to generate
    promptInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleGenerate();
        }
    });

    // Voice input - click to record (Python handles duration)
    if (micBtn) {
        micBtn.addEventListener('click', startRecording);
    }

    // Listen for voice shortcut from main process (Ctrl+Shift+V)
    ipcRenderer.on('start-voice-recording', () => {
        startRecording();
    });

    // Hold-to-talk events
    ipcRenderer.on('voice-recording-started', () => {
        isRecording = true;
        if (micBtn) {
            micBtn.classList.add('recording');
            micBtn.disabled = true;
        }
        showStatus('Recording... Release Ctrl+Shift+V to stop', 'loading');
    });

    ipcRenderer.on('voice-recording-stopping', () => {
        showStatus('Processing speech...', 'loading');
    });

    ipcRenderer.on('voice-recording-result', (event, result) => {
        isRecording = false;
        if (micBtn) {
            micBtn.classList.remove('recording');
            micBtn.disabled = false;
        }

        if (result.error) {
            showStatus('Error: ' + result.error, 'error');
        } else if (result.text) {
            // Append transcribed text to prompt input
            const currentText = promptInput.value.trim();
            if (currentText) {
                promptInput.value = currentText + ' ' + result.text;
            } else {
                promptInput.value = result.text;
            }
            promptInput.focus();
            showStatus('Voice input ready. Press Enter or Generate.', 'success');
        } else {
            showStatus('No speech detected. Try again.', 'error');
        }
    });

    // When AI backend pushes updated agents list, repopulate the dropdown
    ipcRenderer.on('agents-updated', (event, agents) => {
        if (agents && agents.length > 0 && agentSelect) {
            populateAgentSelectorWithData(agents);
        }
    });

    // Clear prompt input when requested (after injection or cancel)
    ipcRenderer.on('clear-prompt', () => {
        if (promptInput) {
            promptInput.value = '';
        }
        if (statusDiv) {
            statusDiv.textContent = '';
            statusDiv.classList.add('hidden');
        }
    });
});


function populateAgentSelectorWithData(agents) {
    if (!agents || !agentSelect) return;

    // Clear existing options
    agentSelect.innerHTML = '';

    // Group agents
    const groups = { auto: [], fast: [], powerful: [], reasoning: [] };
    for (const a of agents) {
        const g = a.group || 'powerful';
        if (!groups[g]) groups[g] = [];
        groups[g].push(a);
    }

    // Add Auto first
    for (const a of (groups.auto || [])) {
        const opt = document.createElement('option');
        opt.value = a.value;
        opt.textContent = a.label;
        agentSelect.appendChild(opt);
    }

    // Add grouped models
    const groupLabels = { fast: 'Fast', powerful: 'Powerful', reasoning: 'Reasoning' };
    for (const gName of ['fast', 'powerful', 'reasoning']) {
        const items = groups[gName] || [];
        if (items.length === 0) continue;
        const optgroup = document.createElement('optgroup');
        optgroup.label = groupLabels[gName];
        for (const a of items) {
            const opt = document.createElement('option');
            opt.value = a.value;
            opt.textContent = a.label;
            optgroup.appendChild(opt);
        }
        agentSelect.appendChild(optgroup);
    }

    // Restore saved selection
    const savedAgent = localStorage.getItem('ghosttype-agent');
    if (savedAgent) {
        agentSelect.value = savedAgent;
    }
}

async function populateAgentSelector() {
    try {
        const agents = await ipcRenderer.invoke('get-agents');
        populateAgentSelectorWithData(agents);
    } catch (e) {
        console.error('Failed to populate agent selector:', e);
    }
}

async function handleGenerate() {
    const prompt = promptInput.value.trim();
    const toneSelect = document.getElementById('tone-select');
    const tone = toneSelect ? toneSelect.value : 'normal';
    const agent = agentSelect ? agentSelect.value : 'auto';

    // Get settings from localStorage (synced with settings window)
    let humanize = false;
    let autoInject = false;
    try {
        const saved = localStorage.getItem('ghosttype-settings');
        if (saved) {
            const settings = JSON.parse(saved);
            humanize = settings.humanizeEnabled || false;
            autoInject = settings.autoInjectEnabled || false;
        }
    } catch (e) {}

    if (!prompt) {
        showStatus('Please enter a prompt', 'error');
        return;
    }

    generateBtn.disabled = true;
    showStatus('Generating text...', 'loading');

    try {
        const context = { tone: tone, humanize: humanize, agent: agent };
        const result = await ipcRenderer.invoke('generate-text', prompt, context);

        if (result.error) {
            showStatus('Error: ' + result.error, 'error');
        } else if (result.text) {
            if (autoInject) {
                // Auto mode: inject directly without showing suggestion
                // Clear UI first, then inject
                promptInput.value = '';
                statusDiv.classList.add('hidden');
                // Wait for injection to complete
                await ipcRenderer.invoke('auto-inject-text', result.text, humanize);
            } else {
                // Suggestion mode: show popup for approval
                ipcRenderer.send('set-generated-text', result.text, humanize);
                ipcRenderer.invoke('show-inline-suggestion', result.text);
                showStatus('Ctrl+Shift+P to paste | Esc to cancel', 'success');
            }
        } else {
            showStatus('Unexpected response format', 'error');
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    } finally {
        generateBtn.disabled = false;
    }
}

function showStatus(message, type) {
    statusDiv.textContent = message;
    statusDiv.className = 'status ' + (type || '');
    statusDiv.classList.remove('hidden');
}

// Voice recording function - uses Python for recording and Google Speech Recognition (free)
async function startRecording() {
    if (isRecording) return;

    isRecording = true;
    micBtn.classList.add('recording');
    micBtn.disabled = true;
    showStatus('Listening... Speak now (stops on silence)', 'loading');

    try {
        // Call Python to record and transcribe
        const result = await ipcRenderer.invoke('transcribe-audio', {
            timeout: 30,       // Max wait for speech to start
            phraseTimeout: 20  // Max recording duration
        });

        if (result.error) {
            showStatus('Error: ' + result.error, 'error');
        } else if (result.text) {
            // Append transcribed text to prompt input
            const currentText = promptInput.value.trim();
            if (currentText) {
                promptInput.value = currentText + ' ' + result.text;
            } else {
                promptInput.value = result.text;
            }
            promptInput.focus();
            showStatus('Voice input ready. Press Enter or Generate.', 'success');
        } else {
            showStatus('No speech detected. Try again.', 'error');
        }
    } catch (error) {
        showStatus('Voice input failed: ' + error.message, 'error');
    } finally {
        isRecording = false;
        micBtn.classList.remove('recording');
        micBtn.disabled = false;
    }
}

