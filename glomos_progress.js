// ─────────────────────────────────────────────────────────────
//  GLOMOS Live Progress Panel  —  polling edition
//  Compatible con Waitress / cualquier WSGI server (sin SSE).
//  API: POST /api/glomos/start  → { job_id }
//       GET  /api/glomos/poll/<job_id>?cursor=N → { events, cursor, done }
// ─────────────────────────────────────────────────────────────

// ── Panel HTML ───────────────────────────────────────────────
function createGlomosPanel() {
  document.getElementById('glomos-live-panel')?.remove();

  const panel = document.createElement('div');
  panel.id = 'glomos-live-panel';
  panel.innerHTML = `
    <div class="glomos-panel-inner">
      <div class="glomos-header">
        <span class="glomos-title">GLOMOS — Conformational Search</span>
        <span id="glomos-status-badge" class="glomos-badge running">Running</span>
      </div>

      <div class="glomos-progress-row">
        <span id="glomos-gen-label" class="glomos-gen-label">Generation 0</span>
        <span id="glomos-eta" class="glomos-eta">Estimating time…</span>
      </div>

      <div class="glomos-bar-track">
        <div id="glomos-bar-fill" class="glomos-bar-fill" style="width:0%"></div>
      </div>

      <div class="glomos-stats-row">
        <div class="glomos-stat">
          <span class="glomos-stat-label">Elapsed</span>
          <span id="glomos-elapsed" class="glomos-stat-value">0:00</span>
        </div>
        <div class="glomos-stat">
          <span class="glomos-stat-label">Best energy</span>
          <span id="glomos-energy" class="glomos-stat-value">—</span>
        </div>
        <div class="glomos-stat">
          <span class="glomos-stat-label">Conformer</span>
          <span id="glomos-conformer" class="glomos-stat-value">—</span>
        </div>
      </div>

      <div class="glomos-log-header">
        <span>Live log</span>
        <button class="glomos-log-toggle" id="glomos-log-toggle" onclick="toggleGlomosLog()">Hide</button>
      </div>
      <div id="glomos-log-box" class="glomos-log-box"></div>
    </div>
  `;

  if (!document.getElementById('glomos-styles')) {
    const style = document.createElement('style');
    style.id = 'glomos-styles';
    style.textContent = `
      #glomos-live-panel {
        margin: 1rem 0;
        font-family: Inter, system-ui, sans-serif;
      }
      .glomos-panel-inner {
        background: #0d1b2a;
        border: 1px solid #1e3a52;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        color: #c9d8e8;
      }
      .glomos-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.75rem;
      }
      .glomos-title { font-weight: 600; font-size: 0.95rem; color: #e0eaf5; }
      .glomos-badge { font-size: 0.72rem; font-weight: 600; padding: 2px 10px; border-radius: 99px; letter-spacing: 0.03em; }
      .glomos-badge.running  { background: #0f6975; color: #9fe1cb; }
      .glomos-badge.done     { background: #1a4a1f; color: #6ed87a; }
      .glomos-badge.error    { background: #4a1515; color: #f08080; }
      .glomos-progress-row { display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 0.4rem; color: #8bafc9; }
      .glomos-gen-label { font-weight: 600; color: #3cb49a; }
      .glomos-eta { color: #7a9ab5; }
      .glomos-bar-track { background: #1a2d40; border-radius: 6px; height: 8px; overflow: hidden; margin-bottom: 0.9rem; }
      .glomos-bar-fill { height: 100%; background: linear-gradient(90deg, #0f6975, #3cb49a); border-radius: 6px; transition: width 0.6s ease; }
      .glomos-stats-row { display: flex; gap: 1.5rem; margin-bottom: 0.9rem; flex-wrap: wrap; }
      .glomos-stat { display: flex; flex-direction: column; gap: 1px; }
      .glomos-stat-label { font-size: 0.7rem; color: #5a7a95; text-transform: uppercase; letter-spacing: 0.06em; }
      .glomos-stat-value { font-size: 0.88rem; font-weight: 600; color: #c9d8e8; font-variant-numeric: tabular-nums; }
      .glomos-log-header { display: flex; justify-content: space-between; align-items: center; font-size: 0.72rem; color: #5a7a95; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.3rem; }
      .glomos-log-toggle { background: none; border: 1px solid #1e3a52; border-radius: 4px; color: #5a7a95; font-size: 0.7rem; padding: 1px 8px; cursor: pointer; }
      .glomos-log-toggle:hover { color: #8bafc9; border-color: #3cb49a; }
      .glomos-log-box { background: #060e17; border: 1px solid #132030; border-radius: 8px; height: 160px; overflow-y: auto; padding: 0.5rem 0.75rem; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.72rem; line-height: 1.6; color: #6fa8c8; scroll-behavior: smooth; }
      .glomos-log-line-gen       { color: #3cb49a; font-weight: 600; }
      .glomos-log-line-energy    { color: #f0b429; }
      .glomos-log-line-conformer { color: #a78bfa; }
      .glomos-log-line-warning   { color: #e8784a; }
      .glomos-log-line-default   { color: #6fa8c8; }
    `;
    document.head.appendChild(style);
  }

  return panel;
}

// ── Helpers ───────────────────────────────────────────────────
function classifyLogLine(line) {
  if (/GENERATION/i.test(line))                   return 'glomos-log-line-gen';
  if (/#\d+\s+\S+\s+-[\d.]+\s+kcal/.test(line))  return 'glomos-log-line-energy';
  if (/(random|mating|mutant)_\d+/i.test(line))  return 'glomos-log-line-conformer';
  if (/warning|error/i.test(line))                return 'glomos-log-line-warning';
  return 'glomos-log-line-default';
}

function toggleGlomosLog() {
  const box = document.getElementById('glomos-log-box');
  const btn = document.getElementById('glomos-log-toggle');
  if (!box) return;
  const hidden = box.style.display === 'none';
  box.style.display = hidden ? '' : 'none';
  btn.textContent   = hidden ? 'Hide' : 'Show';
}

function fmtTime(secs) {
  if (!isFinite(secs) || secs < 0) return '—';
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

// ── Main function: polling-based ─────────────────────────────
function runGlomosWithStream(smiles, glomosParams, onDone, onError) {
  // 1) Insert panel
  const panel = createGlomosPanel();
  const container = document.querySelector('.visualization-controls')
                 || document.querySelector('.conversion-section')
                 || document.body;
  container.prepend(panel);

  // 2) DOM refs
  const elBadge     = document.getElementById('glomos-status-badge');
  const elGenLabel  = document.getElementById('glomos-gen-label');
  const elEta       = document.getElementById('glomos-eta');
  const elBar       = document.getElementById('glomos-bar-fill');
  const elElapsed   = document.getElementById('glomos-elapsed');
  const elEnergy    = document.getElementById('glomos-energy');
  const elConformer = document.getElementById('glomos-conformer');
  const elLog       = document.getElementById('glomos-log-box');

  const startTime = Date.now();
  let totalGenerations = glomosParams.generations || 3;
  let cursor = 0;
  let pollTimer = null;
  let stopped = false;

  // Wall-clock ticker
  const clockInterval = setInterval(() => {
    elElapsed.textContent = fmtTime((Date.now() - startTime) / 1000);
  }, 1000);

  function stop(isError) {
    if (stopped) return;
    stopped = true;
    clearInterval(clockInterval);
    if (pollTimer) clearTimeout(pollTimer);
    if (isError) {
      elBadge.className = 'glomos-badge error';
      elBadge.textContent = 'Error';
    }
  }

  // 3) Start the job on the backend
  fetch('/api/glomos/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ smiles, glomos_params: glomosParams }),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) throw new Error(data.error);
    schedulePoll(data.job_id);
  })
  .catch(err => {
    stop(true);
    elEta.textContent = err.message;
    if (onError) onError(err.message);
  });

  // 4) Polling loop
  function schedulePoll(jobId) {
    if (stopped) return;
    pollTimer = setTimeout(() => poll(jobId), 800);
  }

  function poll(jobId) {
    if (stopped) return;
    fetch(`/api/glomos/poll/${jobId}?cursor=${cursor}`)
      .then(r => {
        if (!r.ok) throw new Error(`Poll HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        if (data.error) throw new Error(data.error);

        // Process all new events
        for (const evt of data.events) {
          handleEvent(evt);
          if (stopped) return; // error event may have stopped us
        }
        cursor = data.cursor;

        if (!data.done) {
          schedulePoll(jobId);
        }
        // If done, handleEvent('done') already called onDone
      })
      .catch(err => {
        stop(true);
        elEta.textContent = 'Connection error: ' + err.message;
        if (onError) onError(err.message);
      });
  }

  // 5) Event handler (same logic as before)
  function handleEvent(evt) {
    if (evt.type === 'start') {
      totalGenerations = evt.generations || totalGenerations;
    }

    else if (evt.type === 'log') {
      const div = document.createElement('div');
      div.className = classifyLogLine(evt.line);
      div.textContent = evt.line;
      elLog.appendChild(div);
      elLog.scrollTop = elLog.scrollHeight;
    }

    else if (evt.type === 'progress') {
      const gen   = evt.gen ?? 0;
      const total = evt.total || totalGenerations;
      const pct   = Math.min(100, Math.round((gen / total) * 100));

      elGenLabel.textContent = `Generation ${gen} / ${total}`;
      elBar.style.width = `${pct}%`;

      if (evt.best_energy != null) {
        elEnergy.textContent = `${evt.best_energy.toFixed(2)} kcal/mol`;
      }
      if (evt.conformer) {
        elConformer.textContent = evt.conformer;
      }
      if (evt.gen_times && evt.gen_times.length > 0 && gen < total) {
        const avg = evt.gen_times.reduce((a, b) => a + b, 0) / evt.gen_times.length;
        elEta.textContent = `ETA ~${fmtTime(avg * (total - gen))}`;
      }
    }

    else if (evt.type === 'done') {
      stop(false);
      elBadge.className = 'glomos-badge done';
      elBadge.textContent = 'Done';
      elGenLabel.textContent = `Generation ${totalGenerations} / ${totalGenerations}`;
      elBar.style.width = '100%';
      elEta.textContent = `Finished in ${fmtTime((Date.now() - startTime) / 1000)}`;
      elConformer.textContent = 'Best conformer selected';
      if (onDone) onDone(evt.xyz);
    }

    else if (evt.type === 'loading') {
      elBadge.className = 'glomos-badge running';
      elBadge.textContent = 'Loading';
      elGenLabel.textContent = evt.message || 'Loading TorchANI…';
      elEta.textContent = 'Please wait…';
    }

    else if (evt.type === 'heartbeat') {
      elEta.textContent = `Processing… (${evt.elapsed}s)`;
    }

    else if (evt.type === 'error') {
      stop(true);
      elEta.textContent = evt.message;
      if (onError) onError(evt.message);
    }
  }
}

window.runGlomosWithStream = runGlomosWithStream;