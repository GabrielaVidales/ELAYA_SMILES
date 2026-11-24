/*
 * view2d.js — the 2D drawing behaves like the 3D view:
 *   - zoom with the mouse wheel / pinch, drag to move, double-click or "Fit" to reset
 *   - Image and Record capture what you see: 3D, 2D or 3D + 2D side by side
 */
(function () {
  'use strict';
  const MIN = 0.5, MAX = 8;
  let st = { k: 1, x: 0, y: 0 };
  let svg = null, panel = null;

  const apply = () => { if (svg) svg.style.transform = `translate(${st.x}px, ${st.y}px) scale(${st.k})`; };
  const reset = () => { st = { k: 1, x: 0, y: 0 }; apply(); };

  function zoomAt(factor, cx, cy) {
    // keep the point under the cursor fixed: positions are relative to the untransformed svg centre
    const r = svg.getBoundingClientRect();
    const ox = r.left + r.width / 2, oy = r.top + r.height / 2;      // current centre on screen
    const k = Math.min(MAX, Math.max(MIN, st.k * factor));
    const f = k / st.k;
    st.x += (cx - ox) * (1 - f);
    st.y += (cy - oy) * (1 - f);
    st.k = k;
    apply();
  }

  function attach(p) {
    const s = p.querySelector('svg');
    if (!s || s === svg) return;
    svg = s; panel = p;
    reset();
    svg.style.transformOrigin = 'center center';
    svg.style.transition = 'none';
    svg.style.cursor = 'grab';
    svg.style.touchAction = 'none';
    p.title = 'Scroll to zoom · drag to move · double-click to reset';

    p.addEventListener('wheel', (e) => {
      if (!svg) return;
      e.preventDefault();
      zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY);
    }, { passive: false });

    const pts = new Map();
    let last = null, pinch = null;
    p.addEventListener('pointerdown', (e) => {
      if (e.target.closest('button, #molecule-controls, .view-toggle')) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      p.setPointerCapture?.(e.pointerId);
      if (pts.size === 1) { last = { x: e.clientX, y: e.clientY }; svg.style.cursor = 'grabbing'; }
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) };
      }
    });
    p.addEventListener('pointermove', (e) => {
      if (!pts.has(e.pointerId)) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 2 && pinch) {
        const [a, b] = [...pts.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch.d > 0) zoomAt(d / pinch.d, (a.x + b.x) / 2, (a.y + b.y) / 2);
        pinch.d = d;
      } else if (last) {
        st.x += e.clientX - last.x; st.y += e.clientY - last.y;
        last = { x: e.clientX, y: e.clientY };
        apply();
      }
    });
    const up = (e) => {
      pts.delete(e.pointerId);
      if (pts.size < 2) pinch = null;
      if (!pts.size) { last = null; if (svg) svg.style.cursor = 'grab'; }
    };
    p.addEventListener('pointerup', up);
    p.addEventListener('pointercancel', up);
    p.addEventListener('dblclick', reset);
  }

  // the 2D panel is re-created every time the view changes: watch for it
  const root = document.getElementById('viewer-container');
  if (root) {
    new MutationObserver(() => {
      const p = document.getElementById('viewer-2d');
      if (p) attach(p); else { svg = null; panel = null; }
    }).observe(root, { childList: true, subtree: true });
  }
  document.addEventListener('click', (e) => { if (e.target.closest('#fit-btn')) reset(); });

  // ------------------------------------------------------------------ capture
  function svgImage(s, px) {
    return new Promise((resolve, reject) => {
      const c = s.cloneNode(true);
      const vb = (s.getAttribute('viewBox') || '0 0 340 340').split(/[\s,]+/).map(Number);
      c.setAttribute('width', String(px));
      c.setAttribute('height', String(Math.round(px * vb[3] / vb[2])));
      c.removeAttribute('style');
      c.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(c)], { type: 'image/svg+xml' }));
      const img = new Image();
      img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = (e) => { URL.revokeObjectURL(url); reject(e); };
      img.src = url;
    });
  }

  // draws the viewer exactly as it is on screen (3D canvas, 2D drawing with its zoom) into `ctx`
  function paint(ctx, scale, img2d) {
    const box = root.getBoundingClientRect();
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, box.width, box.height);
    const c3 = root.querySelector('#viewer-3d canvas');
    if (c3) {
      const r = c3.getBoundingClientRect();
      try { ctx.drawImage(c3, r.left - box.left, r.top - box.top, r.width, r.height); } catch (e) { /* */ }
    }
    const p = document.getElementById('viewer-2d');
    const s = p && p.querySelector('svg');
    if (p && s && img2d) {
      const pr = p.getBoundingClientRect();
      const L = Math.max(pr.left, box.left), T = Math.max(pr.top, box.top);
      const R = Math.min(pr.right, box.right), B = Math.min(pr.bottom, box.bottom);
      ctx.save();
      ctx.beginPath();
      ctx.rect(L - box.left, T - box.top, R - L, B - T);
      ctx.clip();
      if (getComputedStyle(p).backgroundColor !== 'rgba(0, 0, 0, 0)') {
        ctx.fillStyle = getComputedStyle(p).backgroundColor;
        ctx.fillRect(L - box.left, T - box.top, R - L, B - T);
      }
      const sr = s.getBoundingClientRect();
      ctx.drawImage(img2d, sr.left - box.left, sr.top - box.top, sr.width, sr.height);
      ctx.restore();
    }
  }

  async function snapshot() {
    const box = root.getBoundingClientRect();
    const scale = Math.max(2, window.devicePixelRatio || 1);
    const cv = document.createElement('canvas');
    cv.width = Math.round(box.width * scale); cv.height = Math.round(box.height * scale);
    const s = document.querySelector('#viewer-2d svg');
    const img = s ? await svgImage(s, 1600) : null;
    try { currentVisualizations[0]?.render?.(); } catch (e) { /* */ }   // eslint-disable-line no-undef
    paint(cv.getContext('2d'), scale, img);
    return cv;
  }

  // a canvas that keeps repainting the viewer, for MediaRecorder
  async function liveCanvas() {
    const box = root.getBoundingClientRect();
    const scale = Math.min(2, window.devicePixelRatio || 1);
    const cv = document.createElement('canvas');
    cv.width = Math.round(box.width * scale); cv.height = Math.round(box.height * scale);
    const ctx = cv.getContext('2d');
    let img = null, imgFor = null, on = true;
    const loop = async () => {
      if (!on) return;
      const s = document.querySelector('#viewer-2d svg');
      if (s && s !== imgFor) { imgFor = s; try { img = await svgImage(s, 1600); } catch (e) { img = null; } }
      paint(ctx, scale, s ? img : null);
      requestAnimationFrame(loop);
    };
    loop();
    return { canvas: cv, stop: () => { on = false; } };
  }

  window.ElayaView2D = { reset, snapshot, liveCanvas };
})();
