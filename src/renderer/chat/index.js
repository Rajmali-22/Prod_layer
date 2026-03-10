const { ipcRenderer } = require('electron');
const path = require('path');
const { marked, Renderer } = require(path.join(__dirname, '..', 'lib', 'marked.min.js'));

// ── State ──
let currentConversationId = null;
let conversations = [];
let isStreaming = false;
let streamingText = '';
let streamingBubble = null;
let renderTimer = null;
let searchTimer = null;
let useConversationMemory = true;

// ── DOM refs ──
let sidebarList, messagesContainer, chatInput, sendBtn, searchInput;
let chatAgentSelect, emptyState, exportBtn, chatMicBtn;
let memoryToggleBtn, memoryStatusIndicator;

// Voice recording state
let isChatRecording = false;

// ── Marked config ──
const renderer = new Renderer();

renderer.code = function({ text, lang }) {
  const language = lang || '';
  const escaped = escapeHtml(text);
  return `<div class="code-block-wrapper">
    <div class="code-block-header">
      <span class="code-lang-label">${escapeHtml(language)}</span>
      <button class="copy-code-btn" onclick="copyCodeBlock(this)">Copy</button>
    </div>
    <pre><code>${escaped}</code></pre>
  </div>`;
};

marked.setOptions({
  renderer,
  breaks: true,
  gfm: true
});

// Strip leading preamble (***, ##, blank lines) from AI response before display
function filterPreamble(text) {
  if (!text || typeof text !== 'string') return text;
  let s = text;
  const re = /^\s*(\*{2,}|#{1,6})?\s*\n/m;
  let prev;
  do {
    prev = s;
    s = s.replace(re, '');
  } while (s !== prev);
  return s.trimStart();
}

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
  sidebarList = document.getElementById('sidebar-list');
  messagesContainer = document.getElementById('messages-container');
  chatInput = document.getElementById('chat-input');
  sendBtn = document.getElementById('send-btn');
  searchInput = document.getElementById('search-input');
  chatAgentSelect = document.getElementById('chat-agent-select');
  emptyState = document.getElementById('empty-state');
  exportBtn = document.getElementById('export-btn');
  chatMicBtn = document.getElementById('chat-mic-btn');
  memoryToggleBtn = document.getElementById('memory-toggle-btn');
  memoryStatusIndicator = document.getElementById('memory-status');

  // Populate agent selector from backend
  try {
    await populateChatAgentSelector();
  } catch (e) {
    console.error('Failed to populate agent selector:', e);
  }

  // Restore saved chat agent from localStorage
  try {
    const savedAgent = localStorage.getItem('chat-agent');
    if (savedAgent && chatAgentSelect) {
      chatAgentSelect.value = savedAgent;
    }
  } catch (e) {}

  // Restore conversation memory setting
  try {
    const savedMemorySetting = localStorage.getItem('chat-memory-enabled');
    if (savedMemorySetting !== null) {
      useConversationMemory = savedMemorySetting === 'true';
    }
  } catch (e) {
    console.error('Failed to load memory setting:', e);
  }
  ipcRenderer.send('chat-memory-setting-changed', useConversationMemory);

  // Agent selector change handler
  if (chatAgentSelect) {
    chatAgentSelect.addEventListener('change', () => {
      try {
        localStorage.setItem('chat-agent', chatAgentSelect.value);
      } catch (e) {}
      ipcRenderer.send('chat-agent-change', chatAgentSelect.value);
    });
  }

  // Load conversations
  try {
    await loadConversationList();
  } catch (e) {
    console.error('Failed to load conversations:', e);
  }

  // Event listeners
  document.getElementById('close-btn').addEventListener('click', () => {
    ipcRenderer.send('chat-close-window');
  });

  document.getElementById('new-chat-btn').addEventListener('click', createNewConversation);
  sendBtn.addEventListener('click', handlePrimaryAction);
  exportBtn.addEventListener('click', exportCurrentChat);

  // Memory toggle button
  if (memoryToggleBtn) {
    memoryToggleBtn.addEventListener('click', () => {
      useConversationMemory = !useConversationMemory;
      syncConversationMemoryUI();
      ipcRenderer.send('chat-memory-setting-changed', useConversationMemory);

      try {
        localStorage.setItem('chat-memory-enabled', useConversationMemory.toString());
      } catch (e) {
        console.error('Failed to save memory setting:', e);
      }

      // Show feedback to user
      const feedback = document.createElement('div');
      feedback.textContent = useConversationMemory ? 
        '🧠 Memory ON - Full conversation context' : 
        '📝 Memory OFF - Personal context only';
      feedback.style.position = 'fixed';
      feedback.style.bottom = '20px';
      feedback.style.left = '50%';
      feedback.style.transform = 'translateX(-50%)';
      feedback.style.padding = '10px 18px';
      feedback.style.background = useConversationMemory ? 'rgba(100, 150, 255, 0.9)' : 'rgba(150, 100, 255, 0.9)';
      feedback.style.color = 'white';
      feedback.style.borderRadius = '8px';
      feedback.style.fontSize = '13px';
      feedback.style.fontWeight = '500';
      feedback.style.zIndex = '1000';
      feedback.style.boxShadow = '0 2px 12px rgba(0,0,0,0.15)';
      feedback.style.transition = 'all 0.2s';
      document.body.appendChild(feedback);
      
      // Animate feedback
      setTimeout(() => {
        feedback.style.opacity = '0';
        feedback.style.transform = 'translateX(-50%) translateY(10px)';
      }, 1500);
      
      setTimeout(() => {
        feedback.remove();
      }, 2000);
    });
  }
  syncConversationMemoryUI();

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
    if (e.key === 'Escape') {
      ipcRenderer.send('chat-close-window');
    }
  });

  chatInput.addEventListener('input', autoResizeTextarea);

  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => handleSearch(searchInput.value), 300);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      ipcRenderer.send('chat-close-window');
    }
  });

  // Voice input mic button
  if (chatMicBtn) {
    chatMicBtn.addEventListener('click', startChatRecording);
  }

  // Add global error handler for unhandled IPC calls
  window.addEventListener('error', (e) => {
    console.error('Unhandled error:', e.error);
  });

  // IPC listeners for streaming
  ipcRenderer.on('chat-stream-start', onStreamStart);
  ipcRenderer.on('chat-stream-chunk', (e, chunk) => onStreamChunk(chunk));
  ipcRenderer.on('chat-stream-end', (e, data) => onStreamEnd(data));
  ipcRenderer.on('chat-stream-error', (e, error) => onStreamError(error));
  ipcRenderer.on('chat-title-updated', (e, data) => onTitleUpdated(data));
  
  // Show fallback messages to user
  ipcRenderer.on('ai-backend-status', (e, status) => {
    const msg = typeof status === 'string' ? status : (status && status.message ? status.message : '');
    if (msg && msg.includes('switching to')) {
      // Show a temporary notification about provider switch
      const fallbackNotice = document.createElement('div');
      fallbackNotice.style.position = 'fixed';
      fallbackNotice.style.bottom = '20px';
      fallbackNotice.style.right = '20px';
      fallbackNotice.style.padding = '10px 16px';
      fallbackNotice.style.background = 'rgba(100, 150, 255, 0.9)';
      fallbackNotice.style.color = 'white';
      fallbackNotice.style.borderRadius = '8px';
      fallbackNotice.style.fontSize = '12px';
      fallbackNotice.style.zIndex = '1000';
      fallbackNotice.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
      fallbackNotice.textContent = msg;
      document.body.appendChild(fallbackNotice);
      
      setTimeout(() => {
        fallbackNotice.remove();
      }, 5000);
    }
  });

  // Re-populate agent dropdown when backend pushes updated list
  ipcRenderer.on('agents-updated', (event, agents) => {
    if (agents && agents.length > 0 && chatAgentSelect) {
      populateChatAgentSelectorWithData(agents);
    }
  });
});

function syncConversationMemoryUI() {
  if (memoryToggleBtn) {
    memoryToggleBtn.classList.toggle('active', useConversationMemory);
  }

  if (memoryStatusIndicator) {
    memoryStatusIndicator.classList.toggle('memory-on', useConversationMemory);
    memoryStatusIndicator.classList.toggle('memory-off', !useConversationMemory);
    memoryStatusIndicator.textContent = useConversationMemory ? 'Memory on' : 'Memory off';
    memoryStatusIndicator.title = useConversationMemory ?
      'Conversation memory ON - full chat context included' :
      'Conversation memory OFF - only the latest message is sent';
  }
}


// ── Conversation List ──

async function loadConversationList() {
  conversations = await ipcRenderer.invoke('chat-list-conversations');
  renderSidebar(conversations);
}

function renderSidebar(list) {
  sidebarList.innerHTML = '';

  if (list.length === 0) {
    sidebarList.innerHTML = '<div style="padding:20px 10px;text-align:center;color:rgba(255,255,255,0.2);font-size:12px;">No conversations yet</div>';
    return;
  }

  const groups = groupConversationsByDate(list);

  for (const group of groups) {
    const label = document.createElement('div');
    label.className = 'date-group-label';
    label.textContent = group.label;
    sidebarList.appendChild(label);

    for (const conv of group.items) {
      const item = document.createElement('div');
      item.className = 'conv-item' + (conv.id === currentConversationId ? ' active' : '');
      item.innerHTML = `
        <span class="conv-item-title">${escapeHtml(conv.title)}</span>
        <button class="conv-item-delete" title="Delete">&times;</button>
      `;
      item.addEventListener('click', (e) => {
        if (e.target.classList.contains('conv-item-delete')) return;
        loadConversation(conv.id);
      });
      item.querySelector('.conv-item-delete').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteConversation(conv.id);
      });
      sidebarList.appendChild(item);
    }
  }
}

function groupConversationsByDate(list) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86400000;
  const sevenDays = today - 7 * 86400000;

  const groups = [
    { label: 'Today', items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'Previous 7 Days', items: [] },
    { label: 'Older', items: [] }
  ];

  for (const conv of list) {
    const t = conv.updatedAt || conv.createdAt;
    if (t >= today) groups[0].items.push(conv);
    else if (t >= yesterday) groups[1].items.push(conv);
    else if (t >= sevenDays) groups[2].items.push(conv);
    else groups[3].items.push(conv);
  }

  return groups.filter(g => g.items.length > 0);
}


// ── Load Conversation ──

async function loadConversation(id) {
  try {
    const conv = await ipcRenderer.invoke('chat-load-conversation', id);
    if (!conv) return;

    currentConversationId = id;
    renderMessages(conv.messages);
    renderSidebar(conversations); // update active state
  } catch (e) {
    console.error('Failed to load conversation:', e);
  }
}

function renderMessages(messages) {
  messagesContainer.innerHTML = '';

  if (!messages || messages.length === 0) {
    emptyState.style.display = '';
    messagesContainer.appendChild(emptyState);
    return;
  }

  emptyState.style.display = 'none';

  for (const msg of messages) {
    appendMessageToDOM(msg);
  }

  scrollToBottom();
}

function appendMessageToDOM(msg) {
  const div = document.createElement('div');
  div.className = `message ${msg.role}`;
  div.dataset.msgId = msg.id;

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  if (msg.role === 'user') {
    bubble.textContent = msg.content;
  } else {
    bubble.innerHTML = renderMarkdown(msg.content);
  }

  const time = document.createElement('div');
  time.className = 'message-time';
  time.textContent = formatTime(msg.timestamp);

  div.appendChild(bubble);
  div.appendChild(time);
  messagesContainer.appendChild(div);
}


// ── Create & Delete ──

async function createNewConversation() {
  const conv = await ipcRenderer.invoke('chat-create-conversation');
  currentConversationId = conv.id;
  conversations.unshift({
    id: conv.id,
    title: conv.title,
    createdAt: conv.createdAt,
    updatedAt: conv.updatedAt,
    messageCount: 0,
    preview: ''
  });
  renderSidebar(conversations);
  renderMessages([]);
  chatInput.focus();
}

async function deleteConversation(id) {
  try {
    await ipcRenderer.invoke('chat-delete-conversation', id);
    conversations = conversations.filter(c => c.id !== id);
    if (currentConversationId === id) {
      currentConversationId = null;
      renderMessages([]);
    }
    renderSidebar(conversations);
  } catch (e) {
    console.error('Failed to delete conversation:', e);
  }
}


// ── Send Message ──

function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || isStreaming) return;

  // Auto-create conversation if none selected
  if (!currentConversationId) {
    ipcRenderer.invoke('chat-create-conversation').then(conv => {
      currentConversationId = conv.id;
      conversations.unshift({
        id: conv.id, title: conv.title,
        createdAt: conv.createdAt, updatedAt: conv.updatedAt,
        messageCount: 0, preview: ''
      });
      renderSidebar(conversations);
      doSend(text);
    });
    return;
  }

  doSend(text);
}

function doSend(text) {
  // Hide empty state
  emptyState.style.display = 'none';

  // Add user message to DOM
  const userMsg = {
    id: 'pending_user',
    role: 'user',
    content: text,
    timestamp: Date.now()
  };
  appendMessageToDOM(userMsg);
  scrollToBottom();

  // Clear input
  chatInput.value = '';
  autoResizeTextarea();

  // Send to main
  ipcRenderer.send('chat-send-message', currentConversationId, text);

  // Update sidebar preview
  const idx = conversations.findIndex(c => c.id === currentConversationId);
  if (idx >= 0) {
    conversations[idx].preview = text.substring(0, 100);
    conversations[idx].updatedAt = Date.now();
    conversations[idx].messageCount++;
  }
}

function handlePrimaryAction() {
  if (isStreaming) {
    stopStreaming();
    return;
  }

  sendMessage();
}


// ── Streaming Handlers ──

function onStreamStart() {
  isStreaming = true;
  streamingText = '';
  updateSendButton(true);

  // Create streaming message bubble
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.id = 'streaming-message';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = '<span class="streaming-cursor"></span>';

  div.appendChild(bubble);
  messagesContainer.appendChild(div);
  streamingBubble = bubble;
  scrollToBottom();
}

function onStreamChunk(chunk) {
  if (!streamingBubble) return;
  streamingText += chunk;

  // Debounced re-render (100ms); filter preamble so *** / ## etc. are not shown
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => {
    if (streamingBubble) {
      const displayText = filterPreamble(streamingText);
      streamingBubble.innerHTML = renderMarkdown(displayText) + '<span class="streaming-cursor"></span>';
      scrollToBottom();
    }
  }, 100);
}

function onStreamEnd(data) {
  isStreaming = false;
  clearTimeout(renderTimer);
  updateSendButton(false);

  const streamMsg = document.getElementById('streaming-message');
  const finalText = filterPreamble(data.text || streamingText);

  if (streamingBubble) {
    streamingBubble.innerHTML = renderMarkdown(finalText);
  }

  if (streamMsg) {
    streamMsg.removeAttribute('id');
    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = formatTime(Date.now());
    streamMsg.appendChild(time);
  }

  streamingBubble = null;
  streamingText = '';
  scrollToBottom();

  // Refresh sidebar to update preview
  loadConversationList();
}

function onStreamError(error) {
  isStreaming = false;
  clearTimeout(renderTimer);
  updateSendButton(false);

  const raw = (error ?? '').toString();
  let errorMessage = escapeHtml(raw);

  // Provide more user-friendly messages for common errors
  const lower = raw.toLowerCase();
  if (lower.includes('insufficient balance') || lower.includes('credit balance') || lower.includes('add credits')) {
    errorMessage = 'API account has insufficient credits. Add credits or switch to a different provider/model.';
  } else if (lower.includes('api key') || lower.includes('authentication') || lower.includes('unauthorized') || lower.includes('forbidden')) {
    errorMessage = 'Invalid or unauthorized API key. Check your provider key in Settings.';
  } else if (lower.includes('rate limit') || lower.includes('quota') || lower.includes('too many requests')) {
    errorMessage = 'API rate limit exceeded. Try again later or switch to a different provider/model.';
  } else if (lower.includes('backend not ready')) {
    errorMessage = 'AI backend is still starting. Wait 2–5 seconds and try again.';
  } else if (lower.includes('failed to send to ai backend')) {
    errorMessage = 'AI backend was not reachable. Restart the app and try again.';
  }

  const errorHtml = `<div style="color:rgba(255,100,100,0.8);padding:12px;background:rgba(255,100,100,0.05);border-radius:8px;border-left:3px solid rgba(255,100,100,0.3);">
    <strong>Error:</strong> ${errorMessage}
    <div style="margin-top:8px;font-size:12px;color:rgba(255,150,150,0.7);">
      Tip: Check your API settings in the Settings menu or try a different AI provider.
    </div>
  </div>`;

  if (streamingBubble) {
    streamingBubble.innerHTML = errorHtml;
  } else {
    // If we errored before stream-start, create an assistant bubble so the user sees something.
    const div = document.createElement('div');
    div.className = 'message assistant';
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = errorHtml;
    div.appendChild(bubble);
    messagesContainer.appendChild(div);
    scrollToBottom();
  }

  streamingBubble = null;
  streamingText = '';
}

function onTitleUpdated(data) {
  const idx = conversations.findIndex(c => c.id === data.id);
  if (idx >= 0) {
    conversations[idx].title = data.title;
    renderSidebar(conversations);
  }
}

function updateSendButton(streaming) {
  if (streaming) {
    sendBtn.classList.add('stop-btn');
    sendBtn.title = 'Stop generating';
    sendBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
  } else {
    sendBtn.classList.remove('stop-btn');
    sendBtn.title = 'Send message';
    sendBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none"><path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }
}

function stopStreaming() {
  ipcRenderer.send('chat-stop-generation');
  isStreaming = false;
  clearTimeout(renderTimer);
  updateSendButton(false);

  const partialText = filterPreamble(streamingText);
  const streamMsg = document.getElementById('streaming-message');

  if (streamingBubble) {
    streamingBubble.innerHTML = partialText ? renderMarkdown(partialText) : '<em>Response stopped.</em>';
  }

  if (streamMsg) {
    streamMsg.removeAttribute('id');
    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = formatTime(Date.now());
    streamMsg.appendChild(time);
  }

  streamingBubble = null;
  streamingText = '';
}


// ── Search ──

async function handleSearch(query) {
  if (!query || query.trim().length === 0) {
    renderSidebar(conversations);
    return;
  }

  try {
    const results = await ipcRenderer.invoke('chat-search', query);
    sidebarList.innerHTML = '';

    if (results.length === 0) {
      sidebarList.innerHTML = '<div style="padding:20px 10px;text-align:center;color:rgba(255,255,255,0.2);font-size:12px;">No results</div>';
      return;
    }

  for (const r of results) {
    const div = document.createElement('div');
    div.className = 'search-result';
    div.innerHTML = `
      <div class="search-result-type">${r.matchType}</div>
      <div class="search-result-title">${escapeHtml(r.title)}</div>
      ${r.content ? `<div class="search-result-preview">${escapeHtml(r.content)}</div>` : ''}
    `;
    div.addEventListener('click', () => {
      searchInput.value = '';
      loadConversation(r.conversationId);
      renderSidebar(conversations);
    });
    sidebarList.appendChild(div);
  }
  } catch (e) {
    console.error('Search failed:', e);
    sidebarList.innerHTML = '<div style="padding:20px 10px;text-align:center;color:rgba(255,255,255,0.2);font-size:12px;">Search error</div>';
  }
}


// ── Export ──

async function exportCurrentChat() {
  if (!currentConversationId) return;
  try {
    await ipcRenderer.invoke('chat-export-markdown', currentConversationId);
  } catch (e) {
    console.error('Export failed:', e);
  }
}


// ── Markdown ──

function renderMarkdown(text) {
  if (!text) return '';
  try {
    return marked.parse(text);
  } catch (e) {
    return escapeHtml(text);
  }
}


// ── Utilities ──

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  });
}

function autoResizeTextarea() {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
}

// ── Agent Selector ──

function populateChatAgentSelectorWithData(agents) {
  if (!agents || !chatAgentSelect) return;

  chatAgentSelect.innerHTML = '';

  const groups = { auto: [], fast: [], powerful: [], reasoning: [] };
  for (const a of agents) {
    const g = a.group || 'powerful';
    if (!groups[g]) groups[g] = [];
    groups[g].push(a);
  }

  for (const a of (groups.auto || [])) {
    const opt = document.createElement('option');
    opt.value = a.value;
    opt.textContent = a.label;
    chatAgentSelect.appendChild(opt);
  }

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
    chatAgentSelect.appendChild(optgroup);
  }

  const savedAgent = localStorage.getItem('chat-agent');
  if (savedAgent) {
    chatAgentSelect.value = savedAgent;
  }
}

async function populateChatAgentSelector() {
  try {
    const agents = await ipcRenderer.invoke('get-agents');
    populateChatAgentSelectorWithData(agents);
  } catch (e) {
    console.error('Failed to populate chat agent selector:', e);
  }
}


// ── Voice Input ──

async function startChatRecording() {
  if (isChatRecording || isStreaming) return;

  isChatRecording = true;
  chatMicBtn.classList.add('recording');
  chatMicBtn.disabled = true;

  try {
    const result = await ipcRenderer.invoke('transcribe-audio', {
      timeout: 30,
      phraseTimeout: 20
    });

    if (result.error) {
      console.error('Voice input error:', result.error);
    } else if (result.text) {
      const currentText = chatInput.value.trim();
      if (currentText) {
        chatInput.value = currentText + ' ' + result.text;
      } else {
        chatInput.value = result.text;
      }
      chatInput.focus();
      autoResizeTextarea();
    }
  } catch (error) {
    console.error('Voice input failed:', error.message);
  } finally {
    isChatRecording = false;
    chatMicBtn.classList.remove('recording');
    chatMicBtn.disabled = false;
  }
}


function copyCodeBlock(btn) {
  const wrapper = btn.closest('.code-block-wrapper');
  const code = wrapper.querySelector('pre code');
  if (code) {
    navigator.clipboard.writeText(code.textContent).then(() => {
      btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
    });
  }
}

// Make copyCodeBlock globally accessible (called from onclick in rendered HTML)
window.copyCodeBlock = copyCodeBlock;
