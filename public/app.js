'use strict';

let kbId    = null;
let docs    = {};   // filename -> meta
let isAsking = false;

// ── Init ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', initKb);

async function initKb() {
  setStatus('Initialising…', true);
  try {
    const res  = await fetch('/api/kb/new', { method: 'POST' });
    const data = await res.json();
    kbId = data.kb_id;
    setStatus('Ready · ' + kbId, false);
  } catch {
    setStatus('Server offline', false);
  }
}

function setStatus(text, loading) {
  document.getElementById('kbStatusText').textContent = text;
  const dot = document.querySelector('.status-dot');
  dot.classList.toggle('loading', loading);
}

// ── File upload ────────────────────────────────────────────────────────────
function dragOver(e)  { e.preventDefault(); document.getElementById('dropZone').classList.add('over'); }
function dragLeave(e) { document.getElementById('dropZone').classList.remove('over'); }
function dropFile(e)  {
  e.preventDefault();
  document.getElementById('dropZone').classList.remove('over');
  [...e.dataTransfer.files].forEach(f => uploadPDF(f));
}
function handleFiles(e) { [...e.target.files].forEach(f => uploadPDF(f)); }

async function uploadPDF(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) return alert('Only PDF files supported.');
  const apiKey = document.getElementById('apiKey').value.trim();
  if (!apiKey) return alert('Please enter your Anthropic API key first.');
  if (!kbId)   return alert('Knowledge base not ready — refresh the page.');
  if (docs[file.filename]) return;

  showProgress(0, `Uploading ${file.name}…`);

  const form = new FormData();
  form.append('file',   file);
  form.append('apiKey', apiKey);

  try {
    showProgress(40, 'Extracting text…');
    const res  = await fetch(`/api/kb/${kbId}/upload`, { method: 'POST', body: form });
    showProgress(80, 'Building index…');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);

    showProgress(100, 'Done!');
    setTimeout(hideProgress, 600);

    docs[data.filename] = data;
    renderDocList();
    updateStats();
    enableInput();
    addSysMsg(`📄 "${data.filename}" added — ${data.pages} pages, ${data.chunks} chunks indexed.`);

  } catch (err) {
    hideProgress();
    addSysMsg(`⚠️ ${err.message}`, true);
  }
}

function showProgress(pct, label) {
  document.getElementById('uploadProgress').style.display = 'block';
  document.getElementById('progFill').style.width = pct + '%';
  document.getElementById('progLabel').textContent = label;
}
function hideProgress() {
  document.getElementById('uploadProgress').style.display = 'none';
  document.getElementById('progFill').style.width = '0%';
}

async function removeDoc(filename) {
  try {
    await fetch(`/api/kb/${kbId}/remove`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename }),
    });
    delete docs[filename];
    renderDocList();
    updateStats();
    addSysMsg(`🗑 "${filename}" removed from knowledge base.`);
    if (Object.keys(docs).length === 0) disableInput();
  } catch (err) {
    addSysMsg(`⚠️ ${err.message}`, true);
  }
}

function renderDocList() {
  const list  = document.getElementById('docList');
  const count = document.getElementById('docCount');
  const n     = Object.keys(docs).length;
  count.textContent = `${n} doc${n !== 1 ? 's' : ''}`;

  list.innerHTML = Object.entries(docs).map(([name, meta]) => `
    <div class="doc-item">
      <div class="doc-icon">📄</div>
      <div class="doc-info">
        <div class="doc-name">${esc(name)}</div>
        <div class="doc-meta">${meta.pages} pages · ${meta.chunks} chunks</div>
      </div>
      <button class="doc-remove" onclick="removeDoc(${JSON.stringify(name)})">✕</button>
    </div>
  `).join('');
}

async function updateStats() {
  if (!kbId) return;
  try {
    const res  = await fetch(`/api/kb/${kbId}/info`);
    const data = await res.json();
    const card = document.getElementById('statsCard');
    const grid = document.getElementById('statsGrid');

    if (Object.keys(docs).length === 0) { card.style.display = 'none'; return; }
    card.style.display = 'block';

    const turns = data.history_turns || 0;
    grid.innerHTML = `
      <div class="stat-item"><div class="stat-num">${Object.keys(docs).length}</div><div class="stat-label">documents</div></div>
      <div class="stat-item"><div class="stat-num">${data.total_chunks}</div><div class="stat-label">chunks</div></div>
      <div class="stat-item"><div class="stat-num">${turns}</div><div class="stat-label">turns</div></div>
      <div class="stat-item"><div class="stat-num">5</div><div class="stat-label">retrieved / query</div></div>
    `;
  } catch {}
}

// ── Chat ───────────────────────────────────────────────────────────────────
async function sendQuestion() {
  if (isAsking) return;
  const q = document.getElementById('qInput').value.trim();
  if (!q) return;

  document.getElementById('qInput').value = '';
  autoResize(document.getElementById('qInput'));

  clearWelcome();
  addUserMsg(q);
  const thinkId = addThinking();

  isAsking = true;
  document.getElementById('sendBtn').disabled = true;
  document.getElementById('sendBtn').innerHTML = '<span class="spin"></span>';

  try {
    const res  = await fetch(`/api/kb/${kbId}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();
    removeEl(thinkId);

    if (!res.ok) addErrMsg(data.error);
    else         addBotMsg(data);

  } catch (err) {
    removeEl(thinkId);
    addErrMsg(err.message);
  }

  isAsking = false;
  document.getElementById('sendBtn').disabled = false;
  document.getElementById('sendBtn').innerHTML = '↑';
  updateStats();
}

// ── Controls ───────────────────────────────────────────────────────────────
async function clearHistory() {
  if (!kbId) return;
  await fetch(`/api/kb/${kbId}/clear_history`, { method: 'POST' });
  addSysMsg('💬 Conversation history cleared.');
  updateStats();
}

async function clearAll() {
  if (!confirm('Remove all documents and clear conversation history?')) return;
  for (const fn of Object.keys(docs)) await removeDoc(fn);
  await clearHistory();
  docs = {};
  renderDocList();
  updateStats();
  disableInput();
}

// ── Render ─────────────────────────────────────────────────────────────────
function clearWelcome() {
  const w = document.getElementById('welcomeMsg');
  if (w) w.remove();
}

function addUserMsg(text) {
  const id = uid();
  append(`<div class="msg user" id="${id}">
    <div class="msg-av">SK</div>
    <div class="msg-body"><div class="bubble">${esc(text)}</div></div>
  </div>`);
  return id;
}

function addThinking() {
  const id = uid();
  append(`<div class="msg bot" id="${id}">
    <div class="msg-av">🧠</div>
    <div class="msg-body">
      <div class="thinking-bubble">
        <span class="tdots"><span></span><span></span><span></span></span>
        Searching knowledge base…
      </div>
    </div>
  </div>`);
  return id;
}

function addBotMsg(data) {
  const id = uid();
  const citeTags = (data.citations || []).map(c =>
    `<span class="cite-tag">📎 ${esc(c.doc)} · p.${c.page}</span>`
  ).join('');
  const meta = `${data.chunks_used} chunks · ${data.ms}ms`;

  append(`<div class="msg bot" id="${id}">
    <div class="msg-av">🧠</div>
    <div class="msg-body">
      <div class="bubble">${mdFormat(esc(data.answer))}</div>
      ${citeTags ? `<div class="citations">${citeTags}</div>` : ''}
      <div class="msg-meta">${meta}</div>
    </div>
  </div>`);
}

function addErrMsg(msg) {
  const id = uid();
  append(`<div class="msg bot" id="${id}">
    <div class="msg-av">🧠</div>
    <div class="msg-body"><div class="err-bubble">⚠️ ${esc(msg)}</div></div>
  </div>`);
}

function addSysMsg(text, isErr = false) {
  append(`<div class="sys-msg" style="${isErr ? 'color:var(--red)' : ''}">${esc(text)}</div>`);
}

function append(html) {
  const el   = document.createElement('div');
  el.innerHTML = html;
  const msgs = document.getElementById('messages');
  msgs.appendChild(el.firstElementChild);
  msgs.scrollTop = msgs.scrollHeight;
}

function removeEl(id) { document.getElementById(id)?.remove(); }

// ── Input helpers ──────────────────────────────────────────────────────────
function enableInput() {
  document.getElementById('qInput').disabled = false;
  document.getElementById('sendBtn').disabled = false;
  document.getElementById('qInput').placeholder = 'Ask anything across all documents… (Enter to send)';
  document.getElementById('inputMeta').textContent =
    `${Object.keys(docs).length} document(s) indexed · Enter to send · Shift+Enter for new line`;
  document.getElementById('qInput').focus();
}

function disableInput() {
  document.getElementById('qInput').disabled = true;
  document.getElementById('sendBtn').disabled = true;
  document.getElementById('qInput').placeholder = 'Upload PDFs to start asking questions';
  document.getElementById('inputMeta').textContent = 'Upload PDFs to start asking questions';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function toggleKey() {
  const inp = document.getElementById('apiKey');
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

// ── Utils ──────────────────────────────────────────────────────────────────
function uid() { return 'm' + Math.random().toString(36).slice(2, 9); }

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;')
    .replace(/\n/g,'<br>');
}

function mdFormat(s) {
  return s
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>');
}
