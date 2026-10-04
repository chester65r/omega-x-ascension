// OMEGA-X ASCENSION Dashboard
(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);
  let token = sessionStorage.getItem('omega-jwt') || '';
  let pollTimer = null;
  let runPollTimer = null;
  let browserHistory = [];
  let browserHistoryIdx = -1;
  const startTime = Date.now();

  // ── Token / Auth ──
  function setConnected(connected) {
    const badge = $('#conn-status');
    badge.textContent = connected ? 'Connected' : 'Disconnected';
    badge.className = 'status-badge ' + (connected ? 'connected' : 'disconnected');
  }
  $('#jwt-token').value = token;
  if (token) setConnected(true);
  $('#connect-btn').addEventListener('click', () => {
    token = $('#jwt-token').value.trim();
    sessionStorage.setItem('omega-jwt', token);
    setConnected(!!token);
    if (token) { startPolling(); loadRuns(); }
  });

  function authHeaders() {
    return token ? { Authorization: 'Bearer ' + token } : {};
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`${res.status}: ${body}`);
    }
    return res;
  }

  // ── Tabs ──
  $$('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      $$('.tab').forEach((t) => t.classList.remove('active'));
      $$('.tab-content').forEach((c) => c.classList.remove('active'));
      tab.classList.add('active');
      $('#' + tab.dataset.tab).classList.add('active');
    });
  });

  // ── Overview ──
  async function pollHealth() {
    try {
      const live = await (await fetch('/health/live')).json();
      $('#health-live').textContent = live.status === 'ok' ? 'OK' : 'ERR';
      $('#card-live').className = 'card stat-card ' + (live.status === 'ok' ? 'ok' : 'err');
    } catch { $('#health-live').textContent = 'ERR'; $('#card-live').className = 'card stat-card err'; }

    try {
      const ready = await (await fetch('/health/ready')).json();
      if (ready.status === 'ready') {
        $('#health-ready').textContent = 'Ready';
        $('#card-ready').className = 'card stat-card ok';
        $('#model-count').textContent = ready.configured_models ?? 0;
        loadModels();
      } else {
        $('#health-ready').textContent = 'Not Ready';
        $('#card-ready').className = 'card stat-card err';
      }
    } catch { $('#health-ready').textContent = 'ERR'; $('#card-ready').className = 'card stat-card err'; }

    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const m = Math.floor(elapsed / 60), s = elapsed % 60;
    $('#uptime').textContent = `${m}m ${s}s`;
  }

  async function loadModels() {
    try {
      const ready = await (await fetch('/health/ready')).json();
      const count = ready.configured_models ?? 0;
      const list = $('#models-list');
      if (count === 0) {
        list.textContent = 'No models configured';
        return;
      }
      list.textContent = count + ' provider(s) configured';
    } catch {
      $('#models-list').textContent = 'Failed to load model status';
    }
  }

  async function loadMetrics() {
    try {
      const res = await fetch('/metrics');
      const text = await res.text();
      const lines = text.split('\n').filter((l) => !l.startsWith('#')).slice(0, 30);
      $('#metrics').textContent = lines.join('\n');
    } catch { $('#metrics').textContent = 'Failed to load metrics'; }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollHealth();
    loadMetrics();
    pollTimer = setInterval(() => { pollHealth(); loadMetrics(); }, 5000);
  }

  // ── Runs ──
  let selectedRunId = null;

  async function loadRuns() {
    if (!token) return;
    // Note: the API doesn't have a list endpoint, so we track runs locally
    const runs = JSON.parse(sessionStorage.getItem('omega-runs') || '[]');
    const list = $('#runs-list');
    if (runs.length === 0) { list.textContent = 'No runs yet. Create one!'; return; }
    list.innerHTML = '';
    for (const r of runs) {
      const div = document.createElement('div');
      div.className = 'run-item' + (r.id === selectedRunId ? ' active' : '');
      div.innerHTML = `
        <div class="run-id">${escapeHtml(r.id.substring(0, 8))}</div>
        <div class="run-goal">${escapeHtml(r.goal.substring(0, 80))}</div>
        <span class="run-status ${escapeHtml(r.status)}">${escapeHtml(r.status)}</span>`;
      div.addEventListener('click', () => { selectedRunId = r.id; loadRunDetail(r.id); loadRuns(); });
      list.appendChild(div);
    }
  }

  async function loadRunDetail(runId) {
    if (!token) return;
    try {
      const res = await api(`/v1/runs/${runId}`);
      const run = await res.json();
      // Update local store
      const runs = JSON.parse(sessionStorage.getItem('omega-runs') || '[]');
      const idx = runs.findIndex((r) => r.id === runId);
      if (idx >= 0) { runs[idx].status = run.status; runs[idx].output = run.output; runs[idx].error = run.error; sessionStorage.setItem('omega-runs', JSON.stringify(runs)); }
      const detail = $('#run-detail');
      detail.innerHTML = `
        <dl>
          <dt>ID</dt><dd><code>${escapeHtml(run.id)}</code></dd>
          <dt>Goal</dt><dd>${escapeHtml(run.goal)}</dd>
          <dt>Task Type</dt><dd>${escapeHtml(run.task_type)}</dd>
          <dt>Status</dt><dd><span class="run-status ${escapeHtml(run.status)}">${escapeHtml(run.status)}</span></dd>
          <dt>Output</dt><dd>${run.output ? '<pre>' + escapeHtml(run.output) + '</pre>' : '—'}</dd>
          <dt>Error</dt><dd>${run.error ? '<pre style="color:var(--error)">' + escapeHtml(run.error) + '</pre>' : '—'}</dd>
        </dl>`;
      addAgentLog('info', `Run ${runId.substring(0, 8)} status: ${run.status}`);
      if (run.status === 'running') {
        setTimeout(() => loadRunDetail(runId), 3000);
      }
    } catch (e) { $('#run-detail').textContent = 'Error: ' + e.message; }
  }

  $('#create-run-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!token) { alert('Connect with a JWT token first'); return; }
    const goal = $('#run-goal').value.trim();
    const task_type = $('#run-task-type').value;
    const actions = $('#run-actions').value.split(',').map((s) => s.trim()).filter(Boolean);
    try {
      const res = await api('/v1/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, task_type, requested_actions: actions }),
      });
      const run = await res.json();
      const runs = JSON.parse(sessionStorage.getItem('omega-runs') || '[]');
      runs.unshift({ id: run.id, goal: run.goal, status: run.status, output: null, error: null });
      sessionStorage.setItem('omega-runs', JSON.stringify(runs));
      selectedRunId = run.id;
      loadRuns();
      loadRunDetail(run.id);
      addAgentLog('success', `Created run ${run.id.substring(0, 8)} — ${task_type}`);
      $('#run-goal').value = '';
      $('#run-actions').value = '';
    } catch (e) { alert('Failed to create run: ' + e.message); }
  });

  $('#refresh-runs').addEventListener('click', () => {
    const runs = JSON.parse(sessionStorage.getItem('omega-runs') || '[]');
    runs.forEach((r) => loadRunDetail(r.id));
    loadRuns();
  });

  // ── Browser ──
  async function navigateTo(url) {
    if (!token) { alert('Connect with a JWT token first'); return; }
    if (!url) return;
    // If it doesn't look like a URL, treat it as a search query
    if (!/^https?:\/\//i.test(url)) {
      if (url.includes('.') && !url.includes(' ')) { url = 'https://' + url; }
      else { url = 'https://html.duckduckgo.com/html/?q=' + encodeURIComponent(url); }
    }
    $('#browser-status').textContent = 'Loading ' + url + '...';
    try {
      const res = await api('/v1/browser/proxy?url=' + encodeURIComponent(url));
      const html = await res.text();
      $('#browser-frame').srcdoc = html;
      $('#browser-status').textContent = 'Loaded ' + url;
      browserHistory = browserHistory.slice(0, browserHistoryIdx + 1);
      browserHistory.push(url);
      browserHistoryIdx = browserHistory.length - 1;
      $('#browser-url').value = url;
    } catch (e) {
      $('#browser-status').textContent = 'Error: ' + e.message;
    }
  }

  $('#browser-go').addEventListener('click', () => navigateTo($('#browser-url').value.trim()));
  $('#browser-url').addEventListener('keydown', (e) => { if (e.key === 'Enter') navigateTo(e.target.value.trim()); });
  $('#browser-back').addEventListener('click', () => {
    if (browserHistoryIdx > 0) { browserHistoryIdx--; navigateTo(browserHistory[browserHistoryIdx]); }
  });
  $('#browser-forward').addEventListener('click', () => {
    if (browserHistoryIdx < browserHistory.length - 1) { browserHistoryIdx++; navigateTo(browserHistory[browserHistoryIdx]); }
  });
  $('#browser-reload').addEventListener('click', () => {
    if (browserHistoryIdx >= 0) navigateTo(browserHistory[browserHistoryIdx]);
  });

  // ── Terminal ──
  function termPrint(text) {
    const out = $('#terminal-output');
    out.textContent += text + '\n';
    out.scrollTop = out.scrollHeight;
  }

  async function runCommand() {
    if (!token) { alert('Connect with a JWT token first'); return; }
    const cmd = $('#terminal-input').value.trim();
    if (!cmd) return;
    termPrint('$ ' + cmd);
    $('#terminal-input').value = '';
    try {
      const res = await api('/v1/computer/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd }),
      });
      const result = await res.json();
      if (result.stdout) termPrint(result.stdout);
      if (result.stderr) termPrint(result.stderr);
      termPrint(`[exit ${result.returncode}]`);
    } catch (e) { termPrint('Error: ' + e.message); }
  }

  $('#terminal-run').addEventListener('click', runCommand);
  $('#terminal-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') runCommand(); });

  // ── Agent Log ──
  function addAgentLog(level, msg) {
    const log = $('#agent-log');
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="log-time">${time}</span> <span class="log-level ${level}">[${level}]</span> ${escapeHtml(msg)}`;
    log.prepend(entry);
  }

  // ── Utils ──
  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Init ──
  startPolling();
  loadRuns();
})();
