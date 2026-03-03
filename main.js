const { app, BrowserWindow, globalShortcut, ipcMain, clipboard, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const readline = require('readline');
const os = require('os');
const keystore = require(path.join(__dirname, 'src', 'electron', 'keystore.js'));

// Use python3 on macOS/Linux, python on Windows (production-friendly)
function getPythonCommand() {
  return process.platform === 'win32' ? 'python' : 'python3';
}

// Windows: set whether window is excluded from screen capture (Ghost ON) or visible in capture (Ghost OFF)
function applyWindowCaptureAffinity(win) {
  if (os.platform() !== 'win32' || !win || win.isDestroyed()) return;
  try {
    const koffi = require('koffi');
    const user32 = koffi.load('user32.dll');
    const SetWindowDisplayAffinity = user32.func('SetWindowDisplayAffinity', 'bool', ['void *', 'uint32']);
    const WDA_NONE = 0;
    const WDA_EXCLUDEFROMCAPTURE = 0x11; // Windows 10 2004+
    const buf = win.getNativeWindowHandle();
    const hwnd = buf.length === 8 ? Number(buf.readBigUInt64LE(0)) : buf.readUInt32LE(0);
    const affinity = ghostModeEnabled ? WDA_EXCLUDEFROMCAPTURE : WDA_NONE;
    const ok = SetWindowDisplayAffinity(hwnd, affinity);
    if (!ok) console.warn('SetWindowDisplayAffinity failed for window');
  } catch (e) {
    console.warn('Could not set window capture affinity:', e.message);
  }
}

function applyGhostModeToAllWindows() {
  if (mainWindow && !mainWindow.isDestroyed()) applyWindowCaptureAffinity(mainWindow);
  if (outputWindow && !outputWindow.isDestroyed()) applyWindowCaptureAffinity(outputWindow);
  if (explanationWindow && !explanationWindow.isDestroyed()) applyWindowCaptureAffinity(explanationWindow);
  if (settingsWindow && !settingsWindow.isDestroyed()) applyWindowCaptureAffinity(settingsWindow);
  if (chatWindow && !chatWindow.isDestroyed()) applyWindowCaptureAffinity(chatWindow);
}

// Try to load robotjs, but handle errors gracefully
let robot = null;
try {
  robot = require('robotjs');
} catch (error) {
  console.warn('robotjs not available:', error.message);
  console.warn('Falling back to clipboard method. Please run: npm run rebuild');
}

// Load uiohook for key release detection (hold-to-talk)
let uIOhook = null;
try {
  const uiohook = require('uiohook-napi');
  uIOhook = uiohook.uIOhook;
} catch (error) {
  // uiohook-napi not available - hold-to-talk will be disabled
}

let mainWindow = null;
let outputWindow = null;
let settingsWindow = null;
let chatWindow = null;
let isWindowVisible = false;

// Chat streaming state (separate from prompt bar)
let pendingChatRequest = null;  // { conversationId, resolve, reject, text }
let chatStreamActive = false;

// Keystroke monitor state
let keystrokeMonitor = null;
let keystrokeMonitorRL = null;
let pendingBackspaceCount = 0;  // Number of backspaces to send before injecting
let triggerMode = null;  // 'backtick', 'extension', 'clipboard', or 'prompt'
let humanizeTyping = false;  // Whether to use human-like typing
let currentAgent = 'auto';  // Selected LLM agent (model string or 'auto') for prompt bar
let chatAgent = 'auto';     // Selected LLM agent for chat window (independent)
let lastWindowTitle = '';  // Last active window title for per-window memory

// AI Backend service state (persistent process)
let aiBackend = null;
let aiBackendRL = null;
let pendingAIRequest = null;  // { resolve, reject, streaming, text }
let aiBackendReady = false;

// Master control - pause/resume all AI features
let masterEnabled = true;

// Ghost mode: when true, app is hidden from screen capture (Meet/Zoom). When false, app is visible so you can show it in meetings.
let ghostModeEnabled = true;

// Cached config (loaded once at startup)
let cachedEnv = null;

// Keystroke monitor restart settings
const MONITOR_RESTART_DELAY = 2000;  // 2 seconds
const MONITOR_MAX_RESTARTS = 5;

// Normalize text for injection - strip ALL leading whitespace
// User's cursor position + editor auto-indent handles the base indent
function normalizeTextForInjection(text) {
  if (typeof text !== 'string') return text;

  // Remove leading/trailing newlines
  text = text.replace(/^[\r\n]+/, '').replace(/[\r\n]+$/, '');
  if (!text) return text;

  // Strip ALL leading whitespace from each line
  // After Enter, cursor is already at correct position in editor
  const lines = text.split(/\r?\n/);
  const normalizedLines = lines.map(line => line.trimStart());

  return normalizedLines.join('\n');
}
let monitorRestartCount = 0;
let monitorRestartTimer = null;

/** Fix inverted caps (e.g. "hELLO" -> "Hello", "i" -> "I", "HOPE" -> "Hope") from Caps Lock or odd transcription. */
function fixInvertedCaps(str) {
  if (typeof str !== 'string' || !str) return str;
  return str
    .replace(/\b([a-z])([A-Z]*)\b/g, (_, first, rest) => first.toUpperCase() + rest.toLowerCase())
    .replace(/\b([A-Z])([A-Z]+)\b/g, (_, first, rest) => first + rest.toLowerCase());
}

// Voice recording state
let voiceProcess = null;
let isVoiceRecording = false;

// Auto-inject mode (autonomous - no suggestion popup)
let autoInjectEnabled = false;

// Live mode (auto-suggestion on typing pause)
let liveModeEnabled = false;

// Coding mode (show code + explanation windows for interviews)
let codingModeEnabled = false;
let explanationWindow = null;

// Ultra Human typing mode (chain-of-thought code injection for interviews)
let ultraHumanEnabled = false;

// Load and cache environment/config once at startup
function loadCachedConfig() {
  cachedEnv = { ...process.env };

  // All supported provider env vars
  const providerEnvVars = [
    'MISTRAL_API_KEY', 'GROQ_API_KEY', 'DEEPSEEK_API_KEY',
    'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY',
    'XAI_API_KEY', 'TOGETHERAI_API_KEY', 'PERPLEXITYAI_API_KEY',
    'COHERE_API_KEY', 'REPLICATE_API_TOKEN', 'GOOGLE_API_KEY'
  ];

  const configFiles = ['.env', 'config.example.env', 'config.env'];
  for (const configFile of configFiles) {
    const configPath = path.join(__dirname, configFile);
    if (fs.existsSync(configPath)) {
      try {
        const configContent = fs.readFileSync(configPath, 'utf8');

        // Load all provider API keys from config file
        for (const envVar of providerEnvVars) {
          const regex = new RegExp(envVar + '\\s*=\\s*([^\\s#\\n]+)');
          const match = configContent.match(regex);
          if (match) {
            const apiKey = match[1].trim().replace(/^["']|["']$/g, '');
            if (apiKey && !apiKey.includes('your-')) {
              cachedEnv[envVar] = apiKey;
            }
          }
        }
      } catch (err) {
        console.error('Failed to read config file:', configFile, err.message);
      }
    }
  }

  // Overlay encrypted keys from keystore (takes priority over .env)
  try {
    const encryptedKeys = keystore.getAllApiKeys();
    for (const [envVar, key] of Object.entries(encryptedKeys)) {
      if (key && !key.includes('your-')) {
        cachedEnv[envVar] = key;
      }
    }
  } catch (err) {
    console.warn('Failed to load encrypted keys:', err.message);
  }

  // Log which providers are configured
  const configured = providerEnvVars.filter(k => cachedEnv[k] && !cachedEnv[k].includes('your-'));
  console.log('Config loaded. Providers configured:', configured.length > 0 ? configured.join(', ') : 'none');

  if (configured.length === 0) {
    console.warn('No LLM provider keys found. Copy config.example.env to .env and set at least one API key.');
  }
}

// Load settings from localStorage via IPC
function loadSavedSettings() {
  // Settings will be synced when settings window opens
  // For now, just ensure defaults are set
  autoInjectEnabled = false;
  humanizeTyping = false;
  masterEnabled = true;
}

function createWindow() {
  const { screen } = require('electron');
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workAreaSize;

  // Calculate position at bottom center, raised slightly from edge
  const windowWidth = 700;
  const windowHeight = 80;
  const x = Math.floor((width - windowWidth) / 2);
  const y = height - windowHeight - 80;

  // Create transparent overlay window
  mainWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      enableRemoteModule: true
    },
    // Position at bottom of screen
    x: x,
    y: y
  });

  mainWindow.loadFile(path.join('src', 'renderer', 'overlay', 'index.html'));

  // Show window initially so user knows it's running
  // User can hide it with Ctrl+Shift+Space
  mainWindow.show();
  isWindowVisible = true;

  // Prevent window from being minimized
  mainWindow.setMinimumSize(700, 80);

  // Handle window close
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Allow mouse events on the window
  mainWindow.setIgnoreMouseEvents(false);

  applyWindowCaptureAffinity(mainWindow);
}

function createOutputWindow() {
  // Create a compact inline suggestion popup (like autocomplete)
  outputWindow = new BrowserWindow({
    width: 450,
    height: 180,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: false,
    focusable: true,  // Allow focus for vision input mode
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      enableRemoteModule: true
    }
  });

  outputWindow.loadFile(path.join('src', 'renderer', 'output', 'index.html'));
  outputWindow.hide();

  applyWindowCaptureAffinity(outputWindow);

  outputWindow.on('closed', () => {
    outputWindow = null;
  });
}

function createExplanationWindow() {
  // Create explanation window for coding mode (view only, not injectable)
  explanationWindow = new BrowserWindow({
    width: 400,
    height: 250,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: false,
    focusable: false,  // Don't steal focus
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      enableRemoteModule: true
    }
  });

  explanationWindow.loadFile(path.join('src', 'renderer', 'explanation', 'index.html'));
  explanationWindow.hide();

  applyWindowCaptureAffinity(explanationWindow);

  explanationWindow.on('closed', () => {
    explanationWindow = null;
  });
}

function createSettingsWindow() {
  if (settingsWindow) {
    settingsWindow.focus();
    return;
  }

  const { screen } = require('electron');
  const cursor = screen.getCursorScreenPoint();
  const display = screen.getDisplayNearestPoint(cursor);
  const workArea = display.workArea;

  // Fixed wide settings panel — no scrolling, professional layout
  const windowWidth = 720;
  const windowHeight = 560;

  // Position near center of screen
  const x = Math.round(workArea.x + (workArea.width - windowWidth) / 2);
  const y = Math.round(workArea.y + (workArea.height - windowHeight) / 2 - 40);

  settingsWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    minWidth: windowWidth,
    maxWidth: windowWidth,
    minHeight: windowHeight,
    maxHeight: windowHeight,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    minimizable: false,
    maximizable: false,
    x: x,
    y: y,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  settingsWindow.loadFile(path.join('src', 'renderer', 'settings', 'index.html'));

  applyWindowCaptureAffinity(settingsWindow);

  settingsWindow.on('closed', () => {
    settingsWindow = null;
  });

  // Close on blur (click outside)
  settingsWindow.on('blur', () => {
    if (settingsWindow) {
      settingsWindow.close();
    }
  });
}

// ============== Chat Persistence & Window ==============

const CHATS_DIR = path.join(__dirname, 'data', 'chats');
const CHATS_INDEX = path.join(CHATS_DIR, '_index.json');

function ensureChatsDir() {
  if (!fs.existsSync(CHATS_DIR)) {
    fs.mkdirSync(CHATS_DIR, { recursive: true });
  }
}

function generateId(prefix) {
  const ts = Date.now();
  const hex = Math.random().toString(16).substring(2, 6);
  return `${prefix}_${ts}_${hex}`;
}

function loadConversation(id) {
  const filePath = path.join(CHATS_DIR, `${id}.json`);
  if (!fs.existsSync(filePath)) return null;
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (e) {
    console.error('Failed to load conversation:', id, e.message);
    return null;
  }
}

function saveConversation(conv) {
  ensureChatsDir();
  const filePath = path.join(CHATS_DIR, `${conv.id}.json`);
  fs.writeFileSync(filePath, JSON.stringify(conv, null, 2), 'utf8');
  updateConversationIndex(conv);
}

function saveChatMessage(conversationId, msg) {
  const conv = loadConversation(conversationId);
  if (!conv) return null;
  conv.messages.push(msg);
  conv.updatedAt = Date.now();
  saveConversation(conv);
  return conv;
}

function loadConversationIndex() {
  if (!fs.existsSync(CHATS_INDEX)) return [];
  try {
    return JSON.parse(fs.readFileSync(CHATS_INDEX, 'utf8'));
  } catch (e) {
    return [];
  }
}

function updateConversationIndex(conv) {
  const index = loadConversationIndex();
  const existing = index.findIndex(e => e.id === conv.id);
  const lastMsg = conv.messages[conv.messages.length - 1];
  const entry = {
    id: conv.id,
    title: conv.title,
    createdAt: conv.createdAt,
    updatedAt: conv.updatedAt,
    messageCount: conv.messages.length,
    preview: lastMsg ? lastMsg.content.substring(0, 100) : ''
  };
  if (existing >= 0) {
    index[existing] = entry;
  } else {
    index.push(entry);
  }
  fs.writeFileSync(CHATS_INDEX, JSON.stringify(index, null, 2), 'utf8');
}

function deleteConversationFromIndex(id) {
  const index = loadConversationIndex().filter(e => e.id !== id);
  fs.writeFileSync(CHATS_INDEX, JSON.stringify(index, null, 2), 'utf8');
  const filePath = path.join(CHATS_DIR, `${id}.json`);
  if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
}

function rebuildConversationIndex() {
  ensureChatsDir();
  const files = fs.readdirSync(CHATS_DIR).filter(f => f.endsWith('.json') && f !== '_index.json');
  const index = [];
  for (const file of files) {
    try {
      const conv = JSON.parse(fs.readFileSync(path.join(CHATS_DIR, file), 'utf8'));
      const lastMsg = conv.messages && conv.messages[conv.messages.length - 1];
      index.push({
        id: conv.id,
        title: conv.title || 'Untitled',
        createdAt: conv.createdAt,
        updatedAt: conv.updatedAt,
        messageCount: conv.messages ? conv.messages.length : 0,
        preview: lastMsg ? lastMsg.content.substring(0, 100) : ''
      });
    } catch (e) { /* skip corrupt files */ }
  }
  index.sort((a, b) => b.updatedAt - a.updatedAt);
  fs.writeFileSync(CHATS_INDEX, JSON.stringify(index, null, 2), 'utf8');
  return index;
}

function createChatWindow() {
  if (chatWindow) {
    chatWindow.focus();
    return;
  }

  const { screen } = require('electron');
  const cursor = screen.getCursorScreenPoint();
  const display = screen.getDisplayNearestPoint(cursor);
  const workArea = display.workArea;

  const windowWidth = 900;
  const windowHeight = 650;
  const x = Math.round(workArea.x + (workArea.width - windowWidth) / 2);
  const y = Math.round(workArea.y + (workArea.height - windowHeight) / 2);

  chatWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    minWidth: 600,
    minHeight: 400,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    x: x,
    y: y,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  chatWindow.loadFile(path.join('src', 'renderer', 'chat', 'index.html'));
  applyWindowCaptureAffinity(chatWindow);

  chatWindow.on('closed', () => {
    chatWindow = null;
    chatStreamActive = false;
    pendingChatRequest = null;
  });
}

function generateChatStreaming(conversationId, userMessage, apiMessages) {
  if (!aiBackendReady) {
    if (chatWindow && !chatWindow.isDestroyed()) {
      chatWindow.webContents.send('chat-stream-error', 'AI backend not ready');
    }
    return;
  }

  chatStreamActive = true;
  pendingChatRequest = {
    conversationId,
    text: ''
  };

  if (chatWindow && !chatWindow.isDestroyed()) {
    chatWindow.webContents.send('chat-stream-start');
  }

  const sent = sendToAIBackend({
    cmd: 'generate',
    prompt: userMessage,
    messages: apiMessages,
    context: { mode: 'chat', agent: chatAgent, window: 'chat' },
    streaming: true
  });

  if (!sent) {
    chatStreamActive = false;
    pendingChatRequest = null;
    if (chatWindow && !chatWindow.isDestroyed()) {
      chatWindow.webContents.send('chat-stream-error', 'Failed to send to AI backend');
    }
    return;
  }

  // 120s timeout for chat (longer than prompt bar's 60s)
  setTimeout(() => {
    if (chatStreamActive && pendingChatRequest && pendingChatRequest.conversationId === conversationId) {
      const partialText = pendingChatRequest.text;
      chatStreamActive = false;
      pendingChatRequest = null;
      if (chatWindow && !chatWindow.isDestroyed()) {
        chatWindow.webContents.send('chat-stream-end', { text: partialText, timedOut: true });
      }
    }
  }, 120000);
}

// ============== Keystroke Monitor ==============

function startKeystrokeMonitor() {
  const pythonScript = path.join(__dirname, 'src', 'services', 'input', 'monitor.py');

  keystrokeMonitor = spawn(getPythonCommand(), [pythonScript], {
    cwd: __dirname,
    stdio: ['pipe', 'pipe', 'pipe']
  });

  // Read events from monitor's stdout
  keystrokeMonitorRL = readline.createInterface({
    input: keystrokeMonitor.stdout,
    crlfDelay: Infinity
  });

  keystrokeMonitorRL.on('line', (line) => {
    try {
      const event = JSON.parse(line);
      console.log('Received from monitor:', event.event, event.type || '');
      handleKeystrokeEvent(event);
    } catch (e) {
      console.error('Failed to parse keystroke event:', line, e);
    }
  });

  keystrokeMonitor.stderr.on('data', (data) => {
    console.error('Keystroke monitor error:', data.toString());
  });

  keystrokeMonitor.on('close', (code) => {
    console.log('Keystroke monitor exited with code:', code);
    keystrokeMonitor = null;
    keystrokeMonitorRL = null;

    // Auto-restart if unexpected exit and master is enabled
    if (masterEnabled && code !== 0 && monitorRestartCount < MONITOR_MAX_RESTARTS) {
      monitorRestartCount++;
      console.log(`Restarting keystroke monitor (attempt ${monitorRestartCount}/${MONITOR_MAX_RESTARTS})...`);
      monitorRestartTimer = setTimeout(() => {
        startKeystrokeMonitor();
      }, MONITOR_RESTART_DELAY);
    } else if (monitorRestartCount >= MONITOR_MAX_RESTARTS) {
      console.error('Keystroke monitor failed too many times. Manual restart required.');
    }
  });

  keystrokeMonitor.on('error', (err) => {
    console.error('Failed to start keystroke monitor:', err);
  });

  // Reset restart count on successful start
  monitorRestartCount = 0;
}

function sendToMonitor(command) {
  if (keystrokeMonitor && keystrokeMonitor.stdin) {
    console.log('Sending to monitor:', JSON.stringify(command));
    keystrokeMonitor.stdin.write(JSON.stringify(command) + '\n');
  } else {
    console.error('Keystroke monitor not running or stdin not available');
  }
}

// Promise-based buffer request
let pendingBufferResolve = null;

function requestBuffer() {
  return new Promise((resolve) => {
    pendingBufferResolve = resolve;
    sendToMonitor({ cmd: 'get_buffer' });
    // Timeout after 500ms
    setTimeout(() => {
      if (pendingBufferResolve) {
        pendingBufferResolve({ buffer: '', raw_count: 0 });
        pendingBufferResolve = null;
      }
    }, 500);
  });
}

function stopKeystrokeMonitor() {
  if (keystrokeMonitor) {
    sendToMonitor({ cmd: 'shutdown' });
    setTimeout(() => {
      if (keystrokeMonitor) {
        keystrokeMonitor.kill();
      }
    }, 1000);
  }
}

// ============== AI Backend Service (Persistent) ==============

function startAIBackend() {
  const pythonScript = path.join(__dirname, 'src', 'services', 'ai', 'backend.py');

  // Use cached env (loaded once at startup)
  const env = cachedEnv || process.env;

  aiBackend = spawn(getPythonCommand(), [pythonScript], {
    cwd: __dirname,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: env
  });

  // Read events from backend's stdout
  aiBackendRL = readline.createInterface({
    input: aiBackend.stdout,
    crlfDelay: Infinity
  });

  aiBackendRL.on('line', (line) => {
    try {
      const event = JSON.parse(line);
      handleAIBackendEvent(event);
    } catch (e) {
      console.error('Failed to parse AI backend event:', line, e);
    }
  });

  aiBackend.stderr.on('data', (data) => {
    console.log('AI backend debug:', data.toString());
  });

  aiBackend.on('close', (code) => {
    console.log('AI backend exited with code:', code);
    aiBackend = null;
    aiBackendRL = null;
    aiBackendReady = false;

    // Auto-restart if master is enabled
    if (masterEnabled && code !== 0) {
      console.log('Restarting AI backend...');
      setTimeout(startAIBackend, 2000);
    }
  });

  aiBackend.on('error', (err) => {
    console.error('Failed to start AI backend:', err);
  });
}

function sendToAIBackend(command) {
  if (aiBackend && aiBackend.stdin && aiBackendReady) {
    console.log('Sending to AI backend:', JSON.stringify(command).substring(0, 100));
    aiBackend.stdin.write(JSON.stringify(command) + '\n');
    return true;
  } else {
    console.error('AI backend not ready');
    return false;
  }
}

function handleAIBackendEvent(event) {
  if (event.event === 'started') {
    console.log('AI backend started, success:', event.success, 'PID:', event.pid);
    aiBackendReady = event.success;

    // Once backend is ready, fetch agents and push to renderer for dropdown
    if (aiBackendReady) {
      const agentTimeout = setTimeout(() => {
        delete pendingBackendCallbacks['agents_startup'];
      }, 5000);

      pendingBackendCallbacks['agents_startup'] = (evt) => {
        clearTimeout(agentTimeout);
        const agents = evt.agents || [];
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('agents-updated', agents);
        }
        if (chatWindow && !chatWindow.isDestroyed()) {
          chatWindow.webContents.send('agents-updated', agents);
        }
      };

      sendToAIBackend({ cmd: 'get_agents' });
    }

  } else if (event.event === 'chunk') {
    // Streaming chunk received — route to chat or prompt bar
    if (chatStreamActive && pendingChatRequest) {
      pendingChatRequest.text += event.text;
      if (chatWindow && !chatWindow.isDestroyed()) {
        chatWindow.webContents.send('chat-stream-chunk', event.text);
      }
      if (event.final) {
        const fullText = pendingChatRequest.text;
        const convId = pendingChatRequest.conversationId;
        chatStreamActive = false;
        pendingChatRequest = null;
        // Save assistant message to disk
        const assistantMsg = {
          id: generateId('msg'),
          role: 'assistant',
          content: fullText,
          timestamp: Date.now(),
          model: chatAgent
        };
        saveChatMessage(convId, assistantMsg);
        if (chatWindow && !chatWindow.isDestroyed()) {
          chatWindow.webContents.send('chat-stream-end', { text: fullText, messageId: assistantMsg.id });
        }
      }
    } else if (pendingAIRequest && pendingAIRequest.streaming) {
      pendingAIRequest.text += event.text;

      // Send to output window for live display
      if (outputWindow && !pendingAIRequest.autoInject) {
        outputWindow.webContents.send('stream-chunk', event.text);
      }

      // If final chunk, complete the request
      if (event.final) {
        const finalText = pendingAIRequest.text;
        if (outputWindow && !pendingAIRequest.autoInject) {
          outputWindow.webContents.send('stream-end');
        }
        // Store explanation if present (coding mode)
        if (event.explanation) {
          lastGeneratedExplanation = event.explanation;
        } else {
          lastGeneratedExplanation = '';
        }
        if (pendingAIRequest.resolve) {
          pendingAIRequest.resolve({ text: finalText, explanation: event.explanation || '' });
        }
        pendingAIRequest = null;
      }
    }

  } else if (event.event === 'complete') {
    // Non-streaming complete response
    if (pendingAIRequest && pendingAIRequest.resolve) {
      pendingAIRequest.resolve({ text: event.text });
      pendingAIRequest = null;
    }

  } else if (event.event === 'error') {
    console.error('AI backend error:', event.message);
    if (chatStreamActive && pendingChatRequest) {
      // Route error to chat window
      if (chatWindow && !chatWindow.isDestroyed()) {
        chatWindow.webContents.send('chat-stream-error', event.message);
      }
      chatStreamActive = false;
      pendingChatRequest = null;
    } else if (pendingAIRequest && pendingAIRequest.reject) {
      pendingAIRequest.reject(new Error(event.message));
      pendingAIRequest = null;
    }

  } else if (event.event === 'pong') {
    console.log('AI backend pong received');

  } else if (event.event === 'agents') {
    // Response to get_agents command — may be from IPC handler or startup push
    if (pendingBackendCallbacks && pendingBackendCallbacks['agents']) {
      pendingBackendCallbacks['agents'](event);
      delete pendingBackendCallbacks['agents'];
    }
    if (pendingBackendCallbacks && pendingBackendCallbacks['agents_startup']) {
      pendingBackendCallbacks['agents_startup'](event);
      delete pendingBackendCallbacks['agents_startup'];
    }

  } else if (event.event === 'test_result') {
    // Response to test_provider command
    const callbackKey = 'test_result_' + event.model;
    if (pendingBackendCallbacks && pendingBackendCallbacks[callbackKey]) {
      pendingBackendCallbacks[callbackKey](event);
      delete pendingBackendCallbacks[callbackKey];
    }

  } else if (event.event === 'stopped') {
    console.log('AI backend stopped');
  }
}

function stopAIBackend() {
  if (aiBackend) {
    sendToAIBackend({ cmd: 'shutdown' });
    setTimeout(() => {
      if (aiBackend) {
        aiBackend.kill();
      }
    }, 1000);
  }
}

// Generate text using persistent backend with streaming
async function generateTextStreaming(mode, buffer, extraParam = null, autoInject = false) {
  return new Promise((resolve, reject) => {
    if (!aiBackendReady) {
      reject(new Error('AI backend not ready'));
      return;
    }

    // Build context
    const context = { mode: mode, agent: currentAgent, window: lastWindowTitle };
    if (mode === 'extension' && extraParam) {
      context.last_output = extraParam;
    } else if (mode === 'clipboard_with_instruction' && extraParam) {
      context.instruction = extraParam;
    } else if (mode === 'explanation' && extraParam) {
      context.code = extraParam;
    }

    // Show streaming UI if not auto-inject
    if (outputWindow && !autoInject) {
      outputWindow.webContents.send('stream-start');
    }

    // Set up pending request
    pendingAIRequest = {
      resolve,
      reject,
      streaming: true,
      autoInject,
      text: ''
    };

    // Send request to backend
    const sent = sendToAIBackend({
      cmd: 'generate',
      prompt: buffer,
      context: context,
      streaming: true
    });

    if (!sent) {
      pendingAIRequest = null;
      reject(new Error('Failed to send to AI backend'));
    }

    // Timeout after 60 seconds
    setTimeout(() => {
      if (pendingAIRequest) {
        const partialText = pendingAIRequest.text;
        pendingAIRequest = null;
        if (partialText) {
          resolve({ text: partialText });
        } else {
          reject(new Error('AI request timeout'));
        }
      }
    }, 60000);
  });
}

async function handleKeystrokeEvent(event) {
  // Skip all processing if master is disabled
  if (!masterEnabled && event.event === 'trigger') {
    console.log('Master disabled, ignoring trigger');
    return;
  }

  if (event.event === 'trigger') {
    // Backtick, extension, or live trigger from keystroke monitor
    const { type, buffer, char_count, window: windowTitle, last_ai_output } = event;

    console.log('Trigger received - type:', type, 'buffer:', buffer, 'char_count:', char_count);

    // Skip if buffer is empty (nothing to rewrite)
    if (!buffer || buffer.trim().length === 0) {
      console.log('Buffer is empty, skipping');
      return;
    }

    // For live mode, check if it's enabled
    if (type === 'live' && !liveModeEnabled) {
      console.log('Live mode disabled, ignoring live trigger');
      return;
    }

    // Limit buffer size for safety (max 10KB)
    const MAX_BUFFER_SIZE = 10000;
    const safeBuffer = buffer.length > MAX_BUFFER_SIZE ? buffer.substring(0, MAX_BUFFER_SIZE) : buffer;

    // Store the backspace count for injection
    pendingBackspaceCount = char_count;
    triggerMode = type;  // 'backtick', 'extension', or 'live'

    // Generate AI suggestion (using streaming for low latency)
    try {
      // Show output window BEFORE streaming starts (for non-auto-inject)
      if (!autoInjectEnabled) {
        await showOutputWindowAtCursor();
      }

      let result;
      if (type === 'extension' && last_ai_output) {
        // Extension mode - continue writing
        result = await generateTextStreaming('extension', safeBuffer, last_ai_output, autoInjectEnabled);
      } else {
        // Backtick or Live mode - grammar/spelling fix
        result = await generateTextStreaming('backtick', safeBuffer, null, autoInjectEnabled);
      }

      if (result && result.text) {
        lastGeneratedText = result.text;
        // Store explanation if present (coding mode)
        if (result.explanation) {
          lastGeneratedExplanation = result.explanation;
        }

        // Store AI output for potential extension
        sendToMonitor({
          cmd: 'set_ai_output',
          output: result.text,
          context: safeBuffer
        });

        if (autoInjectEnabled) {
          // Auto mode: inject directly without showing suggestion
          // Reset monitor BEFORE injection so it doesn't capture injected text
          sendToMonitor({ cmd: 'reset' });
          await autoInjectWithBackspace(result.text, pendingBackspaceCount, humanizeTyping);
          // Clear state after injection
          lastGeneratedText = '';
          lastGeneratedExplanation = '';
          pendingBackspaceCount = 0;
          triggerMode = null;
          // Reset monitor again after injection to be safe
          sendToMonitor({ cmd: 'reset' });
        }
        // Note: For suggestion mode, text is already displayed via streaming
      }
    } catch (error) {
      console.error('AI generation error:', error);
      // Hide output window on error
      if (outputWindow && !autoInjectEnabled) {
        outputWindow.hide();
      }
    }

  } else if (event.event === 'window_change') {
    // Window changed - reset state and track title for per-window memory
    pendingBackspaceCount = 0;
    triggerMode = null;
    if (event.title) {
      lastWindowTitle = event.title;
    }

  } else if (event.event === 'buffer') {
    // Response to get_buffer request
    if (pendingBufferResolve) {
      pendingBufferResolve({
        buffer: event.buffer || '',
        raw_count: event.raw_count || 0
      });
      pendingBufferResolve = null;
    }

  } else if (event.event === 'started') {
    console.log('Keystroke monitor started, PID:', event.pid);

  } else if (event.event === 'error') {
    console.error('Keystroke monitor error:', event.message);
  }
}

// Auto-inject text directly without showing suggestion popup
async function autoInjectWithBackspace(text, backspaceCount, humanize = false) {
  // Normalize text: trim and re-base indent
  text = normalizeTextForInjection(text);

  return new Promise((resolve) => {
    const pythonInjectPath = path.join(__dirname, 'src', 'services', 'input', 'injector.py');

    // Escape text for Python (will be unescaped by keyboard_inject.py)
    let escapedText = text
      .replace(/\\/g, '\\\\')
      .replace(/\n/g, '\\n')
      .replace(/\r/g, '\\r')
      .replace(/\t/g, '\\t');

    // Build args array for spawn (handles quoting properly)
    const args = [pythonInjectPath, escapedText];
    if (backspaceCount > 0) {
      args.push('--backspace', backspaceCount.toString());
    }
    if (humanize) {
      args.push('--humanize');
    }

    const pythonProcess = spawn(getPythonCommand(), args, {
      cwd: __dirname,
      shell: false
    });

    pythonProcess.on('close', (code) => {
      if (code !== 0) {
        // Fallback: clipboard + Ctrl+V
        try {
          clipboard.writeText(text);
          if (robot) {
            setTimeout(() => {
              robot.keyTap('v', 'control');
              resolve({ success: true, method: 'clipboard-fallback' });
            }, 50);
          } else {
            resolve({ success: true, method: 'clipboard-only' });
          }
        } catch (clipError) {
          resolve({ success: false, error: clipError.message });
        }
      } else {
        resolve({ success: true, method: 'python-inject' });
      }
    });

    pythonProcess.on('error', (err) => {
      clipboard.writeText(text);
      resolve({ success: true, method: 'clipboard-fallback' });
    });
  });
}

// Show output window at cursor (without text - for streaming)
async function showOutputWindowAtCursor() {
  if (outputWindow) {
    const { screen } = require('electron');
    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const workArea = display.workArea;
    const [popupWidth, popupHeight] = outputWindow.getSize();

    let x = cursor.x;
    let y = cursor.y + 20;

    if (y + popupHeight > workArea.y + workArea.height) {
      y = cursor.y - popupHeight - 5;
    }
    if (x + popupWidth > workArea.x + workArea.width) {
      x = workArea.x + workArea.width - popupWidth - 10;
    }

    x = Math.max(workArea.x, x);
    y = Math.max(workArea.y, y);

    outputWindow.setPosition(Math.round(x), Math.round(y));
    outputWindow.showInactive();
    await new Promise(resolve => setTimeout(resolve, 30));
  }
}

async function showSuggestionAtCursor(text) {
  if (outputWindow) {
    const { screen } = require('electron');
    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const workArea = display.workArea;
    const [popupWidth, popupHeight] = outputWindow.getSize();

    let x = cursor.x;
    let y = cursor.y + 20;

    if (y + popupHeight > workArea.y + workArea.height) {
      y = cursor.y - popupHeight - 5;
    }
    if (x + popupWidth > workArea.x + workArea.width) {
      x = workArea.x + workArea.width - popupWidth - 10;
    }

    x = Math.max(workArea.x, x);
    y = Math.max(workArea.y, y);

    outputWindow.setPosition(Math.round(x), Math.round(y));
    outputWindow.showInactive();

    await new Promise(resolve => setTimeout(resolve, 50));
    outputWindow.webContents.send('display-text', text);
  }
}

// Show explanation window (for coding mode)
function showExplanationWindow() {
  if (explanationWindow) {
    const { screen } = require('electron');
    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const workArea = display.workArea;
    const [expWidth, expHeight] = explanationWindow.getSize();

    // Position to the right of cursor (or left if no space)
    let x = cursor.x + 470; // After output window
    let y = cursor.y + 20;

    if (x + expWidth > workArea.x + workArea.width) {
      x = cursor.x - expWidth - 20; // Left side instead
    }
    if (y + expHeight > workArea.y + workArea.height) {
      y = workArea.y + workArea.height - expHeight - 10;
    }

    x = Math.max(workArea.x, x);
    y = Math.max(workArea.y, y);

    explanationWindow.setPosition(Math.round(x), Math.round(y));
    explanationWindow.webContents.send('show-loading');
    explanationWindow.showInactive();
  }
}

// Generate explanation for code (second API call in coding mode)
async function generateExplanation(problemText, codeText) {
  try {
    const result = await generateTextStreaming('explanation', problemText, codeText, true);

    if (result && result.text && explanationWindow) {
      lastGeneratedExplanation = result.text;
      explanationWindow.webContents.send('display-explanation', result.text);
    }
  } catch (error) {
    console.error('Failed to generate explanation:', error);
    if (explanationWindow) {
      explanationWindow.webContents.send('display-explanation', 'Failed to generate explanation');
    }
  }
}

// Hide explanation window
function hideExplanationWindow() {
  if (explanationWindow) {
    explanationWindow.hide();
    explanationWindow.webContents.send('clear-explanation');
  }
}

async function handleScreenshotTrigger() {
  console.log('Screenshot trigger - showing vision input window');

  triggerMode = 'screenshot';
  pendingBackspaceCount = 0;

  // Show the output window in vision-mode (with input field)
  if (outputWindow) {
    const { screen } = require('electron');
    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const workArea = display.workArea;
    const [popupWidth, popupHeight] = outputWindow.getSize();

    let x = cursor.x;
    let y = cursor.y + 20;

    if (y + popupHeight > workArea.y + workArea.height) {
      y = cursor.y - popupHeight - 5;
    }
    if (x + popupWidth > workArea.x + workArea.width) {
      x = workArea.x + workArea.width - popupWidth - 10;
    }

    x = Math.max(workArea.x, x);
    y = Math.max(workArea.y, y);

    outputWindow.setPosition(Math.round(x), Math.round(y));
    outputWindow.show();
    outputWindow.focus();

    await new Promise(resolve => setTimeout(resolve, 50));
    outputWindow.webContents.send('vision-mode');
  }
}

async function processVisionAnalysis(instruction) {
  console.log('Processing vision analysis with instruction:', instruction);

  // Hide window before taking screenshot (so it's not in the capture)
  if (outputWindow) {
    outputWindow.hide();
  }

  // Small delay to ensure window is hidden
  await new Promise(resolve => setTimeout(resolve, 200));

  // Call Python script for screenshot + vision
  const pythonScript = path.join(__dirname, 'src', 'services', 'media', 'vision.py');

  try {
    const instructionJson = JSON.stringify(instruction || '');

    // Use cached env (loaded once at startup)
    const env = cachedEnv || process.env;

    const pythonProcess = spawn(getPythonCommand(), [pythonScript, instructionJson], {
      cwd: __dirname,
      shell: false,
      env: env
    });

    let output = '';
    let errorOutput = '';

    pythonProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
      console.log('Screenshot vision debug:', data.toString());
    });

    pythonProcess.on('close', async (code) => {
      let resultText = '';

      if (code === 0 && output.trim()) {
        try {
          const result = JSON.parse(output.trim());
          if (result.text) {
            lastGeneratedText = result.text;
            resultText = result.text;
          } else if (result.error) {
            console.error('Screenshot vision error:', result.error);
            resultText = 'Error: ' + result.error;
          }
        } catch (e) {
          console.error('Failed to parse screenshot vision output:', output);
          resultText = 'Failed to parse response.';
        }
      } else {
        console.error('Screenshot vision failed:', errorOutput);
        resultText = 'Vision analysis failed. Check console for details.';
      }

      // Show window with result
      if (outputWindow && resultText) {
        const { screen } = require('electron');
        const cursor = screen.getCursorScreenPoint();
        const display = screen.getDisplayNearestPoint(cursor);
        const workArea = display.workArea;
        const [popupWidth, popupHeight] = outputWindow.getSize();

        let x = cursor.x;
        let y = cursor.y + 20;

        if (y + popupHeight > workArea.y + workArea.height) {
          y = cursor.y - popupHeight - 5;
        }
        if (x + popupWidth > workArea.x + workArea.width) {
          x = workArea.x + workArea.width - popupWidth - 10;
        }

        x = Math.max(workArea.x, x);
        y = Math.max(workArea.y, y);

        outputWindow.setPosition(Math.round(x), Math.round(y));
        outputWindow.show();
        outputWindow.webContents.send('display-text', resultText);
      }
    });

  } catch (error) {
    console.error('Screenshot trigger error:', error);
  }
}

async function handleClipboardTrigger() {
  // Read clipboard content
  const clipboardText = clipboard.readText();

  if (!clipboardText || clipboardText.trim().length === 0) {
    return;
  }

  // Get typed instruction from keystroke buffer
  const bufferData = await requestBuffer();
  const typedInstruction = bufferData.buffer.trim();

  console.log('Clipboard trigger - clipboard:', clipboardText.substring(0, 50), '...');
  console.log('Clipboard trigger - typed instruction:', typedInstruction);
  console.log('Coding mode enabled:', codingModeEnabled);

  // Set mode - no backspace needed for clipboard-only, but need backspace if there's instruction
  pendingBackspaceCount = typedInstruction ? bufferData.raw_count : 0;
  triggerMode = 'clipboard';

  // Generate AI response based on clipboard + optional instruction (streaming)
  try {
    // Show output window BEFORE streaming starts (for non-auto-inject)
    if (!autoInjectEnabled) {
      await showOutputWindowAtCursor();
    }

    let result;
    if (typedInstruction) {
      // Combined mode: clipboard as context, typed text as instruction
      result = await generateTextStreaming('clipboard_with_instruction', clipboardText, typedInstruction, autoInjectEnabled);
    } else {
      // Original mode: clipboard only
      result = await generateTextStreaming('clipboard', clipboardText, null, autoInjectEnabled);
    }

    if (result && result.text) {
      lastGeneratedText = result.text;
      lastGeneratedExplanation = '';

      // If coding mode is enabled, generate explanation in parallel
      if (codingModeEnabled && !autoInjectEnabled) {
        showExplanationWindow();
        generateExplanation(clipboardText, result.text);
      }

      if (autoInjectEnabled) {
        // Auto mode: inject directly without showing suggestion
        // Reset monitor BEFORE injection so it doesn't capture injected text
        sendToMonitor({ cmd: 'reset' });
        await autoInjectWithBackspace(result.text, pendingBackspaceCount, humanizeTyping);
        // Clear state after injection
        lastGeneratedText = '';
        lastGeneratedExplanation = '';
        pendingBackspaceCount = 0;
        triggerMode = null;
        // Reset monitor again after injection to be safe
        sendToMonitor({ cmd: 'reset' });
      }
      // Note: For suggestion mode, text is already displayed via streaming
    }
  } catch (error) {
    console.error('Clipboard AI generation error:', error);
    // Hide output window on error
    if (outputWindow && !autoInjectEnabled) {
      outputWindow.hide();
    }
  }
}

// Register global shortcut to toggle window (Ctrl+Shift+Space)
app.whenReady().then(() => {
  // Load config once at startup
  loadCachedConfig();
  loadSavedSettings();

  // Ensure chat data directory exists and rebuild index
  ensureChatsDir();
  rebuildConversationIndex();

  createWindow();
  createOutputWindow();
  createExplanationWindow();

  // Start keystroke monitor for background text capture
  startKeystrokeMonitor();

  // Start AI backend service (persistent process for low latency)
  startAIBackend();

  const toggleShortcut = globalShortcut.register('CommandOrControl+Shift+Space', () => {
    if (mainWindow) {
      if (isWindowVisible) {
        mainWindow.hide();
        isWindowVisible = false;
      } else {
        mainWindow.show();
        mainWindow.focus();
        isWindowVisible = true;
        // When showing prompt window, set mode to 'prompt'
        triggerMode = 'prompt';
        pendingBackspaceCount = 0;
      }
    }
  });

  // Register Ctrl+Shift+D for clipboard trigger
  const clipboardShortcut = globalShortcut.register('CommandOrControl+Shift+D', async () => {
    await handleClipboardTrigger();
  });

  // Register Ctrl+Alt+Enter for AI text trigger (grammar fix / inline completion)
  const triggerShortcut = globalShortcut.register('CommandOrControl+Alt+Enter', () => {
    console.log('Ctrl+Alt+Enter pressed - sending trigger to monitor');
    // Tell keystroke monitor to trigger (sends buffer to Electron)
    sendToMonitor({ cmd: 'trigger' });
  });

  if (triggerShortcut) {
    console.log('Ctrl+Alt+Enter shortcut registered successfully');
  } else {
    console.error('Failed to register Ctrl+Alt+Enter shortcut');
  }

  // Register Ctrl+Shift+F for screenshot + vision trigger
  const screenshotShortcut = globalShortcut.register('CommandOrControl+Shift+F', async () => {
    console.log('Ctrl+Shift+F pressed - screenshot + vision trigger');
    await handleScreenshotTrigger();
  });

  // Register Ctrl+Shift+E to save screenshot of focused app window (works even when window is excluded from OS capture)
  const saveScreenshotShortcut = globalShortcut.register('CommandOrControl+Shift+E', async () => {
    const win = BrowserWindow.getFocusedWindow() || mainWindow;
    const result = await takeWindowScreenshot(win);
    if (result.success && result.filePath && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('screenshot-saved', result.filePath);
    }
  });

  // Register Ctrl+Shift+S for settings window
  const settingsShortcut = globalShortcut.register('CommandOrControl+Shift+S', () => {
    if (settingsWindow) {
      settingsWindow.close();
    } else {
      createSettingsWindow();
    }
  });

  if (settingsShortcut) {
    console.log('Ctrl+Shift+S shortcut registered successfully');
  }

  // Register Ctrl+Shift+C for chat window
  const chatShortcut = globalShortcut.register('CommandOrControl+Shift+C', () => {
    if (chatWindow) {
      chatWindow.close();
    } else {
      createChatWindow();
    }
  });

  if (chatShortcut) {
    console.log('Ctrl+Shift+C shortcut registered successfully');
  }

  // Register Ctrl+Shift+P to paste generated text using Python injection
  const pasteShortcut = globalShortcut.register('CommandOrControl+Shift+P', async () => {
    if (lastGeneratedText) {
      // Hide windows first
      if (mainWindow) {
        mainWindow.hide();
        isWindowVisible = false;
      }
      if (outputWindow) {
        outputWindow.hide();
      }
      // Hide explanation window (coding mode)
      hideExplanationWindow();

      // Check if Ultra Human typing is enabled (for coding interviews)
      if (ultraHumanEnabled) {
        // Use human_typer directly - pass problem, let it generate and type code
        const typerScript = path.join(__dirname, 'src', 'python', 'human_typer.py');

        try {
          // Small delay to ensure focus is on target app
          await new Promise(resolve => setTimeout(resolve, 150));

          // Get clipboard text as the problem (the coding question)
          const problemText = clipboard.readText() || '';

          if (!problemText.trim()) {
            console.log('Ultra Human: No problem in clipboard');
            return;
          }

          console.log('Ultra Human typing - problem:', problemText.substring(0, 50) + '...');

          // Set UTF-8 encoding for emoji support
          const env = { ...(cachedEnv || process.env), PYTHONIOENCODING: 'utf-8' };

          // Call human_typer directly with the problem
          const ultraProcess = spawn(getPythonCommand(), [typerScript, problemText], {
            cwd: __dirname,
            shell: false,
            env: env
          });

          ultraProcess.stdout.on('data', (data) => {
            console.log('Ultra Human stdout:', data.toString());
          });

          ultraProcess.stderr.on('data', (data) => {
            console.log('Ultra Human stderr:', data.toString());
          });

          ultraProcess.on('close', (code) => {
            console.log('Ultra Human typing completed with code:', code);

            // Reset state
            lastGeneratedText = '';
            lastGeneratedExplanation = '';
            pendingBackspaceCount = 0;
            triggerMode = null;
            sendToMonitor({ cmd: 'reset' });

            if (mainWindow) {
              mainWindow.webContents.send('clear-prompt');
            }
          });

          ultraProcess.on('error', (err) => {
            console.error('Ultra Human typing error:', err);
            // Fallback to normal injection
            clipboard.writeText(lastGeneratedText);
            if (robot) {
              robot.keyTap('v', 'control');
            }
            lastGeneratedText = '';
            lastGeneratedExplanation = '';
          });

        } catch (error) {
          console.error('Ultra Human error:', error);
          lastGeneratedText = '';
          lastGeneratedExplanation = '';
          pendingBackspaceCount = 0;
          triggerMode = null;
        }
        return; // Exit early - ultra human handles everything
      }

      // Use Python-based keyboard injection (pynput) - normal mode
      const pythonInjectPath = path.join(__dirname, 'src', 'python', 'keyboard_inject.py');

      try {
        // Small delay to ensure focus is on target app
        await new Promise(resolve => setTimeout(resolve, 150));

        // Escape the text for command line
        let escapedText = lastGeneratedText
          .replace(/\\/g, '\\\\')  // Escape backslashes first
          .replace(/"/g, '\\"')     // Escape quotes
          .replace(/\n/g, '\\n')   // Convert newlines to \n strings
          .replace(/\r/g, '\\r')   // Convert carriage returns to \r strings
          .replace(/\t/g, '\\t');  // Convert tabs to \t strings

        // Wrap in quotes for command line
        escapedText = `"${escapedText}"`;

        // Use pending backspace count (already set correctly for each mode)
        const backspaceCount = pendingBackspaceCount;

        // Call Python injector - pass text, optional backspace count, and humanize flag
        const { exec } = require('child_process');
        let command = `${getPythonCommand()} "${pythonInjectPath}" ${escapedText}`;
        if (backspaceCount > 0) {
          command += ` --backspace ${backspaceCount}`;
        }
        if (humanizeTyping) {
          command += ' --humanize';
        }

        exec(command, { maxBuffer: 10 * 1024 * 1024 }, async (error, stdout, stderr) => {
          if (error) {
            // Fallback: clipboard + Ctrl+V
            try {
              clipboard.writeText(lastGeneratedText);
              if (robot) {
                setTimeout(() => {
                  try {
                    robot.keyTap('v', 'control');
                  } catch (robotError) {
                    // robotjs paste failed
                  }
                }, 50);
              }
            } catch (clipError) {
              // Clipboard write failed
            }
          }

          // Reset state and notify monitor (keep humanizeTyping - it's a user preference)
          lastGeneratedText = '';
          lastGeneratedExplanation = '';
          pendingBackspaceCount = 0;
          triggerMode = null;

          // Tell keystroke monitor to reset buffer
          sendToMonitor({ cmd: 'reset' });

          // Clear prompt input in main window
          if (mainWindow) {
            mainWindow.webContents.send('clear-prompt');
          }
        });
      } catch (error) {
        lastGeneratedText = '';
        lastGeneratedExplanation = '';
        pendingBackspaceCount = 0;
        triggerMode = null;
      }
    }
  });

  // Register Ctrl+Shift+V for voice input (hold-to-talk)
  const voiceShortcut = globalShortcut.register('CommandOrControl+Shift+V', async () => {
    if (isVoiceRecording) return; // Already recording
    startVoiceRecording();
  });

  // Set up key release detection for hold-to-talk
  if (uIOhook) {
    uIOhook.on('keyup', (e) => {
      // V key code is 47 in uiohook
      if (e.keycode === 47 && isVoiceRecording) {
        stopVoiceRecording();
      }
    });

    // Escape key (keycode 1) to close output window and clear generated text
    uIOhook.on('keydown', (e) => {
      if (e.keycode === 1) {
        // Close output window if visible
        if (outputWindow && outputWindow.isVisible()) {
          outputWindow.hide();
        }
        // Close explanation window if visible (coding mode)
        hideExplanationWindow();
        // Clear generated text so Ctrl+Shift+P won't inject old content (keep humanizeTyping - user preference)
        lastGeneratedText = '';
        lastGeneratedExplanation = '';
        pendingBackspaceCount = 0;
        triggerMode = null;
        // Clear prompt input in main window
        if (mainWindow) {
          mainWindow.webContents.send('clear-prompt');
        }
      }
    });

    uIOhook.start();
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  if (uIOhook) {
    uIOhook.stop();
  }
  // Stop keystroke monitor
  stopKeystrokeMonitor();
  // Stop AI backend service
  stopAIBackend();
});

// Voice recording functions for hold-to-talk
function startVoiceRecording() {
  if (isVoiceRecording) return;

  isVoiceRecording = true;

  // Show window and notify
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
    isWindowVisible = true;
    mainWindow.webContents.send('voice-recording-started');
  }

  // Start Python recording (saves to temp file)
  const pythonScript = path.join(__dirname, 'src', 'services', 'media', 'voice.py');
  voiceProcess = spawn(getPythonCommand(), [pythonScript, '--record'], {
    cwd: __dirname
  });

  voiceProcess.on('close', (code) => {
    voiceProcess = null;
    // Transcription will be triggered by stopVoiceRecording
  });

  voiceProcess.on('error', (err) => {
    isVoiceRecording = false;
    voiceProcess = null;
    if (mainWindow) {
      mainWindow.webContents.send('voice-recording-result', { error: err.message });
    }
  });
}

function stopVoiceRecording() {
  if (!isVoiceRecording) return;

  isVoiceRecording = false;

  if (mainWindow) {
    mainWindow.webContents.send('voice-recording-stopping');
  }

  // Kill the recording process
  if (voiceProcess) {
    if (process.platform === 'win32') {
      const { exec } = require('child_process');
      exec(`taskkill /pid ${voiceProcess.pid} /T /F`, (err) => {
        // Small delay to ensure file is saved, then transcribe
        setTimeout(transcribeSavedRecording, 300);
      });
    } else {
      try {
        voiceProcess.kill('SIGTERM');
      } catch (e) {
        // Error killing voice process
      }
      setTimeout(transcribeSavedRecording, 300);
    }
  } else {
    // Process already closed, just transcribe
    transcribeSavedRecording();
  }
}

function transcribeSavedRecording() {
  const pythonScript = path.join(__dirname, 'src', 'python', 'voice_transcribe.py');
  const transcribeProcess = spawn(getPythonCommand(), [pythonScript, '--transcribe'], {
    cwd: __dirname
  });

  let output = '';
  let errorOutput = '';

  transcribeProcess.stdout.on('data', (data) => {
    output += data.toString();
  });

  transcribeProcess.stderr.on('data', (data) => {
    errorOutput += data.toString();
  });

  transcribeProcess.on('close', (code) => {
    let result = { error: 'No result' };

    if (output.trim()) {
      try {
        result = JSON.parse(output.trim());
        if (result.text) result.text = fixInvertedCaps(result.text);
      } catch (e) {
        result = { error: 'Failed to parse result' };
      }
    } else if (errorOutput) {
      result = { error: errorOutput };
    }

    if (mainWindow) {
      mainWindow.webContents.send('voice-recording-result', result);
    }
  });

  transcribeProcess.on('error', (err) => {
    if (mainWindow) {
      mainWindow.webContents.send('voice-recording-result', { error: err.message });
    }
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// IPC handler for generating text (uses persistent backend with streaming)
ipcMain.handle('generate-text', async (event, prompt, context) => {
  try {
    // Use the streaming backend
    const mode = context?.mode || 'prompt';
    const extraParam = mode === 'extension' ? context?.last_output :
      mode === 'clipboard_with_instruction' ? context?.instruction : null;

    const result = await generateTextStreaming(mode, prompt, extraParam, true); // autoInject=true to skip streaming UI
    return result;
  } catch (error) {
    return { error: error.message };
  }
});

// IPC handler for showing inline suggestion at cursor
ipcMain.handle('show-inline-suggestion', async (event, text) => {
  if (outputWindow) {
    const { screen } = require('electron');

    // Get cursor position (mouse position as proxy for text cursor)
    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const workArea = display.workArea;

    // Get window dimensions
    const [popupWidth, popupHeight] = outputWindow.getSize();

    // Position inline - just below cursor like autocomplete
    let x = cursor.x;
    let y = cursor.y + 20;  // Small offset below cursor

    // Keep on screen - flip above if needed
    if (y + popupHeight > workArea.y + workArea.height) {
      y = cursor.y - popupHeight - 5;
    }

    // Keep on screen - adjust horizontal
    if (x + popupWidth > workArea.x + workArea.width) {
      x = workArea.x + workArea.width - popupWidth - 10;
    }

    x = Math.max(workArea.x, x);
    y = Math.max(workArea.y, y);

    outputWindow.setPosition(Math.round(x), Math.round(y));
    outputWindow.showInactive();  // Show without stealing focus

    await new Promise(resolve => setTimeout(resolve, 50));
    outputWindow.webContents.send('display-text', text);
  }
});

// IPC handler for showing output in output window (legacy - redirects to inline)
ipcMain.handle('show-output', async (event, text) => {
  if (outputWindow) {
    const { screen } = require('electron');
    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const workArea = display.workArea;
    const [popupWidth, popupHeight] = outputWindow.getSize();

    let x = cursor.x;
    let y = cursor.y + 20;

    if (y + popupHeight > workArea.y + workArea.height) {
      y = cursor.y - popupHeight - 5;
    }
    if (x + popupWidth > workArea.x + workArea.width) {
      x = workArea.x + workArea.width - popupWidth - 10;
    }

    x = Math.max(workArea.x, x);
    y = Math.max(workArea.y, y);

    outputWindow.setPosition(Math.round(x), Math.round(y));
    outputWindow.showInactive();

    await new Promise(resolve => setTimeout(resolve, 50));
    outputWindow.webContents.send('display-text', text);
  }
});

// IPC handler for hiding output window
ipcMain.handle('hide-output', async () => {
  if (outputWindow) {
    outputWindow.hide();
  }
});

// IPC handler for vision analysis from output window
ipcMain.handle('vision-analyze', async (event, instruction) => {
  console.log('Vision analyze requested with instruction:', instruction);
  await processVisionAnalysis(instruction);
});

// Take screenshot of a window (works even when window is excluded from OS capture)
async function takeWindowScreenshot(win) {
  if (!win || win.isDestroyed()) return { success: false, error: 'No window' };
  const wc = win.webContents;
  if (!wc) return { success: false, error: 'No web contents' };
  try {
    const image = await wc.capturePage();
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const defaultName = `screenshot_${timestamp}.png`;
    const result = await dialog.showSaveDialog(win, {
      title: 'Save screenshot',
      defaultPath: path.join(app.getPath('pictures'), defaultName),
      filters: [{ name: 'PNG Image', extensions: ['png'] }]
    });
    if (result.canceled || !result.filePath) return { success: false, canceled: true };
    const buf = image.toPNG();
    fs.writeFileSync(result.filePath, buf);
    return { success: true, filePath: result.filePath };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

ipcMain.handle('take-screenshot', async (event, windowType) => {
  let win = BrowserWindow.getFocusedWindow();
  if (windowType === 'main' && mainWindow && !mainWindow.isDestroyed()) win = mainWindow;
  else if (windowType === 'settings' && settingsWindow && !settingsWindow.isDestroyed()) win = settingsWindow;
  else if (windowType === 'chat' && chatWindow && !chatWindow.isDestroyed()) win = chatWindow;
  if (!win) win = mainWindow; // fallback to main
  return takeWindowScreenshot(win);
});

// Store for global paste shortcut
let lastGeneratedText = '';
let lastGeneratedExplanation = '';  // Code explanation for coding mode

// IPC handler to store generated text for global shortcut
ipcMain.on('set-generated-text', (event, text, humanize = false) => {
  lastGeneratedText = text;
  humanizeTyping = humanize;
});

// IPC handler to set auto-inject mode
ipcMain.handle('set-auto-inject', async (event, enabled) => {
  autoInjectEnabled = enabled;
  return { success: true, autoInject: autoInjectEnabled };
});

// IPC handler for settings window close
ipcMain.on('close-settings-window', () => {
  if (settingsWindow) {
    settingsWindow.close();
  }
});

// When settings window opens, apply saved settings to main so preferences persist (e.g. after restart or after paste/escape)
ipcMain.on('settings-init-sync', (event, s) => {
  if (s && typeof s === 'object') {
    if (s.humanizeEnabled !== undefined) humanizeTyping = s.humanizeEnabled;
    if (s.masterEnabled !== undefined) masterEnabled = s.masterEnabled;
    if (s.autoInjectEnabled !== undefined) autoInjectEnabled = s.autoInjectEnabled;
    if (s.liveModeEnabled !== undefined) {
      liveModeEnabled = s.liveModeEnabled;
      sendToMonitor({ cmd: 'set_live_mode', enabled: liveModeEnabled });
    }
    if (s.codingModeEnabled !== undefined) codingModeEnabled = s.codingModeEnabled;
    if (s.ultraHumanEnabled !== undefined) ultraHumanEnabled = s.ultraHumanEnabled;
    if (s.ghostModeEnabled !== undefined) {
      ghostModeEnabled = s.ghostModeEnabled;
      applyGhostModeToAllWindows();
    }
  }
});

// IPC handler for humanize toggle from settings
ipcMain.on('settings-humanize-toggle', (event, enabled) => {
  humanizeTyping = enabled;
});

// IPC handler for master on/off toggle
ipcMain.on('settings-master-toggle', (event, enabled) => {
  masterEnabled = enabled;
  console.log('Master enabled:', masterEnabled);

  // Stop or start keystroke monitor based on master state
  if (!masterEnabled) {
    // Clear any pending restart
    if (monitorRestartTimer) {
      clearTimeout(monitorRestartTimer);
      monitorRestartTimer = null;
    }
  }
});

// IPC handler to get current settings state
ipcMain.handle('get-settings-state', async () => {
  return {
    masterEnabled,
    autoInjectEnabled,
    humanizeEnabled: humanizeTyping,
    liveModeEnabled,
    codingModeEnabled,
    ultraHumanEnabled,
    ghostModeEnabled
  };
});

// IPC handler for live mode toggle
ipcMain.on('settings-live-mode-toggle', (event, enabled) => {
  liveModeEnabled = enabled;
  console.log('Live mode enabled:', liveModeEnabled);
  // Tell keystroke monitor about live mode state
  sendToMonitor({ cmd: 'set_live_mode', enabled: liveModeEnabled });
});

// IPC handler for ghost mode toggle (Ghost ON = hidden in screen share, Ghost OFF = visible in meetings)
ipcMain.on('settings-ghost-mode-toggle', (event, enabled) => {
  ghostModeEnabled = enabled;
  console.log('Ghost mode (hide from screen share):', ghostModeEnabled);
  applyGhostModeToAllWindows();
});

// IPC handler for coding mode toggle
ipcMain.on('settings-coding-mode-toggle', (event, enabled) => {
  codingModeEnabled = enabled;
  console.log('Coding mode enabled:', codingModeEnabled);
});

// IPC handler for ultra human typing toggle
ipcMain.on('settings-ultra-human-toggle', (event, enabled) => {
  ultraHumanEnabled = enabled;
  console.log('Ultra Human typing enabled:', ultraHumanEnabled);
});

// IPC handler for agent selection change
ipcMain.on('settings-agent-change', (event, agent) => {
  currentAgent = agent || 'auto';
  console.log('Agent changed to:', currentAgent);
});

// Pending one-shot requests to AI backend (agents list, test results)
let pendingBackendCallbacks = {};

// IPC handler to save an API key (encrypted via keystore)
ipcMain.handle('save-api-key', async (event, provider, key) => {
  try {
    if (!key || key.trim() === '') {
      keystore.removeApiKey(provider);
      // Remove from cached env
      delete cachedEnv[provider];
      return { success: true, action: 'removed' };
    }
    keystore.saveApiKey(provider, key.trim());
    // Update cached env so it takes effect immediately
    cachedEnv[provider] = key.trim();
    return { success: true, action: 'saved' };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

// IPC handler to get configured providers status
ipcMain.handle('get-providers', async () => {
  const providerEnvVars = [
    'MISTRAL_API_KEY', 'GROQ_API_KEY', 'DEEPSEEK_API_KEY',
    'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY',
    'XAI_API_KEY', 'TOGETHERAI_API_KEY', 'PERPLEXITYAI_API_KEY',
    'COHERE_API_KEY', 'REPLICATE_API_TOKEN'
  ];

  const providers = providerEnvVars.map(envVar => ({
    envVar,
    configured: !!(cachedEnv[envVar] && !cachedEnv[envVar].includes('your-')),
    hasKey: !!cachedEnv[envVar],
  }));

  return providers;
});

// IPC handler to get available agents from AI backend
ipcMain.handle('get-agents', async () => {
  return new Promise((resolve) => {
    if (!aiBackendReady) {
      resolve([{ value: 'auto', label: 'Auto', group: 'auto' }]);
      return;
    }

    const timeout = setTimeout(() => {
      delete pendingBackendCallbacks['agents'];
      resolve([{ value: 'auto', label: 'Auto', group: 'auto' }]);
    }, 3000);

    pendingBackendCallbacks['agents'] = (evt) => {
      clearTimeout(timeout);
      resolve(evt.agents || []);
    };

    sendToAIBackend({ cmd: 'get_agents' });
  });
});

// IPC handler for testing a provider from settings
ipcMain.handle('test-provider', async (event, model) => {
  return new Promise((resolve) => {
    if (!aiBackendReady) {
      resolve({ success: false, message: 'AI backend not ready' });
      return;
    }

    const callbackKey = 'test_result_' + model;
    const timeout = setTimeout(() => {
      delete pendingBackendCallbacks[callbackKey];
      resolve({ success: false, message: 'Test timed out' });
    }, 15000);

    pendingBackendCallbacks[callbackKey] = (evt) => {
      clearTimeout(timeout);
      resolve({ success: evt.success, message: evt.message });
    };

    sendToAIBackend({ cmd: 'test_provider', model: model });
  });
});

// IPC handler for auto-inject (autonomous mode - no suggestion popup)
ipcMain.handle('auto-inject-text', async (event, text, humanize = false) => {
  // Normalize text: trim and re-base indent
  text = normalizeTextForInjection(text);

  try {
    // Hide windows silently
    if (mainWindow) {
      mainWindow.hide();
      isWindowVisible = false;
    }
    if (outputWindow) {
      outputWindow.hide();
    }

    // Reset monitor BEFORE injection so it doesn't capture injected text
    sendToMonitor({ cmd: 'reset' });

    // Small delay to ensure focus is on target app
    await new Promise(resolve => setTimeout(resolve, 150));

    // Inject using Python
    const pythonInjectPath = path.join(__dirname, 'src', 'python', 'keyboard_inject.py');

    return new Promise((resolve) => {
      // Escape text for Python (will be unescaped by keyboard_inject.py)
      let escapedText = text
        .replace(/\\/g, '\\\\')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/\t/g, '\\t');

      // Build args array for spawn (handles quoting properly)
      const args = [pythonInjectPath, escapedText];
      if (humanize) {
        args.push('--humanize');
      }

      const pythonProcess = spawn(getPythonCommand(), args, {
        cwd: __dirname,
        shell: false
      });

      pythonProcess.on('close', (code) => {
        // Clear state and reset monitor after injection
        lastGeneratedText = '';
        pendingBackspaceCount = 0;
        triggerMode = null;
        sendToMonitor({ cmd: 'reset' });

        if (code !== 0) {
          // Fallback to clipboard
          clipboard.writeText(text);
          if (robot) {
            setTimeout(() => {
              robot.keyTap('v', 'control');
              resolve({ success: true, method: 'clipboard-fallback' });
            }, 50);
          } else {
            resolve({ success: true, method: 'clipboard-only' });
          }
        } else {
          resolve({ success: true, method: 'python-inject' });
        }
      });

      pythonProcess.on('error', (err) => {
        // Clear state even on error
        lastGeneratedText = '';
        sendToMonitor({ cmd: 'reset' });
        clipboard.writeText(text);
        resolve({ success: true, method: 'clipboard-fallback' });
      });
    });
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// IPC handler for inline text injection using Python injector
ipcMain.handle('inject-text', async (event, text) => {
  // Normalize text: trim and re-base indent
  text = normalizeTextForInjection(text);

  try {
    // Hide main window to allow focus on target app
    if (mainWindow) {
      mainWindow.hide();
      isWindowVisible = false;
    }
    if (outputWindow) {
      outputWindow.hide();
    }

    // Small delay to ensure focus is on the target application
    await new Promise(resolve => setTimeout(resolve, 150));

    // Use Python-based keyboard injection (pynput)
    const pythonInjectPath = path.join(__dirname, 'src', 'python', 'keyboard_inject.py');

    return new Promise((resolve) => {
      // Escape the text for command line
      let escapedText = text
        .replace(/\\/g, '\\\\')
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/\t/g, '\\t');

      escapedText = `"${escapedText}"`;

      const { exec } = require('child_process');
      const command = `${getPythonCommand()} "${pythonInjectPath}" ${escapedText}`;

      exec(command, { maxBuffer: 10 * 1024 * 1024 }, (error, stdout, stderr) => {
        if (error) {
          console.error('Python injection error:', error);
          // Fallback to clipboard
          try {
            clipboard.writeText(text);
            if (robot) {
              setTimeout(() => {
                robot.keyTap('v', 'control');
                resolve({ success: true, method: 'clipboard-fallback' });
              }, 50);
            } else {
              resolve({ success: true, method: 'clipboard', message: 'Press Ctrl+V to paste' });
            }
          } catch (clipError) {
            resolve({ success: false, error: clipError.message });
          }
        } else {
          resolve({ success: true, method: 'keyboard-inject' });
        }
      });
    });
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// IPC handler for voice transcription using Python + Google Speech Recognition (free)
ipcMain.handle('transcribe-audio', async (event, options = {}) => {
  return new Promise((resolve) => {
    const timeout = options.timeout || 10;
    const phraseTimeout = options.phraseTimeout || 5;

    const pythonScript = path.join(__dirname, 'src', 'services', 'media', 'voice.py');

    const pythonProcess = spawn(getPythonCommand(), [pythonScript, '--live', timeout.toString(), phraseTimeout.toString()], {
      cwd: __dirname
    });

    let output = '';
    let errorOutput = '';

    pythonProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (code === 0 && output.trim()) {
        try {
          const result = JSON.parse(output.trim());
          resolve(result);
        } catch (e) {
          resolve({ error: 'Failed to parse transcription result' });
        }
      } else {
        resolve({ error: errorOutput || 'Transcription failed' });
      }
    });

    pythonProcess.on('error', (err) => {
      resolve({ error: 'Failed to start voice recognition: ' + err.message });
    });
  });
});

// IPC handler for typing text at cursor position
ipcMain.handle('type-text', async (event, text) => {
  try {
    // Hide both windows to allow focus on target app
    if (mainWindow) {
      mainWindow.hide();
      isWindowVisible = false;
    }
    if (outputWindow) {
      outputWindow.hide();
    }

    // Small delay to ensure focus is on the target application
    await new Promise(resolve => setTimeout(resolve, 100));

    // Always use clipboard paste method (much faster than typing)
    clipboard.writeText(text);

    // Small delay to ensure clipboard is ready
    await new Promise(resolve => setTimeout(resolve, 50));

    if (robot) {
      // Simulate Ctrl+V to paste instantly
      try {
        robot.keyTap('v', 'control');
        return { success: true, method: 'clipboard-paste' };
      } catch (error) {
        return {
          success: true,
          method: 'clipboard',
          message: 'Text copied to clipboard. Press Ctrl+V to paste.'
        };
      }
    } else {
      return {
        success: true,
        method: 'clipboard',
        message: 'Text copied to clipboard. Press Ctrl+V to paste.'
      };
    }
  } catch (error) {
    // Last resort: copy to clipboard
    try {
      clipboard.writeText(text);
      return {
        success: true,
        method: 'clipboard-fallback',
        message: 'Text copied to clipboard. Press Ctrl+V to paste.'
      };
    } catch (clipError) {
      return { success: false, error: error.message };
    }
  }
});

// ============== Chat Window IPC Handlers ==============

ipcMain.handle('chat-list-conversations', async () => {
  const index = loadConversationIndex();
  return index.sort((a, b) => b.updatedAt - a.updatedAt);
});

ipcMain.handle('chat-load-conversation', async (event, id) => {
  return loadConversation(id);
});

ipcMain.handle('chat-create-conversation', async () => {
  const id = generateId('chat');
  const now = Date.now();
  const conv = {
    id,
    title: 'New Chat',
    createdAt: now,
    updatedAt: now,
    messages: []
  };
  saveConversation(conv);
  return conv;
});

ipcMain.handle('chat-delete-conversation', async (event, id) => {
  try {
    deleteConversationFromIndex(id);
    return { success: true };
  } catch (e) {
    return { success: false, error: e.message };
  }
});

ipcMain.handle('chat-rename-conversation', async (event, id, newTitle) => {
  try {
    const conv = loadConversation(id);
    if (!conv) return { success: false, error: 'Not found' };
    conv.title = newTitle;
    conv.updatedAt = Date.now();
    saveConversation(conv);
    return { success: true };
  } catch (e) {
    return { success: false, error: e.message };
  }
});

ipcMain.handle('chat-search', async (event, query) => {
  if (!query || query.trim().length === 0) return [];
  const q = query.toLowerCase();
  const index = loadConversationIndex();
  const results = [];

  for (const entry of index) {
    // Check title
    if (entry.title.toLowerCase().includes(q)) {
      results.push({ conversationId: entry.id, title: entry.title, matchType: 'title', timestamp: entry.updatedAt });
    }
    // Check message content
    const conv = loadConversation(entry.id);
    if (conv && conv.messages) {
      for (const msg of conv.messages) {
        if (msg.content && msg.content.toLowerCase().includes(q)) {
          results.push({
            conversationId: entry.id,
            title: entry.title,
            content: msg.content.substring(0, 150),
            timestamp: msg.timestamp,
            matchType: 'message'
          });
          break; // one match per conversation is enough
        }
      }
    }
  }
  return results;
});

ipcMain.handle('chat-export-markdown', async (event, id) => {
  const conv = loadConversation(id);
  if (!conv) return { success: false, error: 'Not found' };

  let md = `# ${conv.title}\n\n`;
  for (const msg of conv.messages) {
    const date = new Date(msg.timestamp).toLocaleString();
    if (msg.role === 'user') {
      md += `**You** (${date}):\n${msg.content}\n\n`;
    } else {
      md += `**AI** (${date}):\n${msg.content}\n\n`;
    }
  }

  const result = await dialog.showSaveDialog(chatWindow, {
    title: 'Export Chat',
    defaultPath: `${conv.title.replace(/[^a-z0-9]/gi, '_')}.md`,
    filters: [{ name: 'Markdown', extensions: ['md'] }]
  });

  if (result.canceled || !result.filePath) return { success: false, canceled: true };
  fs.writeFileSync(result.filePath, md, 'utf8');
  return { success: true, filePath: result.filePath };
});

ipcMain.handle('chat-get-current-model', async () => {
  return { agent: chatAgent };
});

ipcMain.on('chat-agent-change', (event, agent) => {
  chatAgent = agent || 'auto';
  console.log('Chat agent changed to:', chatAgent);
});

ipcMain.on('chat-send-message', (event, conversationId, userMessage) => {
  // Save user message to disk
  const userMsg = {
    id: generateId('msg'),
    role: 'user',
    content: userMessage,
    timestamp: Date.now()
  };
  const conv = saveChatMessage(conversationId, userMsg);
  if (!conv) return;

  // Auto-title: first user message → first 6 words
  if (conv.messages.filter(m => m.role === 'user').length === 1) {
    const words = userMessage.split(/\s+/).slice(0, 6).join(' ');
    conv.title = words.length > 50 ? words.substring(0, 50) + '...' : words;
    conv.updatedAt = Date.now();
    saveConversation(conv);
    if (chatWindow && !chatWindow.isDestroyed()) {
      chatWindow.webContents.send('chat-title-updated', { id: conversationId, title: conv.title });
    }
  }

  // Build API messages from conversation history
  const systemMsg = {
    role: 'system',
    content: 'You are a helpful AI assistant. Use markdown formatting in your responses: headings, bold, italic, code blocks with language tags, lists, and tables where appropriate. Be thorough and well-organized.'
  };
  const apiMessages = [systemMsg];
  for (const msg of conv.messages) {
    apiMessages.push({ role: msg.role, content: msg.content });
  }

  generateChatStreaming(conversationId, userMessage, apiMessages);
});

ipcMain.on('chat-stop-generation', () => {
  chatStreamActive = false;
  pendingChatRequest = null;
});

ipcMain.on('chat-close-window', () => {
  if (chatWindow) chatWindow.close();
});
