// ─────────────────────────────────────────────────────────────────────────────
//  GLOMOS live panel (ELAYA v2)
//  Backend: POST /api/glomos/start → {job_id}; GET /api/glomos/poll/<id>?cursor=n;
//           POST /api/glomos/cancel/<id>; GET /api/glomos/result/<id>[?format=xyz]
//  Events are structured JSON from the server (no text scraping).
//  runGlomosWithStream(smiles, params, onDone(bestXyz, result), onError(msg), onSelect(conf))
//  returns { cancel() }.
// ─────────────────────────────────────────────────────────────────────────────

function _gl(id) { return document.getElementById(id); }

function _glEsc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function _glFmtTime(secs) {
  if (!isFinite(secs) || secs < 0) return '—';
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function _glInjectStyles() {
  if (_gl('glomos-styles')) return;
  const style = document.createElement('style');
  style.id = 'glomos-styles';
  style.textContent = `
    #glomos-live-panel { margin: 1rem 0; font-family: Inter, system-ui, sans-serif; }
    .glomos-panel-inner { background:#0d1b2a; border:1px solid #1e3a52; border-radius:12px; padding:1rem 1.2rem; color:#c9d8e8; }
    .glomos-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:.75rem; gap:.5rem; }
    .glomos-header .glomos-title { font-weight:600; font-size:.95rem; color:#e0eaf5; }
    .glomos-actions { display:flex; gap:.5rem; align-items:center; }
    .glomos-badge { font-size:.72rem; font-weight:600; padding:2px 10px; border-radius:99px; letter-spacing:.03em; }
    .glomos-badge.running  { background:#0f6975; color:#9fe1cb; }
    .glomos-badge.queued   { background:#3a3a1a; color:#e6d97a; }
    .glomos-badge.done     { background:#1a4a1f; color:#6ed87a; }
    .glomos-badge.partial  { background:#4a3a15; color:#f0c070; }
    .glomos-badge.error    { background:#4a1515; color:#f08080; }
    .glomos-btn { background:none; border:1px solid #1e3a52; border-radius:6px; color:#8bafc9; font-size:.74rem; padding:3px 10px; cursor:pointer; }
    .glomos-btn:hover { color:#e0eaf5; border-color:#3cb49a; }
    .glomos-btn.danger:hover { border-color:#f08080; color:#f08080; }
    .glomos-btn:disabled { opacity:.4; cursor:default; }
    .glomos-progress-row { display:flex; justify-content:space-between; font-size:.8rem; margin-bottom:.4rem; color:#8bafc9; gap:1rem; }
    .glomos-gen-label { font-weight:600; color:#3cb49a; }
    .glomos-bar-track { background:#1a2d40; border-radius:6px; height:8px; overflow:hidden; margin-bottom:.9rem; }
    .glomos-bar-fill { height:100%; background:linear-gradient(90deg,#0f6975,#3cb49a); border-radius:6px; transition:width .6s ease; }
    .glomos-stats-row { display:flex; gap:1.5rem; margin-bottom:.9rem; flex-wrap:wrap; }
    .glomos-stat { display:flex; flex-direction:column; gap:1px; }
    .glomos-stat-label { font-size:.7rem; color:#5a7a95; text-transform:uppercase; letter-spacing:.06em; }
    .glomos-stat-value { font-size:.88rem; font-weight:600; color:#c9d8e8; font-variant-numeric:tabular-nums; }
    .glomos-notes { font-size:.76rem; color:#f0c070; margin-bottom:.7rem; line-height:1.5; }
    .glomos-notes.info { color:#8bafc9; }
    .glomos-log-header { display:flex; justify-content:space-between; align-items:center; font-size:.72rem; color:#5a7a95; text-transform:uppercase; letter-spacing:.06em; margin-bottom:.3rem; }
    .glomos-log-box { background:#060e17; border:1px solid #132030; border-radius:8px; height:140px; overflow-y:auto; padding:.5rem .75rem; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.72rem; line-height:1.6; color:#6fa8c8; }
    .glomos-log-line-gen { color:#3cb49a; font-weight:600; }
    .glomos-log-line-energy { color:#f0b429; }
    .glomos-log-line-warning { color:#e8784a; }
    .glomos-table-wrap { margin:.6rem 0 .4rem; max-height:236px; overflow:auto; border:1px solid #132030; border-radius:8px; }
    table.glomos-table { width:100%; border-collapse:collapse; font-size:.76rem; font-variant-numeric:tabular-nums; }
    .glomos-table th { position:sticky; top:0; background:#122234; color:#8bafc9; font-weight:600; text-align:right; padding:5px 8px; }
    .glomos-table td { text-align:right; padding:4px 8px; border-top:1px solid #132030; }
    .glomos-table th:nth-child(1), .glomos-table td:nth-child(1), .glomos-table th:nth-child(2), .glomos-table td:nth-child(2) { text-align:left; }
    .glomos-table tbody tr { cursor:pointer; }
    .glomos-table tbody tr:hover { background:#16304a; }
    .glomos-table tbody tr.selected { background:#0f4a55; color:#fff; }
    .glomos-export { display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; margin-top:.4rem; font-size:.76rem; }
    .glomos-lab { margin:0 0 .7rem; padding:.45rem .7rem; background:#060e17; border:1px solid #132030; border-radius:8px;
                  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.74rem; line-height:1.25;
                  color:#98ebc4; white-space:pre; overflow:hidden; cursor:pointer; user-select:none; }
    .glomos-stats-row { display:grid !important; grid-template-columns:repeat(5,minmax(0,1fr)); gap:.4rem .8rem !important; }
    .glomos-stat-value { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .glomos-export select { background:#0d1b2a; color:#c9d8e8; border:1px solid #1e3a52; border-radius:6px; padding:3px 6px; }
  `;
  document.head.appendChild(style);
}


// ── ASCII lab: shown while a job runs, driven by the real events ─────────────────────────────
//   left worker spins bonds (new candidates), the belt carries them, the right worker relaxes
//   them with ANI and stamps them. Each 'optimized' event puts a molecule on the belt; a new
//   generation makes both cheer. Click the scene to say hi.
function _glAsciiLab(pre) {
  const W = 46;                                   // characters per line
  const GLYPHS = ['o-o', 'o=o', '<o>', 'o~o', 'o-<', '>o<'];
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let tick = 0, items = [], pending = 0, stamped = 0, relaxed = 0, cheer = 0, wave = 0, gen = 0, phase = 'load', timer = null;
  const BELT0 = 7, BELT1 = 37;                     // belt between the two workers

  const left = () => {
    if (cheer > 0 || wave > 0) return ['\\o/', ' | ', '/ \\'];
    const f = Math.floor(tick / 3) % 4;          // spinning a bond
    return [[' o_', ' o ', '_o ', ' o '][f], ['/| ', '/|\\', ' |\\', '/|\\'][f], ['/ \\', '| |', '/ \\', '| |'][f]];
  };
  const right = () => {
    if (cheer > 0 || wave > 0) return ['\\o/', ' | ', '/ \\'];
    const busy = items.some(it => it.x >= BELT1 - 4);
    const f = busy ? Math.floor(tick / 2) % 2 : 0;  // stamping
    return [[' o ', ' o_'][f], ['/|\\', '/|'][f] .padEnd(3), ['/ \\', '/ \\'][f]];
  };

  function frame() {
    tick++;
    if (cheer > 0) cheer--;
    if (wave > 0) wave--;
    if (phase === 'run') {
      if (pending > 0 && !items.some(it => it.x < BELT0 + 5)) { items.push({ x: BELT0, g: GLYPHS[(stamped + pending) % GLYPHS.length] }); pending--; }
      else if (!items.length && tick % 28 === 0) items.push({ x: BELT0, g: GLYPHS[tick % GLYPHS.length], idle: true });
      items.forEach(it => { it.x += 1; });
      items = items.filter(it => {
        if (it.x >= BELT1 - 2) { if (!it.idle) stamped++; return false; }
        return true;
      });
    }
    const L = left(), R = right();
    const row = Array(W).fill(' ');
    items.forEach(it => { for (let k = 0; k < it.g.length; k++) if (it.x + k < BELT1 - 1) row[it.x + k] = it.g[k]; });
    const belt = Array(W).fill(' ');
    for (let k = BELT0 - 1; k < BELT1; k++) belt[k] = (phase === 'run' ? ((k + tick) % 4 === 0 ? '=' : '-') : '-');
    const pile = '✓'.repeat(Math.min(stamped, 6)) + (stamped > 6 ? '+' : '');
    const place = (arr, col, str) => { for (let k = 0; k < str.length; k++) arr[col + k] = str[k]; return arr; };
    let status;
    if (phase === 'load') status = `  loading the ANI model${'.'.repeat(1 + (tick >> 2) % 3)}`;
    else if (phase === 'polish') status = '  final tight re-optimisation...';
    else status = `  generation ${gen} · relaxed ${relaxed}${cheer > 0 ? '   NEW GENERATION!' : wave > 0 ? '   hi! :)' : ''}`;
    const l1 = place(place(row.slice(), 1, L[0]), BELT1 + 2, R[0]).join('');
    const l2 = place(place(belt.slice(), 1, L[1]), BELT1 + 2, R[1]).join('');
    const l3 = place(place(Array(W).fill(' '), 1, L[2]), BELT1 + 2, R[2]).join('') + ' ' + pile;
    pre.textContent = [status.padEnd(W), l1, l2, l3].join('\n');
  }

  pre.addEventListener('click', () => { wave = 10; frame(); });
  const api = {
    start() { if (!timer) { frame(); if (!reduce) timer = setInterval(frame, 140); } },
    stop() { clearInterval(timer); timer = null; },
    running() { phase = 'run'; },
    optimized() { phase = 'run'; relaxed++; pending = Math.min(pending + 1, 8); if (reduce) { stamped++; frame(); } },
    generation(g) { if (g !== gen) { gen = g; if (g > 0) cheer = 14; } },
    polish() { phase = 'polish'; },
  };
  return api;
}

function createGlomosPanel() {
  _glInjectStyles();
  _gl('glomos-live-panel')?.remove();
  const panel = document.createElement('div');
  panel.id = 'glomos-live-panel';
  panel.innerHTML = `
    <div class="glomos-panel-inner">
      <div class="glomos-header">
        <span class="glomos-title">GLOMOS — Conformational search</span>
        <span class="glomos-actions">
          <button class="glomos-btn danger" id="gl-cancel">Cancel</button>
          <span id="gl-badge" class="glomos-badge queued">Starting</span>
        </span>
      </div>
      <pre id="gl-lab" class="glomos-lab" title="GLOMOS is working — click to say hi" aria-label="GLOMOS is running"></pre>
      <div id="gl-notes"></div>
      <div class="glomos-progress-row">
        <span id="gl-gen" class="glomos-gen-label">Preparing…</span>
        <span id="gl-eta">&nbsp;</span>
      </div>
      <div class="glomos-bar-track"><div id="gl-bar" class="glomos-bar-fill" style="width:0%"></div></div>
      <div class="glomos-stats-row">
        <div class="glomos-stat"><span class="glomos-stat-label">Elapsed</span><span id="gl-elapsed" class="glomos-stat-value">0:00</span></div>
        <div class="glomos-stat"><span class="glomos-stat-label" title="ANI electronic energy of the best structure">Best E (kcal/mol)</span><span id="gl-best" class="glomos-stat-value">—</span></div>
        <div class="glomos-stat"><span class="glomos-stat-label">Rotors</span><span id="gl-rotors" class="glomos-stat-value">—</span></div>
        <div class="glomos-stat"><span class="glomos-stat-label">Model</span><span id="gl-model" class="glomos-stat-value">—</span></div>
        <div class="glomos-stat"><span class="glomos-stat-label">Evaluated</span><span id="gl-evals" class="glomos-stat-value">0</span></div>
      </div>
      <div id="gl-results"></div>
      <div class="glomos-log-header">
        <span>Log</span>
        <span><button class="glomos-btn" id="gl-log-toggle">Hide</button>
              <button class="glomos-btn" id="gl-log-copy">Copy</button></span>
      </div>
      <div id="gl-log" class="glomos-log-box"></div>
    </div>`;
  return panel;
}

function classifyLogLine(line) {
  if (/GENERATION/i.test(line)) return 'glomos-log-line-gen';
  if (/^#\d+\s/.test(line)) return 'glomos-log-line-energy';
  if (/warning|error|discard|failed/i.test(line)) return 'glomos-log-line-warning';
  return '';
}

function _glDownload(name, text, mime) {
  const blob = new Blob([text], { type: mime || 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

function runGlomosWithStream(smiles, glomosParams, onDone, onError, onSelect) {
  window.ELAYA_CONFORMERS = null;          // a new job: the previous conformer set no longer applies
  const panel = createGlomosPanel();
  const container = document.querySelector('.visualization-controls')
                 || document.querySelector('.conversion-section')
                 || document.body;
  container.prepend(panel);

  const el = {
    badge: _gl('gl-badge'), gen: _gl('gl-gen'), eta: _gl('gl-eta'), bar: _gl('gl-bar'),
    elapsed: _gl('gl-elapsed'), best: _gl('gl-best'), rotors: _gl('gl-rotors'), model: _gl('gl-model'),
    evals: _gl('gl-evals'), log: _gl('gl-log'), notes: _gl('gl-notes'), results: _gl('gl-results'),
    cancel: _gl('gl-cancel'),
  };
  const lab = _glAsciiLab(_gl('gl-lab'));
  lab.start();
  const t0 = Date.now();
  let jobId = null, cursor = 0, stopped = false, timer = null, errors = 0, nEval = 0, gatewayErrors = 0;
  let totalGen = glomosParams.generations ?? 3;
  let genTimes = [];

  const clock = setInterval(() => { el.elapsed.textContent = _glFmtTime((Date.now() - t0) / 1000); }, 1000);
  const setBadge = (cls, text) => { el.badge.className = 'glomos-badge ' + cls; el.badge.textContent = text; el.badge.style.display = ''; };
  const addLog = (line) => {
    const d = document.createElement('div');
    const c = classifyLogLine(line); if (c) d.className = c;
    d.textContent = line;
    el.log.appendChild(d);
    if (el.log.childElementCount > 600) el.log.firstChild.remove();
    el.log.scrollTop = el.log.scrollHeight;
  };
  const notes = (items, cls) => {
    if (!items || !items.length) return;
    const div = document.createElement('div');
    div.className = 'glomos-notes ' + (cls || '');
    div.innerHTML = items.map(t => '• ' + _glEsc(t)).join('<br>');
    el.notes.appendChild(div);
  };

  _gl('gl-log-toggle').onclick = (e) => {
    const hidden = el.log.style.display === 'none';
    el.log.style.display = hidden ? '' : 'none';
    e.target.textContent = hidden ? 'Hide' : 'Show';
  };
  _gl('gl-log-copy').onclick = () => {
    const text = Array.from(el.log.children).map(d => d.textContent).join('\n');
    navigator.clipboard?.writeText(text).catch(() => {});
  };

  function finishClock() {
    clearInterval(clock); if (timer) clearTimeout(timer); el.cancel.disabled = true;
    lab.stop(); const p = _gl('gl-lab'); if (p) p.style.display = 'none';      // the scene only lives while it runs
  }

  function fail(msg) {
    if (stopped) return;
    stopped = true; finishClock();
    setBadge('error', 'Error');
    el.eta.textContent = msg;
    addLog('ERROR: ' + msg);
    if (onError) onError(msg);
  }

  el.cancel.onclick = () => ctrl.cancel();
  const ctrl = {
    cancel() {
      if (!jobId || stopped) return;
      el.cancel.disabled = true;
      el.eta.textContent = 'Cancelling…';
      fetch(`/api/glomos/cancel/${jobId}`, { method: 'POST' }).catch(() => {});
    },
  };

  // 1) start
  fetch('/api/glomos/start', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ smiles, glomos_params: glomosParams }),
  })
    .then(async r => {
      let data = {};
      try { data = await r.json(); } catch (e) { /* non-JSON error page */ }
      if (!r.ok || data.error) throw new Error(data.error || `Server error (HTTP ${r.status})`);
      return data;
    })
    .then(data => {
      jobId = data.job_id;
      el.model.textContent = data.model || '—';
      el.rotors.textContent = data.n_rotors ?? '—';
      totalGen = (data.params && data.params.generations) ?? totalGen;
      notes(data.notes, 'info');
      notes(data.warnings);
      if (data.n_rotors === 0) notes(['No rotatable torsions: only the starting conformers (rings) are explored.'], 'info');
      schedule(600);
    })
    .catch(err => fail(err.message));

  function schedule(ms) { if (!stopped) timer = setTimeout(poll, ms); }

  function poll() {
    if (stopped) return;
    fetch(`/api/glomos/poll/${jobId}?cursor=${cursor}`)
      .then(async r => {
        if (r.status === 404) {
          const msg = gatewayErrors
            ? 'The server restarted while the job was running (most likely it ran out of memory: GLOMOS needs ~1 GB of RAM). Try again, or use the "fast" preset.'
            : 'The job no longer exists on the server (it expired or the server restarted).';
          throw Object.assign(new Error(msg), { fatal: true });
        }
        if (!r.ok) {
          let detail = '';
          try { const j = await r.json(); detail = j && j.error ? `: ${j.error}` : ''; } catch (e) { /* HTML from a proxy */ }
          if (r.status === 502 || r.status === 503 || r.status === 504) {
            gatewayErrors += 1;
            throw new Error(`server not responding (HTTP ${r.status}, it may be restarting)`);
          }
          throw new Error(`Poll HTTP ${r.status}${detail}`);
        }
        return r.json();
      })
      .then(data => {
        errors = 0;
        cursor = data.cursor;
        for (const e of data.events) handle(e);
        if (data.status === 'queued') {
          setBadge('queued', 'Queued');
          el.gen.textContent = `Waiting in queue (position ${data.queue_position || 1})`;
        } else if (data.status === 'running') {
          setBadge('running', 'Running');
          el.badge.style.display = 'none';          // the ASCII scene says it better
        }
        if (data.done) return conclude(data);
        schedule(1000);
      })
      .catch(err => {
        if (err.fatal) return fail(err.message);
        errors += 1;
        if (errors > 20) return fail('Lost connection to the server: ' + err.message +
          (gatewayErrors ? ' — the server kept failing while the job ran; it most likely ran out of memory (GLOMOS needs ~1 GB of RAM).' : ''));
        el.eta.textContent = `Reconnecting… (${errors})`;
        schedule(Math.min(2000 * errors, 15000));
      });
  }

  function handle(e) {
    switch (e.type) {
      case 'start':
        lab.running();
        totalGen = e.generations ?? totalGen;
        if (e.n_rotors != null) el.rotors.textContent = e.n_rotors;
        if (e.model) el.model.textContent = e.model;
        break;
      case 'log': addLog(e.line); break;
      case 'optimized': nEval += 1; el.evals.textContent = nEval; lab.optimized(); break;
      case 'progress': {
        const gen = e.gen ?? 0, of = e.of || 1, done = e.done || 0;
        lab.running(); lab.generation(gen);
        const pct = Math.min(99, Math.round(((gen + done / of) / (totalGen + 1)) * 100));
        el.bar.style.width = pct + '%';
        el.gen.textContent = gen === 0 ? 'Generation 0 (initial population)' : `Generation ${gen} / ${totalGen}`;
        if (e.best_energy != null) el.best.textContent = e.best_energy.toFixed(3);
        genTimes = e.gen_times || genTimes;
        if (genTimes.length && gen < totalGen) {
          const avg = genTimes.reduce((a, b) => a + b, 0) / genTimes.length;
          el.eta.textContent = `ETA ≤ ~${_glFmtTime(avg * (totalGen - gen))}`;
        }
        break;
      }
      case 'phase':
        if (e.name === 'polish') { el.gen.textContent = 'Final tight re-optimisation…'; lab.polish(); }
        break;
      case 'error': addLog('ERROR: ' + (e.message || '')); break;
      default: break;
    }
  }

  function conclude(data) {
    if (stopped) return;
    stopped = true; finishClock();
    if (data.status === 'error') {
      setBadge('error', 'Error');
      el.eta.textContent = data.error || 'GLOMOS failed';
      if (onError) onError(data.error || 'GLOMOS failed');
      return;
    }
    fetch(`/api/glomos/result/${jobId}`)
      .then(r => r.json())
      .then(res => {
        if (res.error) throw new Error(res.error);
        el.bar.style.width = '100%';
        const partial = data.status !== 'done';
        setBadge(partial ? 'partial' : 'done', data.status === 'cancelled' ? 'Cancelled (partial)' : data.status === 'timeout' ? 'Time limit (partial)' : 'Done');
        const m = res.meta || {};
        el.eta.textContent = `Finished in ${_glFmtTime((Date.now() - t0) / 1000)}` +
          (m.stop_reason === 'stagnation' ? ' (converged: lowest structures stopped changing)' : '');
        el.gen.textContent = `${res.conformers.length} conformer(s) · ${m.n_evaluated ?? nEval} ANI relaxations · seed ${m.random_seed ?? '?'}`;
        renderResults(res);
        el.log.style.display = 'none';                       // results first; the log is one click away
        _gl('gl-log-toggle').textContent = 'Show';
        try {   // lets the page estimate the duration of the next run on this server
          const atoms = parseInt(String(res.conformers[0]?.xyz || '').split('\n')[0], 10) || 0;
          window.dispatchEvent(new CustomEvent('elaya:glomos-done', { detail: {
            seconds: (Date.now() - t0) / 1000, n_evaluated: m.n_evaluated ?? nEval, atoms,
            screening: m.screening || 'ensemble', status: data.status } }));
        } catch (e) { /* informative only */ }
        const best = res.conformers[0];
        if (onDone) onDone(best.xyz, res);
      })
      .catch(err => { setBadge('error', 'Error'); el.eta.textContent = err.message; if (onError) onError(err.message); });
  }

  function renderResults(res) {
    const c = res.conformers;
    const rows = c.map((x, i) => {
      const rc = x.rotational_constants || {};
      const g = v => (v == null ? '—' : v.toFixed(3));
      return `<tr data-i="${i}" class="${i === 0 ? 'selected' : ''}">
        <td>${i + 1}</td><td>${_glEsc(x.name)}</td><td>${x.rel_kcal.toFixed(3)}</td>
        <td>${(100 * x.boltzmann_298).toFixed(1)}</td><td>${g(rc.A_GHz)}</td><td>${g(rc.B_GHz)}</td><td>${g(rc.C_GHz)}</td></tr>`;
    }).join('');
    el.results.innerHTML = `
      <div class="glomos-table-wrap"><table class="glomos-table">
        <thead><tr><th>#</th><th>Name</th><th>ΔE (kcal/mol)</th><th>Pop. 298 K (%)</th><th>A (GHz)</th><th>B (GHz)</th><th>C (GHz)</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <div class="glomos-notes info">Relative ANI electronic energies (no ZPE/thermal corrections): populations are indicative.
        Click a row to show it in the viewer.</div>
      <div class="glomos-export">
        <button class="glomos-btn" id="gl-dl-all">Download all (multi-XYZ)</button>
        <button class="glomos-btn" id="gl-dl-json">Download results (JSON)</button>
        <span class="gl-export-hint">Other formats (MOL, SDF, PDB, MOL2, CML) and .zip of all conformers: structure card below.</span>
      </div>`;
    let sel = 0;
    const select = (i) => {
      if (!(i >= 0 && i < c.length)) return;
      sel = i;
      el.results.querySelectorAll('tbody tr').forEach(r => r.classList.toggle('selected', Number(r.dataset.i) === i));
      el.results.querySelector(`tbody tr[data-i="${i}"]`)?.scrollIntoView({ block: 'nearest' });
      if (window.ELAYA_CONFORMERS && window.ELAYA_CONFORMERS.list === c) window.ELAYA_CONFORMERS.index = i;
      if (onSelect) onSelect(c[i], i, res);
    };
    // shared with the viewer: conformer bar, keyboard arrows and format tabs use the same set
    window.ELAYA_CONFORMERS = { list: c, smiles, result: res, index: 0, select };
    el.results.querySelectorAll('tbody tr').forEach(tr => tr.addEventListener('click', () => select(Number(tr.dataset.i))));
    _gl('gl-dl-all').onclick = () => _glDownload('elaya_conformers.xyz', c.map(x => x.xyz).join(''), 'chemical/x-xyz');
    _gl('gl-dl-json').onclick = () => _glDownload('elaya_glomos_result.json', JSON.stringify(res, null, 2), 'application/json');
  }

  return ctrl;
}

// kept for backward compatibility with older markup
function toggleGlomosLog() { _gl('gl-log-toggle')?.click(); }
function copyGlomosLog() { _gl('gl-log-copy')?.click(); }

window.runGlomosWithStream = runGlomosWithStream;
