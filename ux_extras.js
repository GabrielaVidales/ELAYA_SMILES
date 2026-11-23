/*
 * ux_extras.js — small conveniences around the SMILES input and the options.
 *
 *  - ✕ button to clear the SMILES field.
 *  - Live check of the SMILES (debounced /api/analyze): formula, mass and atom count when valid,
 *    the parser's message when not.
 *  - The chosen options (method, force field, post-optimisation, GLOMOS settings, file format) are
 *    remembered in this browser.
 *  - GLOMOS estimate: number of ANI relaxations of the chosen settings and, after one run on this
 *    server, an approximate duration scaled by the number of atoms.
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage off */ } },
  };

  // ---------------------------------------------------------------- clear button + live check
  let lastInfo = null;            // analyze result of the current SMILES (atoms for the estimate)

  function initSmilesField() {
    const input = $('smiles');
    if (!input) return;
    // app.js wraps the input later (overflow indicator), so anchor the button to the input's box
    const wrap = input.closest('.input-overlay-wrapper') || input.parentElement;
    if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';

    const clear = document.createElement('button');
    clear.type = 'button';
    clear.id = 'smiles-clear';
    clear.title = 'Clear';
    clear.setAttribute('aria-label', 'Clear SMILES');
    clear.textContent = '✕';
    wrap.appendChild(clear);
    clear.addEventListener('click', () => {
      input.value = '';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    });

    const status = document.createElement('div');
    status.id = 'smiles-status';
    status.setAttribute('aria-live', 'polite');
    const examples = $('smiles-examples');
    (examples || input).parentNode.insertBefore(status, examples || input.nextSibling);

    const place = () => {
      const op = clear.offsetParent || wrap;
      const a = input.getBoundingClientRect(), b = op.getBoundingClientRect();
      if (!a.width) return;
      clear.style.top = `${a.top - b.top + a.height / 2}px`;
      clear.style.right = `${b.right - a.right + 46}px`;
    };
    window.addEventListener('resize', place);

    let timer = null, seq = 0;
    const check = async () => {
      const s = input.value.trim();
      clear.style.display = s ? 'flex' : 'none';
      place();
      if (!s) { status.className = ''; status.textContent = ''; input.classList.remove('smiles-invalid'); lastInfo = null; updateEstimate(); return; }
      if (s.includes('\n')) return;
      const my = ++seq;
      try {
        const r = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ smiles: s }) });
        const d = await r.json();
        if (my !== seq) return;
        if (r.ok) {
          lastInfo = d;
          input.classList.remove('smiles-invalid');
          status.className = 'ok';
          const warn = (d.warnings || []).length ? ` · ⚠ ${d.warnings[0]}` : '';
          status.textContent = `✓ ${d.formula} · ${Number(d.mol_weight).toFixed(2)} g/mol · ${d.atoms_with_h} atoms` +
                               ` · ${d.rotatable_bonds} rotatable bond${d.rotatable_bonds === 1 ? '' : 's'}${warn}`;
        } else {
          lastInfo = null;
          input.classList.add('smiles-invalid');
          status.className = 'bad';
          status.textContent = `✗ ${d.error || 'Invalid SMILES'}`;
        }
      } catch (e) {
        if (my === seq) { status.className = ''; status.textContent = ''; }
      }
      updateEstimate();
    };
    input.addEventListener('input', () => { clear.style.display = input.value ? 'flex' : 'none'; place(); clearTimeout(timer); timer = setTimeout(check, 450); });
    check();
  }

  // ---------------------------------------------------------------- remember options
  // post-optimisation is NOT restored: GLOMOS would then start by itself on the first-visit demo
  const REMEMBER = ['conversion-method', 'force-field', 'glomos-preset', 'glomos-initpop',
                    'glomos-matings', 'glomos-mutants', 'glomos-generations', 'glomos-ecut', 'glomos-keep',
                    'glomos-ani', 'glomos-minutes', 'glomos-screening'];

  function restoreOptions() {
    const saved = store.get('elaya.options', {});
    // order matters: the preset first (its change handler overwrites the numbers), then the rest
    const ids = ['glomos-preset', ...REMEMBER.filter(i => i !== 'glomos-preset')];
    for (const id of ids) {
      const el = $(id);
      if (!el || saved[id] === undefined) continue;
      if (el.tagName === 'SELECT' && ![...el.options].some(o => o.value === saved[id] && !o.disabled)) continue;
      el.value = saved[id];
      if (id === 'glomos-preset') el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (saved['glomos-preset'] !== undefined && $('glomos-preset')) $('glomos-preset').value = saved['glomos-preset'];
    $('conversion-method')?.dispatchEvent(new Event('change', { bubbles: true }));
    if (typeof toggleForceField === 'function') { try { toggleForceField(); } catch (e) { /* */ } }
  }

  function saveOptions() {
    const out = {};
    REMEMBER.forEach(id => { const el = $(id); if (el) out[id] = el.value; });
    store.set('elaya.options', out);
  }

  // ---------------------------------------------------------------- GLOMOS estimate
  function relaxations() {
    const n = (id, d) => { const v = Number($(id)?.value); return Number.isFinite(v) ? v : d; };
    return n('glomos-initpop', 6) + n('glomos-generations', 4) * (n('glomos-matings', 4) + n('glomos-mutants', 4))
         + n('glomos-keep', 6);
  }

  function updateEstimate() {
    const grid = document.querySelector('#glomos-panel .glomos-grid');
    if (!grid) return;
    let box = $('glomos-estimate');
    if (!box) { box = document.createElement('div'); box.id = 'glomos-estimate'; grid.appendChild(box); }
    const n = relaxations();
    let text = `Up to <b>${n}</b> ANI relaxations (fewer if it converges early).`;
    const rate = store.get('elaya.glomosRate', null);
    const atoms = lastInfo?.atoms_with_h;
    if (rate && rate.secPerRelaxAtom > 0 && atoms) {
      let sec = n * atoms * rate.secPerRelaxAtom;
      if (($('glomos-screening')?.value || 'ensemble') !== (rate.screening || 'ensemble')) {
        sec *= ($('glomos-screening')?.value === 'single') ? 0.35 : 2.8;        // measured ratio of the two modes
      }
      const lim = Number($('glomos-minutes')?.value) || 20;
      const min = sec / 60;
      text += ` Estimated <b>≈ ${min < 1 ? '<1' : Math.round(min)} min</b> on this server (from your last run)` +
              (min > lim ? ` — longer than the time limit: the best structures found by then are returned.` : '.');
    }
    box.innerHTML = text;
  }

  window.addEventListener('elaya:glomos-done', (e) => {
    const d = e.detail || {};
    if (d.status !== 'done' || !d.n_evaluated || !d.atoms || !d.seconds) return;
    store.set('elaya.glomosRate', { secPerRelaxAtom: d.seconds / (d.n_evaluated * d.atoms), screening: d.screening });
    updateEstimate();
  });


  // ---------------------------------------------------------------- SMILES files
  const esc = (t) => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /** .smi/.txt: "SMILES [name ...]"; .csv/.tsv: a header with a smiles column (name/id/title optional). */
  function parseSmilesText(text, filename) {
    const lines = String(text || '').replace(/^﻿/, '').split(/\r?\n/);
    const out = [];
    const isTable = /\.(csv|tsv)$/i.test(filename || '') ||
      (/,|\t/.test(lines.find(l => l.trim()) || '') && /smiles/i.test(lines.find(l => l.trim()) || ''));
    if (isTable) {
      const first = lines.findIndex(l => l.trim());
      if (first < 0) return out;
      const delim = lines[first].includes('\t') ? '\t' : ',';
      const split = (l) => l.split(delim).map(x => x.trim().replace(/^"(.*)"$/, '$1'));
      const head = split(lines[first]).map(h => h.toLowerCase());
      let si = head.findIndex(h => h === 'smiles' || h.includes('smiles'));
      const ni = head.findIndex(h => ['name', 'id', 'title', 'compound', 'molecule'].includes(h));
      const hasHeader = si >= 0;
      if (si < 0) si = 0;
      lines.slice(hasHeader ? first + 1 : first).forEach((l, k) => {
        if (!l.trim() || /^\s*#/.test(l)) return;
        const c = split(l);
        if (!c[si]) return;
        out.push({ smiles: c[si], id: (ni >= 0 && c[ni]) ? c[ni] : `mol_${out.length + 1}` });
      });
      return out;
    }
    lines.forEach(l => {
      const t = l.trim();
      if (!t || /^(#|\/\/)/.test(t)) return;
      const parts = t.split(/\s+/);
      if (/^smiles$/i.test(parts[0])) return;                    // a header line
      out.push({ smiles: parts[0], id: parts.slice(1).join(' ') || `mol_${out.length + 1}` });
    });
    return out;
  }
  window.ElayaFiles = { parse: parseSmilesText };

  function initFiles() {
    const input = $('smiles-file');
    const zone = $('file-dropzone');
    if (!input || !zone) return;
    const setFile = (file) => {
      if (!file) return;
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    };
    ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach(ev => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove('drag'); }));
    zone.addEventListener('drop', (e) => setFile(e.dataTransfer?.files?.[0]));
    zone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });

    $('ffe-download-sample')?.addEventListener('click', () => {
      const txt = '# ELAYA example: SMILES, then a name (optional)\n' +
        'CCO                       ethanol\nCC(=O)Oc1ccccc1C(=O)O     aspirin\nC1=CC(=C(C=C1CCN)O)O      dopamine\n' +
        'C1=CC2=C(C=C1O)NC=C2CCN   serotonin\nCOc1ccc2c(c1)c(c[nH]2)CCNC(=O)C   melatonin\n';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([txt], { type: 'text/plain' }));
      a.download = 'elaya_example.smi';
      document.body.appendChild(a); a.click(); a.remove();
    });

    window.addEventListener('elaya:file-loaded', async (e) => {
      const { name, molecules } = e.detail || {};
      const box = $('file-summary');
      if (!box || !Array.isArray(molecules)) return;
      zone.classList.add('loaded');
      zone.querySelector('.fd-main').innerHTML = `<b>${esc(name)}</b> · ${molecules.length} molecule${molecules.length === 1 ? '' : 's'}`;
      zone.querySelector('.fd-sub').textContent = 'Drop another file or click to replace it';
      box.style.display = 'block';
      box.innerHTML = `<div class="fs-head">Checking ${molecules.length} SMILES…</div>`;
      let results = null;
      try {
        const r = await fetch('/api/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                 body: JSON.stringify({ smiles: molecules.slice(0, 2000).map(m => m.smiles) }) });
        if (r.ok) results = (await r.json()).results;
      } catch (err) { /* offline: show the list without checks */ }
      const bad = results ? results.filter(x => !x.ok).length : 0;
      const rows = molecules.slice(0, 200).map((m, k) => {
        const v = results && results[k];
        const st = !v ? '' : v.ok ? `<span class="fs-ok" title="${esc(v.formula)}">✓ ${esc(v.formula)}</span>`
                                  : `<span class="fs-bad" title="${esc(v.error)}">✗ ${esc(v.error)}</span>`;
        return `<tr class="${v && !v.ok ? 'bad' : ''}"><td>${k + 1}</td><td>${esc(m.id)}</td><td><code>${esc(m.smiles)}</code></td><td>${st}</td></tr>`;
      }).join('');
      box.innerHTML = `
        <div class="fs-head">
          <span><b>${molecules.length}</b> loaded${results ? ` · <b class="fs-okc">${molecules.length - bad}</b> valid` : ''}${bad ? ` · <b class="fs-badc">${bad}</b> invalid` : ''}</span>
          ${bad ? '<button type="button" class="ffe-btn" id="fs-drop-bad">Remove invalid</button>' : ''}
          <span class="fs-hint">Press <b>Convert structure</b> to choose which ones to build.</span>
        </div>
        <div class="fs-table-wrap"><table class="fs-table"><thead><tr><th>#</th><th>Name</th><th>SMILES</th><th>Check</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
        ${molecules.length > 200 ? `<div class="fs-hint">Showing the first 200 of ${molecules.length}.</div>` : ''}`;
      $('fs-drop-bad')?.addEventListener('click', () => {
        const keep = molecules.filter((m, k) => !results || !results[k] || results[k].ok);
        window.allMolecules = keep.slice();
        window.molecules = keep.slice();
        window.dispatchEvent(new CustomEvent('elaya:file-loaded', { detail: { name, molecules: keep } }));
      });
    });
  }

  // ---------------------------------------------------------------- init
  function init() {
    initSmilesField();
    initFiles();
    restoreOptions();
    REMEMBER.forEach(id => $(id)?.addEventListener('change', saveOptions));
    ['glomos-initpop', 'glomos-matings', 'glomos-mutants', 'glomos-generations', 'glomos-keep',
     'glomos-preset', 'glomos-screening', 'glomos-minutes'].forEach(id => {
      $(id)?.addEventListener('input', updateEstimate);
      $(id)?.addEventListener('change', updateEstimate);
    });
    updateEstimate();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
