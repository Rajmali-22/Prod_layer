const { ipcRenderer } = require('electron');
const path = require('path');
const { marked } = require(path.join(__dirname, '..', 'lib', 'marked.min.js'));

let isStreaming = false;
let streamingText = '';
let renderTimer = null;

const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const questionBlock = document.getElementById('question-block');
const questionText = document.getElementById('question-text');
const answerBody = document.getElementById('answer-body');
const closeBtn = document.getElementById('close-btn');

function setStatus(status, message = '') {
  statusDot.classList.remove('listening', 'transcribing', 'answering', 'error');
  if (status && status !== 'ready') statusDot.classList.add(status);
  statusText.textContent = message || ({
    ready: 'Ready',
    listening: 'Listening...',
    transcribing: 'Transcribing...',
    answering: 'Answering...'
  }[status] || 'Ready');
}

function scrollToBottom() {
  const container = answerBody.parentElement;
  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
  });
}

function renderAnswer(text, showCursor = false) {
  const safeText = (text || '').trim();
  if (!safeText) {
    answerBody.innerHTML = '<span style="color:rgba(255,255,255,0.25);font-size:13px;">Listening for interview questions...</span>';
    return;
  }

  try {
    answerBody.innerHTML = marked.parse(safeText) + (showCursor ? '<span class="streaming-cursor"></span>' : '');
  } catch {
    answerBody.textContent = safeText;
  }
}

function showError(message) {
  setStatus('error', 'Error');
  answerBody.innerHTML = `<div class="error-box"><strong>Error:</strong> ${escapeHtml(message || 'Unknown error')}</div>`;
  scrollToBottom();
}

function escapeHtml(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

closeBtn.addEventListener('click', () => {
  ipcRenderer.send('interview-close-window');
});

ipcRenderer.on('interview-question', (e, question) => {
  if (question && question.trim()) {
    questionBlock.style.display = '';
    questionText.textContent = question.trim();
  } else {
    questionBlock.style.display = 'none';
    questionText.textContent = '';
  }
});

ipcRenderer.on('interview-partial-question', (e, partial) => {
  if (partial && partial.trim()) {
    questionBlock.style.display = '';
    questionText.textContent = partial.trim();
    setStatus('transcribing', 'Transcribing...');
  }
});

ipcRenderer.on('interview-listener-status', (e, payload) => {
  const status = payload?.status || 'ready';
  const message = payload?.message || '';
  if (status === 'ready') setStatus('ready', message || 'Ready');
  else if (status === 'listening') setStatus('listening', message || 'Listening...');
  else if (status === 'transcribing') setStatus('transcribing', message || 'Transcribing...');
});

ipcRenderer.on('interview-stream-start', () => {
  isStreaming = true;
  streamingText = '';
  setStatus('answering', 'Answering...');
  renderAnswer('', false);
});

ipcRenderer.on('interview-stream-chunk', (e, chunk) => {
  if (!isStreaming) return;
  streamingText += chunk || '';
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => {
    renderAnswer(streamingText, true);
    scrollToBottom();
  }, 50);
});

ipcRenderer.on('interview-stream-end', (e, data) => {
  isStreaming = false;
  clearTimeout(renderTimer);
  streamingText = data?.text || streamingText;
  renderAnswer(streamingText, false);
  setStatus('listening', 'Listening...');
  scrollToBottom();
});

ipcRenderer.on('interview-stream-error', (e, error) => {
  isStreaming = false;
  clearTimeout(renderTimer);
  showError(error || 'Interview streaming failed');
});

ipcRenderer.on('ai-backend-status', (e, status) => {
  const msg = typeof status === 'string' ? status : (status?.message || '');
  if (!msg) return;
  if (msg.includes('switching to')) {
    setStatus('transcribing', msg);
  }
});

setStatus('ready', 'Ready');
