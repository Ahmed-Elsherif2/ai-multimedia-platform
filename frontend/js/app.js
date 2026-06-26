'use strict';

const API_BASE = `${window.location.origin}/api`;

// ─── Authentication ──────────────────────────────────────────────

let currentUser = null;

async function checkAuth() {
  try {
    const response = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
    if (response.ok) {
      const user = await response.json();
      currentUser = user;
      document.getElementById('loginScreen').classList.add('hidden');
      document.getElementById('registerScreen').classList.add('hidden');
      document.getElementById('mainApp').classList.remove('hidden');
      // Update username display
      const nameEl = document.getElementById('userDisplayName');
      if (nameEl) nameEl.textContent = user.username;
      return user;
    } else {
      showLogin();
      return null;
    }
  } catch (e) {
    showLogin();
    return null;
  }
}

function showLogin() {
  document.getElementById('loginScreen').classList.remove('hidden');
  document.getElementById('registerScreen').classList.add('hidden');
  document.getElementById('mainApp').classList.add('hidden');
  document.getElementById('loginError').classList.add('hidden');
}

function showRegister() {
  document.getElementById('loginScreen').classList.add('hidden');
  document.getElementById('registerScreen').classList.remove('hidden');
  document.getElementById('mainApp').classList.add('hidden');
  document.getElementById('registerError').classList.add('hidden');
}

async function loginUser() {
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value.trim();
  const errorEl = document.getElementById('loginError');
  errorEl.classList.add('hidden');
  
  if (!username || !password) {
    errorEl.textContent = 'Please enter username and password';
    errorEl.classList.remove('hidden');
    return;
  }
  
  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      credentials: 'include'
    });
    const data = await response.json();
    if (response.ok) {
      currentUser = data.user;
      // Show main app
      document.getElementById('loginScreen').classList.add('hidden');
      document.getElementById('mainApp').classList.remove('hidden');
      // Update username in dropdown
      const nameEl = document.getElementById('userDisplayName');
      if (nameEl) nameEl.textContent = currentUser.username;
      // Load user data
      await loadChats();
      renderHistoryList();
      updateProcessBtn();
    } else {
      errorEl.textContent = data.error || 'Login failed';
      errorEl.classList.remove('hidden');
    }
  } catch (e) {
    errorEl.textContent = 'Network error';
    errorEl.classList.remove('hidden');
  }
}

async function registerUser() {
  const username = document.getElementById('regUsername').value.trim();
  const password = document.getElementById('regPassword').value.trim();
  const errorEl = document.getElementById('registerError');
  errorEl.classList.add('hidden');
  
  if (!username || !password) {
    errorEl.textContent = 'Please fill all fields';
    errorEl.classList.remove('hidden');
    return;
  }
  if (username.length < 3) {
    errorEl.textContent = 'Username must be at least 3 characters';
    errorEl.classList.remove('hidden');
    return;
  }
  if (password.length < 6) {
    errorEl.textContent = 'Password must be at least 6 characters';
    errorEl.classList.remove('hidden');
    return;
  }
  
  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      credentials: 'include'
    });
    const data = await response.json();
    if (response.ok) {
      currentUser = data.user;
      document.getElementById('registerScreen').classList.add('hidden');
      document.getElementById('mainApp').classList.remove('hidden');
      // Update username in dropdown
      const nameEl = document.getElementById('userDisplayName');
      if (nameEl) nameEl.textContent = currentUser.username;
      await loadChats();
      renderHistoryList();
      updateProcessBtn();
    } else {
      errorEl.textContent = data.error || 'Registration failed';
      errorEl.classList.remove('hidden');
    }
  } catch (e) {
    errorEl.textContent = 'Network error';
    errorEl.classList.remove('hidden');
  }
}

async function logoutUser() {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
  } catch {}
  // Clear local state
  chats = [];
  activeChatId = null;
  processingQueue = [];
  isProcessing = false;
  currentUser = null;
  // Reset username display
  const nameEl = document.getElementById('userDisplayName');
  if (nameEl) nameEl.textContent = 'Guest';  // or leave as 'Demo User' if you prefer
  document.getElementById('mainApp').classList.add('hidden');
  showLogin();
}

let chats = [];
let activeChatId = null;
let selectedPreviewId = null;
let chatToRename = null;
let chatToDelete = null;
let processingQueue = [];
let isProcessing = false;

// ─── Delete File Modal Variables ──────────────────────────
let fileToDelete = null;

const $ = (id) => document.getElementById(id);

// ─── Utilities ───────────────────────────────────────────────
function escapeHtml(text) {
  if (!text) return '';
  const d = document.createElement('div');
  d.textContent = String(text);
  return d.innerHTML.replace(/\n/g, '<br>');
}

function escapeAttr(s) {
  return String(s || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

async function apiCall(endpoint, method = 'GET', body = null, isFormData = false, timeoutMs = 8000) {
  const headers = {};
  if (!isFormData) headers['Content-Type'] = 'application/json';
  const options = { method, headers, credentials: 'include' };
  if (body) options.body = isFormData ? body : JSON.stringify(body);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  options.signal = controller.signal;
  try {
    const r = await fetch(`${API_BASE}${endpoint}`, options);
    clearTimeout(timer);
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.error || `HTTP ${r.status}`);
    }
    return r.json();
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') throw new Error('Request timed out');
    throw err;
  }
}

// ─── Dropdowns (fixed position above trigger) ──────────────
let ignoreOutsideClickUntil = 0;

function closeAllDropdowns() {
  document.querySelectorAll('.dropdown-panel.is-open').forEach((p) => {
    // Don't close if the user is interacting with the panel
    if (p.contains(document.activeElement)) return;
    if (p.matches(':hover')) return;
    p.classList.remove('is-open');
    p.style.top = '';
    p.style.right = '';
    p.style.left = '';
    p.style.bottom = '';
  });
}

function positionDropdown(panel, trigger) {
  if (!panel || !trigger) return;
  const rect = trigger.getBoundingClientRect();
  const gap = 8;
  panel.style.position = 'fixed';
  panel.style.left = 'auto';
  panel.style.bottom = 'auto';
  panel.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
  panel.style.top = `${Math.max(8, rect.top - panel.offsetHeight - gap)}px`;
  if (rect.top - panel.offsetHeight - gap < 8) {
    panel.style.top = `${rect.bottom + gap}px`;
  }
}

function toggleDropdown(id, trigger) {
  const panel = $(id);
  if (!panel) return;
  const willOpen = !panel.classList.contains('is-open');
  closeAllDropdowns();
  if (!willOpen) return;
  panel.classList.add('is-open');
  
  // Remove any existing listeners to avoid duplicates
  panel.removeEventListener('wheel', stopDropdownClose);
  panel.removeEventListener('touchmove', stopDropdownClose);
  panel.addEventListener('wheel', stopDropdownClose, { passive: true });
  panel.addEventListener('touchmove', stopDropdownClose, { passive: true });
  
  if (id === 'fileDropdown') renderCurrentChatFiles();
  if (id === 'bellDropdown') renderNotifications();
  
  requestAnimationFrame(() => {
    positionDropdown(panel, trigger || document.querySelector(`[data-dropdown-toggle="${id}"]`));
  });
  ignoreOutsideClickUntil = Date.now() + 200;
}

// Helper function to stop event propagation
function stopDropdownClose(e) {
  e.stopPropagation();
}

// ─── Tabs ──────────────────────────────────────────────────
function switchTab(n) {
  document.querySelectorAll('[id^="content-"]').forEach((el) => el.classList.add('hidden'));
  const panel = $('content-' + n);
  if (panel) panel.classList.remove('hidden');
  document.querySelectorAll('nav a[data-tab]').forEach((el) => el.classList.remove('tab-active'));
  const tab = $('tab-' + n);
  if (tab) tab.classList.add('tab-active');
  closeAllDropdowns();
  if (n === 1) updateQueueDisplay();
  if (n === 3) loadTranscriptTab();
  if (n === 4) loadSummariesTab();
  if (n === 5) {
    renderHistoryList();
    selectedPreviewId = null;
    const area = $('previewArea');
    if (area) {
      area.className = 'flex-1 glass rounded-2xl p-5 chat-scroll overflow-y-auto text-slate-600 text-sm text-center flex items-center justify-center';
      area.textContent = 'Select a chat on the left';
    }
    const hdr = $('previewHeader');
    if (hdr) hdr.innerHTML = '';
  }
}

function highlightProcessBtn() {
  switchTab(1);
}

// ─── Activity ──────────────────────────────────────────────
function addActivity(msg, type = 'info') {
  const f = $('activityFeed');
  if (!f) return;
  const empty = f.querySelector('.text-center');
  if (empty) empty.remove();
  const icons = {
    info: 'fa-circle-info text-slate-500',
    success: 'fa-circle-check text-teal-400',
    error: 'fa-circle-xmark text-red-400',
    processing: 'fa-circle-notch fa-spin text-blue-400',
  };
  const colors = {
    info: 'text-slate-400',
    success: 'text-teal-300',
    error: 'text-red-300',
    processing: 'text-blue-300',
  };
  const d = document.createElement('div');
  d.className = `flex items-start gap-2 ${colors[type] || colors.info}`;
  d.innerHTML = `<i class="fa-solid ${icons[type] || icons.info} mt-0.5 text-xs"></i><span class="break-all text-xs">${escapeHtml(msg)}</span>`;
  f.appendChild(d);
  f.scrollTop = f.scrollHeight;
}

// ─── Health ────────────────────────────────────────────────
async function checkBackendHealth() {
  const s = $('backendStatus');
  const host = $('backendHostLabel');
  if (host) host.textContent = window.location.host || 'API';
  try {
    await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
    if (s) {
      s.innerHTML = '<span class="w-2 h-2 rounded-full status-online"></span><span class="text-green-400">Connected</span>';
    }
    return true;
  } catch {
    if (s) {
      s.innerHTML = '<span class="w-2 h-2 rounded-full status-offline"></span><span class="text-red-400">Offline</span>';
    }
    return false;
  }
}

// ─── Chats ─────────────────────────────────────────────────
async function loadChats() {
  try {
    chats = await apiCall('/chats');
    if (!Array.isArray(chats)) chats = [];
    
    // Restore processed/summarized status for each chat
    for (const chat of chats) {
      await restoreChatFileStatus(chat);
    }
    
    if (!chats.length) await createNewChat();
    else {
      activeChatId = chats[0].id;
      loadActiveChat();
    }
    renderHistoryList();
  } catch {
    chats = [{ id: 'local-demo', title: 'Demo Chat', messages: [], attached: [], pinned: false }];
    activeChatId = chats[0].id;
    loadActiveChat();
    renderHistoryList();
  }
}

async function restoreChatFileStatus(chat) {
  chat.processedFiles = chat.processedFiles || {};
  chat.summarizedFiles = chat.summarizedFiles || {};
  chat.failedFiles = chat.failedFiles || {};
  
  const files = chat.attached || [];
  if (files.length === 0) return;
  
  for (const file of files) {
    const fileId = file.fileId;
    if (!fileId) continue;
    
    try {
      if (file.type === 'pdf') {
        // PDF: Only check summary
        const summary = await apiCall(`/summary/${fileId}`).catch(() => null);
        if (summary && (summary.groq || summary.template || summary.gemma)) {
          chat.summarizedFiles[fileId] = { fileName: file.name, summary };
        }
      } else {
        // Audio/Video: Check transcript
        const transcript = await apiCall(`/transcript/${fileId}`).catch(() => null);
        if (transcript && transcript.full_text) {
          chat.processedFiles[fileId] = { fileName: file.name, transcript };
        }
      }
    } catch (e) {
      // Not processed yet
    }
  }
  
  await updateChat(chat);
}

async function createNewChat() {
  try {
    const nc = await apiCall('/chats', 'POST', { title: 'Chat ' + new Date().toLocaleTimeString() });
    chats.unshift(nc);
    activeChatId = nc.id;
    loadActiveChat();
    renderHistoryList();
    switchTab(0);
  } catch (e) {
    addActivity('Could not create chat: ' + e.message, 'error');
  }
}

async function updateChat(chat) {
  try {
    await apiCall(`/chats/${chat.id}`, 'PUT', chat);
  } catch {
    /* offline/local */
  }
}

function getActiveChat() {
  const chat = chats.find((c) => c.id === activeChatId);
  if (chat) {
    if (typeof chat.processedFiles === 'string') {
      try { chat.processedFiles = JSON.parse(chat.processedFiles); } catch { chat.processedFiles = {}; }
    }
    if (typeof chat.summarizedFiles === 'string') {
      try { chat.summarizedFiles = JSON.parse(chat.summarizedFiles); } catch { chat.summarizedFiles = {}; }
    }
    if (typeof chat.failedFiles === 'string') {
      try { chat.failedFiles = JSON.parse(chat.failedFiles); } catch { chat.failedFiles = {}; }
    }
  }
  return chat;
}

function loadActiveChat() {
  const chat = getActiveChat();
  if (!chat) return;
  
  if (typeof chat.processedFiles === 'string') {
    try { chat.processedFiles = JSON.parse(chat.processedFiles); } catch { chat.processedFiles = {}; }
  }
  if (typeof chat.summarizedFiles === 'string') {
    try { chat.summarizedFiles = JSON.parse(chat.summarizedFiles); } catch { chat.summarizedFiles = {}; }
  }
  if (typeof chat.failedFiles === 'string') {
    try { chat.failedFiles = JSON.parse(chat.failedFiles); } catch { chat.failedFiles = {}; }
  }
  
  const titleEl = $('chatTitle');
  if (titleEl) titleEl.textContent = chat.title || 'Chat';
  const area = $('chatArea');
  if (!area) return;
  area.innerHTML = '';
  area.className = 'flex-1 p-5 chat-scroll space-y-4 overflow-y-auto';
  if (!chat.messages?.length) {
    area.innerHTML =
      '<div class="flex justify-start"><div class="max-w-[80%] msg-bot px-5 py-3 text-sm leading-relaxed">Welcome! Upload audio or PDF files, then click <button type="button" onclick="highlightProcessBtn()" class="text-teal-400 font-semibold underline underline-offset-2 decoration-dotted cursor-pointer bg-transparent border-0 p-0 text-sm hover:text-teal-300 transition-colors">Process Content</button>.</div></div>';
  } else {
    chat.messages.forEach((msg) => {
      const div = document.createElement('div');
      div.className = msg.role === 'user' ? 'flex justify-end' : 'flex justify-start';
      if (msg.role === 'user') {
        div.innerHTML = `<div class="max-w-[80%] msg-user px-5 py-3 text-sm">${escapeHtml(msg.content)}</div>`;
      } else {
        div.innerHTML = `<div class="max-w-[85%] msg-bot px-5 py-3 text-sm">${msg.content || ''}</div>`;
      }
      area.appendChild(div);
    });
  }
  area.scrollTop = area.scrollHeight;
  updateProcessBtn();
}

// ─── Upload & process ──────────────────────────────────────
function setUploadBtnState(btnId, loading, label) {
  const btn = $(btnId);
  if (!btn) return;
  const otherId = btnId === 'uploadAudioBtn' ? 'uploadPdfBtn' : 'uploadAudioBtn';
  const other = $(otherId);
  if (loading) {
    btn.disabled = true;
    btn.dataset.origHtml = btn.innerHTML;
    btn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin text-sm"></i> ${label || 'Uploading…'}`;
    if (other) other.disabled = true;
  } else {
    btn.disabled = false;
    if (btn.dataset.origHtml) { btn.innerHTML = btn.dataset.origHtml; delete btn.dataset.origHtml; }
    if (other) other.disabled = false;
  }
}

async function handleAudioUpload(e) {
  const files = Array.from(e.target.files || []);
  e.target.value = '';
  if (!files.length) return;
  setUploadBtnState('uploadAudioBtn', true, 'Uploading…');
  for (const file of files) {
    const ext = file.name.split('.').pop().toLowerCase();
    const isVideo = file.type.startsWith('video/') || ['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v', 'mpg', 'mpeg'].includes(ext);
    const sizeMB = (file.size / 1024 / 1024).toFixed(1);
    if (file.size > 500 * 1024 * 1024) {
      addActivity(`Too large: ${file.name} (${sizeMB}MB)`, 'error');
      continue;
    }

    // ✅ Videos are uploaded as audio (no auto-processing)
    // They will be processed when user clicks "Process Content"
    addActivity(`Uploading ${isVideo ? 'video' : 'audio'}: ${file.name}${isVideo ? ' (will process later)' : ''}`, 'processing');
    const fd = new FormData();
    fd.append('audio', file, file.name);
    try {
      const data = await apiCall('/upload/audio', 'POST', fd, true, 120000);
      const chat = getActiveChat();
      if (chat) {
        const prev = (chat.attached || []).find((f) => f.name === file.name);
        if (prev?.fileId && chat.processedFiles) delete chat.processedFiles[prev.fileId];
        chat.attached = (chat.attached || []).filter((f) => f.name !== file.name);
        chat.attached.push({ type: 'audio', name: file.name, fileId: data.file_id });
        await updateChat(chat);
      }
      addActivity(`Uploaded: ${file.name}`, 'success');
    } catch (err) {
      addActivity(`Upload failed: ${file.name} — ${err.message}`, 'error');
    }
  }
  setUploadBtnState('uploadAudioBtn', false);
  updateProcessBtn();
}

async function handlePdfUpload(e) {
  const files = Array.from(e.target.files || []);
  e.target.value = '';
  if (!files.length) return;
  setUploadBtnState('uploadPdfBtn', true, 'Uploading…');
  for (const file of files) {
    addActivity(`Uploading PDF: ${file.name}`, 'processing');
    const fd = new FormData();
    fd.append('pdf', file);
    try {
      const data = await apiCall('/upload/pdf', 'POST', fd, true);
      const chat = getActiveChat();
      if (chat) {
        chat.attached = chat.attached || [];
        chat.attached.push({ type: 'pdf', name: file.name, fileId: data.file_id });
        await updateChat(chat);
      }
      addActivity(`Uploaded: ${file.name}`, 'success');
    } catch (err) {
      addActivity(`Upload failed: ${file.name} — ${err.message}`, 'error');
    }
  }
  setUploadBtnState('uploadPdfBtn', false);
  updateProcessBtn();
}

function updateProcessBtn() {
  const btn = document.getElementById('processBtn');
  if (!btn) return;
  
  const chat = getActiveChat();
  if (!chat) {
    btn.disabled = true;
    return;
  }
  
  const files = chat.attached || [];
  const processedFiles = chat.processedFiles || {};
  const summarizedFiles = chat.summarizedFiles || {};
  
  // Check if any file is in the queue with status 'queued' or 'processing'
  const inQueue = processingQueue.some(q => q.status === 'processing' || q.status === 'queued');
  
  // Check for unprocessed files (PDFs need summary, audio needs transcript)
  const hasUnprocessed = files.some(f => {
    const fileId = f.fileId;
    const isProcessed = f.type === 'pdf' 
      ? summarizedFiles[fileId] 
      : processedFiles[fileId];
    const isInQueue = processingQueue.some(q => q.fileId === fileId && (q.status === 'processing' || q.status === 'queued'));
    return !isProcessed && !isInQueue;
  });
  
  const pendingCount = files.filter(f => {
    const fileId = f.fileId;
    const isProcessed = f.type === 'pdf' 
      ? summarizedFiles[fileId] 
      : processedFiles[fileId];
    const isInQueue = processingQueue.some(q => q.fileId === fileId && (q.status === 'processing' || q.status === 'queued'));
    return !isProcessed && !isInQueue;
  }).length;
  
  if (hasUnprocessed && !inQueue) {
    btn.disabled = false;
    btn.className = 'w-full rounded-xl py-2.5 text-sm btn-primary transition-all';
    btn.innerHTML = `<i class="fa-solid fa-bolt mr-1.5"></i> Process Content (${pendingCount} pending)`;
  } else {
    btn.disabled = true;
    btn.className = 'w-full rounded-xl py-2.5 text-sm cursor-not-allowed opacity-40 bg-white/5 border border-white/10 text-slate-400 transition-all';
    if (inQueue) {
      btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin mr-1.5"></i> Processing…';
    } else if (files.length === 0) {
      btn.innerHTML = '<i class="fa-solid fa-bolt mr-1.5"></i> Upload a file first';
    } else {
      btn.innerHTML = '<i class="fa-solid fa-check mr-1.5"></i> All processed!';
    }
  }
}

function resetPipelineSteps(type) {
  ['step1', 'step2', 'step3', 'step4'].forEach((id) => {
    const el = $(id);
    if (el) {
      el.className = 'step-pending text-xs font-semibold';
      el.textContent = 'Pending';
    }
  });
  const labels =
    type === 'pdf'
      ? ['Upload', 'Text Extraction', 'Groq Summarization', 'Complete']
      : ['Upload', 'Diarization', 'Transcription', 'Complete'];
  ['step1label', 'step2label', 'step3label', 'step4label'].forEach((id, i) => {
    const el = $(id);
    if (el) el.textContent = labels[i];
  });
}

function updateQueueDisplay() {
  const c = $('processingList');
  if (!c) return;
  
  if (!processingQueue.length) {
    c.className = 'space-y-3 text-sm text-slate-600 text-center py-10';
    c.innerHTML = '<i class="fa-solid fa-hourglass text-2xl mb-2 block opacity-40"></i>No active processes';
    return;
  }
  
  c.className = 'space-y-3 text-sm';
  const colors = { queued: 'text-slate-400', processing: 'text-amber-400', completed: 'text-teal-400', failed: 'text-red-400' };
  const icons = { queued: 'fa-clock', processing: 'fa-circle-notch fa-spin', completed: 'fa-circle-check', failed: 'fa-circle-xmark' };
  
  c.innerHTML = processingQueue
    .map((item) => {
      const st = item.status || 'queued';
      return `<div class="glass rounded-xl p-4">
        <div class="flex justify-between items-center mb-2">
          <span class="truncate text-sm font-medium mr-2">${escapeHtml(item.fileName)}</span>
          <span class="${colors[st]} text-xs flex items-center gap-1.5"><i class="fa-solid ${icons[st]}"></i>${st}</span>
        </div>
        ${st === 'processing' ? `<div class="h-1.5 progress-track"><div class="progress-fill" style="width:${item.progress || 10}%"></div></div>` : ''}
      </div>`;
    })
    .join('');
}

function clearCompleted() {
  processingQueue = processingQueue.filter((i) => i.status !== 'completed' && i.status !== 'failed');
  updateQueueDisplay();
}

async function processSingleFile(fileId, fileName, chatId, type) {
  // Check if already processed before starting
  const chat = chats.find(c => c.id === chatId);
  if (chat) {
    // Ensure processedFiles and summarizedFiles are objects, not strings
    chat.processedFiles = typeof chat.processedFiles === 'string' 
      ? JSON.parse(chat.processedFiles) 
      : (chat.processedFiles || {});
    chat.summarizedFiles = typeof chat.summarizedFiles === 'string' 
      ? JSON.parse(chat.summarizedFiles) 
      : (chat.summarizedFiles || {});
    
    // Check if already processed
    if (type === 'pdf' && chat.summarizedFiles?.[fileId]) {
      addActivity(`Skipping ${fileName} - already summarized`, 'info');
      return;
    }
    if (type !== 'pdf' && chat.processedFiles?.[fileId]) {
      addActivity(`Skipping ${fileName} - already processed`, 'info');
      return;
    }
  }
  
  const item = { fileId, fileName, chatId, type, status: 'processing', progress: 10 };
  processingQueue.push(item);
  updateQueueDisplay();
  resetPipelineSteps(type);
  
  const s1 = document.getElementById('step1');
  if (s1) {
    s1.className = 'step-done text-xs font-semibold';
    s1.textContent = 'Uploaded ✓';
  }
  const s2 = document.getElementById('step2');
  if (s2) {
    s2.className = 'step-running text-xs font-semibold';
    s2.textContent = 'Running…';
  }
  addActivity(`Processing: ${fileName}`, 'processing');

  const iv = setInterval(() => {
    if (item.status === 'processing') {
      item.progress = Math.min((item.progress || 10) + 5, 90);
      updateQueueDisplay();
    }
  }, 3000);

  try {
    // Call the processing endpoint
    if (type === 'pdf') {
      await apiCall(`/summarize/${fileId}`, 'POST', null, false, 120000);
    } else {
      await apiCall(`/process/${fileId}`, 'POST', null, false, 660000);
    }
    
    clearInterval(iv);
    item.status = 'completed';
    item.progress = 100;
    updateQueueDisplay();
    
    ['step2', 'step3', 'step4'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.className = 'step-done text-xs font-semibold';
        el.textContent = 'Done ✓';
      }
    });
    
    addActivity(`Completed: ${fileName}`, 'success');
    
    // ─── Fetch the actual result and update chat state ───
    if (chat) {
      try {
        let resultData = null;
        if (type === 'pdf') {
          resultData = await apiCall(`/summary/${fileId}`);
          // Ensure object
          chat.summarizedFiles = typeof chat.summarizedFiles === 'string' 
            ? JSON.parse(chat.summarizedFiles) 
            : (chat.summarizedFiles || {});
          chat.summarizedFiles[fileId] = { fileName, summary: resultData };
        } else {
          resultData = await apiCall(`/transcript/${fileId}`);
          // Ensure object
          chat.processedFiles = typeof chat.processedFiles === 'string' 
            ? JSON.parse(chat.processedFiles) 
            : (chat.processedFiles || {});
          chat.processedFiles[fileId] = { fileName, transcript: resultData };
        }
        
        // ─── Save the updated chat to backend ───
        await updateChat(chat);
        
        // Update analytics
        if (resultData && resultData.full_text) {
          updateAnalytics(resultData);
        }
        
        console.log(`[Process] Updated chat state for ${fileId}`);
      } catch (e) {
        console.warn('Failed to fetch result:', e);
      }
    }
    
  } catch (error) {
    clearInterval(iv);
    item.status = 'failed';
    item.error = error.message;
    updateQueueDisplay();
    
    const s2f = document.getElementById('step2');
    if (s2f) {
      s2f.className = 'step-fail text-xs font-semibold';
      s2f.textContent = 'Failed';
    }
    addActivity(`Failed: ${fileName} — ${error.message}`, 'error');
    
    if (chat) {
      chat.failedFiles = typeof chat.failedFiles === 'string' 
        ? JSON.parse(chat.failedFiles) 
        : (chat.failedFiles || {});
      chat.failedFiles[fileId] = { fileName, failedAt: new Date().toISOString(), error: error.message };
      await updateChat(chat);
    }
  }
  
  updateQueueDisplay();
  updateProcessBtn();
}

async function processContent() {
  if (isProcessing) return;
  const chat = getActiveChat();
  if (!chat) {
    addActivity('No active chat', 'error');
    return;
  }
  
  // ─── CRITICAL: Refresh chat state from backend ───
  try {
    const freshChat = await apiCall(`/chats/${chat.id}`);
    if (freshChat) {
      // Update the chat with fresh data
      chat.attached = freshChat.attached || [];
      chat.processedFiles = freshChat.processedFiles || {};
      chat.summarizedFiles = freshChat.summarizedFiles || {};
      chat.messages = freshChat.messages || chat.messages || [];
      // Save back to ensure consistency
      await updateChat(chat);
    }
  } catch (e) {
    console.warn('Could not refresh chat state:', e);
  }
  
  const files = chat.attached || [];
  if (!files.length) {
    addActivity('No files uploaded yet', 'error');
    return;
  }
  
  // Find unprocessed files
  const unprocessed = files.filter(f => {
    const fileId = f.fileId;
    const isProcessed = f.type === 'pdf' 
      ? chat.summarizedFiles?.[fileId] 
      : chat.processedFiles?.[fileId];
    const isInQueue = processingQueue.some(q => q.fileId === fileId && q.status !== 'completed' && q.status !== 'failed');
    return !isProcessed && !isInQueue;
  });
  
  if (!unprocessed.length) {
    const allProcessed = files.every(f => {
      const fileId = f.fileId;
      return f.type === 'pdf' 
        ? chat.summarizedFiles?.[fileId] 
        : chat.processedFiles?.[fileId];
    });
    if (allProcessed) {
      addActivity('✅ All files already processed!', 'success');
    } else {
      addActivity('Files are in queue, please wait...', 'info');
    }
    updateProcessBtn();
    return;
  }
  
  addActivity(`📦 Processing ${unprocessed.length} file(s)...`, 'processing');
  isProcessing = true;
  updateProcessBtn();
  switchTab(1);
  
  for (const f of unprocessed) {
    await processSingleFile(f.fileId, f.name, activeChatId, f.type || 'audio');
  }
  
  isProcessing = false;
  updateProcessBtn();
  
  // ─── Final refresh after all processing ───
  try {
    const freshChat = await apiCall(`/chats/${chat.id}`);
    if (freshChat) {
      chat.attached = freshChat.attached || [];
      chat.processedFiles = freshChat.processedFiles || {};
      chat.summarizedFiles = freshChat.summarizedFiles || {};
      await updateChat(chat);
    }
  } catch (e) {}
  
  loadActiveChat();
  addActivity('✅ All processing complete!', 'success');
}

// ─── RAG chat ──────────────────────────────────────────────
function formatRagAnswer(answer) {
  if (!answer) return '';
  let f = escapeHtml(answer);
  f = f.replace(/\*\*([^*]+)\*\*/g, '<strong class="text-teal-400">$1</strong>');
  return f;
}

async function sendMessage() {
  const input = $('chatInput');
  const text = input?.value.trim();
  if (!text) return;
  const chat = getActiveChat();
  if (!chat) return;
  chat.messages = chat.messages || [];
  chat.messages.push({ role: 'user', content: text });
  input.value = '';
  loadActiveChat();
  const area = $('chatArea');
  const typing = document.createElement('div');
  typing.id = 'typingIndicator';
  typing.className = 'flex justify-start';
  typing.innerHTML =
    '<div class="msg-bot px-5 py-3 text-sm"><div class="flex gap-1.5"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div></div>';
  area.appendChild(typing);
  area.scrollTop = area.scrollHeight;

  let answer;
  try {
    const r = await apiCall('/rag/ask', 'POST', { query: text, chat_id: activeChatId }, false, 120000);
    if (r?.answer) answer = r.answer;
  } catch {
    /* fallback below */
  }
  $('typingIndicator')?.remove();
  if (!answer) {
    const p = Object.keys(chat.processedFiles || {}).length;
    const s = Object.keys(chat.summarizedFiles || {}).length;
    answer = p || s
      ? `I have ${p} transcript(s) and ${s} summary(ies). Looks like the backend is offline!!`
      : 'Upload and process files to enable Q&A.';
  }
  chat.messages.push({ role: 'assistant', content: formatRagAnswer(answer) });
  loadActiveChat();
  await updateChat(chat);
}

// ─── Analytics ─────────────────────────────────────────────
function updateAnalytics(transcript) {
  if (!transcript) return;
  const text = transcript.full_text || '';
  const words = text.split(/\s+/).filter((w) => w.length > 0).length;
  const speakers =
    transcript.speaker_count ||
    (transcript.segments ? new Set(transcript.segments.map((s) => s.speaker)).size : 0);
  let duration = 0;
  if (transcript.segments?.length) duration = Math.max(...transcript.segments.map((s) => s.end || 0));
  const wer = $('werValue');
  if (wer) wer.textContent = '--';
  const dv = $('durValue');
  if (dv) dv.textContent = duration > 0 ? Math.round(duration) + 's' : '--';
  const sv = $('spkValue');
  if (sv) sv.textContent = speakers || '--';
  const wv = $('wrdValue');
  if (wv) wv.textContent = words || '--';
}

// ─── Transcript tab ────────────────────────────────────────
const SPK_PALETTE = [
  { dot: 'bg-teal-400', text: 'text-teal-300', bubble: 'bubble-left', avatar: 'bg-teal-400/20 text-teal-300' },
  { dot: 'bg-indigo-400', text: 'text-indigo-300', bubble: 'bubble-right', avatar: 'bg-indigo-400/20 text-indigo-300' },
  { dot: 'bg-orange-400', text: 'text-orange-300', bubble: 'bubble-other', avatar: 'bg-orange-400/20 text-orange-300' },
];

async function loadTranscriptTab() {
  const chat = getActiveChat();
  const container = $('audioList');
  if (!container) return;
  const audioFiles = chat?.attached?.filter((f) => f.type === 'audio') || [];
  if (!audioFiles.length) {
    container.innerHTML =
      '<div class="text-slate-600 text-xs text-center py-6"><i class="fa-solid fa-music text-2xl block mb-2 opacity-30"></i>No audio</div>';
    return;
  }
  container.innerHTML = audioFiles
    .map((f) => {
      const done = chat.processedFiles?.[f.fileId];
      return `<div class="file-item glass-hover rounded-xl p-2.5 flex items-center justify-between cursor-pointer" data-file-id="${f.fileId}" data-file-name="${escapeAttr(f.name)}">
        <div class="flex items-center gap-2 min-w-0 flex-1">
          <i class="fa-solid fa-music text-teal-400 text-xs"></i>
          <span class="truncate text-xs">${escapeHtml(f.name)}</span>
          ${done ? '<i class="fa-solid fa-circle-check text-teal-400 text-[10px]"></i>' : ''}
        </div>
        <i class="file-delete fa-solid fa-trash text-[10px] text-slate-600 hover:text-red-400 cursor-pointer" data-delete="${f.fileId}"></i>
      </div>`;
    })
    .join('')
  container.querySelectorAll('[data-file-id]').forEach((el) => {
    el.addEventListener('click', (e) => {
      if (e.target.closest('[data-delete]')) return;
      selectAudio(el.dataset.fileId, el.dataset.fileName, el);
    });
  });
  container.querySelectorAll('[data-delete]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteFile(el.dataset.delete);
    });
  });
}

async function selectAudio(fileId, fileName, rowEl) {
  const title = $('selectedAudioTitle');
  if (title) title.innerHTML = `<span class="text-slate-500">Transcript:</span> <span class="grad-text">${escapeHtml(fileName)}</span>`;
  document.querySelectorAll('#audioList .file-item').forEach((el) => el.classList.remove('glass-active'));
  rowEl?.classList.add('glass-active');

  const preview = $('transcriptPreview');
  if (preview) {
    preview.className = 'flex-1 p-4 chat-scroll overflow-y-auto';
    preview.innerHTML =
      '<div class="flex flex-col items-center justify-center h-full gap-3 text-slate-500 text-sm"><i class="fa-solid fa-circle-notch fa-spin text-teal-400"></i>Loading…</div>';
  }

  const chat = getActiveChat();
  const processed = chat?.processedFiles?.[fileId];
  try {
    const data = processed?.transcript || (await apiCall(`/transcript/${fileId}`));
    displayTranscript(data);
    if (chat && !processed) {
      chat.processedFiles = chat.processedFiles || {};
      chat.processedFiles[fileId] = { fileName, transcript: data };
      await updateChat(chat);
    }
  } catch {
    if (preview) preview.innerHTML = '<p class="text-red-400 text-sm text-center py-8">Transcript not available</p>';
  }
  try {
    const emotionData = await apiCall(`/emotion/${fileId}?_=${Date.now()}`);
    displayEmotion(emotionData);
  } catch {
    /* emotion optional */
  }
}

function displayTranscript(data) {
  const previewDiv = $('transcriptPreview');
  const segDiv = $('speakerSegments');
  if (!previewDiv) return;
  previewDiv.className = 'flex-1 p-4 chat-scroll overflow-y-auto space-y-3';
  const speakerIdx = {};
  const speakers = [];

  function getColor(spk) {
    if (!(spk in speakerIdx)) {
      speakerIdx[spk] = Object.keys(speakerIdx).length % SPK_PALETTE.length;
      speakers.push(spk);
    }
    return SPK_PALETTE[speakerIdx[spk]];
  }

  if (data.conversation?.length) {
    let html = '<div class="space-y-3">';
    data.conversation.forEach((turn) => {
      const spk = turn.speaker || 'SPEAKER_00';
      const c = getColor(spk);
      const isRight = speakerIdx[spk] % 2 === 1;
      html += `<div class="flex gap-2.5 ${isRight ? 'flex-row-reverse' : ''}">
        <div class="spk-avatar ${c.avatar}">${spk.slice(-2)}</div>
        <div class="${c.bubble} rounded-2xl px-4 py-3 max-w-[85%]">
          <div class="text-[10px] font-bold ${c.text} mb-1">${escapeHtml(spk)}</div>
          <p class="text-sm text-slate-200">${escapeHtml(turn.text)}</p>
        </div>
      </div>`;
    });
    html += '</div>';
    previewDiv.innerHTML = html;
  } else if (data.full_text) {
    previewDiv.innerHTML = `<div class="bubble-left rounded-2xl px-4 py-3"><p class="text-sm">${escapeHtml(data.full_text)}</p></div>`;
  } else {
    previewDiv.innerHTML = '<p class="text-slate-600 text-sm text-center py-8">No transcript</p>';
  }

  if (segDiv) {
    segDiv.innerHTML = speakers.length
      ? speakers
          .map((s) => {
            const c = getColor(s);
            return `<span class="text-[11px] ${c.text} px-2 py-1 rounded-lg bg-white/[0.04]">${escapeHtml(s)}</span>`;
          })
          .join('')
      : '<span class="text-slate-600 text-xs">No speakers</span>';
  }
  updateAnalytics(data);
}

function getEmotionColor(emotion) {
  const m = {
    joy: 'text-yellow-400',
    anger: 'text-red-500',
    sadness: 'text-blue-400',
    neutral: 'text-slate-400',
    positive: 'text-teal-400',
    negative: 'text-red-400',
  };
  return m[emotion] || 'text-slate-300';
}

function displayEmotion(data) {
  if (!data) return;
  const sentimentLabel = data.sentiment?.label || 'neutral';
  const emotionLabel = data.emotion?.label || 'neutral';
  const topEmotions = data.top_3_emotions?.length
    ? data.top_3_emotions
    : [{ label: emotionLabel, score: data.emotion?.score || 0.5 }];

  const sd = $('sentimentDisplay');
  if (sd) {
    sd.innerHTML = `<div class="text-xl font-bold ${getEmotionColor(sentimentLabel)} capitalize">${escapeHtml(sentimentLabel)}</div>`;
  }
  const pd = $('primaryEmotionDisplay');
  if (pd) {
    pd.innerHTML = `<div class="text-xl font-bold ${getEmotionColor(emotionLabel)} capitalize">${escapeHtml(emotionLabel)}</div>`;
  }
  const tl = $('topEmotionsList');
  if (tl) {
    tl.innerHTML = topEmotions
      .slice(0, 4)
      .map((e) => {
        const label = e.label || e;
        const score = e.score || 0.5;
        return `<div class="text-[11px] flex justify-between ${getEmotionColor(label)}"><span class="capitalize">${escapeHtml(label)}</span><span>${Math.round(score * 100)}%</span></div>`;
      })
      .join('')
  }
  const conf = topEmotions[0]?.score || 0.5;
  const cs = $('confidenceScore');
  const cb = $('confidenceBar');
  if (cs) cs.textContent = Math.round(conf * 100) + '%';
  if (cb) cb.style.width = conf * 100 + '%';
}

// ─── Summaries Tab (UPDATED for Groq) ─────────────────────
async function loadSummariesTab() {
  const chat = getActiveChat();
  const container = $('documentList');
  if (!container) return;
  const pdfs = chat?.attached?.filter((f) => f.type === 'pdf') || [];
  if (!pdfs.length) {
    container.innerHTML = '<p class="text-slate-600 text-xs text-center py-6"><i class="fa-solid fa-file-pdf text-2xl block mb-2 opacity-30"></i>No PDFs uploaded</p>';
    return;
  }
  container.innerHTML = pdfs
    .map((f) => {
      const done = chat.summarizedFiles?.[f.fileId];
      return `<div class="file-item glass-hover rounded-xl p-2.5 flex items-center justify-between cursor-pointer group transition-all" onclick="selectDocument('${f.fileId}','${escapeAttr(f.name)}')">
        <div class="flex items-center gap-2 flex-1 min-w-0">
          <i class="fa-solid fa-file-pdf text-indigo-400 text-xs flex-shrink-0"></i>
          <span class="truncate text-xs font-medium">${escapeHtml(f.name)}</span>
          ${done ? '<i class="fa-solid fa-circle-check text-teal-400 text-[10px] flex-shrink-0"></i>' : ''}
        </div>
        <i class="file-delete fa-solid fa-trash text-[10px] text-slate-600 hover:text-red-400 opacity-0 cursor-pointer flex-shrink-0 ml-1 transition-all" onclick="deleteFile('${f.fileId}');event.stopPropagation();"></i>
      </div>`;
    })
    .join('');
}

async function selectDocument(fileId, fileName) {
  const title = $('selectedDocumentTitle');
  if (title) title.innerHTML = `<span class="text-slate-500 font-normal">Summary:</span> <span class="text-indigo-300">${escapeHtml(fileName)}</span>`;
  
  ['summaryGroq', 'summaryTemplate', 'summaryT5'].forEach(id => {
    const el = $(id);
    if (el) el.innerHTML = '<span class="text-slate-600 text-sm italic">Loading…</span>';
  });
  
  const chat = getActiveChat();
  const cached = chat?.summarizedFiles?.[fileId];
  if (cached?.summary) { 
    displaySummary(cached.summary); 
    return; 
  }
  
  try {
    const data = await apiCall(`/summary/${fileId}`);
    displaySummary(data);
    if (chat) {
      chat.summarizedFiles = chat.summarizedFiles || {};
      chat.summarizedFiles[fileId] = { fileName, summary: data };
      await updateChat(chat);
    }
  } catch(e) {
    const g = $('summaryGroq');
    if (g) g.innerHTML = '<span class="text-red-400 text-sm">Failed to load</span>';
    const t = $('summaryTemplate');
    if (t) t.textContent = 'N/A';
    const t5 = $('summaryT5');
    if (t5) t5.textContent = 'N/A';
  }
}

function displaySummary(data) {
  // Groq is primary - render markdown
  const groqEl = document.getElementById('summaryGroq');
  if (groqEl) {
    const rawSummary = data.groq || data.template || 'No summary available';
    
    // Check if marked is available
    if (typeof marked !== 'undefined') {
      // Configure marked for clean output
      marked.setOptions({
        breaks: true,
        gfm: true
      });
      groqEl.innerHTML = marked.parse(rawSummary);
    } else {
      // Fallback manual render
      groqEl.innerHTML = renderMarkdown(rawSummary);
    }
  }
  
  // Template (always available)
  const templateEl = document.getElementById('summaryTemplate');
  if (templateEl) {
    templateEl.textContent = data.template || '—';
  }
  
  // T5 (legacy)
  const t5El = document.getElementById('summaryT5');
  if (t5El) {
    t5El.textContent = data.t5 || '—';
  }
}

// Manual markdown renderer (fallback if marked.js not loaded)
function renderMarkdown(text) {
  if (!text) return '';
  let html = text;
  
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');
  
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  
  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  
  // Bullet points - wrap in ul
  let inList = false;
  const lines = html.split('\n');
  let result = [];
  for (let line of lines) {
    if (line.match(/^- (.+)$/)) {
      if (!inList) { result.push('<ul>'); inList = true; }
      result.push(`<li>${line.replace(/^- /, '')}</li>`);
    } else if (line.match(/^\d+\. (.+)$/)) {
      if (!inList) { result.push('<ol>'); inList = true; }
      result.push(`<li>${line.replace(/^\d+\. /, '')}</li>`);
    } else {
      if (inList) { 
        result.push(inList === 'ul' ? '</ul>' : '</ol>'); 
        inList = false; 
      }
      if (line.trim()) result.push(line);
    }
  }
  if (inList) result.push(inList === 'ul' ? '</ul>' : '</ol>');
  html = result.join('\n');
  
  // Paragraphs (split by double newlines)
  html = html.replace(/\n\n/g, '</p><p>');
  if (!html.startsWith('<h') && !html.startsWith('<ul') && !html.startsWith('<ol')) {
    html = '<p>' + html + '</p>';
  }
  
  return html;
}

// ─── Delete File Modal ─────────────────────────────────────
let selectedFilesToDelete = new Set();

async function showDeleteFileModal() {
  const modal = document.getElementById('deleteFileModal');
  const container = document.getElementById('fileListContainer');
  if (!modal || !container) return;
  
  modal.classList.remove('hidden');
  selectedFilesToDelete.clear();
  container.innerHTML = '<div class="text-slate-500 text-sm text-center py-4">Loading files...</div>';
  document.getElementById('confirmDeleteFilesBtn').disabled = true;
  document.getElementById('selectedCount').textContent = '0 selected';
  document.getElementById('selectAllFiles').checked = false;
  
  try {
    const chat = getActiveChat();
    const files = chat?.attached || [];
    
    if (files.length === 0) {
      container.innerHTML = '<div class="text-slate-500 text-sm text-center py-4">No files available to delete</div>';
      return;
    }
    
    container.innerHTML = files.map(f => `
      <label class="file-item flex items-center gap-3 p-2.5 rounded-xl hover:bg-white/[0.04] cursor-pointer transition-colors">
        <input type="checkbox" class="file-checkbox w-4 h-4 accent-red-500 rounded border-white/20 bg-slate-700 flex-shrink-0" data-file-id="${f.fileId}" data-file-name="${escapeAttr(f.name)}">
        <span class="text-sm truncate text-slate-300">${escapeHtml(f.name)}</span>
        <span class="text-[10px] text-slate-500 ml-auto flex-shrink-0">${f.type || 'unknown'}</span>
      </label>
    `).join('');
    
    // Add event listeners to checkboxes
    container.querySelectorAll('.file-checkbox').forEach(cb => {
      cb.addEventListener('change', updateDeleteSelection);
    });
    
    // Select All checkbox
    document.getElementById('selectAllFiles').addEventListener('change', function() {
      const checkboxes = container.querySelectorAll('.file-checkbox');
      checkboxes.forEach(cb => cb.checked = this.checked);
      updateDeleteSelection();
    });
    
    updateDeleteSelection();
    
  } catch (e) {
    container.innerHTML = `<div class="text-red-400 text-sm text-center py-4">Error: ${e.message}</div>`;
  }
}

function updateDeleteSelection() {
  const checkboxes = document.querySelectorAll('.file-checkbox');
  selectedFilesToDelete.clear();
  checkboxes.forEach(cb => {
    if (cb.checked) selectedFilesToDelete.add(cb.dataset.fileId);
  });
  
  const count = selectedFilesToDelete.size;
  document.getElementById('selectedCount').textContent = `${count} selected`;
  document.getElementById('confirmDeleteFilesBtn').disabled = count === 0;
  
  // Update Select All checkbox state
  const selectAll = document.getElementById('selectAllFiles');
  const total = checkboxes.length;
  const checked = document.querySelectorAll('.file-checkbox:checked').length;
  if (total > 0) {
    selectAll.checked = checked === total;
    selectAll.indeterminate = checked > 0 && checked < total;
  }
}

function closeDeleteFileModal() {
  document.getElementById('deleteFileModal').classList.add('hidden');
  selectedFilesToDelete.clear();
  document.getElementById('confirmDeleteFilesBtn').disabled = true;
}

async function confirmDeleteFiles() {
  const fileIds = Array.from(selectedFilesToDelete);
  if (fileIds.length === 0) return;
  
  if (!confirm(`Are you sure you want to permanently delete ${fileIds.length} file(s)?`)) return;
  
  let deleted = 0;
  let failed = 0;
  
  for (const fileId of fileIds) {
    try {
      const response = await apiCall(`/file/${fileId}`, 'DELETE');
      if (response.success) {
        deleted++;
        // Remove from chat
        const chat = getActiveChat();
        if (chat) {
          chat.attached = chat.attached?.filter(f => f.fileId !== fileId) || [];
          if (chat.processedFiles) delete chat.processedFiles[fileId];
          if (chat.summarizedFiles) delete chat.summarizedFiles[fileId];
          await updateChat(chat);
        }
      } else {
        failed++;
      }
    } catch (e) {
      failed++;
      console.error(`Failed to delete ${fileId}:`, e);
    }
  }
  
  // Refresh UI
  loadTranscriptTab();
  loadSummariesTab();
  updateProcessBtn();
  renderCurrentChatFiles();
  
  if (deleted > 0) {
    addActivity(`Deleted ${deleted} file(s)${failed > 0 ? `, ${failed} failed` : ''}`, failed > 0 ? 'warning' : 'success');
  } else {
    addActivity(`Failed to delete ${failed} file(s)`, 'error');
  }
  
  closeDeleteFileModal();
}

// ─── Delete File ───────────────────────────────────────────
async function deleteFile(fileId) {
  const chat = getActiveChat();
  if (!chat) return;
  chat.attached = (chat.attached || []).filter((f) => f.fileId !== fileId);
  if (chat.processedFiles) delete chat.processedFiles[fileId];
  if (chat.summarizedFiles) delete chat.summarizedFiles[fileId];
  processingQueue = processingQueue.filter((q) => q.fileId !== fileId);
  await updateChat(chat);
  loadTranscriptTab();
  loadSummariesTab();
  updateProcessBtn();
  addActivity('File removed', 'info');
}

// ─── Storage Stats ─────────────────────────────────────────
async function showStorageStats() {
  const modal = document.getElementById('storageStatsModal');
  const content = document.getElementById('storageStatsContent');
  if (!modal || !content) return;
  
  modal.classList.remove('hidden');
  content.innerHTML = '<p class="text-slate-500">Loading...</p>';
  
  try {
    const stats = await apiCall('/cleanup/stats');
    const db = stats.database || {};
    const storage = stats.storage || {};
    
    content.innerHTML = `
      <div class="space-y-3">
        <div class="flex justify-between py-2 border-b border-white/5">
          <span class="text-slate-400">📄 Files</span>
          <span class="text-white font-medium">${db.files || 0}</span>
        </div>
        <div class="flex justify-between py-2 border-b border-white/5">
          <span class="text-slate-400">📝 Transcripts</span>
          <span class="text-white font-medium">${db.transcripts || 0}</span>
        </div>
        <div class="flex justify-between py-2 border-b border-white/5">
          <span class="text-slate-400">📋 Summaries</span>
          <span class="text-white font-medium">${db.summaries || 0}</span>
        </div>
        <div class="flex justify-between py-2 border-b border-white/5">
          <span class="text-slate-400">💾 Storage Used</span>
          <span class="text-white font-medium">${storage.total_size_mb || 0} MB</span>
        </div>
        <div class="flex justify-between py-2">
          <span class="text-slate-400">📁 Files on Disk</span>
          <span class="text-white font-medium">${storage.file_count || 0}</span>
        </div>
      </div>
    `;
  } catch (e) {
    content.innerHTML = `<p class="text-red-400">Error loading stats: ${e.message}</p>`;
  }
}

function closeStorageStats() {
  document.getElementById('storageStatsModal').classList.add('hidden');
}

// ─── History ───────────────────────────────────────────────
function renderHistoryList() {
  const container = $('historyList');
  if (!container) return;
  container.innerHTML = '';
  [...chats]
    .sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || new Date(b.createdAt) - new Date(a.createdAt))
    .forEach((chat) => {
      const div = document.createElement('div');
      div.className = `glass rounded-xl p-3.5 cursor-pointer flex justify-between items-center glass-hover ${chat.id === activeChatId ? 'glass-active' : ''}`;
      div.innerHTML = `
        <div class="flex-1 min-w-0" data-preview="${chat.id}">
          <div class="font-medium text-sm truncate">${escapeHtml(chat.title)}</div>
          <div class="text-[11px] text-slate-500">${chat.messages?.length || 0} messages</div>
        </div>
        <div class="flex gap-2 text-slate-600 ml-2">
          <i class="fa-solid fa-thumbtack hover:text-teal-400 cursor-pointer ${chat.pinned ? 'text-teal-400' : ''}" data-pin="${chat.id}"></i>
          <i class="fa-solid fa-pencil hover:text-teal-400 cursor-pointer" data-rename="${chat.id}"></i>
          <i class="fa-solid fa-trash hover:text-red-400 cursor-pointer" data-del="${chat.id}"></i>
        </div>`;
      div.querySelector('[data-preview]')?.addEventListener('click', () => selectPreviewChat(chat.id));
      div.querySelector('[data-pin]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        togglePin(chat.id);
      });
      div.querySelector('[data-rename]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        showRenameModal(chat.id);
      });
      div.querySelector('[data-del]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        showDeleteModal(chat.id);
      });
      container.appendChild(div);
    });
}

function selectPreviewChat(id) {
  selectedPreviewId = id;
  const chat = chats.find((c) => c.id === id);
  if (!chat) return;
  const hdr = $('previewHeader');
  if (hdr) {
    hdr.innerHTML = `<span class="font-semibold text-sm">${escapeHtml(chat.title)}</span>`;
    hdr.className = 'flex justify-between items-center mb-4 flex-shrink-0';
  }
  const area = $('previewArea');
  if (!area) return;
  area.className = 'flex-1 glass rounded-2xl p-5 chat-scroll space-y-4 overflow-y-auto';
  area.innerHTML = '';
  if (!chat.messages?.length) {
    area.innerHTML = '<p class="text-slate-600 text-center text-sm">No messages</p>';
    return;
  }
  chat.messages.forEach((msg) => {
    const div = document.createElement('div');
    div.className = msg.role === 'user' ? 'flex justify-end' : 'flex justify-start';
    div.innerHTML =
      msg.role === 'user'
        ? `<div class="max-w-[70%] msg-user px-4 py-2.5 text-sm">${escapeHtml(msg.content)}</div>`
        : `<div class="max-w-[70%] msg-bot px-4 py-2.5 text-sm">${msg.content || ''}</div>`;
    area.appendChild(div);
  });
}

function loadSelectedChatIntoDashboard() {
  if (!selectedPreviewId) return;
  activeChatId = selectedPreviewId;
  loadActiveChat();
  switchTab(0);
}

async function togglePin(id) {
  const c = chats.find((x) => x.id === id);
  if (c) {
    c.pinned = !c.pinned;
    await updateChat(c);
    renderHistoryList();
  }
}

function showRenameModal(id) {
  chatToRename = chats.find((c) => c.id === id);
  if (!chatToRename) return;
  $('renameInput').value = chatToRename.title;
  $('renameModal').classList.remove('hidden');
}

async function confirmRename() {
  const renamedId = chatToRename?.id;
  if (chatToRename) {
    const t = $('renameInput').value.trim();
    if (t) {
      chatToRename.title = t;
      await updateChat(chatToRename);
    }
  }
  closeRenameModal();
  renderHistoryList();
  if (activeChatId === renamedId) loadActiveChat();
}

function closeRenameModal() {
  $('renameModal').classList.add('hidden');
  chatToRename = null;
}

function showDeleteModal(id) {
  chatToDelete = id;
  const c = chats.find((x) => x.id === id);
  $('deleteChatName').textContent = c?.title || '';
  $('deleteModal').classList.remove('hidden');
}

async function confirmDelete() {
  if (chatToDelete) {
    try {
      await apiCall(`/chats/${chatToDelete}`, 'DELETE');
    } catch {
      /* local */
    }
    chats = chats.filter((c) => c.id !== chatToDelete);
    if (activeChatId === chatToDelete) activeChatId = chats[0]?.id || null;
  }
  closeDeleteModal();
  renderHistoryList();
  if (activeChatId) loadActiveChat();
  else await createNewChat();
}

function closeDeleteModal() {
  $('deleteModal').classList.add('hidden');
  chatToDelete = null;
}

function renderCurrentChatFiles() {
  const chat = getActiveChat();
  const c = document.getElementById('currentChatFiles');
  const countEl = document.getElementById('fileCount');
  
  if (!c) return;
  
  c.style.overflowY = 'auto';
  c.style.overscrollBehavior = 'contain';
  
  if (!chat?.attached?.length) {
    c.innerHTML = '<div class="text-slate-600 text-xs p-2 text-center">No files in this chat</div>';
    if (countEl) countEl.textContent = '0';
    return;
  }
  
  const files = chat.attached;
  if (countEl) countEl.textContent = files.length;
  
  c.innerHTML = files.map((f) => {
    const isPdf = f.type === 'pdf';
    const ext = f.name.split('.').pop().toUpperCase();
    const baseName = f.name.replace(/\.[^/.]+$/, '');
    const shortName = baseName.length > 28 ? baseName.slice(0, 14) + '…' + baseName.slice(-10) : baseName;
    const processed = isPdf ? chat.summarizedFiles?.[f.fileId] : chat.processedFiles?.[f.fileId];
    return `<div class="flex items-center gap-2.5 px-2 py-2 rounded-xl hover:bg-white/[0.06] transition-colors">
      <div class="flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center ${isPdf ? 'bg-indigo-400/10' : 'bg-teal-400/10'}">
        <i class="fa-solid ${isPdf ? 'fa-file-pdf text-indigo-400' : 'fa-music text-teal-400'} text-xs"></i>
      </div>
      <div class="flex-1 min-w-0">
        <div class="text-xs text-slate-200 font-medium leading-tight" title="${escapeHtml(f.name)}">${escapeHtml(shortName)}</div>
        <div class="flex items-center gap-1.5 mt-0.5">
          <span class="text-[9px] font-bold px-1 py-0.5 rounded ${isPdf ? 'bg-indigo-400/15 text-indigo-400' : 'bg-teal-400/15 text-teal-400'}">${ext}</span>
          ${processed ? '<span class="text-[9px] text-teal-400"><i class="fa-solid fa-circle-check mr-0.5"></i>Processed</span>' : '<span class="text-[9px] text-slate-500">Pending</span>'}
        </div>
      </div>
    </div>`;
  }).join('');
}

function renderNotifications() {
  const p = processingQueue.filter((i) => i.status === 'processing').length;
  const q = processingQueue.filter((i) => i.status === 'queued').length;
  const el = $('bellContent');
  if (!el) return;
  let h = '';
  if (p) h += `<p class="text-amber-400 text-xs"><i class="fa-solid fa-circle-notch fa-spin mr-1"></i>${p} processing</p>`;
  if (q) h += `<p class="text-teal-400 text-xs"><i class="fa-solid fa-clock mr-1"></i>${q} queued</p>`;
  if (!h) h = '<p class="text-teal-400 text-xs"><i class="fa-solid fa-check mr-1"></i>All clear</p>';
  el.innerHTML = h;
}

// ─── Init ──────────────────────────────────────────────────
function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach((a) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      switchTab(Number(a.dataset.tab));
    });
  });
  document.querySelectorAll('[data-tab-link]').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(Number(btn.dataset.tabLink)));
  });
  document.querySelectorAll('[data-dropdown-toggle]').forEach((btn) => {
    btn.classList.add('dropdown-trigger');
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleDropdown(btn.dataset.dropdownToggle, btn);
    });
  });
  document.addEventListener('click', (e) => {
    if (Date.now() < ignoreOutsideClickUntil) return;
    if (e.target.closest('.dropdown-wrap') || e.target.closest('.dropdown-panel')) return;
    closeAllDropdowns();
  });
  window.addEventListener('resize', closeAllDropdowns);
  window.addEventListener('scroll', closeAllDropdowns, true);

    // ─── Delete File Button ──────────────────────────────────
  const deleteFileBtn = document.getElementById('deleteFileBtn');
  if (deleteFileBtn) {
    deleteFileBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      closeAllDropdowns();
      showDeleteFileModal();
    });
  }

  // ─── Storage Stats Button ────────────────────────────────
  const storageStatsBtn = document.getElementById('storageStatsBtn');
  if (storageStatsBtn) {
    storageStatsBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      closeAllDropdowns();
      showStorageStats();
    });
  }

  // ─── Reset Demo Button ───────────────────────────────────
  const resetDemoBtn = document.getElementById('resetDemoBtn');
  if (resetDemoBtn) {
    resetDemoBtn.addEventListener('click', function() {
      if (confirm('Reset demo?')) location.reload();
    });
  }

  $('uploadAudioBtn')?.addEventListener('click', () => $('audioFileInput')?.click());
  $('uploadPdfBtn')?.addEventListener('click', () => $('pdfFileInput')?.click());
  $('audioFileInput')?.addEventListener('change', handleAudioUpload);
  $('pdfFileInput')?.addEventListener('change', handlePdfUpload);
  $('processBtn')?.addEventListener('click', processContent);
  $('sendMessageBtn')?.addEventListener('click', sendMessage);
  $('chatInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      sendMessage();
    }
  });
  $('clearCompletedBtn')?.addEventListener('click', clearCompleted);
  $('newChatBtn')?.addEventListener('click', createNewChat);
  $('loadChatBtn')?.addEventListener('click', loadSelectedChatIntoDashboard);
  $('renameCancelBtn')?.addEventListener('click', closeRenameModal);
  $('renameConfirmBtn')?.addEventListener('click', confirmRename);
  $('deleteCancelBtn')?.addEventListener('click', closeDeleteModal);
  $('deleteConfirmBtn')?.addEventListener('click', confirmDelete);
  $('resetDemoBtn')?.addEventListener('click', () => {
    if (confirm('Reset demo?')) location.reload();
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  bindEvents();
  const user = await checkAuth();
  if (user) {
    // User is logged in, proceed to load chats
    const ok = await checkBackendHealth();
    if (ok) await loadChats();
    else {
      addActivity('Backend offline — start server on port 5000', 'error');
      await loadChats();
    }
  }
});