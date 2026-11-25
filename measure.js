/*
 * measure.js — simple geometry in the 3D viewer.
 * Turn on "Measure", then click atoms: 2 atoms → distance (Å), 3 → angle (°), 4 → dihedral (°).
 * The fifth click starts a new measurement; results stay listed until "Clear".
 * Uses the 3Dmol viewer that app.js keeps in `currentVisualizations[0]`; rotation is paused while measuring.
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const MINT = '#8fe3cb', GOLD = '#ffbf00', LAV = '#c9a7f0';
  let on = false, viewer = null, picks = [], history = [], wasPaused = false, watch = null, hoverLabel = null;

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

  // hover tag (C1, O5…): solid mint chip with dark bold text, just above the atom, readable on any background
  const HOVER_STYLE = (atom) => ({
    position: { x: atom.x, y: atom.y + 0.45, z: atom.z }, inFront: true, fontSize: 15, bold: true,
    fontColor: '#0d1020', backgroundColor: '#8fe3cb', backgroundOpacity: 1, borderThickness: 1.5, borderColor: '#0d1020',
    alignment: 'bottomCenter',
  });

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
    box.innerHTML = `
      <div class="mp-head"><b>Measure</b><button type="button" class="mp-x" id="mp-done" aria-label="Stop measuring">✕</button></div>
      ${r ? `<div class="mp-val"><span>${esc(r.text)}</span><b>${r.value}</b></div>` : `<div class="mp-need">${need}</div>`}
      ${older.length ? `<ul class="mp-hist">${older.map(h => `<li><span>${esc(h.text)}</span><b>${h.value}</b></li>`).join('')}</ul>` : ''}
      ${history.length ? `<div class="mp-actions"><button type="button" id="mp-copy">Copy</button><button type="button" id="mp-clear">Clear</button></div>` : ''}`;
    if (!$('mp-clear')) { $('mp-done').onclick = () => toggle(false); return; }
    $('mp-clear').onclick = () => { picks = []; history = []; draw(); panel(); };
    $('mp-done').onclick = () => toggle(false);
    if (!$('mp-copy')) return;
    $('mp-copy').onclick = async () => {
      const txt = history.map(h => `${h.kind}\t${h.text}\t${h.value}`).join('\n');
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
        (atom) => { if (!on || hoverLabel || picks.some(p => p.index === atom.index)) return; hoverLabel = viewer.addLabel(name(atom), HOVER_STYLE(atom)); viewer.render(); },
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
     
      attach();
      draw();
      clearInterval(watch);
      watch = setInterval(() => {          // a new molecule/conformer creates a new viewer
        const v = getViewer();
        if (on && v && v !== viewer) { picks = []; history = []; attach(); draw(); panel(); }
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
    window.ElayaMeasure = { toggle, pick: onPick, geometry: { dist, angle, dihedral }, _hoverStyle: HOVER_STYLE };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
