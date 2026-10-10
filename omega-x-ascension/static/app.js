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
  const LOCAL_LOG_KEY = 'omega-local-logs';
  let storedLogs = [];
  try {
    const parsedLogs = JSON.parse(localStorage.getItem(LOCAL_LOG_KEY) || '[]');
    storedLogs = Array.isArray(parsedLogs) ? parsedLogs.slice(0, 200) : [];
  } catch (_) { storedLogs = []; }
  let serverAuditEvents = [];
  let assistantMessages = [];
  let assistantRunTimer = null;
  let activeAssistantRunId = null;
  let latestAssistantAnswer = '';

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
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname);
    if (parsed.protocol === 'http:' && !loopback) {
      throw new Error('Remote API servers must use HTTPS. Plain HTTP is allowed only for localhost.');
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
      const nextApiBase = normalizeApiBase($('#api-base').value);
      if (apiBase && apiBase !== nextApiBase) {
        token = '';
        sessionStorage.removeItem('omega-jwt');
        $('#jwt-token').value = '';
        setConnected(false);
        addAgentLog('info', 'API server URL changed; reconnect with a token issued by the new server.');
      }
      apiBase = nextApiBase;
      localStorage.setItem('omega-api-base', apiBase);
      $('#api-base').value = apiBase;
      startPolling();
      if (token) loadRuns();
      else setAssistantStatus('API URL saved. Connect with a signed JWT to use server agent workflows.', 'warning');
    } catch (e) { alert(e.message || 'Enter a valid API server URL.'); }
  });

  // Local on-device model mode: talks directly to a llama.cpp OpenAI-compatible server.
  let localAiBase = localStorage.getItem('omega-local-ai-base') || 'http://127.0.0.1:8080';
  let localAiMessages = [];
  $('#local-ai-url').value = localAiBase;

  function normalizeLocalAiBase(value) {
    const parsed = new URL(value.trim());
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
      throw new Error('Enter a valid local HTTP/HTTPS URL without credentials.');
    }
    if (parsed.hostname !== '127.0.0.1' && parsed.hostname !== 'localhost' && parsed.hostname !== '[::1]') {
      throw new Error('For safety, Local AI only accepts localhost / 127.0.0.1.');
    }
    return parsed.origin.replace(/\/$/, '');
  }

  function setLocalAiStatus(text, connected) {
    const el = $('#local-ai-status');
    el.textContent = text;
    el.classList.toggle('connected', Boolean(connected));
  }

  function renderLocalAiMessages() {
    const list = $('#local-ai-messages');
    list.replaceChildren();
    if (!localAiMessages.length) {
      const welcome = document.createElement('div');
      welcome.className = 'local-ai-welcome';
      welcome.textContent = 'Your local conversation will appear here. Messages stay in this page session.';
      list.appendChild(welcome);
      return;
    }
    for (const message of localAiMessages) {
      const item = document.createElement('article');
      item.className = 'local-ai-message ' + (message.role === 'user' ? 'user' : 'assistant');
      const label = document.createElement('div');
      label.className = 'local-ai-message-role';
      label.textContent = message.role === 'user' ? 'YOU' : 'LOCAL MODEL';
      const body = document.createElement('div');
      body.className = 'local-ai-message-body';
      body.textContent = message.content;
      item.append(label, body);
      list.appendChild(item);
    }
    list.scrollTop = list.scrollHeight;
  }

  $('#local-ai-check').addEventListener('click', async () => {
    const button = $('#local-ai-check');
    button.disabled = true;
    setLocalAiStatus('CHECKING…', false);
    try {
      localAiBase = normalizeLocalAiBase($('#local-ai-url').value);
      $('#local-ai-url').value = localAiBase;
      localStorage.setItem('omega-local-ai-base', localAiBase);
      const response = await fetch(localAiBase + '/health', { method: 'GET' });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      setLocalAiStatus('MODEL SERVER ONLINE', true);
      addAgentLog('success', 'Local model server is reachable.');
    } catch (error) {
      setLocalAiStatus('NOT CONNECTED', false);
      alert('Could not reach the local model server. Start llama-server in Termux and check its port and CORS settings. ' + (error.message || ''));
    } finally {
      button.disabled = false;
    }
  });

  $('#local-ai-clear').addEventListener('click', () => {
    localAiMessages = [];
    renderLocalAiMessages();
  });

  $('#local-ai-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const prompt = $('#local-ai-prompt').value.trim();
    if (!prompt) return;
    const button = $('#local-ai-send');
    button.disabled = true;
    $('#local-ai-prompt').disabled = true;
    localAiMessages.push({ role: 'user', content: prompt });
    renderLocalAiMessages();
    $('#local-ai-prompt').value = '';
    const pending = { role: 'assistant', content: 'Thinking…' };
    localAiMessages.push(pending);
    renderLocalAiMessages();
    const requestController = new AbortController();
    const requestTimeout = window.setTimeout(() => requestController.abort(), 180000);
    try {
      localAiBase = normalizeLocalAiBase($('#local-ai-url').value);
      localStorage.setItem('omega-local-ai-base', localAiBase);
      const response = await fetch(localAiBase + '/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'local-model',
          messages: [
            { role: 'system', content: 'You are a helpful assistant. Answer clearly and honestly. If unsure, say so.' },
            ...localAiMessages.filter((m) => m !== pending).slice(-4).map((m, index, messages) => ({
              role: m.role,
              content: String(m.content).slice(index === messages.length - 1 ? -1200 : -240)
            }))
          ],
          temperature: 0.4,
          max_tokens: 256,
          stream: false
        }),
        signal: requestController.signal
      });
      if (!response.ok) throw new Error('HTTP ' + response.status + ': ' + (await response.text()).slice(0, 400));
      const data = await response.json();
      const answer = data.choices?.[0]?.message?.content;
      if (!answer) throw new Error('The local model returned no text.');
      pending.content = answer;
      setLocalAiStatus('MODEL SERVER ONLINE', true);
    } catch (error) {
      pending.content = error.name === 'AbortError'
        ? 'Local inference timed out after 180 seconds. On-device generation can be slow; reduce the prompt or close other apps and retry.'
        : 'Local inference failed: ' + (error.message || String(error)) + '\\n\\nCheck that llama-server is running, the model has finished loading, and CORS allows https://appassets.androidplatform.net.';
      setLocalAiStatus('REQUEST FAILED', false);
      addAgentLog('error', 'Local inference failed: ' + (error.message || String(error)).slice(0, 300));
    } finally {
      window.clearTimeout(requestTimeout);
      renderLocalAiMessages();
      button.disabled = false;
      $('#local-ai-prompt').disabled = false;
      $('#local-ai-prompt').focus();
    }
  });

  renderLocalAiMessages();

  $('#jwt-token').value = token;
  setConnected(false);
  $('#connect-btn').addEventListener('click', async () => {
    const candidate = $('#jwt-token').value.trim();
    if (!candidate) {
      token = '';
      sessionStorage.removeItem('omega-jwt');
      setConnected(false);
      alert('Paste a signed JWT token first.');
      return;
    }
    if (!apiBase) {
      alert('Save your API server URL first.');
      return;
    }
    const button = $('#connect-btn');
    button.disabled = true;
    button.textContent = 'Checking…';
    token = candidate;
    sessionStorage.setItem('omega-jwt', token);
    try {
      await api('/v1/runs?limit=1');
      setConnected(true);
      startPolling();
      await loadRuns();
      addAgentLog('success', 'API token verified successfully.');
    } catch (error) {
      token = '';
      sessionStorage.removeItem('omega-jwt');
      setConnected(false);
      alert('Connection failed. Verify the API URL, token validity, and runs:read scope. ' + (error.message || ''));
    } finally {
      button.disabled = false;
      button.textContent = 'Connect';
    }
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
    if (name === 'logs') loadLogs();
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
      const response = await apiFetch('/health/models');
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      const providers = Array.isArray(data.providers) ? data.providers : [];
      const list = $('#models-list');
      $('#model-count').textContent = String(data.healthy_models ?? 0) + '/' + String(data.configured_models ?? providers.length);
      list.replaceChildren();
      if (!providers.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No model providers are configured. Cloud agent runs cannot execute until one is configured.';
        list.appendChild(empty);
        return;
      }
      for (const provider of providers) {
        const item = document.createElement('div');
        item.className = 'model-item';
        const name = document.createElement('div');
        name.className = 'model-name';
        name.textContent = String(provider.name || 'Unnamed provider');
        const state = document.createElement('span');
        state.className = 'run-status ' + (provider.healthy ? 'succeeded' : 'failed');
        state.textContent = provider.healthy ? 'ONLINE' : 'OFFLINE';
        const capabilities = document.createElement('div');
        capabilities.className = 'model-url';
        capabilities.textContent = Array.isArray(provider.capabilities) ? provider.capabilities.join(' · ') : 'No capability metadata';
        item.append(name, state, capabilities);
        list.appendChild(item);
      }
    } catch (error) {
      $('#models-list').textContent = 'Unable to check model health: ' + (error.message || String(error));
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
    if (runPollTimer) clearInterval(runPollTimer);
    runPollTimer = token ? setInterval(() => {
      loadRuns();
      if (selectedRunId) loadRunDetail(selectedRunId);
    }, 10000) : null;
  }

  // Runs
  let selectedRunId = null;

  async function loadRuns() {
    const list = $('#runs-list');
    if (!token) {
      list.innerHTML = '<div class="empty-state">Connect with a signed JWT to manage runs.</div>';
      return;
    }
    try {
      const response = await api('/v1/runs?limit=50');
      const runs = await response.json();
      sessionStorage.setItem('omega-runs', JSON.stringify(runs));
      if (runs.length === 0) {
        list.innerHTML = '<div class="empty-state">No runs found for this account. Create your first task.</div>';
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
        item.addEventListener('click', () => {
          selectedRunId = run.id;
          loadRunDetail(run.id);
          loadRuns();
        });
        list.appendChild(item);
      }
    } catch (error) {
      list.innerHTML = '<div class="empty-state">Unable to load server run history. Check the API connection and runs:read permission.</div>';
      addAgentLog('error', 'Run history unavailable: ' + (error.message || 'request failed'));
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

  // Browser: search is a structured API call; page navigation always goes through the SSRF-checked proxy.
  function addBrowserHistory(item, recordHistory) {
    if (!recordHistory) return;
    browserHistory = browserHistory.slice(0, browserHistoryIdx + 1);
    browserHistory.push(item);
    if (browserHistory.length > 100) browserHistory.shift();
    browserHistoryIdx = browserHistory.length - 1;
  }

  function browserStatus(message, level = 'info') {
    $('#browser-status').textContent = message;
    $('#browser-status').dataset.level = level;
  }

  function browserReady() {
    if (!apiBase) {
      browserStatus('Set the HTTPS API server URL in Backend Connection first.', 'error');
      return false;
    }
    if (!token) {
      browserStatus('Connect with a signed JWT token that includes runs:read before browsing.', 'error');
      return false;
    }
    return true;
  }

  function renderBrowserResults(payload, query) {
    const results = $('#browser-results');
    const frame = $('#browser-frame');
    frame.hidden = true;
    results.hidden = false;
    results.replaceChildren();
    if (payload.error) {
      const error = document.createElement('div');
      error.className = 'empty-state';
      error.textContent = 'Search failed: ' + payload.error;
      results.appendChild(error);
      return;
    }
    const rows = Array.isArray(payload.results) ? payload.results : [];
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'No results returned for “' + query + '”. Try a different query.';
      results.appendChild(empty);
      return;
    }
    for (const row of rows) {
      const card = document.createElement('article');
      card.className = 'browser-result';
      const title = document.createElement('h3');
      title.textContent = String(row.title || row.url || 'Search result');
      const snippet = document.createElement('p');
      snippet.textContent = String(row.snippet || '');
      const link = document.createElement('div');
      link.className = 'browser-result-url';
      link.textContent = String(row.url || '');
      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'btn btn-primary';
      open.textContent = 'Open page';
      open.addEventListener('click', () => navigateTo(String(row.url || '')));
      card.append(title, snippet, link, open);
      results.appendChild(card);
    }
  }

  async function searchBrowser(query, recordHistory = true) {
    if (!browserReady()) return;
    const cleanQuery = String(query || '').trim();
    if (!cleanQuery) return;
    if (cleanQuery.length > 300) {
      browserStatus('Search queries must be 300 characters or fewer.', 'error');
      return;
    }
    browserStatus('Searching the web…');
    $('#browser-frame').hidden = true;
    $('#browser-results').hidden = false;
    $('#browser-results').replaceChildren();
    const pending = document.createElement('div');
    pending.className = 'empty-state';
    pending.textContent = 'Searching for “' + cleanQuery + '”…';
    $('#browser-results').appendChild(pending);
    try {
      const response = await api('/v1/browser/search?q=' + encodeURIComponent(cleanQuery));
      const payload = await response.json();
      renderBrowserResults(payload, cleanQuery);
      if (payload.error) {
        browserStatus('Search failed: ' + payload.error, 'error');
        addAgentLog('error', 'Browser search failed: ' + String(payload.error).slice(0, 160));
        return;
      }
      browserStatus('Search complete · ' + (payload.results || []).length + ' result(s)');
      addBrowserHistory({ type: 'search', value: cleanQuery }, recordHistory);
      $('#browser-url').value = cleanQuery;
      addAgentLog('success', 'Browser search completed: ' + cleanQuery.slice(0, 100));
    } catch (error) {
      renderBrowserResults({ error: error.message || String(error), results: [] }, cleanQuery);
      browserStatus('Search failed: ' + (error.message || String(error)), 'error');
      addAgentLog('error', 'Browser search failed: ' + (error.message || String(error)));
    }
  }

  async function navigateTo(value, recordHistory = true) {
    if (!browserReady()) return;
    let raw = String(value || '').trim();
    if (!raw) return;
    let url;
    if (/^https?:\/\//i.test(raw)) {
      url = raw;
    } else if (/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::\d{1,5})?(?:\/[^\s]*)?$/i.test(raw) && raw.includes('.')) {
      url = 'https://' + raw;
    } else {
      await searchBrowser(raw, recordHistory);
      return;
    }

    try {
      const parsed = new URL(url);
      if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
        throw new Error('Only public HTTP/HTTPS pages without embedded credentials can be opened.');
      }
      url = parsed.href;
    } catch (error) {
      browserStatus(error.message || 'Enter a valid public URL.', 'error');
      return;
    }

    browserStatus('Loading ' + url + '…');
    $('#browser-results').hidden = true;
    $('#browser-frame').hidden = false;
    try {
      const res = await api('/v1/browser/proxy?url=' + encodeURIComponent(url));
      const html = await res.text();
      $('#browser-frame').srcdoc = html;
      browserStatus('Loaded through the secure proxy · ' + url);
      addBrowserHistory({ type: 'url', value: url }, recordHistory);
      $('#browser-url').value = url;
      addAgentLog('success', 'Browser page loaded: ' + url.slice(0, 160));
    } catch (error) {
      browserStatus('Page failed to load: ' + (error.message || String(error)), 'error');
      addAgentLog('error', 'Browser navigation failed: ' + (error.message || String(error)));
    }
  }

  async function restoreBrowserHistory(item) {
    if (!item) return;
    if (item.type === 'search') await searchBrowser(item.value, false);
    else await navigateTo(item.value, false);
  }

  $('#browser-go').addEventListener('click', () => navigateTo($('#browser-url').value));
  $('#browser-url').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      navigateTo(event.target.value);
    }
  });
  $('#browser-back').addEventListener('click', async () => {
    if (browserHistoryIdx > 0) {
      browserHistoryIdx--;
      await restoreBrowserHistory(browserHistory[browserHistoryIdx]);
    }
  });
  $('#browser-forward').addEventListener('click', async () => {
    if (browserHistoryIdx < browserHistory.length - 1) {
      browserHistoryIdx++;
      await restoreBrowserHistory(browserHistory[browserHistoryIdx]);
    }
  });
  $('#browser-reload').addEventListener('click', async () => {
    if (browserHistoryIdx >= 0) await restoreBrowserHistory(browserHistory[browserHistoryIdx]);
  });
  window.addEventListener('message', (event) => {
    const frame = $('#browser-frame');
    if (event.source !== frame.contentWindow) return;
    const data = event.data;
    if (!data || data.source !== 'omega-browser') return;
    if (data.action === 'navigate' && typeof data.url === 'string') {
      try {
        const url = new URL(data.url);
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
          throw new Error('Only public HTTP/HTTPS navigation is allowed.');
        }
        navigateTo(url.href);
      } catch (error) {
        browserStatus(error.message || 'The browser rejected this navigation.', 'error');
      }
    } else if (data.action === 'notice' && typeof data.message === 'string') {
      browserStatus(data.message);
    }
  });

  // Sandbox file manager — the API validates permissions and the sandbox confines paths.
  async function loadComputerFiles(directory) {
    if (!token) { alert('Connect with a signed JWT token first.'); return; }
    const path = (directory ?? $('#computer-path').value).trim() || '.';
    $('#computer-path').value = path;
    const list = $('#computer-files-list');
    list.replaceChildren();
    $('#computer-file-status').textContent = 'Loading workspace files…';
    try {
      const res = await api('/v1/computer/files?path=' + encodeURIComponent(path));
      const data = await res.json();
      const entries = Array.isArray(data.entries) ? data.entries : [];
      if (path !== '.') {
        const parent = path.replace(/\/+$/, '').split('/').slice(0, -1).join('/') || '.';
        const up = document.createElement('button');
        up.type = 'button';
        up.className = 'computer-file-entry';
        up.textContent = '↰  .. (parent folder)';
        up.addEventListener('click', () => loadComputerFiles(parent));
        list.appendChild(up);
      }
      if (!entries.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'This folder is empty.';
        list.appendChild(empty);
      }
      for (const entry of entries) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'computer-file-entry';
        const label = entry.type === 'dir' ? '▸  ' : entry.type === 'link' ? '↗  ' : '·  ';
        button.textContent = label + entry.name + (entry.type === 'file' ? '  (' + String(entry.size) + ' B)' : '');
        button.title = entry.type === 'link' ? 'Symbolic links cannot be opened from the file manager.' : entry.name;
        button.addEventListener('click', () => {
          if (entry.type === 'dir') {
            const base = path === '.' ? '' : path.replace(/\/+$/, '');
            loadComputerFiles((base ? base + '/' : '') + entry.name);
          } else if (entry.type === 'file') {
            const base = path === '.' ? '' : path.replace(/\/+$/, '') + '/';
            openComputerFile(base + entry.name);
          } else {
            $('#computer-file-status').textContent = 'Symbolic links are not opened by the file manager.';
          }
        });
        list.appendChild(button);
      }
      $('#computer-file-status').textContent = data.truncated
        ? 'Showing up to 200 entries. Use a narrower folder path.'
        : 'Workspace: ' + path + ' · ' + entries.length + ' item(s)';
    } catch (error) {
      const message = document.createElement('div');
      message.className = 'empty-state';
      message.textContent = 'Cannot list files: ' + (error.message || String(error)) + '. Check computer:read permission and server policy.';
      list.appendChild(message);
      $('#computer-file-status').textContent = 'File listing failed.';
    }
  }

  async function openComputerFile(path) {
    if (!path || path.startsWith('/')) {
      $('#computer-file-status').textContent = 'Enter a relative workspace path.';
      return;
    }
    $('#computer-file-editor-path').value = path;
    $('#computer-file-status').textContent = 'Opening ' + path + '…';
    try {
      const res = await api('/v1/computer/files/read?path=' + encodeURIComponent(path));
      const data = await res.json();
      $('#computer-file-content').value = data.content ?? '';
      $('#computer-file-status').textContent = 'Opened ' + path;
    } catch (error) {
      $('#computer-file-status').textContent = 'Open failed: ' + (error.message || String(error)) + '. New files can be created by entering a relative path and saving.';
    }
  }

  $('#computer-files-refresh').addEventListener('click', () => loadComputerFiles());
  $('#computer-file-read').addEventListener('click', () => openComputerFile($('#computer-file-editor-path').value.trim()));
  $('#computer-file-save').addEventListener('click', async () => {
    if (!token) { alert('Connect with a signed JWT token first.'); return; }
    const path = $('#computer-file-editor-path').value.trim();
    if (!path || path.startsWith('/')) {
      $('#computer-file-status').textContent = 'Enter a relative workspace file path first.';
      return;
    }
    if (!window.confirm('Save this text into the isolated workspace file "' + path + '"?')) return;
    const button = $('#computer-file-save');
    button.disabled = true;
    $('#computer-file-status').textContent = 'Saving ' + path + '…';
    try {
      await api('/v1/computer/files', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, content: $('#computer-file-content').value }),
      });
      $('#computer-file-status').textContent = 'Saved ' + path;
      await loadComputerFiles();
    } catch (error) {
      $('#computer-file-status').textContent = 'Save failed: ' + (error.message || String(error)) + '. Requires computer:write and runs:approve.';
    } finally {
      button.disabled = false;
    }
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
    if (!window.confirm('Run this command inside the isolated computer sandbox?\n\n' + command)) return;
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

  // Personal assistant tasks run through the real OMEGA workflow API; errors remain visible.
  function renderAssistantMessages() {
    const list = $('#assistant-messages');
    list.replaceChildren();
    if (!assistantMessages.length) {
      const empty = document.createElement('div');
      empty.className = 'assistant-welcome';
      empty.textContent = 'Your task history appears here during this app session. Responses are returned by the configured model provider, not generated by a placeholder.';
      list.appendChild(empty);
      return;
    }
    for (const message of assistantMessages) {
      const item = document.createElement('article');
      item.className = 'assistant-message ' + (message.role === 'user' ? 'user' : 'assistant');
      const label = document.createElement('div');
      label.className = 'assistant-message-role';
      label.textContent = message.role === 'user' ? 'YOU' : 'OMEGA ASSISTANT';
      const body = document.createElement('div');
      body.className = 'assistant-message-body';
      body.textContent = message.content;
      item.append(label, body);
      list.appendChild(item);
    }
    list.scrollTop = list.scrollHeight;
  }

  function setAssistantStatus(message, level = 'info') {
    $('#assistant-status').textContent = message;
    $('#assistant-status').dataset.level = level;
  }

  async function pollAssistantRun(runId, responseIndex, elapsed = 0) {
    if (activeAssistantRunId !== runId || !assistantMessages[responseIndex]) return;
    if (elapsed >= 300000) {
      assistantMessages[responseIndex].content = 'The run is still processing after five minutes. Open Runs to inspect its current status; polling was stopped to avoid a permanent background loop.';
      renderAssistantMessages();
      setAssistantStatus('Run is still active. Check Runs for the latest status.', 'warning');
      return;
    }
    try {
      const response = await api('/v1/runs/' + encodeURIComponent(runId));
      const run = await response.json();
      if (run.status === 'succeeded') {
        latestAssistantAnswer = String(run.output || '');
        assistantMessages[responseIndex].content = latestAssistantAnswer || 'The workflow completed but returned an empty output.';
        renderAssistantMessages();
        setAssistantStatus('Task completed successfully · ' + String(runId).slice(0, 8), 'success');
        addAgentLog('success', 'Assistant task succeeded: ' + String(runId).slice(0, 8));
        if (window.OmegaNative && typeof window.OmegaNative.postMessage === 'function') {
          window.OmegaNative.postMessage(JSON.stringify({ action: 'haptic' }));
        } else if (navigator.vibrate) {
          navigator.vibrate(25);
        }
        return;
      }
      if (run.status === 'failed') {
        assistantMessages[responseIndex].content = 'The workflow failed. ' + String(run.error || 'No error details were supplied by the server.');
        renderAssistantMessages();
        setAssistantStatus('Task failed · open Logs for audit records.', 'error');
        addAgentLog('error', 'Assistant task failed: ' + String(runId).slice(0, 8));
        return;
      }
      if (run.status === 'waiting_approval') {
        assistantMessages[responseIndex].content = 'This task is waiting for an approval. Open Runs, select this task, and review the requested action before approving it.';
        renderAssistantMessages();
        setAssistantStatus('Approval required · ' + String(runId).slice(0, 8), 'warning');
        return;
      }
      assistantMessages[responseIndex].content = 'Task ' + String(run.status || 'pending') + ' · ' + String(runId).slice(0, 8) + '. Checking for the real result…';
      renderAssistantMessages();
      assistantRunTimer = window.setTimeout(() => pollAssistantRun(runId, responseIndex, elapsed + 3000), 3000);
    } catch (error) {
      if (elapsed < 15000) {
        assistantRunTimer = window.setTimeout(() => pollAssistantRun(runId, responseIndex, elapsed + 3000), 3000);
      } else {
        assistantMessages[responseIndex].content = 'Lost contact while checking this task: ' + (error.message || String(error)) + '. The task may still be running; inspect Runs after reconnecting.';
        renderAssistantMessages();
        setAssistantStatus('Could not check task status.', 'error');
      }
    }
  }

  async function submitAssistantTask(prompt) {
    const clean = String(prompt || '').trim();
    if (!clean) return;
    if (!apiBase || !token) {
      setAssistantStatus('Connect the API server first. Cloud agent tasks require a signed JWT with runs:write and a healthy configured model.', 'error');
      addAgentLog('warning', 'Assistant task was not sent because the backend is not connected.');
      return;
    }
    if (assistantRunTimer) window.clearTimeout(assistantRunTimer);
    assistantMessages.push({ role: 'user', content: clean });
    const responseIndex = assistantMessages.push({ role: 'assistant', content: 'Submitting the task to the OMEGA workflow service…' }) - 1;
    renderAssistantMessages();
    const button = $('#assistant-send');
    button.disabled = true;
    setAssistantStatus('Submitting task to the server…');
    try {
      const response = await api('/v1/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: clean, task_type: $('#assistant-task-type').value, requested_actions: [] }),
      });
      const run = await response.json();
      activeAssistantRunId = run.id;
      assistantMessages[responseIndex].content = 'Task accepted by the server. Run ID: ' + run.id + '\nCurrent status: ' + run.status + '\nWaiting for the configured model workflow to finish…';
      renderAssistantMessages();
      setAssistantStatus('Run accepted · ' + String(run.id).slice(0, 8), 'success');
      addAgentLog('success', 'Assistant submitted run ' + String(run.id).slice(0, 8));
      $('#assistant-prompt').value = '';
      await loadRuns();
      pollAssistantRun(run.id, responseIndex);
    } catch (error) {
      assistantMessages[responseIndex].content = 'The server did not accept this task. ' + (error.message || String(error)) + '\n\nCommon causes: missing runs:write scope, no healthy provider for this task type, or backend / model service unavailable. No fake answer was generated.';
      renderAssistantMessages();
      setAssistantStatus('Task could not be started. Check Logs and provider health.', 'error');
      addAgentLog('error', 'Assistant task was rejected: ' + (error.message || String(error)).slice(0, 400));
    } finally {
      button.disabled = false;
    }
  }

  $('#assistant-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submitAssistantTask($('#assistant-prompt').value);
  });
  document.querySelectorAll('[data-assistant-prompt]').forEach((button) => {
    button.addEventListener('click', () => {
      $('#assistant-prompt').value = button.dataset.assistantPrompt || '';
      $('#assistant-prompt').focus();
    });
  });
  $('#assistant-clear').addEventListener('click', () => {
    if (assistantRunTimer) window.clearTimeout(assistantRunTimer);
    activeAssistantRunId = null;
    assistantMessages = [];
    latestAssistantAnswer = '';
    renderAssistantMessages();
    setAssistantStatus('Session cleared. Server-side workflow and audit records are unchanged.');
  });

  function nativeMessage(action, payload = {}) {
    if (!window.OmegaNative || typeof window.OmegaNative.postMessage !== 'function') return false;
    window.OmegaNative.postMessage(JSON.stringify({ action, ...payload }));
    return true;
  }

  $('#assistant-voice').addEventListener('click', () => {
    if (nativeMessage('voiceInput')) {
      setAssistantStatus('Opening Android speech recognition…');
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setAssistantStatus('Voice dictation is unavailable in this WebView. Use the keyboard microphone or install a supported Android speech recognizer.', 'warning');
      return;
    }
    try {
      const recognition = new SpeechRecognition();
      recognition.lang = navigator.language || 'en-US';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.onresult = (event) => {
        const text = event.results?.[0]?.[0]?.transcript || '';
        $('#assistant-prompt').value = text;
        $('#assistant-prompt').focus();
        setAssistantStatus(text ? 'Voice text captured. Review it before sending.' : 'No speech was recognized.', text ? 'success' : 'warning');
      };
      recognition.onerror = (event) => setAssistantStatus('Voice recognition failed: ' + event.error, 'error');
      recognition.start();
      setAssistantStatus('Listening…');
    } catch (error) {
      setAssistantStatus('Voice recognition could not start: ' + (error.message || String(error)), 'error');
    }
  });

  $('#assistant-speak').addEventListener('click', () => {
    const answer = latestAssistantAnswer || [...assistantMessages].reverse().find((message) => message.role === 'assistant')?.content || '';
    if (!answer) {
      setAssistantStatus('There is no assistant response to read aloud yet.', 'warning');
      return;
    }
    if (nativeMessage('speak', { text: answer.slice(0, 4000) })) {
      setAssistantStatus('Sending the answer to Android text-to-speech…');
      return;
    }
    if (window.speechSynthesis && typeof window.SpeechSynthesisUtterance === 'function') {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(answer.slice(0, 4000)));
      setAssistantStatus('Reading the answer aloud.');
    } else {
      setAssistantStatus('Text-to-speech is not available in this WebView.', 'warning');
    }
  });

  $('#assistant-share').addEventListener('click', async () => {
    const answer = latestAssistantAnswer || [...assistantMessages].reverse().find((message) => message.role === 'assistant')?.content || '';
    if (!answer) {
      setAssistantStatus('There is no assistant response to share yet.', 'warning');
      return;
    }
    if (nativeMessage('share', { text: answer.slice(0, 8000) })) {
      setAssistantStatus('Opening the Android share sheet…');
      return;
    }
    try {
      if (navigator.share) {
        await navigator.share({ title: 'OMEGA-X Assistant', text: answer.slice(0, 8000) });
      } else if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(answer);
        setAssistantStatus('Share is not available here; the answer was copied to the clipboard.', 'success');
      } else {
        throw new Error('Neither the system share sheet nor clipboard API is available.');
      }
    } catch (error) {
      setAssistantStatus('Could not share the answer: ' + (error.message || String(error)), 'warning');
    }
  });

  window.addEventListener('omega:native', (event) => {
    const detail = event.detail || {};
    if (detail.action === 'speech-result') {
      $('#assistant-prompt').value = detail.text || '';
      $('#assistant-prompt').focus();
      setAssistantStatus(detail.text ? 'Voice text captured. Review it before sending.' : 'No speech was recognized.', detail.text ? 'success' : 'warning');
    } else if (detail.action === 'speech-error') {
      setAssistantStatus(detail.message || 'Android speech recognition failed.', 'error');
    } else if (detail.action === 'device-info') {
      $('#device-info').textContent = detail.text || 'Device details unavailable.';
      $('#about-runtime-status').textContent = 'Android native message channel responded successfully.';
    } else if (detail.action === 'native-error') {
      setAssistantStatus(detail.message || 'Android action failed.', 'error');
    }
  });

  $('#about-device-refresh').addEventListener('click', () => {
    if (!nativeMessage('deviceInfo')) {
      $('#device-info').textContent = 'Native device details are unavailable on this WebView version.';
    } else {
      $('#device-info').textContent = 'Reading device details…';
    }
  });

  // Local and server audit logs are separate; clearing local logs never deletes server records.
  function renderLogList(container, records, emptyText) {
    if (!container) return;
    container.replaceChildren();
    if (!records.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = emptyText;
      container.appendChild(empty);
      return;
    }
    for (const record of records) {
      const entry = document.createElement('article');
      entry.className = 'log-entry';
      const time = document.createElement('span');
      time.className = 'log-time';
      const rawTime = record.time || record.created_at;
      const parsedTime = rawTime ? new Date(rawTime) : null;
      time.textContent = parsedTime && !Number.isNaN(parsedTime.getTime()) ? parsedTime.toLocaleString() : 'Time unavailable';
      const label = document.createElement('span');
      label.className = 'log-level ' + String(record.level || 'info').replace(/[^a-z_-]/g, '');
      label.textContent = '[' + String(record.level || record.kind || 'info') + ']';
      const message = document.createElement('div');
      message.className = 'log-message';
      message.textContent = String(record.message || record.kind || 'Event') + (record.run_id ? ' · run ' + record.run_id : '');
      if (record.payload && Object.keys(record.payload).length) {
        const details = document.createElement('pre');
        details.textContent = JSON.stringify(record.payload, null, 2);
        entry.append(time, document.createTextNode(' '), label, message, details);
      } else {
        entry.append(time, document.createTextNode(' '), label, message);
      }
      container.appendChild(entry);
    }
  }

  function renderLocalLogs() {
    renderLogList($('#agent-log'), storedLogs.slice(0, 60), 'No activity yet. Create a run to see agent activity.');
    renderLogList($('#logs-list'), storedLogs, 'No local events recorded yet.');
  }

  async function loadLogs() {
    renderLocalLogs();
    const container = $('#server-audit-list');
    if (!token || !apiBase) {
      renderLogList(container, [], 'Connect to the backend with a signed JWT carrying runs:read to load server audit records.');
      return;
    }
    try {
      const response = await api('/v1/events?limit=100');
      const events = await response.json();
      serverAuditEvents = Array.isArray(events) ? events : [];
      renderLogList(container, serverAuditEvents.map((event) => ({
        created_at: event.created_at,
        kind: event.kind,
        run_id: event.run_id,
        payload: event.payload,
        message: event.kind,
        level: String(event.kind || '').includes('failed') ? 'error' : 'info',
      })), 'The server returned no audit events for this tenant.');
    } catch (error) {
      serverAuditEvents = [];
      renderLogList(container, [], 'Server audit log unavailable: ' + (error.message || String(error)));
    }
  }

  $('#logs-refresh').addEventListener('click', loadLogs);
  $('#logs-clear').addEventListener('click', () => {
    if (!window.confirm('Clear local app logs from this device? Server audit records will remain unchanged.')) return;
    storedLogs = [];
    try { localStorage.removeItem(LOCAL_LOG_KEY); } catch (_) {}
    renderLocalLogs();
  });
  $('#logs-export').addEventListener('click', () => {
    const payload = {
      app: 'OMEGA-X ASCENSION',
      version: '0.7.0',
      exported_at: new Date().toISOString(),
      local_events: storedLogs,
      server_audit_events: serverAuditEvents,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'omega-x-logs.json';
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    addAgentLog('success', 'Exported local and currently loaded server logs.');
  });

  // Device-persistent app log with a bounded 200-record retention limit.
  function addAgentLog(level, message) {
    const record = {
      time: new Date().toISOString(),
      level: String(level || 'info').slice(0, 20),
      message: String(message || '').slice(0, 2000),
    };
    storedLogs.unshift(record);
    storedLogs = storedLogs.slice(0, 200);
    try { localStorage.setItem(LOCAL_LOG_KEY, JSON.stringify(storedLogs)); } catch (_) {}
    renderLocalLogs();
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  if (window.matchMedia('(max-width: 720px)').matches && !apiBase && !token) {
    const connectionDetails = $('#connection-details');
    if (connectionDetails) connectionDetails.open = false;
  }
  renderLocalLogs();
  $('#about-runtime-status').textContent = 'Runtime connectivity has not yet been verified.';
  startPolling();
  loadRuns();
})();
