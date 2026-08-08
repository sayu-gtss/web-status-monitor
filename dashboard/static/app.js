/* ==========================================================================
   Website Availability Monitor Dashboard — Frontend Logic
   ========================================================================== */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let statusData = {};     // Latest monitor_state.json contents
let urlList = [];        // Current WEBSITES_TO_MONITOR list
let configData = {};     // Current .env key/value map
let refreshTimer = null;
let checkEventSource = null;
let chartInstances = {}; // Active Chart.js instances
let rawLatencyData = {}; // Full latency dataset cache

const REFRESH_INTERVAL_MS = 30_000;

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
const VIEWS = ['overview', 'urls', 'analytics', 'db-logs', 'settings'];
const VIEW_TITLES = {
  overview: 'Overview',
  urls: 'Monitor URLs',
  analytics: 'Analytics',
  'db-logs': 'Database Logs',
  settings: 'Settings',
};

function navigateTo(view) {
  VIEWS.forEach((v) => {
    const btn = $(`nav-${v}`);
    const section = $(`view-${v}`);
    if (!btn || !section) return;
    const isActive = v === view;
    btn.classList.toggle('active', isActive);
    section.style.display = isActive ? '' : 'none';
    if (isActive) section.classList.add('view');
  });
  $('pageTitle').textContent = VIEW_TITLES[view] || view;

  // Load data for the selected view
  if (view === 'overview') loadStatus();
  if (view === 'urls') loadUrls();
  if (view === 'analytics') loadAnalytics();
  if (view === 'db-logs') loadDbLogs();
  if (view === 'settings') loadConfig();
}

document.querySelectorAll('.nav-btn').forEach((btn) => {
  btn.addEventListener('click', () => navigateTo(btn.dataset.view));
});

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------
function classifyStatus(status) {
  if (!status || status === 'UNKNOWN' || status === 'Checking...' || status.includes('Pending')) return 'unknown';
  if (status === '200 OK' || status === 'UP') return 'up';
  if (status === 'SLOW') return 'slow';
  return 'down';
}

function relativeTime(ts) {
  if (!ts) return 'Never';
  try {
    const d = new Date(ts.replace(' ', 'T'));
    const diffMs = Date.now() - d.getTime();
    const diffS = Math.round(diffMs / 1000);
    if (diffS < 5)   return 'just now';
    if (diffS < 60)  return `${diffS}s ago`;
    const diffM = Math.round(diffS / 60);
    if (diffM < 60)  return `${diffM}m ago`;
    const diffH = Math.round(diffM / 60);
    if (diffH < 24)  return `${diffH}h ago`;
    return `${Math.round(diffH / 24)}d ago`;
  } catch { return ts; }
}

function downtimeDuration(downSince) {
  if (!downSince) return null;
  try {
    const d = new Date(downSince.replace(' ', 'T'));
    const diffS = Math.round((Date.now() - d.getTime()) / 1000);
    const h = Math.floor(diffS / 3600);
    const m = Math.floor((diffS % 3600) / 60);
    const s = diffS % 60;
    const parts = [];
    if (h > 0) parts.push(`${h}h`);
    if (m > 0 || h > 0) parts.push(`${m}m`);
    parts.push(`${s}s`);
    return parts.join(' ');
  } catch { return null; }
}

// ---------------------------------------------------------------------------
// Status grid (Overview)
// ---------------------------------------------------------------------------
async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    statusData = await res.json();
    renderStatusGrid();
    updateStats();
    $('lastRefreshLabel').textContent = `Last refreshed ${relativeTime(new Date().toISOString().replace('T', ' ').slice(0, 19))}`;
  } catch (err) {
    showToast('Failed to load status data', 'error');
    console.error(err);
  }
}

function renderStatusGrid() {
  const grid = $('statusGrid');
  const urls = Object.keys(statusData);

  if (urls.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <p class="empty-title">No check data yet</p>
        <p class="empty-sub">Click <strong>Run Check Now</strong> to perform the first health check.</p>
      </div>`;
    return;
  }

  grid.innerHTML = urls.map((url) => buildStatusCard(url, statusData[url])).join('');
}

function buildStatusCard(url, data) {
  const kind = classifyStatus(data.status);
  const pillLabels = { up: '200 OK', down: 'DOWN', slow: 'SLOW', unknown: 'UNKNOWN' };
  const label = (data.status && data.status !== 'UNKNOWN') ? data.status : pillLabels[kind];
  const downDur = (kind !== 'up' && kind !== 'unknown') ? downtimeDuration(data.down_since) : null;

  return `
    <div class="status-card card--${kind}" role="listitem">
      <div class="card-top">
        <div class="status-pill pill--${kind}">
          <span class="dot dot--${kind}"></span>
          ${escHtml(label)}
        </div>
      </div>
      <div class="card-url">${escHtml(url)}</div>
      <div class="card-meta">
        <div class="meta-row">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
          <span class="meta-label">Last check:</span>
          <span class="meta-value">${relativeTime(data.last_check)}</span>
        </div>
        ${downDur ? `
        <div class="meta-row">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <span class="meta-label">Down for:</span>
          <span class="meta-value" style="color:var(--danger)">${downDur}</span>
        </div>` : ''}
        ${data.down_since && kind === 'down' ? `
        <div class="meta-row">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          <span class="meta-label">Since:</span>
          <span class="meta-value">${escHtml(data.down_since)}</span>
        </div>` : ''}
      </div>
    </div>`;
}

function updateStats() {
  const entries = Object.values(statusData);
  const total = entries.length;
  let up = 0, down = 0, slow = 0;
  entries.forEach((d) => {
    const k = classifyStatus(d.status);
    if (k === 'up')   up++;
    else if (k === 'slow') slow++;
    else if (k === 'down') down++;
  });

  $('val-total').textContent = total;
  $('val-up').textContent    = up;
  $('val-down').textContent  = down;
  $('val-slow').textContent  = slow;

  // Show red badge on sidebar if something is down
  const badge = $('badge-down');
  if (down > 0) {
    badge.textContent = down;
    badge.style.display = 'flex';
  } else {
    badge.style.display = 'none';
  }
}

// ---------------------------------------------------------------------------
// URL manager
// ---------------------------------------------------------------------------
async function loadUrls() {
  try {
    const [urlRes, statusRes] = await Promise.all([
      fetch('/api/urls'),
      fetch('/api/status'),
    ]);
    urlList = await urlRes.json();
    statusData = await statusRes.json();
    renderUrlList();
  } catch (err) {
    showToast('Failed to load URL list', 'error');
    console.error(err);
  }
}

function renderUrlList() {
  const container = $('urlList');
  $('urlCountLabel').textContent = `${urlList.length} URL${urlList.length !== 1 ? 's' : ''}`;
  $('count-urls').textContent = urlList.length;

  if (urlList.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
        </div>
        <p class="empty-title">No URLs added yet</p>
        <p class="empty-sub">Use the form above to add your first monitored URL.</p>
      </div>`;
    return;
  }

  container.innerHTML = urlList.map((url) => {
    const d = statusData[url] || {};
    const kind = classifyStatus(d.status);
    const dotColors = { up: 'var(--success)', down: 'var(--danger)', slow: 'var(--warning)', unknown: 'var(--text-muted)' };
    const statusText = { up: '200 OK', down: 'DOWN', slow: 'SLOW', unknown: 'Unknown' };
    const statusColors = { up: 'color:var(--success)', down: 'color:var(--danger)', slow: 'color:var(--warning)', unknown: 'color:var(--text-muted)' };
    return `
      <div class="url-item" role="listitem">
        <span class="url-item-dot" style="background:${dotColors[kind]}"></span>
        <span class="url-item-text">${escHtml(url)}</span>
        <span class="url-item-status" style="${statusColors[kind]}">${statusText[kind]}</span>
        <button class="url-item-delete" aria-label="Remove ${escHtml(url)}" onclick="removeUrl('${escHtml(url).replace(/'/g, "\\'")}')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/>
            <path d="M9 6V4h6v2"/>
          </svg>
        </button>
      </div>`;
  }).join('');
}

async function addUrl() {
  const input = $('newUrlInput');
  const url = input.value.trim();
  if (!url) { showToast('Please enter a URL', 'error'); return; }
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    showToast('URL must start with http:// or https://', 'error'); return;
  }

  const btn = $('addUrlBtn');
  btn.disabled = true;

  try {
    const res = await fetch('/api/urls', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Failed to add URL', 'error'); return; }
    input.value = '';
    urlList = data.urls;
    renderUrlList();
    showToast(`Added: ${url}`, 'success');
  } catch (err) {
    showToast('Network error adding URL', 'error');
    console.error(err);
  } finally {
    btn.disabled = false;
  }
}

async function removeUrl(url) {
  try {
    const res = await fetch('/api/urls', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Failed to remove URL', 'error'); return; }
    urlList = data.urls;
    renderUrlList();
    showToast(`Removed: ${url}`, 'info');
  } catch (err) {
    showToast('Network error removing URL', 'error');
    console.error(err);
  }
}

// Add URL on Enter key
$('newUrlInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') addUrl();
});
$('addUrlBtn').addEventListener('click', addUrl);

// ---------------------------------------------------------------------------
// Config / Settings
// ---------------------------------------------------------------------------
const CONFIG_FIELDS = {
  heartbeat: ['CHECK_INTERVAL_SECONDS', 'CHECK_INTERVAL_MINUTES', 'REQUEST_TIMEOUT_SECONDS', 'SLOW_THRESHOLD_SECONDS'],
  email:     ['SMTP_SERVER', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'NOTIFICATION_RECEIVER'],
  voice:     ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM_NUMBER', 'TWILIO_TO_NUMBER', 'TWILIO_PLAY_URL'],
  storage:   ['SQLITE_DB_PATH', 'RETENTION_DAYS', 'GOOGLE_SHEET_ID', 'GOOGLE_CREDS_FILE'],
};

async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    configData = await res.json();
    populateConfig();
  } catch (err) {
    showToast('Failed to load configuration', 'error');
    console.error(err);
  }
}

function populateConfig() {
  Object.values(CONFIG_FIELDS).flat().forEach((key) => {
    const input = $(`cfg-${key}`);
    if (input && configData[key] !== undefined) {
      input.value = configData[key];
    }
  });
}

function enableEditConfig(section) {
  const fields = CONFIG_FIELDS[section] || [];
  fields.forEach((key) => {
    const input = $(`cfg-${key}`);
    if (input) input.disabled = false;
  });
  const editBtn = $(`edit-${section}`);
  const actions = $(`actions-${section}`);
  if (editBtn) editBtn.style.display = 'none';
  if (actions) actions.style.display = 'flex';
}

function cancelEditConfig(section) {
  populateConfig();
  const fields = CONFIG_FIELDS[section] || [];
  fields.forEach((key) => {
    const input = $(`cfg-${key}`);
    if (input) input.disabled = true;
  });
  const editBtn = $(`edit-${section}`);
  const actions = $(`actions-${section}`);
  if (editBtn) editBtn.style.display = '';
  if (actions) actions.style.display = 'none';
}

async function saveConfig(section) {
  const fields = CONFIG_FIELDS[section] || [];
  const updates = {};
  fields.forEach((key) => {
    const input = $(`cfg-${key}`);
    if (input) updates[key] = input.value.trim();
  });

  const btn = $(`save-${section}`);
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinning" style="display:inline-block;width:16px;height:16px">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg></span> Saving…`;

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Save failed', 'error'); return; }
    showToast('Settings saved successfully', 'success');
    Object.assign(configData, updates);

    // Lock fields after successful save
    fields.forEach((key) => {
      const input = $(`cfg-${key}`);
      if (input) input.disabled = true;
    });
    const editBtn = $(`edit-${section}`);
    const actions = $(`actions-${section}`);
    if (editBtn) editBtn.style.display = '';
    if (actions) actions.style.display = 'none';
  } catch (err) {
    showToast('Network error saving settings', 'error');
    console.error(err);
  } finally {
    setTimeout(() => { btn.disabled = false; btn.innerHTML = origHtml; }, 600);
  }
}

// Make functions accessible from HTML onclick
window.enableEditConfig = enableEditConfig;
window.cancelEditConfig = cancelEditConfig;
window.saveConfig = saveConfig;

// ---------------------------------------------------------------------------
// Settings tabs
// ---------------------------------------------------------------------------
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.tab === tab);
      b.setAttribute('aria-selected', b.dataset.tab === tab ? 'true' : 'false');
    });
    document.querySelectorAll('.tab-panel').forEach((panel) => {
      panel.style.display = panel.id === `tab-${tab}` ? '' : 'none';
    });
    if (tab === 'users') loadUsers();
  });
});

// ---------------------------------------------------------------------------
// Run Check Now (Server-Sent Events)
// ---------------------------------------------------------------------------
function runCheck() {
  // Open output panel
  const panel = $('outputPanel');
  panel.classList.add('open');
  panel.setAttribute('aria-hidden', 'false');

  const body = $('outputBody');
  const status = $('outputStatus');

  // Cancel any previous stream
  if (checkEventSource) { checkEventSource.close(); checkEventSource = null; }

  status.textContent = 'Running…';
  status.className = 'output-status running';

  const runBtn = $('runCheckBtn');
  runBtn.disabled = true;

  // Add separator line
  if (body.innerHTML) {
    const sep = el('span', 'output-line line--dim');
    sep.textContent = '─'.repeat(60);
    body.appendChild(sep);
  }

  // Timestamp header
  const header = el('span', 'output-line line--dim');
  header.textContent = `▶ Check started at ${new Date().toLocaleTimeString()}`;
  body.appendChild(header);
  body.scrollTop = body.scrollHeight;

  // POST triggers the SSE stream
  fetch('/api/run-check', { method: 'POST' }).then((res) => {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    function processChunk(chunk) {
      buffer += chunk;
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete last line
      lines.forEach((line) => {
        if (!line.startsWith('data: ')) return;
        const text = line.slice(6);
        if (text === '__DONE__') {
          status.textContent = 'Done';
          status.className = 'output-status';
          runBtn.disabled = false;
          return;
        }
        appendOutputLine(text);
      });
    }

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) {
          status.textContent = 'Done';
          status.className = 'output-status';
          runBtn.disabled = false;
          // Refresh status after check
          setTimeout(() => loadStatus(), 1000);
          return;
        }
        processChunk(decoder.decode(value, { stream: true }));
        read();
      }).catch((err) => {
        appendOutputLine(`❌ Stream error: ${err}`);
        status.textContent = 'Error';
        status.className = 'output-status';
        runBtn.disabled = false;
      });
    }
    read();
  }).catch((err) => {
    appendOutputLine(`❌ Failed to start check: ${err}`);
    status.textContent = 'Error';
    status.className = 'output-status';
    runBtn.disabled = false;
  });
}

function appendOutputLine(text) {
  const body = $('outputBody');
  const line = el('span', 'output-line');

  // Colorize based on content
  if (/\bERROR\b|❌|DOWN|ALERT/.test(text)) line.classList.add('line--error');
  else if (/✅|BACK ONLINE|UP|200 OK|success/i.test(text)) line.classList.add('line--ok');
  else if (/SLOW|WARN|⚠/i.test(text))  line.classList.add('line--warn');
  else if (/^---/.test(text))           line.classList.add('line--dim');

  line.textContent = text;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

$('runCheckBtn').addEventListener('click', runCheck);

$('closeOutputBtn').addEventListener('click', () => {
  $('outputPanel').classList.remove('open');
  $('outputPanel').setAttribute('aria-hidden', 'true');
});

$('clearOutputBtn').addEventListener('click', () => {
  $('outputBody').innerHTML = '';
});

// ---------------------------------------------------------------------------
// Refresh button (manual)
// ---------------------------------------------------------------------------
$('refreshBtn').addEventListener('click', async () => {
  const btn = $('refreshBtn');
  const icon = btn.querySelector('svg');
  if (icon) icon.classList.add('spinning');
  btn.disabled = true;
  await loadStatus();
  setTimeout(() => {
    if (icon) icon.classList.remove('spinning');
    btn.disabled = false;
  }, 600);
});

// ---------------------------------------------------------------------------
// Auto-refresh
// ---------------------------------------------------------------------------
let autoRefreshSec = 15;
let countdownSec = 15;
let countdownTimer = null;

function startAutoRefresh() {
  if (countdownTimer) clearInterval(countdownTimer);
  countdownSec = autoRefreshSec;
  updateRefreshUI();

  if (autoRefreshSec <= 0) return;

  countdownTimer = setInterval(() => {
    countdownSec--;
    if (countdownSec <= 0) {
      countdownSec = autoRefreshSec;
      triggerAutoRefresh();
    }
    updateRefreshUI();
  }, 1000);
}

function triggerAutoRefresh() {
  const overviewActive = $('nav-overview')?.classList.contains('active');
  const analyticsActive = $('nav-analytics')?.classList.contains('active');

  if (overviewActive) {
    loadStatus();
  } else if (analyticsActive) {
    loadAnalytics();
  }
}

function updateRefreshUI() {
  const label = $('refreshLabel');
  if (!label) return;
  if (autoRefreshSec <= 0) {
    label.textContent = 'Auto-refresh: Off';
  } else {
    label.textContent = `Auto-refresh: ${autoRefreshSec}s (${countdownSec}s)`;
  }
}

// ---------------------------------------------------------------------------
// Password toggle
// ---------------------------------------------------------------------------
function togglePwd(inputId, btn) {
  const input = $(inputId);
  if (!input) return;
  const isPass = input.type === 'password';
  input.type = isPass ? 'text' : 'password';
  btn.innerHTML = isPass
    ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
         <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
         <line x1="1" y1="1" x2="23" y2="23"/>
       </svg>`
    : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
         <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
       </svg>`;
}
window.togglePwd = togglePwd;

// ---------------------------------------------------------------------------
// Toast notifications
// ---------------------------------------------------------------------------
const TOAST_ICONS = {
  success: `<svg class="toast-icon success" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>`,
  error:   `<svg class="toast-icon error" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  info:    `<svg class="toast-icon info" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
};

function showToast(message, type = 'info', duration = 3500) {
  const container = $('toastContainer');
  const toast = el('div', `toast toast--${type}`);
  toast.innerHTML = `${TOAST_ICONS[type] || ''}<span>${escHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast--out');
    setTimeout(() => toast.remove(), 280);
  }, duration);
}

// ---------------------------------------------------------------------------
// Analytics & Charts
// ---------------------------------------------------------------------------
async function loadAnalytics() {
  try {
    const res = await fetch('/api/latency');
    rawLatencyData = await res.json();
    filterAndRenderCharts();
  } catch (err) {
    showToast('Failed to load latency analytics', 'error');
    console.error(err);
  }
}

function filterAndRenderCharts() {
  const preset = $('timeRangePreset').value;
  const customGroup = $('customTimeGroup');

  let cutoffMs = 0;

  if (preset === 'custom') {
    customGroup.style.display = 'flex';
    const val = parseInt($('customTimeValue').value) || 1;
    const unit = $('customTimeUnit').value;
    const hours = unit === 'days' ? val * 24 : val;
    cutoffMs = hours * 60 * 60 * 1000;
  } else {
    customGroup.style.display = 'none';
    const mapping = {
      '1h': 1 * 60 * 60 * 1000,
      '8h': 8 * 60 * 60 * 1000,
      '12h': 12 * 60 * 60 * 1000,
      '24h': 24 * 60 * 60 * 1000,
      '3d': 3 * 24 * 60 * 60 * 1000,
      '7d': 7 * 24 * 60 * 60 * 1000,
      'all': Infinity
    };
    cutoffMs = mapping[preset] || (24 * 60 * 60 * 1000);
  }

  const now = Date.now();
  const filteredData = {};

  Object.keys(rawLatencyData).forEach((url) => {
    const history = rawLatencyData[url] || [];
    if (cutoffMs === Infinity) {
      filteredData[url] = history;
    } else {
      filteredData[url] = history.filter((item) => {
        const itemTime = new Date(item.timestamp.replace(' ', 'T')).getTime();
        return (now - itemTime) <= cutoffMs;
      });
    }
  });

  renderCharts(filteredData);
}

function renderCharts(data) {
  const container = $('chartsContainer');
  const urls = Object.keys(data);

  // Destroy old charts to prevent memory leaks
  Object.values(chartInstances).forEach((chart) => chart.destroy());
  chartInstances = {};

  if (urls.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
          </svg>
        </div>
        <p class="empty-title">No latency data logged yet</p>
        <p class="empty-sub">Run a few checks using the <strong>Run Check Now</strong> button to generate graphs.</p>
      </div>`;
    return;
  }

  container.innerHTML = urls.map((url, idx) => {
    const safeId = `chart-canvas-${idx}`;
    return `
      <div class="chart-card">
        <div class="chart-card-header">
          <h4 class="chart-card-title">${escHtml(url)}</h4>
          <span class="chart-card-meta" id="chart-meta-${idx}">Loading stats...</span>
        </div>
        <div class="chart-wrapper">
          <canvas id="${safeId}"></canvas>
        </div>
      </div>`;
  }).join('');

  urls.forEach((url, idx) => {
    const safeId = `chart-canvas-${idx}`;
    const history = data[url] || [];

    // Calculate stats
    const validLatencies = history.map(h => h.latency_ms).filter(l => l !== null);
    let avgText = 'N/A';
    let maxText = 'N/A';
    if (validLatencies.length > 0) {
      const avg = validLatencies.reduce((a, b) => a + b, 0) / validLatencies.length;
      const max = Math.max(...validLatencies);
      avgText = `${avg.toFixed(1)}ms`;
      maxText = `${max.toFixed(1)}ms`;
    }
    $(`chart-meta-${idx}`).textContent = `Checks: ${history.length} · Avg Latency: ${avgText} · Peak: ${maxText}`;

    // Format chart labels and datasets
    const labels = history.map(h => {
      const parts = h.timestamp.split(' ');
      return parts[1] || h.timestamp;
    });

    const chartData = history.map(h => h.latency_ms);
    const canvas = $(safeId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Dynamic point and line segment status coloring (Green for OK, Red for Down/Timeout)
    const statuses = history.map(h => String(h.status || h.status_desc || (h.status_code === 200 ? '200 OK' : 'Error')));
    const pointColors = statuses.map(st => {
      if (st.includes('200') || st === 'UP' || st.includes('OK')) {
        return '#10b981'; // Emerald Green for OK
      }
      return '#ef4444'; // Bright Red for Down / Timeout / Error
    });

    const gradient = ctx.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, 'rgba(16, 185, 129, 0.25)');
    gradient.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

    chartInstances[url] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Response Time (ms)',
          data: chartData,
          borderColor: '#10b981',
          segment: {
            borderColor: ctx => {
              const idx = ctx.p1DataIndex;
              const st = statuses[idx] || '';
              return (st.includes('200') || st === 'UP' || st.includes('OK')) ? '#10b981' : '#ef4444';
            },
            backgroundColor: ctx => {
              const idx = ctx.p1DataIndex;
              const st = statuses[idx] || '';
              return (st.includes('200') || st === 'UP' || st.includes('OK')) ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.25)';
            }
          },
          borderWidth: 2,
          pointBackgroundColor: pointColors,
          pointBorderColor: pointColors,
          pointBorderWidth: 1.5,
          pointRadius: 3.5,
          pointHoverRadius: 6,
          fill: true,
          backgroundColor: gradient,
          tension: 0.35
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0d1427',
            titleColor: '#f1f5f9',
            bodyColor: '#94a3b8',
            borderColor: 'rgba(255,255,255,0.08)',
            borderWidth: 1,
            padding: 10,
            cornerRadius: 8,
            displayColors: false,
            callbacks: {
              label: function(context) {
                const val = context.parsed.y;
                const item = history[context.dataIndex] || {};
                if (val === null || isNaN(val)) return `Status: ${item.status || 'Timeout/Error'}`;
                return `Latency: ${val.toFixed(1)} ms (${item.status || 'OK'})`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.02)' },
            ticks: {
              color: '#475569',
              font: { size: 10 },
              maxTicksLimit: 12
            }
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.04)' },
            ticks: {
              color: '#475569',
              font: { size: 10 },
              callback: function(value) { return value + ' ms'; }
            },
            suggestedMin: 0
          }
        }
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Security: escape HTML
// ---------------------------------------------------------------------------
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Daemon management
// ---------------------------------------------------------------------------
let isDaemonActive = false;

async function checkDaemonStatus() {
  try {
    const res = await fetch('/api/daemon');
    const data = await res.json();
    isDaemonActive = !!data.running;
    updateDaemonUI(isDaemonActive);
  } catch (err) {
    console.error('Failed to get daemon status:', err);
    updateDaemonUI(null);
  }
}

function updateDaemonUI(active) {
  const badge = $('daemonStatusBadge');
  const dot = $('daemonStatusDot');
  const text = $('daemonStatusText');
  const btn = $('toggleDaemonBtn');

  if (!badge || !dot || !text || !btn) return;

  btn.disabled = false;

  if (active === null) {
    badge.className = 'status-pill pill--unknown';
    dot.className = 'dot dot--unknown';
    text.textContent = 'Daemon: Error';
    btn.textContent = 'Start Daemon';
    btn.className = 'btn btn-ghost btn-sm';
    return;
  }

  isDaemonActive = active;

  if (active) {
    badge.className = 'status-pill pill--up';
    dot.className = 'dot dot--up';
    text.textContent = 'Daemon: Active';
    btn.textContent = 'Stop Daemon';
    btn.className = 'btn btn-danger btn-sm';
  } else {
    badge.className = 'status-pill pill--down';
    dot.className = 'dot dot--down';
    text.textContent = 'Daemon: Inactive';
    btn.textContent = 'Start Daemon';
    btn.className = 'btn btn-primary btn-sm';
    btn.style.boxShadow = 'none'; // Keep header looking clean
  }
}

async function toggleDaemon() {
  const btn = $('toggleDaemonBtn');
  if (!btn) return;
  btn.disabled = true;
  const endpoint = isDaemonActive ? '/api/daemon/stop' : '/api/daemon/start';
  const actionName = isDaemonActive ? 'Stopping' : 'Starting';

  showToast(`${actionName} monitor daemon…`, 'info');

  try {
    const res = await fetch(endpoint, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Server error');

    showToast(isDaemonActive ? 'Monitor daemon stopped' : 'Monitor daemon started', 'success');
    checkDaemonStatus();
  } catch (err) {
    showToast(`Failed to ${isDaemonActive ? 'stop' : 'start'} daemon: ${err.message}`, 'error');
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
function init() {
  // Check session authentication
  checkAuthStatus();

  // Default view
  navigateTo('overview');
  startAutoRefresh();

  // Daemon setup
  checkDaemonStatus();
  $('toggleDaemonBtn')?.addEventListener('click', toggleDaemon);
  setInterval(checkDaemonStatus, 10_000);

  // Time range filters for analytics
  $('timeRangePreset')?.addEventListener('change', filterAndRenderCharts);
  $('customTimeValue')?.addEventListener('input', filterAndRenderCharts);
  $('customTimeUnit')?.addEventListener('change', filterAndRenderCharts);

  // Database logs filters
  $('dbLogDomainFilter')?.addEventListener('change', applyDbLogFilters);
  $('dbLogStatusFilter')?.addEventListener('change', applyDbLogFilters);
  $('dbLogSearchInput')?.addEventListener('input', applyDbLogFilters);
  $('dbLogTimeFilter')?.addEventListener('change', applyDbLogFilters);

  // Auto-refresh selector
  const refreshSelect = $('autoRefreshSelect');
  if (refreshSelect) {
    refreshSelect.addEventListener('change', (e) => {
      autoRefreshSec = parseInt(e.target.value, 10);
      startAutoRefresh();
    });
  }
}

// ---------------------------------------------------------------------------
// Database Logs View
// ---------------------------------------------------------------------------
let rawDbLogs = [];
let filteredDbLogs = [];
let currentLogsPage = 1;
const LOGS_PER_PAGE = 25;

async function loadDbLogs() {
  try {
    const res = await fetch('/api/db-logs?limit=2000');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to fetch logs');
    rawDbLogs = data.logs || [];
    populateDbLogDomainFilter();
    applyDbLogFilters();
  } catch (err) {
    console.error('Error loading DB logs:', err);
    const tbody = $('dbLogsTableBody');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="8" style="padding:24px;text-align:center;color:var(--color-down);">❌ Error loading database logs: ${err.message}</td></tr>`;
    }
  }
}

function populateDbLogDomainFilter() {
  const domainSelect = $('dbLogDomainFilter');
  if (!domainSelect) return;
  const currentVal = domainSelect.value;
  const domains = Array.from(new Set(rawDbLogs.map(l => l.domain).filter(Boolean))).sort();
  
  domainSelect.innerHTML = '<option value="all">All Domains</option>';
  domains.forEach(domain => {
    const opt = document.createElement('option');
    opt.value = domain;
    opt.textContent = domain;
    domainSelect.appendChild(opt);
  });
  if (domains.includes(currentVal)) {
    domainSelect.value = currentVal;
  }
}

function applyDbLogFilters() {
  const domainFilter = $('dbLogDomainFilter')?.value || 'all';
  const statusFilter = $('dbLogStatusFilter')?.value || 'all';
  const searchFilter = ($('dbLogSearchInput')?.value || '').toLowerCase().trim();
  const timeFilter = $('dbLogTimeFilter')?.value || '24h';

  const now = Date.now();
  let timeCutoff = 0;
  if (timeFilter === '1h') timeCutoff = now - 3600 * 1000;
  else if (timeFilter === '8h') timeCutoff = now - 8 * 3600 * 1000;
  else if (timeFilter === '24h') timeCutoff = now - 24 * 3600 * 1000;
  else if (timeFilter === '7d') timeCutoff = now - 7 * 24 * 3600 * 1000;

  filteredDbLogs = rawDbLogs.filter(item => {
    // Time filter
    if (timeCutoff > 0) {
      const itemTime = new Date(item.timestamp).getTime();
      if (!isNaN(itemTime) && itemTime < timeCutoff) return false;
    }
    // Domain filter
    if (domainFilter !== 'all' && item.domain !== domainFilter) return false;
    // Status filter
    if (statusFilter === '200' && item.status_code !== 200) return false;
    if (statusFilter === 'error' && (item.status_code === 200 || item.status_desc === 'Timeout' || item.status_desc === 'SLOW')) return false;
    if (statusFilter === 'timeout' && item.status_desc !== 'Timeout') return false;
    if (statusFilter === 'slow' && item.speed_rating !== 'SLOW' && item.status_desc !== 'SLOW') return false;
    // Search text filter
    if (searchFilter) {
      const matchUrl = (item.website_url || '').toLowerCase().includes(searchFilter);
      const matchStatus = (item.status_desc || '').toLowerCase().includes(searchFilter);
      const matchDomain = (item.domain || '').toLowerCase().includes(searchFilter);
      if (!matchUrl && !matchStatus && !matchDomain) return false;
    }
    return true;
  });

  currentLogsPage = 1;
  renderDbLogsTable();
}

function renderDbLogsTable() {
  const tbody = $('dbLogsTableBody');
  const countInfo = $('dbLogsCountInfo');
  const pageIndicator = $('dbLogsPageIndicator');
  const prevBtn = $('btnPrevLogsPage');
  const nextBtn = $('btnNextLogsPage');

  if (!tbody) return;

  const total = filteredDbLogs.length;
  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="padding:32px;text-align:center;color:var(--text-secondary);">No matching database logs found.</td></tr>`;
    if (countInfo) countInfo.textContent = 'Showing 0 of 0 logs';
    if (pageIndicator) pageIndicator.textContent = 'Page 1 of 1';
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    return;
  }

  const totalPages = Math.ceil(total / LOGS_PER_PAGE);
  if (currentLogsPage > totalPages) currentLogsPage = totalPages;
  if (currentLogsPage < 1) currentLogsPage = 1;

  const startIdx = (currentLogsPage - 1) * LOGS_PER_PAGE;
  const pageItems = filteredDbLogs.slice(startIdx, startIdx + LOGS_PER_PAGE);

  tbody.innerHTML = pageItems.map(item => {
    let statusBadgeClass = 'pill--up';
    let statusLabel = item.status_desc || (item.status_code ? `${item.status_code}` : 'OK');
    if (item.status_code !== 200 || item.status_desc === 'Timeout') {
      statusBadgeClass = 'pill--down';
    } else if (item.speed_rating === 'SLOW' || item.status_desc === 'SLOW') {
      statusBadgeClass = 'pill--unknown';
    }

    const latencyStr = item.response_time_ms != null ? `${parseFloat(item.response_time_ms).toFixed(1)} ms` : '—';
    const alertSentBadge = item.notification_sent 
      ? `<span class="status-pill pill--down" style="padding:2px 8px;font-size:0.7rem;">Yes</span>` 
      : `<span style="color:var(--text-secondary);font-size:0.75rem;">No</span>`;

    return `<tr style="border-bottom:1px solid var(--border);transition:background 0.15s ease;">
      <td style="padding:10px 16px;color:var(--text-secondary);font-weight:500;">#${item.id}</td>
      <td style="padding:10px 16px;white-space:nowrap;font-size:0.8rem;color:var(--text-secondary);">${item.timestamp}</td>
      <td style="padding:10px 16px;font-weight:600;color:var(--text-main);max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${item.website_url}">${item.website_url}</td>
      <td style="padding:10px 16px;color:var(--text-secondary);">${item.domain}</td>
      <td style="padding:10px 16px;">
        <span class="status-pill ${statusBadgeClass}" style="padding:3px 10px;font-size:0.75rem;display:inline-flex;align-items:center;gap:4px;">
          ${statusLabel}
        </span>
      </td>
      <td style="padding:10px 16px;font-weight:500;color:var(--text-main);">${latencyStr}</td>
      <td style="padding:10px 16px;font-size:0.75rem;color:var(--text-secondary);">${item.speed_rating || '—'}</td>
      <td style="padding:10px 16px;">${alertSentBadge}</td>
    </tr>`;
  }).join('');

  if (countInfo) countInfo.textContent = `Showing ${startIdx + 1}–${Math.min(startIdx + LOGS_PER_PAGE, total)} of ${total} logs`;
  if (pageIndicator) pageIndicator.textContent = `Page ${currentLogsPage} of ${totalPages}`;
  if (prevBtn) prevBtn.disabled = currentLogsPage <= 1;
  if (nextBtn) nextBtn.disabled = currentLogsPage >= totalPages;
}

function changeLogsPage(delta) {
  currentLogsPage += delta;
  renderDbLogsTable();
}

function exportLogs(format) {
  if (filteredDbLogs.length === 0) {
    showToast('No logs available to export', 'warning');
    return;
  }

  const dateStr = new Date().toISOString().slice(0, 10);
  if (format === 'json') {
    const jsonStr = JSON.stringify(filteredDbLogs, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `monitor_logs_${dateStr}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Exported logs as JSON', 'success');
  } else {
    // CSV export
    const headers = ['ID', 'Timestamp', 'Website URL', 'Domain', 'Status Code', 'Status Description', 'Response Time (ms)', 'Speed Rating', 'Notification Sent'];
    const rows = filteredDbLogs.map(item => [
      item.id,
      `"${item.timestamp}"`,
      `"${item.website_url}"`,
      `"${item.domain}"`,
      item.status_code,
      `"${item.status_desc}"`,
      item.response_time_ms != null ? item.response_time_ms : '',
      `"${item.speed_rating || ''}"`,
      item.notification_sent ? 'Yes' : 'No'
    ]);
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `monitor_logs_${dateStr}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Exported logs as CSV', 'success');
  }
}

// Make accessible to HTML onclick
window.changeLogsPage = changeLogsPage;
window.exportLogs = exportLogs;
window.loadDbLogs = loadDbLogs;

// ---------------------------------------------------------------------------
// Authentication & User Management Logic
// ---------------------------------------------------------------------------
let currentUser = null;

async function checkAuthStatus() {
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    if (res.ok && data.authenticated && data.user) {
      currentUser = data.user;
      showAppScreen(currentUser);
      return true;
    } else {
      showLoginScreen();
      return false;
    }
  } catch (err) {
    console.error('Auth check error:', err);
    showLoginScreen();
    return false;
  }
}

function resetSettingsTabs() {
  document.querySelectorAll('.tab-btn').forEach((b) => {
    const isHeartbeat = b.dataset.tab === 'heartbeat';
    b.classList.toggle('active', isHeartbeat);
    b.setAttribute('aria-selected', isHeartbeat ? 'true' : 'false');
  });
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.style.display = panel.id === 'tab-heartbeat' ? '' : 'none';
  });
}

function showLoginScreen() {
  const overlay = $('loginOverlay');
  if (overlay) overlay.style.display = 'flex';
  const sidebarGroup = $('sidebarUserGroup');
  if (sidebarGroup) sidebarGroup.style.display = 'none';
  resetSettingsTabs();
}

function showAppScreen(user) {
  const overlay = $('loginOverlay');
  if (overlay) overlay.style.display = 'none';

  const sidebarGroup = $('sidebarUserGroup');
  const nameLabel = $('userNameLabel');
  const userTabBtn = $('tab-btn-users');

  if (sidebarGroup) sidebarGroup.style.display = 'flex';
  if (nameLabel) nameLabel.textContent = `${user.username} (${user.role})`;

  if (userTabBtn) {
    userTabBtn.style.display = user.role === 'superadmin' ? '' : 'none';
  }

  // Always reset navigation to Overview page on login
  navigateTo('overview');
  resetSettingsTabs();
}

// ---------------------------------------------------------------------------
// Change Password Modal Handlers
// ---------------------------------------------------------------------------

function openChangePasswordModal() {
  const modal = $('changePwdModal');
  const alertBox = $('changePwdAlert');
  if (alertBox) alertBox.style.display = 'none';
  if ($('currPasswordInput')) $('currPasswordInput').value = '';
  if ($('newPwdInput')) $('newPwdInput').value = '';
  if ($('confirmPwdInput')) $('confirmPwdInput').value = '';
  if (modal) modal.style.display = 'flex';
}

function closeChangePasswordModal() {
  const modal = $('changePwdModal');
  if (modal) modal.style.display = 'none';
}

async function submitChangePassword() {
  const currPwd = $('currPasswordInput')?.value.trim();
  const newPwd = $('newPwdInput')?.value.trim();
  const confirmPwd = $('confirmPwdInput')?.value.trim();
  const alertBox = $('changePwdAlert');
  const btn = $('changePwdSubmitBtn');

  if (!currPwd || !newPwd || !confirmPwd) {
    showModalAlert('Please fill in all password fields.', false);
    return;
  }
  if (newPwd !== confirmPwd) {
    showModalAlert('New passwords do not match.', false);
    return;
  }
  if (newPwd.length < 4) {
    showModalAlert('Password must be at least 4 characters long.', false);
    return;
  }

  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currPwd, new_password: newPwd })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to change password');

    showToast('Password changed successfully!', 'success');
    closeChangePasswordModal();
  } catch (err) {
    showModalAlert(err.message, false);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function showModalAlert(msg, isSuccess) {
  const alertBox = $('changePwdAlert');
  if (!alertBox) return;
  alertBox.textContent = msg;
  alertBox.style.display = 'block';
  alertBox.style.background = isSuccess ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)';
  alertBox.style.border = isSuccess ? '1px solid rgba(16,185,129,0.3)' : '1px solid rgba(239,68,68,0.3)';
  alertBox.style.color = isSuccess ? '#10b981' : '#ef4444';
}

window.openChangePasswordModal = openChangePasswordModal;
window.closeChangePasswordModal = closeChangePasswordModal;
window.submitChangePassword = submitChangePassword;

async function handleLogin() {
  const uInput = $('loginUsername');
  const pInput = $('loginPassword');
  const errBox = $('loginErrorAlert');
  const btn = $('loginSubmitBtn');

  if (!uInput || !pInput) return;
  const username = uInput.value.trim();
  const password = pInput.value.trim();

  if (!username || !password) {
    if (errBox) {
      errBox.textContent = 'Please enter both username and password.';
      errBox.style.display = 'block';
    }
    return;
  }

  if (btn) btn.disabled = true;
  if (errBox) errBox.style.display = 'none';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Login failed');

    currentUser = data.user;
    showAppScreen(currentUser);
    showToast(`Welcome back, ${currentUser.username}!`, 'success');
    loadStatus();
  } catch (err) {
    if (errBox) {
      errBox.textContent = err.message || 'Invalid username or password.';
      errBox.style.display = 'block';
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
    currentUser = null;
    showToast('Logged out successfully', 'info');
    showLoginScreen();
  } catch (err) {
    console.error('Logout error:', err);
    showLoginScreen();
  }
}

// User Management (Superadmin)
async function loadUsers() {
  if (!currentUser || currentUser.role !== 'superadmin') return;
  try {
    const res = await fetch('/api/users');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to load users');
    renderUsersTable(data.users || []);
  } catch (err) {
    console.error('Error loading users:', err);
  }
}

function renderUsersTable(users) {
  const tbody = $('usersTableBody');
  if (!tbody) return;

  if (users.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="padding:16px;text-align:center;color:var(--text-secondary);">No user accounts found.</td></tr>`;
    return;
  }

  tbody.innerHTML = users.map(u => {
    const isSuper = u.username === 'superadmin';
    const deleteBtn = isSuper 
      ? `<span style="color:var(--text-secondary);font-size:0.75rem;">Protected</span>`
      : `<button class="btn btn-ghost btn-sm" onclick="deleteUserAccount('${u.username}')" style="color:var(--danger,#ef4444);padding:4px 8px;font-size:0.75rem;">Delete</button>`;

    return `<tr style="border-bottom:1px solid var(--border);">
      <td style="padding:10px 14px;color:var(--text-secondary);">#${u.id}</td>
      <td style="padding:10px 14px;font-weight:600;color:var(--text-main);">${u.username}</td>
      <td style="padding:10px 14px;"><span class="status-pill ${u.role === 'superadmin' ? 'pill--up' : 'pill--unknown'}" style="padding:2px 8px;font-size:0.72rem;">${u.role}</span></td>
      <td style="padding:10px 14px;color:var(--text-secondary);font-size:0.8rem;">${u.created_at}</td>
      <td style="padding:10px 14px;text-align:right;">${deleteBtn}</td>
    </tr>`;
  }).join('');
}

async function createNewUserAccount() {
  const uInput = $('newUsernameInput');
  const pInput = $('newPasswordInput');
  const rSelect = $('newRoleSelect');

  if (!uInput || !pInput) return;
  const username = uInput.value.trim();
  const password = pInput.value.trim();
  const role = rSelect ? rSelect.value : 'admin';

  if (!username || !password) {
    showToast('Username and password are required', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, role })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to create user');

    showToast(`User '${username}' created successfully!`, 'success');
    uInput.value = '';
    pInput.value = '';
    loadUsers();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteUserAccount(username) {
  if (!confirm(`Are you sure you want to delete user account '${username}'?`)) return;

  try {
    const res = await fetch(`/api/users/${username}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to delete user');

    showToast(`User '${username}' deleted`, 'info');
    loadUsers();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

window.handleLogin = handleLogin;
window.handleLogout = handleLogout;
window.createNewUserAccount = createNewUserAccount;
window.deleteUserAccount = deleteUserAccount;

document.addEventListener('DOMContentLoaded', init);
