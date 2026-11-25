/*
 * measure.js — simple geometry in the 3D viewer.
 * Turn on "Measure", then click atoms: 2 atoms → distance (Å), 3 → angle (°), 4 → dihedral (°).
 * Without clicking: whole-molecule size (longest distance, radius of gyration, extent along the principal
 * axes) and intramolecular hydrogen bonds (H···N/O ≤ 2.5 Å, D–H···A ≥ 120°), which can be drawn.
 * The fifth click starts a new measurement; results stay listed until "Clear".
 * Uses the 3Dmol viewer that app.js keeps in `currentVisualizations[0]`; rotation is paused while measuring.
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const MINT = '#8fe3cb', GOLD = '#ffbf00', LAV = '#c9a7f0';
  let on = false, viewer = null, picks = [], history = [], wasPaused = false, watch = null, hoverLabel = null;
  let hbShow = false, molCache = null;

  const getViewer = () => {
    try { return (typeof currentVisualizations !== 'undefined' && currentVisualizations[0]) || null; } catch (e) { return null; }
  };
  const setPaused = (v) => { try { if (typeof isRotationPaused !== 'undefined') isRotationPaused = v; } catch (e) { /* */ } };
  const getPaused = () => { try { return typeof isRotationPaused !== 'undefined' ? isRotationPaused : false; } catch (e) { return false; } };

  // ------------------------------------------------------------------ geometry
  const sub = (a, b) => [a.x - b.x, a.y - b.y, a.z - b.z];
  const dot = (u, v) => u[0] * v[0] + u[1] * v[1] + u[2] * v[2];
  const cross = (u, v) => [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
  const norm = (u) => Math.sqrt(dot(u, u));
  const deg = (r) => r * 180 / Math.PI;
  const dist = (a, b) => norm(sub(a, b));
  const angle = (a, b, c) => {
    const u = sub(a, b), v = sub(c, b);
    return deg(Math.acos(Math.max(-1, Math.min(1, dot(u, v) / (norm(u) * norm(v))))));
  };
  const dihedral = (a, b, c, d) => {
    const b0 = sub(a, b), b1 = sub(c, b), b2 = sub(d, c);
    const n1 = norm(b1), b1n = [b1[0] / n1, b1[1] / n1, b1[2] / n1];
    const v = b0.map((x, i) => x - dot(b0, b1n) * b1n[i]);
    const w = b2.map((x, i) => x - dot(b2, b1n) * b1n[i]);
    return deg(Math.atan2(dot(cross(b1n, v), w), dot(v, w)));
  };
  const mid = (...ps) => ({ x: ps.reduce((s, p) => s + p.x, 0) / ps.length, y: ps.reduce((s, p) => s + p.y, 0) / ps.length, z: ps.reduce((s, p) => s + p.z, 0) / ps.length });
  const name = (a) => `${a.elem}${(a.index ?? a.serial ?? 0) + 1}`;

  // ------------------------------------------------------------------ whole molecule
  const MASS = { H: 1.008, B: 10.81, C: 12.011, N: 14.007, O: 15.999, F: 18.998, Si: 28.085, P: 30.974, S: 32.06,
                 Cl: 35.45, Br: 79.904, I: 126.904 };
  function atomsOf(v) {
    try { return v.selectedAtoms({}).filter(a => a.elem && Number.isFinite(a.x)); } catch (e) { return []; }
  }
  /** Size descriptors and H-bonds of the molecule shown in the viewer (cached per viewer). */
  function molecule() {
    if (molCache && molCache.viewer === viewer) return molCache;
    const at = atomsOf(viewer);
    const out = { viewer, n: at.length, length: 0, rg: 0, extent: null, hbonds: [] };
    if (at.length < 2) return (molCache = out);
    let maxd = 0;
    for (let i = 0; i < at.length; i++) for (let j = i + 1; j < at.length; j++) maxd = Math.max(maxd, dist(at[i], at[j]));
    out.length = maxd;
    const m = at.map(a => MASS[a.elem] || 12);
    const M = m.reduce((s, x) => s + x, 0);
    const c = { x: 0, y: 0, z: 0 };
    at.forEach((a, k) => { c.x += m[k] * a.x / M; c.y += m[k] * a.y / M; c.z += m[k] * a.z / M; });
    out.rg = Math.sqrt(at.reduce((s, a, k) => s + m[k] * dist(a, c) ** 2, 0) / M);
    // extent along the principal axes of the (unweighted) coordinate covariance: power iteration, 3 axes
    const P = at.map(a => [a.x - c.x, a.y - c.y, a.z - c.z]);
    const C = [0, 1, 2].map(i => [0, 1, 2].map(j => P.reduce((s, p) => s + p[i] * p[j], 0)));
    const axes = [];
    for (let k = 0; k < 3; k++) {
      let v = [1, 0.7 - 0.3 * k, 0.3 + 0.2 * k];
      for (let it = 0; it < 60; it++) {
        axes.forEach(a => { const d = dot(v, a); v = v.map((x, i) => x - d * a[i]); });
        const w = C.map(r => dot(r, v)); const n = norm(w) || 1; v = w.map(x => x / n);
      }
      axes.forEach(a => { const d = dot(v, a); v = v.map((x, i) => x - d * a[i]); });
      const n = norm(v) || 1; axes.push(v.map(x => x / n));
    }
    out.extent = axes.map(a => { const pr = P.map(p => dot(p, a)); return Math.max(...pr) - Math.min(...pr); });
    // hydrogen bonds: H bonded to N/O (donor D), acceptor A = N/O not bonded to D
    const byIdx = new Map(at.map(a => [a.index, a]));
    const bonded = (a, b) => (a.bonds || []).includes(b.index);
    for (const h of at) {
      if (h.elem !== 'H') continue;
      const d = (h.bonds || []).map(i => byIdx.get(i)).find(x => x && (x.elem === 'N' || x.elem === 'O'));
      if (!d) continue;
      for (const a of at) {
        if ((a.elem !== 'N' && a.elem !== 'O') || a === d || bonded(a, d) || bonded(a, h)) continue;
        const r = dist(h, a);
        if (r <= 2.5 && angle(d, h, a) >= 120) out.hbonds.push({ h, a, d, r });
      }
    }
    return (molCache = out);
  }

  // ------------------------------------------------------------------ drawing
  function label(text, pos, color) {
    viewer.addLabel(text, {
      position: pos, inFront: true, fontSize: 13, fontColor: color || MINT,
      backgroundColor: '#1a1d33', backgroundOpacity: 0.88, borderThickness: 1, borderColor: color || MINT,
      alignment: 'center',
    });
  }
  function result() {
    const p = picks;
    if (p.length === 2) return { kind: 'Distance', text: `${name(p[0])}–${name(p[1])}`, value: `${dist(p[0], p[1]).toFixed(3)} Å`, at: mid(p[0], p[1]) };
    if (p.length === 3) return { kind: 'Angle', text: `${name(p[0])}–${name(p[1])}–${name(p[2])}`, value: `${angle(p[0], p[1], p[2]).toFixed(1)}°`, at: p[1] };
    if (p.length === 4) return { kind: 'Dihedral', text: `${name(p[0])}–${name(p[1])}–${name(p[2])}–${name(p[3])}`, value: `${dihedral(p[0], p[1], p[2], p[3]).toFixed(1)}°`, at: mid(p[1], p[2]) };
    return null;
  }
  function draw() {
    if (!viewer) return;
    try {
      viewer.removeAllShapes();
      viewer.removeAllLabels();
      picks.forEach((a, i) => {
        viewer.addSphere({ center: { x: a.x, y: a.y, z: a.z }, radius: 0.38, color: i === picks.length - 1 ? GOLD : MINT, opacity: 0.75 });
        if (i) viewer.addCylinder({ start: picks[i - 1], end: a, radius: 0.045, color: GOLD, dashed: true, fromCap: 1, toCap: 1 });
      });
      picks.forEach(a => label(name(a), { x: a.x, y: a.y + 0.55, z: a.z }, LAV));
      if (hbShow) molecule().hbonds.forEach(b => {
        viewer.addCylinder({ start: b.h, end: b.a, radius: 0.05, color: LAV, dashed: true, dashLength: 0.18, gapLength: 0.14, fromCap: 1, toCap: 1 });
        label(`${b.r.toFixed(2)} Å`, mid(b.h, b.a), LAV);
      });
      const r = result();
      if (r) label(r.value, r.at, MINT);
      viewer.render();
    } catch (e) { console.warn('measure: draw failed', e); }
  }

  // ------------------------------------------------------------------ panel
  function panel() {
    const box = $('measure-panel');
    if (!box) return;
    box.hidden = !on;
    if (!on) return;
    const r = result();
    const need = ['Click 2 atoms (distance), 3 (angle) or 4 (dihedral).', 'Click another atom.', '', '', ''][Math.min(picks.length, 4)];
    const older = history.slice(r ? 1 : 0, 4);
    const mol = molecule();
    const nh = mol.hbonds.length;
    const molRow = mol.n > 1 ? `
      <div class="mp-mol" title="Whole molecule, no clicks needed">
        <span><i>Length</i><b>${mol.length.toFixed(1)} Å</b></span>
        <span title="Radius of gyration (mass-weighted)"><i>R<sub>g</sub></i><b>${mol.rg.toFixed(2)} Å</b></span>
        ${mol.extent ? `<span title="Extent along the three principal axes"><i>Size</i><b>${mol.extent.map(x => x.toFixed(1)).join(' × ')} Å</b></span>` : ''}
        <span title="Intramolecular hydrogen bonds: H···N/O ≤ 2.5 Å, D–H···A ≥ 120°"><i>H-bonds</i><b>${nh}</b>${nh ? `<button type="button" id="mp-hb" class="mp-hb${hbShow ? ' on' : ''}">${hbShow ? 'Hide' : 'Show'}</button>` : ''}</span>
      </div>` : '';
    box.innerHTML = `
      <div class="mp-head"><b>Measure</b><button type="button" class="mp-x" id="mp-done" aria-label="Stop measuring">✕</button></div>${molRow}
      ${r ? `<div class="mp-val"><span>${esc(r.text)}</span><b>${r.value}</b></div>` : `<div class="mp-need">${need}</div>`}
      ${older.length ? `<ul class="mp-hist">${older.map(h => `<li><span>${esc(h.text)}</span><b>${h.value}</b></li>`).join('')}</ul>` : ''}
      ${history.length ? `<div class="mp-actions"><button type="button" id="mp-copy">Copy</button><button type="button" id="mp-clear">Clear</button></div>` : ''}`;
    if ($('mp-hb')) $('mp-hb').onclick = () => { hbShow = !hbShow; draw(); panel(); };
    if (!$('mp-clear')) { $('mp-done').onclick = () => toggle(false); return; }
    $('mp-clear').onclick = () => { picks = []; history = []; draw(); panel(); };
    $('mp-done').onclick = () => toggle(false);
    if (!$('mp-copy')) return;
    $('mp-copy').onclick = async () => {
      const m = molecule();
      const whole = m.n > 1 ? [`Length\tmolecule\t${m.length.toFixed(2)} Å`, `Radius of gyration\tmolecule\t${m.rg.toFixed(2)} Å`,
        `H-bonds\tmolecule\t${m.hbonds.length}`] : [];
      const txt = [...history.map(h => `${h.kind}\t${h.text}\t${h.value}`), ...whole].join('\n');
      try { await navigator.clipboard.writeText(txt); $('mp-copy').textContent = 'Copied ✓'; } catch (e) { /* */ }
    };
  }

  function onPick(atom) {
    if (!on || !atom) return;
    if (hoverLabel) { try { viewer.removeLabel(hoverLabel); } catch (e) { /* */ } hoverLabel = null; }
    const a = { x: atom.x, y: atom.y, z: atom.z, elem: atom.elem, index: atom.index, serial: atom.serial };
    if (picks.length === 4) picks = [];
    const last = picks[picks.length - 1];
    if (last && last.index === a.index) return;               // same atom twice
    picks.push(a);
    const r = result();
    if (r) {          // every step is kept: a 4-atom chain lists its distance, angle and dihedral
      history.unshift({ kind: r.kind, text: r.text, value: r.value });
      history = history.slice(0, 8);
    }
    draw();
    panel();
  }

  // ------------------------------------------------------------------ on / off
  function attach() {
    viewer = getViewer();
    if (!viewer) return false;
    try {
      viewer.setClickable({}, true, (atom) => onPick(atom));
      viewer.setHoverable({}, true,
        (atom) => { if (!on || hoverLabel || picks.some(p => p.index === atom.index)) return; hoverLabel = viewer.addLabel(name(atom), { position: atom, inFront: true, fontSize: 11, fontColor: '#e8eef2', backgroundColor: '#000', backgroundOpacity: 0.6 }); viewer.render(); },
        () => { if (hoverLabel) { try { viewer.removeLabel(hoverLabel); viewer.render(); } catch (e) { /* */ } hoverLabel = null; } });
      viewer.setHoverDuration?.(60);
      viewer.render();      // 3Dmol builds its pick list while rendering; rotation is paused, so render once here
    } catch (e) { console.warn('measure: could not attach', e); return false; }
    return true;
  }
  function detach() {
    if (!viewer) return;
    try {
      viewer.setClickable({}, false);
      viewer.setHoverable({}, false);
      viewer.removeAllShapes();
      viewer.removeAllLabels();
      viewer.render();
    } catch (e) { /* the viewer may already be gone */ }
  }

  function toggle(state) {
    const btn = $('measure-btn');
    const want = state === undefined ? !on : state;
    if (want) {
      if (!getViewer()) { flash('Convert a molecule first, then measure it in 3D.'); return; }
      if (typeof is3DEnabled !== 'undefined' && !is3DEnabled) document.querySelector('#toggle-3d')?.click();
      on = true;
      wasPaused = getPaused();
      setPaused(true);
      picks = [];
      molCache = null;
      attach();
      draw();
      clearInterval(watch);
      watch = setInterval(() => {          // a new molecule/conformer creates a new viewer
        const v = getViewer();
        if (on && v && v !== viewer) { picks = []; history = []; molCache = null; attach(); draw(); panel(); }
      }, 400);
    } else {
      on = false;
      clearInterval(watch);
      detach();
      picks = [];
      setPaused(wasPaused);
    }
    document.querySelector('.visualization-container')?.classList.toggle('measuring', on);
    if (btn) { btn.classList.toggle('active', on); btn.setAttribute('aria-pressed', on ? 'true' : 'false'); }
    panel();
  }

  function flash(msg) {
    const box = $('measure-panel');
    if (!box) return;
    box.hidden = false;
    box.innerHTML = `<div class="mp-head"><b>Measure</b></div><div class="mp-need">${esc(msg)}</div>`;
    setTimeout(() => { if (!on) box.hidden = true; }, 2600);
  }

  function init() {
    $('measure-btn')?.addEventListener('click', () => toggle());
    document.addEventListener('keydown', (e) => { if (on && e.key === 'Escape') toggle(false); });
    window.ElayaMeasure = { toggle, pick: onPick, geometry: { dist, angle, dihedral }, molecule: () => (viewer ? molecule() : null) };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
