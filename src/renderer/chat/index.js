const { ipcRenderer } = require('electron');
const path = require('path');
const { marked, Renderer } = require(path.join(__dirname, 'lib', 'marked.min.js'));

// ── State ──
let currentConversationId = null;
let conversations = [];
let isStreaming = false;
let streamingText = '';
let streamingBubble = null;
let renderTimer = null;
let searchTimer = null;

// ── DOM refs ──
let sidebarList, messagesContainer, chatInput, sendBtn, searchInput;
let chatAgentSelect, emptyState, exportBtn, chatMicBtn;

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

  // Populate agent selector from backend
  await populateChatAgentSelector();

  // Restore saved chat agent from localStorage
  try {
    const savedAgent = localStorage.getItem('chat-agent');
    if (savedAgent && chatAgentSelect) {
      chatAgentSelect.value = savedAgent;
    }
  } catch (e) {}

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
  await loadConversationList();

  // Event listeners
  document.getElementById('close-btn').addEventListener('click', () => {
    ipcRenderer.send('chat-close-window');
  });

  document.getElementById('new-chat-btn').addEventListener('click', createNewConversation);
  sendBtn.addEventListener('click', sendMessage);
  exportBtn.addEventListener('click', exportCurrentChat);

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

  // IPC listeners for streaming
  ipcRenderer.on('chat-stream-start', onStreamStart);
  ipcRenderer.on('chat-stream-chunk', (e, chunk) => onStreamChunk(chunk));
  ipcRenderer.on('chat-stream-end', (e, data) => onStreamEnd(data));
  ipcRenderer.on('chat-stream-error', (e, error) => onStreamError(error));
  ipcRenderer.on('chat-title-updated', (e, data) => onTitleUpdated(data));

  // Re-populate agent dropdown when backend pushes updated list
  ipcRenderer.on('agents-updated', (event, agents) => {
    if (agents && agents.length > 0 && chatAgentSelect) {
      populateChatAgentSelectorWithData(agents);
    }
  });
});


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
  const conv = await ipcRenderer.invoke('chat-load-conversation', id);
  if (!conv) return;

  currentConversationId = id;
  renderMessages(conv.messages);
  renderSidebar(conversations); // update active state
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
  await ipcRenderer.invoke('chat-delete-conversation', id);
  conversations = conversations.filter(c => c.id !== id);
  if (currentConversationId === id) {
    currentConversationId = null;
    renderMessages([]);
  }
  renderSidebar(conversations);
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

  // Debounced re-render (100ms)
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => {
    if (streamingBubble) {
      streamingBubble.innerHTML = renderMarkdown(streamingText) + '<span class="streaming-cursor"></span>';
      scrollToBottom();
    }
  }, 100);
}

function onStreamEnd(data) {
  isStreaming = false;
  clearTimeout(renderTimer);
  updateSendButton(false);

  if (streamingBubble) {
    const finalText = data.text || streamingText;
    streamingBubble.innerHTML = renderMarkdown(finalText);

    // Add time
    const streamMsg = document.getElementById('streaming-message');
    if (streamMsg) {
      streamMsg.removeAttribute('id');
      const time = document.createElement('div');
      time.className = 'message-time';
      time.textContent = formatTime(Date.now());
      streamMsg.appendChild(time);
    }
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

  if (streamingBubble) {
    streamingBubble.innerHTML = `<span style="color:rgba(255,100,100,0.8);">Error: ${escapeHtml(error)}</span>`;
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
    sendBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
    sendBtn.onclick = () => {
      ipcRenderer.send('chat-stop-generation');
      isStreaming = false;
      updateSendButton(false);
      if (streamingBubble) {
        streamingBubble.innerHTML = renderMarkdown(streamingText);
      }
      streamingBubble = null;
      streamingText = '';
    };
  } else {
    sendBtn.classList.remove('stop-btn');
    sendBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none"><path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    sendBtn.onclick = sendMessage;
  }
}


// ── Search ──

async function handleSearch(query) {
  if (!query || query.trim().length === 0) {
    renderSidebar(conversations);
    return;
  }

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
}


// ── Export ──

async function exportCurrentChat() {
  if (!currentConversationId) return;
  await ipcRenderer.invoke('chat-export-markdown', currentConversationId);
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
