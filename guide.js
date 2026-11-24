/*
 * guide.js — makes the first visit obvious.
 *   - which page you are on (body[data-page]) and a sliding indicator under the active menu item
 *   - a 4-step bar on the explorer that follows what you do (current step glows, finished steps get ✓)
 *   - spotlight on the next thing to do, a "start here" bubble, an empty results card
 *   - a short guided tour (offered once on the first visit, always available from the step bar)
 *   - on About / Contact: a floating arrow that says there is more below, and turns into "back to top"
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const NAV_H = 48;

  // ------------------------------------------------------------------ page + menu indicator
  const page = () => document.body.dataset.page || 'explore';
  function initPages() {
    const map = { '#explore': 'explore', '#about': 'about', '#contact': 'contact' };
    const bar = document.querySelector('.navbar-container');
    let ind = null;
    if (bar) {
      ind = document.createElement('span');
      ind.className = 'nav-indicator';
      ind.setAttribute('aria-hidden', 'true');
      bar.appendChild(ind);
    }
    const place = () => {
      const a = document.querySelector(`.navbar a[href="#${page()}"]`);
      document.querySelectorAll('.navbar a[href^="#"]').forEach(x => {
        if (map[x.getAttribute('href')]) x.toggleAttribute('aria-current', x === a);
      });
      if (!ind || !a) return;
      const r = a.getBoundingClientRect(), rb = bar.getBoundingClientRect();
      ind.style.width = `${r.width - 16}px`;
      ind.style.transform = `translateX(${r.left - rb.left + 8}px)`;
      ind.classList.add('on');
    };
    const set = (p) => {
      document.body.dataset.page = p;
      place();
      document.dispatchEvent(new CustomEvent('elaya:page', { detail: { page: p } }));
    };
    Object.entries(map).forEach(([href, p]) => {
      document.querySelectorAll(`a[href="${href}"]`).forEach(a => a.addEventListener('click', () => set(p)));
    });
    window.addEventListener('resize', place);
    document.fonts?.ready?.then(place);
    set('explore');
    setTimeout(place, 300);
  }

  // ------------------------------------------------------------------ explorer: step bar + spotlight
  const hasResults = () => {
    const c = $('molecule-controls');
    if (c && c.style.display !== 'none' && getComputedStyle(c).display !== 'none') return true;
    if ((window.ELAYA_CONFORMERS?.list || []).length) return true;
    const x = $('xyz-display');
    return !!(x && x.style.display !== 'none' && x.textContent.trim().length > 20);
  };
  const isBusy = () => {
    const w = document.querySelector('#convert-molecules .water-loader');
    return !!(window.ELAYA_GLOMOS_RUNNING || (w && w.style.display !== 'none' && getComputedStyle(w).display !== 'none'));
  };
  const moleculeReady = () => {
    const fileMode = document.querySelector('input[name="input-method"][value="file"]')?.checked;
    if (fileMode) return !!($('smiles-file')?.files?.length);
    const st = $('smiles-status');
    const v = ($('smiles')?.value || '').trim();
    return !!v && (!st || st.className !== 'bad');
  };

  const TARGETS = {
    input: () => document.querySelector('.input-section'),
    settings: () => document.querySelector('.method-controls'),
    convert: () => $('convert-molecules'),
    results: () => document.querySelector('.visualization-container'),
  };

  function scrollToEl(el, focus) {
    if (!el) return;
    const top = el.getBoundingClientRect().top + window.scrollY - NAV_H - 70;
    window.scrollTo({ top: Math.max(0, top), behavior: reduceMotion ? 'auto' : 'smooth' });
    if (focus) setTimeout(() => focus.focus({ preventScroll: true }), 350);
  }

  function initSteps() {
    const bar = $('guide-steps');
    if (!bar) return;
    const items = [...bar.querySelectorAll('li[data-step]')];
    let lastState = '';

    // the "start here" bubble next to the SMILES box
    const bubble = document.createElement('div');
    bubble.className = 'start-bubble';
    bubble.innerHTML = '<span class="sb-arrow" aria-hidden="true">↓</span> Start here: type a SMILES or click an example';
    const wrap = $('single-input');
    if (wrap) wrap.insertAdjacentElement('afterbegin', bubble);

    const cta = document.createElement('div');
    cta.className = 'convert-cta';
    cta.innerHTML = 'Next: <b>Convert</b> <span aria-hidden="true">→</span>';
    const btn = $('convert-molecules');
    if (btn) btn.insertAdjacentElement('beforebegin', cta);

    const update = () => {
      if (page() !== 'explore') return;
      const s1 = moleculeReady();
      const res = hasResults();
      const busy = isBusy();
      const cur = res ? 4 : s1 ? 3 : 1;
      const state = `${s1}|${res}|${busy}|${cur}`;
      if (state === lastState) return;
      lastState = state;

      items.forEach(li => {
        const n = Number(li.dataset.step);
        const done = n < cur || (n === 4 && res) || (n === 2 && s1);
        li.classList.toggle('done', done && !(n === 3 && busy));
        li.classList.toggle('current', n === cur && !(n === 4 && res && false));
        li.classList.toggle('busy', n === 3 && busy);
        li.querySelector('button').setAttribute('aria-current', n === cur ? 'step' : 'false');
      });
      if (busy) items[2].querySelector('small').textContent = 'Working… please wait';
      else items[2].querySelector('small').textContent = res ? 'Done · convert again any time' : 'Build the 3D structure';

      document.body.classList.toggle('g-no-molecule', !s1 && !res);
      document.body.classList.toggle('g-ready', s1 && !res && !busy);
      document.body.classList.toggle('g-results', res);
      document.body.classList.toggle('g-busy', busy);
      const empty = (($('smiles')?.value || '').trim() === '');
      bubble.classList.toggle('show', !s1 && !res && empty && !document.querySelector('input[name="input-method"][value="file"]')?.checked);
      cta.classList.toggle('show', s1 && !res && !busy);
      if (res) {   // they found their way: the welcome card is no longer needed
        const w = document.querySelector('.welcome-card');
        if (w) { w.classList.remove('show'); setTimeout(() => w.remove(), 300); store.set('elaya.tour.seen', true); }
      }
    };

    bar.querySelectorAll('button[data-target]').forEach(b => b.addEventListener('click', () => {
      const t = b.dataset.target;
      const el = TARGETS[t]?.();
      scrollToEl(el, t === 'input' ? $('smiles') : t === 'convert' ? $('convert-molecules') : null);
      if (el) { el.classList.remove('g-flash'); void el.offsetWidth; el.classList.add('g-flash'); }
    }));

    ['input', 'change', 'click', 'keyup'].forEach(ev => document.addEventListener(ev, () => setTimeout(update, 60), true));
    window.addEventListener('elaya:file-loaded', () => setTimeout(update, 60));
    window.addEventListener('elaya:glomos-state', () => setTimeout(update, 60));
    window.addEventListener('elaya:glomos-done', () => setTimeout(update, 300));
    setInterval(update, 700);
    update();

    document.querySelectorAll('.re-example').forEach(b => b.addEventListener('click', () => {
      const chip = document.querySelector(`.example-chip[data-smiles="${b.dataset.smiles}"]`);
      if (chip) chip.click();
      else { const i = $('smiles'); i.value = b.dataset.smiles; i.dispatchEvent(new Event('input', { bubbles: true })); }
      scrollToEl(TARGETS.input());
    }));
  }

  // ------------------------------------------------------------------ guided tour
  const TOUR = [
    { el: () => $('guide-steps'), t: 'Four steps, in order', b: 'This bar shows where you are. The glowing step is the next thing to do; finished steps get a ✓. Click any step to jump to it.' },
    { el: () => document.querySelector('.input-section'), t: '1 · Enter a molecule', b: 'Type a SMILES string (a molecule written as text) and press Enter, or click one of the examples. Below the box ELAYA tells you the formula and whether the SMILES is valid.' },
    { el: () => document.querySelector('.input-method'), t: 'Many molecules?', b: 'Switch to “SMILES File” and drop a .smi, .txt or .csv file with one molecule per line. You can download an example file there.' },
    { el: () => document.querySelector('.method-controls'), t: '2 · Settings (optional)', b: 'How to build the 3D structure, an optional force-field clean-up, and the advanced GLOMOS conformer search. The defaults work. Each ⓘ explains its option.' },
    { el: () => $('convert-molecules'), t: '3 · Convert', b: 'Builds the 3D structure. It usually takes a second; GLOMOS takes minutes and shows its progress live.' },
    { el: () => document.querySelector('.visualization-container'), t: '4 · Explore', b: 'Drag to rotate, scroll to zoom. Switch between 3D and 2D, record a video or take a picture, and use ⤢ for full screen.' },
    { el: () => document.querySelector('.visualization-controls'), t: 'Results & downloads', b: 'Coordinates in six formats (XYZ, MOL, SDF, PDB, MOL2, CML), quality checks, and buttons to download one or all.' },
    { el: () => document.querySelector('.navbar a[href="#about"]'), t: 'New to chemistry?', b: 'The About tab has a 15-minute mini-course: SMILES, 3D structures, conformers and GLOMOS, with interactive examples.' },
  ];

  function initTour() {
    let i = 0, layer = null, spot = null, card = null, prevFocus = null;
    const close = (done) => {
      if (!layer) return;
      layer.remove(); spot.remove(); card.remove();
      document.body.classList.remove('tour-on');
      layer = spot = card = null;
      document.removeEventListener('keydown', onKey, true);
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
      store.set('elaya.tour.seen', true);
      if (done) toast('You are ready. Start with step 1 ✨');
      prevFocus?.focus?.({ preventScroll: true });
    };
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); close(false); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); go(i + 1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); go(i - 1); }
    };
    const place = () => {
      if (!card) return;
      const el = TOUR[i].el();
      if (!el) return;
      const r = el.getBoundingClientRect(), pad = 8;
      Object.assign(spot.style, { left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + 2 * pad}px`, height: `${r.height + 2 * pad}px` });
      const cw = Math.min(360, window.innerWidth - 24), ch = card.offsetHeight || 180;
      let top = r.bottom + 16;
      if (top + ch > window.innerHeight - 12) top = r.top - ch - 16;
      if (top < NAV_H + 8) top = Math.min(window.innerHeight - ch - 12, Math.max(NAV_H + 8, r.top + 16));
      let left = Math.min(window.innerWidth - cw - 12, Math.max(12, r.left + r.width / 2 - cw / 2));
      Object.assign(card.style, { width: `${cw}px`, left: `${left}px`, top: `${top}px` });
    };
    const go = (k) => {
      if (k >= TOUR.length) return close(true);
      if (k < 0) return;
      i = k;
      const st = TOUR[i], el = st.el();
      if (el) {
        const r = el.getBoundingClientRect();
        const want = r.top + window.scrollY - Math.max(NAV_H + 20, (window.innerHeight - Math.min(r.height, window.innerHeight * 0.55)) / 2 - 60);
        window.scrollTo({ top: Math.max(0, want), behavior: 'auto' });
      }
      card.innerHTML = `
        <div class="tour-top"><span class="tour-count">${i + 1} / ${TOUR.length}</span><button type="button" class="tour-x" aria-label="Close the tour">✕</button></div>
        <h3 id="tour-title">${st.t}</h3><p>${st.b}</p>
        <div class="tour-dots" aria-hidden="true">${TOUR.map((_, k) => `<span class="${k === i ? 'on' : k < i ? 'done' : ''}"></span>`).join('')}</div>
        <div class="tour-nav">
          <button type="button" class="tour-skip">Skip</button>
          <span>${i ? '<button type="button" class="tour-back">← Back</button>' : ''}
          <button type="button" class="tour-next">${i === TOUR.length - 1 ? 'Finish ✓' : 'Next →'}</button></span>
        </div>`;
      card.querySelector('.tour-x').onclick = () => close(false);
      card.querySelector('.tour-skip').onclick = () => close(false);
      card.querySelector('.tour-next').onclick = () => go(i + 1);
      const back = card.querySelector('.tour-back'); if (back) back.onclick = () => go(i - 1);
      place();
      requestAnimationFrame(place);
      card.querySelector('.tour-next').focus({ preventScroll: true });
    };
    const start = () => {
      if (page() !== 'explore') document.querySelector('.navbar a[href="#explore"]')?.click();
      hideWelcome();
      prevFocus = document.activeElement;
      layer = document.createElement('div'); layer.className = 'tour-layer';
      layer.addEventListener('click', () => close(false));
      spot = document.createElement('div'); spot.className = 'tour-spot';
      card = document.createElement('div'); card.className = 'tour-card';
      card.setAttribute('role', 'dialog'); card.setAttribute('aria-modal', 'true'); card.setAttribute('aria-labelledby', 'tour-title');
      document.body.append(layer, spot, card);
      document.body.classList.add('tour-on');
      document.addEventListener('keydown', onKey, true);
      window.addEventListener('resize', place);
      window.addEventListener('scroll', place, true);
      setTimeout(() => go(0), page() === 'explore' ? 0 : 400);
    };
    $('guide-tour-btn')?.addEventListener('click', start);

    // welcome card, only the first time
    let welcome = null;
    const hideWelcome = () => { welcome?.classList.remove('show'); setTimeout(() => welcome?.remove(), 300); };
    if (!store.get('elaya.tour.seen', false)) {
      welcome = document.createElement('div');
      welcome.className = 'welcome-card';
      welcome.setAttribute('role', 'dialog');
      welcome.setAttribute('aria-label', 'Welcome');
      welcome.innerHTML = `<b>👋 New to ELAYA?</b><p>A 30-second tour shows you the four steps.</p>
        <div><button type="button" class="wc-go">Take the tour</button><button type="button" class="wc-no">No, thanks</button></div>`;
      document.body.appendChild(welcome);
      setTimeout(() => welcome.classList.add('show'), 900);
      welcome.querySelector('.wc-go').onclick = start;
      welcome.querySelector('.wc-no').onclick = () => { store.set('elaya.tour.seen', true); hideWelcome(); };
    }
  }

  function toast(msg) {
    let t = document.querySelector('.learn-toast');
    if (!t) { t = document.createElement('div'); t.className = 'learn-toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._h);
    t._h = setTimeout(() => t.classList.remove('show'), 3000);
  }

  // ------------------------------------------------------------------ About / Contact: "more below" ↔ "back to top"
  function initScrollCue() {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'scroll-cue';
    b.innerHTML = '<span class="sc-label">More below</span><span class="sc-arrow" aria-hidden="true"><svg viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg></span>';
    document.body.appendChild(b);
    const update = () => {
      const p = page();
      if (p === 'explore') { b.classList.remove('show'); return; }
      const left = document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);
      const atEnd = left < 260;
      b.classList.add('show');
      b.classList.toggle('up', atEnd);
      b.querySelector('.sc-label').textContent = atEnd ? 'Back to top' : 'More below';
      b.setAttribute('aria-label', atEnd ? 'Back to top' : 'Scroll down to see more');
      b.classList.toggle('compact', window.scrollY > 120 && !atEnd);
    };
    b.addEventListener('click', () => {
      if (b.classList.contains('up')) { window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' }); return; }
      // jump to the next block (lesson, panel) below the fold, or one screen down
      const blocks = [...document.querySelectorAll(page() === 'about'
        ? '#about-section .lesson, #about-section .lp-bottom-grid, #about-section .learn'
        : '#contact-section .contact-layout, #contact-section .contact-panel, #contact-section .contact-two')];
      const next = blocks.map(el => el.getBoundingClientRect().top).filter(t => t > NAV_H + 90).sort((a, c) => a - c)[0];
      const dy = next !== undefined && next < window.innerHeight * 1.4 ? next - NAV_H - 20 : window.innerHeight * 0.8;
      window.scrollBy({ top: dy, behavior: reduceMotion ? 'auto' : 'smooth' });
    });
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    document.addEventListener('elaya:page', () => setTimeout(update, 450));
    update();
  }

  function init() {
    initPages();
    initSteps();
    initTour();
    initScrollCue();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
