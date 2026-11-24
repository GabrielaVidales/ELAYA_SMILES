/*
 * structure_panel.js — the structure card under/next to the 3D viewer.
 *
 *  - Title of what is on screen ("Conformer 2/4 · random_000_0004 · ΔE 1.460 kcal/mol").
 *  - Format tabs (XYZ · MOL · SDF · PDB · MOL2 · CML) for ANY result: single SMILES, file batch or
 *    GLOMOS. Non-XYZ text comes from /api/export (cached).
 *  - Download the structure on screen, or all of them (molecules of a file / conformers of a GLOMOS
 *    run) as a .zip, in the selected format.
 *  - Conformer bar over the viewer (◀ 2/4 ▶) synchronised with the GLOMOS table; ← → keys.
 *  - The 3D view is re-fitted whenever its box changes size (the molecule used to end up cropped
 *    after the GLOMOS card appeared, because the canvas was sized once at creation).
 *
 * Uses globals from app.js (classic scripts share top-level bindings): molecules,
 * currentMoleculeIndex, currentXYZ, currentVisualizations, showError, showGlomosConformer.
 */
(function () {
  'use strict';

  const FORMATS = ['xyz', 'mol', 'sdf', 'pdb', 'mol2', 'cml'];
  const LS_FMT = 'elaya.format';
  let fmt = 'xyz';
  try { const f = sessionStorage.getItem(LS_FMT); if (FORMATS.includes(f)) fmt = f; } catch (e) { /* storage off */ }
  const cache = new Map();                    // `${fmt}\u0000${smiles}\u0000${xyz}` -> text

  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const short = (t, n = 34) => { t = String(t || ''); return t.length > n ? t.slice(0, n - 1) + '…' : t; };
  const safe = (t) => String(t || 'structure').replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 60) || 'structure';

  // ------------------------------------------------------------------ state of the screen
  function molList() {
    try { if (Array.isArray(molecules) && molecules.length) return molecules; } catch (e) { /* */ }
    return Array.isArray(window.molecules) ? window.molecules : [];
  }
  function molIndex() {
    try { if (typeof currentMoleculeIndex === 'number') return currentMoleculeIndex; } catch (e) { /* */ }
    return Number.isInteger(window.currentMoleculeIndex) ? window.currentMoleculeIndex : 0;
  }
  function shownXYZ() {
    let x = '';
    try { x = currentXYZ || ''; } catch (e) { /* */ }
    return String(x || window.currentXYZ || '').trim();
  }
  const sameXYZ = (a, b) => String(a || '').trim() === String(b || '').trim();
  // name given in the .smi file (second column, stored as id by app.js), else the SMILES
  const molLabel = (m) => (m && (m.alias || m.name || m.title || (m.id && m.id !== m.smiles ? m.id : '') || m.smiles)) || '';

  /** Conformer set that contains the structure on screen, or null. */
  function conformerSet() {
    const xyz = shownXYZ();
    if (!xyz) return null;
    const g = window.ELAYA_CONFORMERS;
    if (g && Array.isArray(g.list)) {
      const i = g.list.findIndex(c => sameXYZ(c.xyz, xyz));
      if (i >= 0) return { list: g.list, index: i, smiles: g.smiles, select: g.select };
    }
    const m = molList()[molIndex()];
    const conf = m && m.glomos && Array.isArray(m.glomos.conformers) ? m.glomos.conformers : null;
    if (conf) {
      const i = conf.findIndex(c => sameXYZ(c.xyz, xyz));
      if (i >= 0) {
        return { list: conf, index: i, smiles: m.smiles,
                 select: (k) => { if (conf[k] && typeof showGlomosConformer === 'function') showGlomosConformer(conf[k], m.smiles); } };
      }
    }
    return null;
  }

  /** What is on screen: {smiles, xyz, name, label, title}. */
  function current() {
    const xyz = shownXYZ();
    const list = molList(), i = molIndex(), m = list[i] || {};
    const set = conformerSet();
    if (set) {
      const c = set.list[set.index];
      return {
        smiles: set.smiles || m.smiles, xyz, set, conf: c,
        name: `${safe(molLabel(m) || set.smiles)}_conf${set.index + 1}_${safe(c.name)}`,
        label: `${molLabel(m) || set.smiles} | conformer ${set.index + 1} (${c.name})`,
        title: `Conformer ${set.index + 1}/${set.list.length}`,
        sub: `${c.name} · ΔE ${Number(c.rel_kcal).toFixed(3)} kcal/mol · ${(100 * (c.boltzmann_298 || 0)).toFixed(1)} % (298 K)`,
      };
    }
    const label = molLabel(m);
    return {
      smiles: m.smiles || '', xyz, set: null,
      name: safe(label) || `molecule_${i + 1}`,
      label: label || `molecule ${i + 1}`,
      title: list.length > 1 ? `Molecule ${i + 1}/${list.length}` : 'Structure',
      sub: label && label !== m.smiles ? `${label} · ${short(m.smiles || '', 60)}` : short(m.smiles || '', 80),
    };
  }

  // ------------------------------------------------------------------ export
  async function exportText(smiles, xyz, f, name, props) {
    if (f === 'xyz') return xyz.endsWith('\n') ? xyz : xyz + '\n';
    const key = `${f}\u0000${smiles}\u0000${name || ''}\u0000${xyz}`;
    if (cache.has(key)) return cache.get(key);
    const r = await fetch('/api/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ smiles, xyz, format: f, name: name || 'ELAYA', properties: props || {} }),
    });
    if (!r.ok) {
      let msg = `HTTP ${r.status}`;
      try { msg = (await r.json()).error || msg; } catch (e) { /* */ }
      throw new Error(msg);
    }
    const t = await r.text();
    if (cache.size > 200) cache.clear();
    cache.set(key, t);
    return t;
  }

  function saveBlob(name, blob) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1500);
  }

  async function downloadCurrent() {
    const cur = current();
    if (!cur.xyz) return;
    try {
      const props = cur.conf ? { Energy_kcal_mol: Number(cur.conf.energy_kcal).toFixed(4),
                                 Rel_energy_kcal_mol: Number(cur.conf.rel_kcal).toFixed(4) } : {};
      const text = await exportText(cur.smiles, cur.xyz, fmt, cur.label, props);
      saveBlob(`${cur.name}.${fmt}`, new Blob([text], { type: 'text/plain' }));
    } catch (e) { showErr(`Export to ${fmt.toUpperCase()} failed: ${e.message}`); }
  }

  /** Every structure of the current context: conformers of a GLOMOS run, else molecules of a file. */
  function allItems() {
    const set = conformerSet();
    if (set && set.list.length > 1) {
      const base = safe(molLabel(molList()[molIndex()]) || set.smiles);
      return { kind: 'conformers', items: set.list.map((c, k) => ({
        smiles: set.smiles, xyz: c.xyz, name: `${base}_conf${k + 1}_${safe(c.name)}`,
        label: `${molLabel(molList()[molIndex()]) || set.smiles} | conformer ${k + 1} (${c.name})`,
        props: { Energy_kcal_mol: Number(c.energy_kcal).toFixed(4), Rel_energy_kcal_mol: Number(c.rel_kcal).toFixed(4) } })) };
    }
    const list = molList().filter(m => m && m.xyz);
    if (list.length > 1) {
      return { kind: 'molecules', items: list.map((m, k) => ({
        smiles: m.smiles, xyz: m.xyz, name: `${String(k + 1).padStart(3, '0')}_${safe(molLabel(m))}`, label: molLabel(m) })) };
    }
    return { kind: null, items: [] };
  }

  async function downloadAll() {
    const { kind, items } = allItems();
    if (!items.length) return;
    const btn = $('sp-dl-all');
    if (btn) { btn.disabled = true; btn.dataset.label = btn.textContent; btn.textContent = 'Preparing…'; }
    try {
      const texts = [];
      for (const it of items) texts.push(await exportText(it.smiles, it.xyz, fmt, it.label || it.name, it.props));
      const zipName = `elaya_${kind}_${fmt}`;
      if (window.JSZip) {
        const zip = new JSZip();
        items.forEach((it, k) => zip.file(`${it.name}.${fmt}`, texts[k]));
        saveBlob(`${zipName}.zip`, await zip.generateAsync({ type: 'blob' }));
      } else if (fmt === 'xyz' || fmt === 'sdf') {          // multi-structure formats without a zip
        saveBlob(`${zipName}.${fmt}`, new Blob([texts.join(fmt === 'sdf' ? '' : '')], { type: 'text/plain' }));
      } else {
        throw new Error('ZIP library not loaded');
      }
    } catch (e) {
      showErr(`Download failed: ${e.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = btn.dataset.label || btn.textContent; }
    }
  }

  function showErr(msg) { if (typeof showError === 'function') showError(msg); else console.error(msg); }

  // ------------------------------------------------------------------ formula line on top of the card
  const infoCache = new Map();
  let infoFor = '';
  async function showInfo(smiles) {
    const el = $('sp-info');
    if (!el) return;
    if (!smiles) { el.hidden = true; return; }
    if (smiles === infoFor && !el.hidden) return;
    infoFor = smiles;
    let d = infoCache.get(smiles);
    if (!d) {
      try {
        const r = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ smiles }) });
        if (!r.ok) { el.hidden = true; return; }
        d = await r.json();
        infoCache.set(smiles, d);
      } catch (e) { el.hidden = true; return; }
    }
    if (infoFor !== smiles) return;
    const rb = d.rotatable_bonds;
    el.textContent = `✓ ${d.formula} · ${Number(d.mol_weight).toFixed(2)} g/mol · ${d.atoms_with_h} atoms · ${rb} rotatable bond${rb === 1 ? '' : 's'}`;
    el.hidden = false;
  }

  // ------------------------------------------------------------------ the card (title + tabs)
  function ensureCard() {
    const disp = $('xyz-display');
    if (!disp) return null;
    let head = $('sp-head');
    if (!head) {
      head = document.createElement('div');
      head.id = 'sp-head';
      head.className = 'sp-head';
      head.innerHTML = `
        <div class="sp-title"><strong id="sp-title"></strong><span id="sp-sub"></span></div>
        <div class="sp-info" id="sp-info" hidden></div>
        <div class="sp-tabs" role="tablist" aria-label="File format">
          ${FORMATS.map(f => `<button type="button" role="tab" class="sp-tab" data-fmt="${f}">${f.toUpperCase()}</button>`).join('')}
          <button type="button" class="sp-copy" id="sp-copy" title="Copy to clipboard">Copy</button>
        </div>`;
      disp.parentNode.insertBefore(head, disp);
      head.querySelectorAll('.sp-tab').forEach(b => b.addEventListener('click', () => setFormat(b.dataset.fmt)));
      $('sp-copy').addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(disp.textContent || ''); flash($('sp-copy'), 'Copied ✓'); }
        catch (e) { showErr('Copy failed: ' + e.message); }
      });
    }
    return head;
  }

  function flash(btn, text) {
    if (!btn) return;
    const t = btn.textContent;
    btn.textContent = text;
    setTimeout(() => { btn.textContent = t; }, 1200);
  }

  function setFormat(f) {
    if (!FORMATS.includes(f)) return;
    fmt = f;
    try { sessionStorage.setItem(LS_FMT, f); } catch (e) { /* */ }
    refresh();
  }

  /** Aligned XYZ (same layout as app.js). */
  function formatXYZ(raw) {
    const lines = String(raw || '').trim().split('\n');
    if (lines.length < 3) return lines.join('\n');
    const atoms = lines.slice(2).map(line => {
      const p = line.trim().split(/\s+/);
      if (p.length < 4) return line;
      const f = v => parseFloat(v).toFixed(4).padStart(10);
      return `${p[0].padEnd(2)}  ${f(p[1])}  ${f(p[2])}  ${f(p[3])}`;
    });
    return [lines[0].trim(), lines[1] || '', ...atoms].join('\n');
  }

  let renderToken = 0;
  async function renderText() {
    const disp = $('xyz-display');
    const cur = current();
    if (!disp || !cur.xyz) return;
    const token = ++renderToken;                      // any older pending export is now stale
    if (fmt === 'xyz') {
      disp.classList.remove('sp-loading');
      disp.textContent = formatXYZ(cur.xyz);
      return;
    }
    disp.classList.add('sp-loading');
    try {
      const text = await exportText(cur.smiles, cur.xyz, fmt, cur.label);
      if (token === renderToken && fmt !== 'xyz') disp.textContent = text;
    } catch (e) {
      if (token === renderToken) disp.textContent = `Could not build ${fmt.toUpperCase()}: ${e.message}`;
    } finally {
      if (token === renderToken) disp.classList.remove('sp-loading');
    }
  }

  // ------------------------------------------------------------------ conformer bar on the viewer
  function ensureBar() {
    const host = document.querySelector('.visualization-container');
    if (!host) return null;
    let bar = $('conformer-bar');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'conformer-bar';
      bar.innerHTML = `
        <button type="button" class="control-btn" id="cb-prev" title="Previous conformer (←)">◀</button>
        <div class="cb-text"><strong id="cb-title"></strong><span id="cb-sub"></span></div>
        <button type="button" class="control-btn" id="cb-next" title="Next conformer (→)">▶</button>`;
      host.appendChild(bar);
      $('cb-prev').addEventListener('click', () => stepConformer(-1));
      $('cb-next').addEventListener('click', () => stepConformer(+1));
    }
    return bar;
  }

  function stepConformer(d) {
    const set = conformerSet();
    if (!set) return false;
    const k = set.index + d;
    if (k < 0 || k >= set.list.length) return true;
    set.select(k);
    return true;
  }

  // ← → : conformers when a GLOMOS set is on screen, otherwise molecules of a file
  document.addEventListener('keydown', (e) => {
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const t = e.target;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    const d = e.key === 'ArrowLeft' ? -1 : 1;
    if (stepConformer(d)) { e.preventDefault(); return; }
    const btn = $(d < 0 ? 'prev-molecule' : 'next-molecule');
    if (btn && btn.style.display !== 'none' && !btn.disabled) { e.preventDefault(); btn.click(); }
  });

  // ------------------------------------------------------------------ download buttons
  function renderDownloads() {
    const box = $('individual-downloads');
    if (!box) return;
    const cur = current();
    if (window.ELAYA_GLOMOS_RUNNING || !cur.xyz) { box.innerHTML = ''; box.style.display = 'none'; return; }
    const legacy = $('download-xyz'); if (legacy) legacy.style.display = 'none';
    const { kind, items } = allItems();
    const F = fmt.toUpperCase();
    box.innerHTML = '';
    const one = document.createElement('button');
    one.type = 'button';
    one.id = 'sp-dl-one';
    one.className = 'btn btn-primary xyz-download';
    one.textContent = `Download ${F}: ${short(cur.set ? `${cur.title} · ${cur.conf.name}` : molLabel(molList()[molIndex()]) || cur.smiles, 40)}`;
    one.title = cur.smiles;
    one.addEventListener('click', downloadCurrent);
    box.appendChild(one);
    if (items.length > 1) {
      const all = document.createElement('button');
      all.type = 'button';
      all.id = 'sp-dl-all';
      all.className = 'btn btn-primary xyz-download-all';
      all.textContent = `Download all ${items.length} ${kind} · ${F}${window.JSZip ? ' (.zip)' : ''}`;
      all.addEventListener('click', downloadAll);
      box.appendChild(all);
    }
    box.style.display = 'flex';
  }

  // ------------------------------------------------------------------ refresh everything
  function hideAll(head, bar) {
    if (head) head.style.display = 'none';
    if (bar) bar.style.display = 'none';
    ['xyz-display', 'structure-qa', 'individual-downloads', 'download-xyz'].forEach(id => {
      const e = $(id); if (e) e.style.display = 'none';
    });
  }

  function refresh() {
    const cur = current();
    const head = ensureCard();
    const bar = ensureBar();
    if (window.ELAYA_GLOMOS_RUNNING) { hideAll(head, bar); return; }   // conformers are not there yet
    const disp = $('xyz-display');
    if (disp && cur.xyz) disp.style.display = 'block';
    if (!cur.xyz) {
      if (head) head.style.display = 'none';
      if (bar) bar.style.display = 'none';
      return;
    }
    if (head) {
      head.style.display = 'flex';
      $('sp-title').textContent = cur.title;
      $('sp-sub').textContent = cur.sub ? ` · ${cur.sub}` : '';
      showInfo(cur.smiles);
      head.querySelectorAll('.sp-tab').forEach(b => {
        const on = b.dataset.fmt === fmt;
        b.classList.toggle('active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    }
    if (bar) {
      if (cur.set && cur.set.list.length > 0) {
        bar.style.display = 'flex';
        $('cb-title').textContent = cur.title;
        $('cb-sub').textContent = cur.sub;
        $('cb-prev').disabled = cur.set.index <= 0;
        $('cb-next').disabled = cur.set.index >= cur.set.list.length - 1;
      } else {
        bar.style.display = 'none';
      }
    }
    renderDownloads();
    renderText();
  }

  // ------------------------------------------------------------------ fit the 3D view to its box
  function fitViewers() {
    let vs = [];
    try { vs = Array.isArray(currentVisualizations) ? currentVisualizations : []; } catch (e) { /* */ }
    vs.forEach(v => {
      try {
        const c = v.container || (v.getCanvas && v.getCanvas().parentElement);
        if (c && (c.offsetWidth === 0 || c.offsetHeight === 0)) return;
        v.resize();
        if (window.elayaFitWhole) window.elayaFitWhole(v); else { v.zoomTo(); v.zoom(0.9); }
        v.render();
      } catch (e) { /* viewer gone */ }
    });
  }
  window.elayaFitViewer = fitViewers;

  function watchViewerSize() {
    const box = $('viewer-container') || document.querySelector('.visualization-container');
    if (!box || !('ResizeObserver' in window)) return;
    let last = '', timer = null;
    new ResizeObserver(entries => {
      const r = entries[0].contentRect;
      const key = `${Math.round(r.width)}x${Math.round(r.height)}`;
      if (key === last || r.width === 0 || r.height === 0) return;
      last = key;
      clearTimeout(timer);
      timer = setTimeout(fitViewers, 120);
    }).observe(box);
  }

  function addFitButton() {
    const right = document.querySelector('#molecule-controls .controls-right');
    if (!right || $('fit-btn')) return;
    const b = document.createElement('button');
    b.id = 'fit-btn';
    b.type = 'button';
    b.className = 'control-btn';
    b.title = 'Fit the whole molecule in the view';
    b.textContent = 'Fit';
    b.addEventListener('click', fitViewers);
    right.insertBefore(b, right.firstChild);
  }

  // ------------------------------------------------------------------ hooks into app.js
  function wrap(name, after) {
    const f = window[name];
    if (typeof f !== 'function' || f.__elayaWrapped) return false;
    const w = function (...args) { const r = f.apply(this, args); try { after(); } catch (e) { console.debug(e); } return r; };
    w.__elayaWrapped = true;
    window[name] = w;
    return true;
  }

  function init() {
    // function declarations of app.js are properties of window, so they can be wrapped; calls made
    // from inside app.js resolve the global name at call time and therefore reach the wrapper.
    wrap('updateXYZDisplay', refresh);
    wrap('updateDownloadButtons', renderDownloads);
    addFitButton();
    watchViewerSize();
    refresh();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.addEventListener('elaya:glomos-state', () => refresh());

  window.ElayaPanel = { refresh, setFormat, current, downloadAll, downloadCurrent, fitViewers };
})();
