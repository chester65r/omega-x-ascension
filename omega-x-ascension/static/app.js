// OMEGA-X ASCENSION Dashboard
(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);
  let token = sessionStorage.getItem('omega-jwt') || '';
  let apiBase = localStorage.getItem('omega-api-base') || '';
  let pollTimer = null;
  let runPollTimer = null;
  let browserHistory = [];
  let browserHistoryIdx = -1;
  const startTime = Date.now();

  function setConnected(connected) {
    const badge = $('#conn-status');
    badge.innerHTML = '<span class="status-dot"></span> ' + (connected ? 'Connected' : 'Disconnected');
    badge.className = 'status-badge ' + (connected ? 'connected' : 'disconnected');
  }

  function normalizeApiBase(value) {
    const parsed = new URL(value.trim());
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
      throw new Error('Use a valid HTTP or HTTPS server URL without login details.');
    }
    return parsed.origin + parsed.pathname.replace(/\/+$/, '');
  }

  async function apiFetch(path, options = {}) {
    if (!apiBase) throw new Error('Save your API server URL first.');
    return fetch(apiBase + (path.startsWith('/') ? path : '/' + path), options);
  }

  $('#api-base').value = apiBase;
  $('#save-server-btn').addEventListener('click', () => {
    try {
      apiBase = normalizeApiBase($('#api-base').value);
      localStorage.setItem('omega-api-base', apiBase);
      $('#api-base').value = apiBase;
      startPolling();
      if (token) loadRuns();
    } catch (e) { alert(e.message || 'Enter a valid API server URL.'); }
  });

  $('#jwt-token').value = token;
  setConnected(false);
  $('#connect-btn').addEventListener('click', () => {
    token = $('#jwt-token').value.trim();
    if (!token) {
      sessionStorage.removeItem('omega-jwt');
      setConnected(false);
      alert('Paste a signed JWT token first.');
      return;
    }
    if (!apiBase) {
      alert('Save your API server URL first.');
      return;
    }
    sessionStorage.setItem('omega-jwt', token);
    setConnected(true);
    startPolling();
    loadRuns();
  });

  function authHeaders() {
    return token ? { Authorization: 'Bearer ' + token } : {};
  }

  async function api(path, opts = {}) {
    const res = await apiFetch(path, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`${res.status}: ${body}`);
    }
    return res;
  }

  // Main navigation
  function activateTab(name) {
    const target = $('#' + name);
    if (!target || !target.classList.contains('tab-content')) return;
    $$('.tab').forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle('active', active);
      if (active) tab.setAttribute('aria-current', 'page');
      else tab.removeAttribute('aria-current');
    });
    $$('.tab-content').forEach((panel) => panel.classList.toggle('active', panel.id === name));
    target.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }
  $$('.tab').forEach((tab) => tab.addEventListener('click', () => activateTab(tab.dataset.tab)));
  $$('[data-go-tab]').forEach((button) => button.addEventListener('click', () => activateTab(button.dataset.goTab)));

  // Overview
  async function pollHealth() {
    try {
      const response = await apiFetch('/health/live');
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const live = await response.json();
      $('#health-live').textContent = live.status === 'ok' ? 'Online' : 'Error';
      $('#card-live').className = 'card stat-card ' + (live.status === 'ok' ? 'ok' : 'err');
    } catch {
      $('#health-live').textContent = 'Offline';
      $('#card-live').className = 'card stat-card err';
    }
    try {
      const response = await apiFetch('/health/ready');
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const ready = await response.json();
      if (ready.status === 'ready') {
        $('#health-ready').textContent = 'Ready';
        $('#card-ready').className = 'card stat-card ok';
        $('#model-count').textContent = ready.configured_models ?? 0;
        loadModels();
      } else {
        $('#health-ready').textContent = 'Waiting';
        $('#card-ready').className = 'card stat-card err';
        $('#model-count').textContent = ready.configured_models ?? 0;
      }
    } catch {
      $('#health-ready').textContent = 'Offline';
      $('#card-ready').className = 'card stat-card err';
      $('#model-count').textContent = '--';
    }
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const m = Math.floor(elapsed / 60), s = elapsed % 60;
    $('#uptime').textContent = `${m}m ${s}s`;
  }

  async function loadModels() {
    try {
      const response = await apiFetch('/health/ready');
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const ready = await response.json();
      const count = ready.configured_models ?? 0;
      const list = $('#models-list');
      if (count === 0) {
        list.innerHTML = '<div class="empty-state">No model providers are configured.</div>';
        return;
      }
      list.innerHTML = '';
      const item = document.createElement('div');
      item.className = 'model-item';
      const name = document.createElement('div');
      name.className = 'model-name';
      name.textContent = count + (count === 1 ? ' provider configured' : ' providers configured');
      const url = document.createElement('div');
      url.className = 'model-url';
      url.textContent = 'Provider endpoints are configured on the server.';
      item.append(name, url);
      list.appendChild(item);
    } catch {
      $('#models-list').innerHTML = '<div class="empty-state">Unable to read model status. Check the API server.</div>';
    }
  }

  async function loadMetrics() {
    try {
      const res = await apiFetch('/metrics');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const content = await res.text();
      const lines = content.split('\n').filter((line) => line && !line.startsWith('#')).slice(0, 30);
      $('#metrics').textContent = lines.length ? lines.join('\n') : 'No metrics reported yet.';
    } catch {
      $('#metrics').textContent = apiBase ? 'Metrics unavailable. Verify the server connection.' : 'Save your API server URL to view metrics.';
    }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    if (!apiBase) {
      $('#health-live').textContent = 'Set URL';
      $('#health-ready').textContent = 'Set URL';
      $('#models-list').innerHTML = '<div class="empty-state">Save your API server URL to inspect model status.</div>';
      $('#metrics').textContent = 'Waiting for server configuration.';
      return;
    }
    pollHealth();
    loadMetrics();
    pollTimer = setInterval(() => { pollHealth(); loadMetrics(); }, 10000);
  }

  // Runs
  let selectedRunId = null;

  async function loadRuns() {
    if (!token) {
      $('#runs-list').innerHTML = '<div class="empty-state">Connect with a signed JWT to manage runs.</div>';
      return;
    }
    const runs = JSON.parse(sessionStorage.getItem('omega-runs') || '[]');
    const list = $('#runs-list');
    if (runs.length === 0) {
      list.innerHTML = '<div class="empty-state">No runs in this session yet. Create your first task.</div>';
      return;
    }
    list.innerHTML = '';
    for (const run of runs) {
      const item = document.createElement('div');
      item.className = 'run-item' + (run.id === selectedRunId ? ' active' : '');
      const id = document.createElement('div');
      id.className = 'run-id';
      id.textContent = String(run.id).substring(0, 8);
      const goal = document.createElement('div');
      goal.className = 'run-goal';
      goal.textContent = String(run.goal || '').substring(0, 120);
      const status = document.createElement('span');
      status.className = 'run-status ' + String(run.status || 'pending').replace(/[^a-z_]/g, '');
      status.textContent = String(run.status || 'pending').replace(/_/g, ' ');
      item.append(id, goal, status);
      item.addEventListener('click', () => { selectedRunId = run.id; loadRunDetail(run.id); loadRuns(); });
      list.appendChild(item);
    }
  }

  async function loadRunDetail(runId) {
    if (!token) return;
    try {
      const res = await api(`/v1/runs/${encodeURIComponent(runId)}`);
      const run = await res.json();
      const runs = JSON.parse(sessionStorage.getItem('omega-runs') || '[]');
      const idx = runs.findIndex((item) => item.id === runId);
      if (idx >= 0) {
        runs[idx].status = run.status;
        runs[idx].output = run.output;
        runs[idx].error = run.error;
        sessionStorage.setItem('omega-runs', JSON.stringify(runs));
      }
      const detail = $('#run-detail');
      detail.innerHTML = `
        <dl>
          <dt>ID</dt><dd><code>${escapeHtml(run.id)}</code></dd>
          <dt>Goal</dt><dd>${escapeHtml(run.goal)}</dd>
          <dt>Task type</dt><dd>${escapeHtml(run.task_type)}</dd>
          <dt>Status</dt><dd><span class="run-status ${escapeHtml(run.status)}">${escapeHtml(String(run.status || '').replace(/_/g, ' '))}</span></dd>
          <dt>Output</dt><dd>${run.output ? '<pre>' + escapeHtml(run.output) + '</pre>' : '—'}</dd>
          <dt>Error</dt><dd>${run.error ? '<pre style="color:var(--error)">' + escapeHtml(run.error) + '</pre>' : '—'}</dd>
        </dl>${run.status === 'waiting_approval' ? '<button id="approve-run" class="btn btn-primary" type="button">Approve run</button>' : ''}`;
      const approveButton = $('#approve-run');
      if (approveButton) {
        approveButton.addEventListener('click', async () => {
          approveButton.disabled = true;
          try {
            await api(`/v1/runs/${encodeURIComponent(runId)}/approve`, { method: 'POST' });
            addAgentLog('success', `Approved run ${String(runId).substring(0, 8)}`);
            await loadRunDetail(runId);
            await loadRuns();
          } catch (e) {
            approveButton.disabled = false;
            $('#run-detail').insertAdjacentText('beforeend', ` Approval failed: ${e.message}`);
          }
        });
      }
      addAgentLog('info', `Run ${String(runId).substring(0, 8)} status: ${run.status}`);
      if (run.status === 'running') setTimeout(() => loadRunDetail(runId), 3000);
    } catch (e) { $('#run-detail').textContent = 'Error: ' + e.message; }
  }

  $('#create-run-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!token) { alert('Connect with a signed JWT token first.'); return; }
    const goal = $('#run-goal').value.trim();
    const task_type = $('#run-task-type').value;
    const actions = $('#run-actions').value.split(',').map((value) => value.trim()).filter(Boolean);
    const submit = $('#create-run-form').querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Launching…';
    try {
      const res = await api('/v1/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, task_type, requested_actions: actions }),
      });
      const run = await res.json();
      const runs = JSON.parse(sessionStorage.getItem('omega-runs') || '[]');
      runs.unshift({ id: run.id, goal: run.goal || goal, status: run.status || 'pending', output: null, error: null });
      sessionStorage.setItem('omega-runs', JSON.stringify(runs));
      selectedRunId = run.id;
      await loadRuns();
      await loadRunDetail(run.id);
      addAgentLog('success', `Created run ${String(run.id).substring(0, 8)} — ${task_type}`);
      $('#run-goal').value = '';
      $('#run-actions').value = '';
    } catch (e) { alert('Failed to create run: ' + e.message); }
    finally {
      submit.disabled = false;
      submit.innerHTML = 'Launch workflow <span aria-hidden="true">↗</span>';
    }
  });

  $('#refresh-runs').addEventListener('click', async () => {
    const runs = JSON.parse(sessionStorage.getItem('omega-runs') || '[]');
    await Promise.all(runs.map((run) => loadRunDetail(run.id)));
    await loadRuns();
  });

  // Browser
  async function navigateTo(value, recordHistory = true) {
    if (!token) { alert('Connect with a signed JWT token first.'); return; }
    if (!value) return;
    let url = value;
    if (!/^https?:\/\//i.test(url)) {
      if (url.includes('.') && !url.includes(' ')) url = 'https://' + url;
      else url = 'https://html.duckduckgo.com/html/?q=' + encodeURIComponent(url);
    }
    $('#browser-status').textContent = 'Loading ' + url + '…';
    try {
      const res = await api('/v1/browser/proxy?url=' + encodeURIComponent(url));
      const html = await res.text();
      $('#browser-frame').srcdoc = html;
      $('#browser-status').textContent = 'Loaded ' + url;
      if (recordHistory) {
        browserHistory = browserHistory.slice(0, browserHistoryIdx + 1);
        browserHistory.push(url);
        browserHistoryIdx = browserHistory.length - 1;
      }
      $('#browser-url').value = url;
    } catch (e) {
      $('#browser-status').textContent = 'Error: ' + e.message;
    }
  }

  $('#browser-go').addEventListener('click', () => navigateTo($('#browser-url').value.trim()));
  $('#browser-url').addEventListener('keydown', (event) => { if (event.key === 'Enter') navigateTo(event.target.value.trim()); });
  $('#browser-back').addEventListener('click', () => {
    if (browserHistoryIdx > 0) {
      browserHistoryIdx--;
      navigateTo(browserHistory[browserHistoryIdx], false);
    }
  });
  $('#browser-forward').addEventListener('click', () => {
    if (browserHistoryIdx < browserHistory.length - 1) {
      browserHistoryIdx++;
      navigateTo(browserHistory[browserHistoryIdx], false);
    }
  });
  $('#browser-reload').addEventListener('click', () => {
    if (browserHistoryIdx >= 0) navigateTo(browserHistory[browserHistoryIdx], false);
  });

  // Terminal — server policy remains authoritative.
  function termPrint(message) {
    const output = $('#terminal-output');
    if (output.querySelector('.empty-state')) output.textContent = '';
    output.textContent += message + '\n';
    output.scrollTop = output.scrollHeight;
  }
  async function runCommand() {
    if (!token) { alert('Connect with a signed JWT token first.'); return; }
    const input = $('#terminal-input');
    const command = input.value.trim();
    if (!command) return;
    termPrint('$ ' + command);
    input.value = '';
    const button = $('#terminal-run');
    button.disabled = true;
    try {
      const res = await api('/v1/computer/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      });
      const result = await res.json();
      if (result.stdout) termPrint(result.stdout);
      if (result.stderr) termPrint(result.stderr);
      termPrint(`[exit ${result.returncode}]`);
    } catch (e) { termPrint('Error: ' + e.message); }
    finally { button.disabled = false; }
  }
  $('#terminal-run').addEventListener('click', runCommand);
  $('#terminal-input').addEventListener('keydown', (event) => { if (event.key === 'Enter') runCommand(); });

  // Agent log
  function addAgentLog(level, message) {
    const log = $('#agent-log');
    const empty = log.querySelector('.empty-state');
    if (empty) empty.remove();
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const time = document.createElement('span');
    time.className = 'log-time';
    time.textContent = new Date().toLocaleTimeString();
    const label = document.createElement('span');
    label.className = 'log-level ' + level;
    label.textContent = '[' + level + ']';
    entry.append(time, document.createTextNode(' '), label, document.createTextNode(' ' + String(message)));
    log.prepend(entry);
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  startPolling();
  loadRuns();
})();
