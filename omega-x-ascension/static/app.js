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
      apiBase = normalizeApiBase($('#api-base').value);
      localStorage.setItem('omega-api-base', apiBase);
      $('#api-base').value = apiBase;
      startPolling();
      if (token) loadRuns();
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
