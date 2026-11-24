/*
 * learn.js — the mini-course in the About page.
 *   - table of contents with scroll-spy, reading progress and "lesson read" ticks (kept in this browser)
 *   - SMILES playground: tokenises the string and explains every character; 2D drawing + facts from the server
 *   - butane explorer: Newman projection, torsional energy curve and Boltzmann populations
 *   - GLOMOS stepper and a short quiz
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const store = {
    get(k, d) { try { const v = sessionStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* */ } },
  };
  const NAV_OFFSET = 70;

  // ------------------------------------------------------------------ TOC, progress, read ticks
  // shared course state (used by the search, the quiz and the flowchart)
  const course = { go: () => {}, markRead: () => {}, openAboutThen: (fn) => fn() };

  function toast(msg) {
    let t = document.querySelector('.learn-toast');
    if (!t) { t = document.createElement('div'); t.className = 'learn-toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._h);
    t._h = setTimeout(() => t.classList.remove('show'), 3200);
  }

  function initToc() {
    const toc = document.querySelector('.learn-toc');
    const lessons = [...document.querySelectorAll('.learn .lesson')];
    if (!toc || !lessons.length) return;
    const links = [...toc.querySelectorAll('a[data-ch]')];
    const read = new Set(store.get('elaya.learn.read', []));
    const counted = lessons.filter(l => l.id !== 'c-more');
    const aboutVisible = () => { const a = $('about-section'); return a && a.style.display !== 'none'; };

    const paint = () => {
      links.forEach(a => a.classList.toggle('read', read.has(a.dataset.ch)));
      const n = counted.filter(l => read.has(l.id)).length;
      if ($('learn-done-count')) $('learn-done-count').textContent = `${n}/${counted.length}`;
      if ($('learn-toc-bar')) $('learn-toc-bar').style.width = `${(100 * n / counted.length).toFixed(0)}%`;
      const cont = $('hero-continue-btn'), first = counted.find(l => !read.has(l.id));
      if (cont) {
        cont.hidden = !(n > 0 && first);
        if (first) { cont.setAttribute('href', `#${first.id}`); cont.textContent = `Continue the course: ${first.querySelector('h2')?.textContent || ''} ↓`; }
      }
    };
    const markRead = (id) => {
      if (!id || read.has(id) || !counted.some(l => l.id === id)) return;
      read.add(id);
      store.set('elaya.learn.read', [...read]);
      paint();
      if (counted.every(l => read.has(l.id))) toast('🎉 Mini-course completed! You are ready to run GLOMOS.');
    };
    course.markRead = markRead;

    // on narrow screens the contents become a sticky chip bar, which also covers the top of the page
    const tocCovers = () => getComputedStyle(toc).position === 'sticky' && window.innerWidth <= 1000 ? toc.offsetHeight + 8 : 0;
    let jumping = false, jumpTimer = null;      // lessons flown over by a jump are not "visited"
    const go = (id, el) => {
      const t = el || $(id);
      if (!t) return;
      jumping = true;
      clearTimeout(jumpTimer);
      jumpTimer = setTimeout(() => { jumping = false; spy(); }, 1100);
      window.scrollTo({ top: t.getBoundingClientRect().top + window.scrollY - NAV_OFFSET - tocCovers() - (el ? 24 : 0), behavior: 'smooth' });
    };
    const openAboutThen = (fn) => {
      if (aboutVisible()) return fn();
      document.querySelector('a[href="#about"]')?.click();
      setTimeout(fn, 450);
    };
    course.go = go;
    course.openAboutThen = openAboutThen;

    links.forEach(a => a.addEventListener('click', (e) => { e.preventDefault(); go(a.dataset.ch); }));
    // any other link to a lesson (hero buttons, contact page) opens About first
    document.querySelectorAll('a[href^="#c-"]:not([data-ch])').forEach(a => a.addEventListener('click', (e) => {
      e.preventDefault();
      const id = a.getAttribute('href').slice(1);
      openAboutThen(() => go(id));
    }));
    document.querySelectorAll('.lesson-next').forEach(b => b.addEventListener('click', () => {
      markRead(b.closest('.lesson')?.id);
      go(b.dataset.next);
    }));
    $('learn-reset')?.addEventListener('click', () => {
      read.clear(); store.set('elaya.learn.read', []); paint();
      toast('Progress reset.');
    });

    // A lesson counts as visited once you have scrolled to its end (its bottom edge is on screen while the
    // lesson fills the reading area), or after it has been the lesson you are reading for a few seconds.
    let activeId = null, activeSince = 0;
    const spy = () => {
      if (!aboutVisible()) return;
      const vh = window.innerHeight;
      const line = Math.max(vh * 0.35, NAV_OFFSET + tocCovers() + 20);
      let active = lessons[0].id;
      for (const l of lessons) {
        const r = l.getBoundingClientRect();
        if (r.top < line) active = l.id;
        if (!jumping && r.height && r.bottom <= vh - 4 && r.bottom > NAV_OFFSET) markRead(l.id);     // its end is visible
      }
      if (active !== activeId) {
        activeId = active; activeSince = performance.now();
        const k = lessons.findIndex(l => l.id === active);
        const sub = $('learn-toc-sub');
        if (sub) sub.textContent = k < counted.length ? `You are on lesson ${k} of ${counted.length - 1} · ${lessons[k].querySelector('h2')?.textContent || ''}` : 'Extra: videos, papers and glossary';
      }
      links.forEach(a => {
        const on = a.dataset.ch === active;
        if (on && !a.classList.contains('active')) {
          a.setAttribute('aria-current', 'true');
          const ol = a.closest('ol');      // keep the active chip visible in the horizontal bar (mobile)
          if (ol && ol.scrollWidth > ol.clientWidth) ol.scrollTo({ left: a.offsetLeft - ol.offsetLeft - 16, behavior: 'smooth' });
        } else if (!on) a.removeAttribute('aria-current');
        a.classList.toggle('active', on);
      });
      const learn = $('learn');
      const bar = $('learn-progress-bar');
      if (learn && bar) {
        const r = learn.getBoundingClientRect();
        const p = Math.min(1, Math.max(0, (vh * 0.5 - r.top) / r.height));
        bar.style.width = `${(p * 100).toFixed(1)}%`;
      }
    };
    setInterval(() => {      // dwell: 6 s on a lesson also counts (long lessons read on a small screen)
      if (aboutVisible() && activeId && !document.hidden && performance.now() - activeSince > 6000) markRead(activeId);
    }, 1000);
    window.addEventListener('scroll', spy, { passive: true });
    window.addEventListener('resize', spy);
    document.querySelector('a[href="#about"]')?.addEventListener('click', () => setTimeout(spy, 300));

    paint();
    spy();
  }

  // ------------------------------------------------------------------ course search (history kept for this session)
  const SYN = {      // Spanish → English, so Spanish speakers find things in the English course
    conformero: 'conformer', conformeros: 'conformer', enlace: 'bond', enlaces: 'bond', anillo: 'ring', anillos: 'ring',
    energia: 'energy', poblacion: 'population', algoritmo: 'algorithm', genetico: 'genetic', archivo: 'file', formato: 'format',
    estereo: 'stereo', carga: 'charge', temperatura: 'temperature', molecula: 'molecule', atomo: 'atom', doble: 'double',
    triple: 'triple', rama: 'branch', ramificacion: 'branch', aromatico: 'aromatic', campo: 'force field', fuerza: 'force',
    mutacion: 'mutation', cruce: 'mating', generacion: 'generation', semilla: 'seed', diedro: 'dihedral', torsion: 'torsion',
    descargar: 'download', citar: 'cite', rotacional: 'rotational', constantes: 'constants', isomero: 'isomer', red: 'network',
    neuronal: 'neural', video: 'video', videos: 'video', glosario: 'glossary', butano: 'butane', hidrogeno: 'hydrogen',
  };
  const norm = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

  function initSearch() {
    const q = $('learn-q'), box = $('learn-results');
    if (!q || !box) return;
    const HKEY = 'elaya.learn.searches';
    const hist = { get: () => { try { return JSON.parse(sessionStorage.getItem(HKEY) || '[]'); } catch (e) { return []; } },
                   set: (v) => { try { sessionStorage.setItem(HKEY, JSON.stringify(v)); } catch (e) { /* */ } } };
    const remember = (term) => {
      term = term.trim();
      if (term.length < 2) return;
      hist.set([term, ...hist.get().filter(h => norm(h) !== norm(term))].slice(0, 8));
    };

    let index = null;
    const build = () => {
      const out = [];
      document.querySelectorAll('.learn .lesson').forEach(l => {
        const where = l.querySelector('h2')?.textContent.trim() || '';
        l.querySelectorAll('h2, h3, p, li, tr, dt, .res, .learn-card, .learn-callout, .fc-node, .bt-note, .pg-title').forEach(el => {
          if (el.closest('.res') && !el.classList.contains('res')) return;
          if (el.closest('.learn-card') && !el.classList.contains('learn-card')) return;
          if (el.closest('.learn-callout') && !el.classList.contains('learn-callout')) return;
          if (el.closest('.fc-node') && !el.classList.contains('fc-node')) return;
          let text;
          if (el.tagName === 'TR') text = [...el.children].map(c => c.textContent.trim()).join(' — ');
          else if (el.classList.contains('fc-node')) text = `${el.querySelector('b')?.textContent}: ${el.querySelector('small')?.textContent}`;
          else if (el.classList.contains('res')) text = [...el.querySelectorAll('b, span:not(.res-tag)')].map(c => c.textContent.trim()).join(' — ');
          else text = el.textContent;
          text = text.replace(/\s+/g, ' ').trim();
          if (el.tagName === 'DT') text += ' — ' + (el.nextElementSibling?.textContent || '').trim();
          if (el.tagName === 'H2') text = `Lesson: ${text}`;
          if (text.length > 2) out.push({ where, lesson: l.id, el, text, n: norm(text) });
        });
      });
      STEPS.forEach((st, k) => out.push({ where: 'GLOMOS step by step', lesson: 'c-glomos', step: k, text: `${k + 1}. ${st.t} — ${st.b} ${st.p}`, n: norm(`${st.t} ${st.b} ${st.p}`) }));
      QUIZ.forEach((x, k) => out.push({ where: 'Check yourself', lesson: 'c-quiz', el: null, quiz: k, text: `${x.q} ${x.why}`, n: norm(`${x.q} ${x.why}`) }));
      return out;
    };

    const terms = (s) => norm(s).split(/\s+/).filter(Boolean).map(w => SYN[w] ? norm(SYN[w]) : w);
    const snippet = (text, ts) => {
      const n = norm(text);
      let at = -1;
      for (const t of ts) { at = n.indexOf(t); if (at >= 0) break; }
      const start = Math.max(0, at - 50);
      let out = (start ? '…' : '') + text.slice(start, start + 150) + (start + 150 < text.length ? '…' : '');
      out = esc(out);
      ts.forEach(t => {
        if (t.length < 2) return;
        const re = new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').split('').map(c => c === 'a' ? '[aáà]' : c === 'e' ? '[eéè]' : c === 'i' ? '[ií]' : c === 'o' ? '[oóò]' : c === 'u' ? '[uúü]' : c === 'n' ? '[nñ]' : c).join('')})`, 'gi');
        out = out.replace(re, '<mark>$1</mark>');
      });
      return out;
    };

    let results = [], sel = -1;
    const open = (on) => { box.hidden = !on; q.setAttribute('aria-expanded', on ? 'true' : 'false'); };
    const showHistory = () => {
      const h = hist.get();
      if (!h.length) { open(false); return; }
      box.innerHTML = `<div class="lr-head">Recent searches (this session)<button type="button" id="lr-clear">clear</button></div>
        <div class="lr-hist">${h.map(x => `<button type="button" data-h="${esc(x)}">${esc(x)}</button>`).join('')}</div>`;
      box.querySelectorAll('[data-h]').forEach(b => b.addEventListener('mousedown', (e) => { e.preventDefault(); q.value = b.dataset.h; run(); }));
      $('lr-clear').addEventListener('mousedown', (e) => { e.preventDefault(); hist.set([]); open(false); });
      open(true);
    };
    const run = () => {
      const raw = q.value.trim();
      if (raw.length < 2) { results = []; showHistory(); return; }
      index = index || build();
      const ts = terms(raw);
      results = index.map(r => {
        let score = 0;
        for (const t of ts) { const i = r.n.indexOf(t); if (i < 0) return null; score += (i < 40 ? 3 : 1) + (r.el && /^H[23]$/.test(r.el.tagName) ? 4 : 0); }
        return { r, score: score - r.text.length / 400 };
      }).filter(Boolean).sort((a, b) => b.score - a.score).slice(0, 8).map(x => x.r);
      sel = -1;
      box.innerHTML = results.length
        ? `<div class="lr-head">${results.length} result${results.length === 1 ? '' : 's'}</div>` +
          results.map((r, i) => `<button type="button" class="lr-item" role="option" data-i="${i}"><span class="lr-where">${esc(r.where)}</span>${snippet(r.text, ts)}</button>`).join('')
        : `<div class="lr-empty">No results for “${esc(raw)}”. Try another word (e.g. ring, conformer, ANI).</div>`;
      box.querySelectorAll('.lr-item').forEach(b => b.addEventListener('mousedown', (e) => { e.preventDefault(); pick(Number(b.dataset.i)); }));
      open(true);
    };
    const pick = (i) => {
      const r = results[i];
      if (!r) return;
      remember(q.value);
      open(false);
      q.blur();
      course.openAboutThen(() => {
        let target = r.el;
        if (r.step !== undefined) { window.elayaShowStep?.(r.step); target = $('glomos-stepper'); }
        if (r.quiz !== undefined) target = document.querySelectorAll('#learn-quiz .qz')[r.quiz];
        target = target || $(r.lesson);
        const det = target.closest('details'); if (det) det.open = true;
        course.go(r.lesson, target);
        target.classList.remove('learn-flash'); void target.offsetWidth; target.classList.add('learn-flash');
        setTimeout(() => target.classList.remove('learn-flash'), 2300);
      });
    };
    const mark = () => box.querySelectorAll('.lr-item').forEach((b, i) => { b.classList.toggle('sel', i === sel); if (i === sel) b.scrollIntoView({ block: 'nearest' }); });

    q.addEventListener('input', run);
    q.addEventListener('focus', run);
    q.addEventListener('blur', () => setTimeout(() => open(false), 120));
    q.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' && results.length) { e.preventDefault(); sel = (sel + 1) % results.length; mark(); }
      else if (e.key === 'ArrowUp' && results.length) { e.preventDefault(); sel = (sel - 1 + results.length) % results.length; mark(); }
      else if (e.key === 'Enter') { e.preventDefault(); if (results.length) pick(sel < 0 ? 0 : sel); else remember(q.value); }
      else if (e.key === 'Escape') { open(false); q.blur(); }
    });
    // "/" focuses the search while reading the course
    document.addEventListener('keydown', (e) => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (document.activeElement?.tagName || '').toLowerCase();
      if (['input', 'textarea', 'select'].includes(tag) || document.activeElement?.isContentEditable) return;
      const about = $('about-section');
      if (!about || about.style.display === 'none') return;
      e.preventDefault();
      q.focus();
    });
  }

  // ------------------------------------------------------------------ lesson 0 flowchart
  const FLOW = {
    1: '<b>Input.</b> Type a SMILES string, pick an example, or upload a file with one molecule per line (names are kept).',
    2: '<b>Check.</b> RDKit reads the string: valences, charges, rings, stereocentres and E/Z bonds. Invalid input is flagged before anything runs.',
    3: '<b>Build 3D.</b> Atoms get x, y, z coordinates with RDKit (distance geometry), OpenBabel (templates) or NetworkX (graph layout). The result is checked back against your SMILES.',
    4: '<b>Relax (optional).</b> A force field (UFF or MMFF94) nudges the structure into the nearest energy valley in a fraction of a second.',
    5: '<b>GLOMOS (optional).</b> A genetic algorithm twists the rotatable bonds, relaxes every candidate with the ANI neural network and keeps the best — generation after generation.',
    6: '<b>Results.</b> Explore the structure in 3D, compare conformers (ΔE, populations, rotational constants) and download XYZ, MOL, SDF, PDB, MOL2 or CML.',
  };
  function initFlow() {
    const flow = $('elaya-flow');
    if (!flow) return;
    const det = $('fc-detail');
    const nodes = [...flow.querySelectorAll('.fc-node')];
    const show = (n) => {
      nodes.forEach(b => b.classList.toggle('on', b.dataset.detail === String(n)));
      const b = nodes.find(x => x.dataset.detail === String(n));
      const title = $(b?.dataset.go)?.querySelector('h2')?.textContent || '';
      det.innerHTML = `${FLOW[n]} <span class="fc-more">→ ${esc(title)}</span>`;
    };
    nodes.forEach(b => {
      b.addEventListener('mouseenter', () => show(b.dataset.detail));
      b.addEventListener('focus', () => show(b.dataset.detail));
      b.addEventListener('click', () => course.go(b.dataset.go));
    });
    // gently walk through the steps until the user interacts
    let k = 1, auto = setInterval(() => { show(k); k = k % 6 + 1; }, 3200);
    const stop = () => { clearInterval(auto); auto = null; };
    flow.addEventListener('mouseenter', stop, { once: true });
    flow.addEventListener('focusin', stop, { once: true });
    flow.addEventListener('touchstart', stop, { once: true, passive: true });
    show(1);
  }

  // ------------------------------------------------------------------ SMILES playground
  const ORGANIC = { B: 'boron', C: 'carbon', N: 'nitrogen', O: 'oxygen', P: 'phosphorus', S: 'sulfur', F: 'fluorine',
                    I: 'iodine', Cl: 'chlorine', Br: 'bromine' };
  const AROM = { b: 'boron', c: 'carbon', n: 'nitrogen', o: 'oxygen', p: 'phosphorus', s: 'sulfur' };
  const BONDS = { '-': 'single bond (usually implicit: two atoms written together are single-bonded)', '=': 'double bond',
                  '#': 'triple bond', '$': 'quadruple bond', ':': 'aromatic bond',
                  '/': 'directional single bond: with \\ it fixes cis/trans (E/Z) around a double bond',
                  '\\': 'directional single bond: with / it fixes cis/trans (E/Z) around a double bond' };

  function tokenize(s) {
    const out = [];
    const re = /(\[[^\]]*\])|(Cl|Br|[BCNOPSFI])|([bcnops])|(%\d\d|\d)|([-=#$:/\\])|(\()|(\))|(\.)|(.)/g;
    let m;
    while ((m = re.exec(s))) {
      const t = m[0];
      if (m[1]) out.push({ t, k: 'atom', d: bracket(t) });
      else if (m[2]) out.push({ t, k: 'atom', d: `${ORGANIC[t]} atom; its hydrogens are added automatically to complete the usual valence` });
      else if (m[3]) out.push({ t, k: 'arom', d: `aromatic ${AROM[t]} (lowercase = part of an aromatic ring such as benzene)` });
      else if (m[4]) out.push({ t, k: 'ring', d: '' });
      else if (m[5]) out.push({ t, k: 'bond', d: BONDS[t] });
      else if (m[6]) out.push({ t, k: 'branch', d: 'opens a branch: what follows hangs off the previous atom' });
      else if (m[7]) out.push({ t, k: 'branch', d: 'closes the branch: continue from the atom before "("' });
      else if (m[8]) out.push({ t, k: 'dot', d: 'separates disconnected pieces (e.g. a salt: [Na+].[Cl-])' });
      else out.push({ t, k: 'bad', d: 'not a SMILES character here' });
    }
    // pair ring-closure digits
    const open = {};
    let ringNo = 0;
    out.forEach((tk, i) => {
      if (tk.k !== 'ring') return;
      if (open[tk.t] === undefined) { open[tk.t] = i; tk.pair = ringNo++; tk.d = `ring-closure ${tk.t} opens: the ring closes where ${tk.t} appears again`; }
      else { const j = open[tk.t]; tk.pair = out[j].pair; tk.d = `ring-closure ${tk.t} closes the ring (bonded to the atom before the first ${tk.t})`; delete open[tk.t]; }
    });
    Object.values(open).forEach(i => { out[i].k = 'bad'; out[i].d = `ring-closure ${out[i].t} is never closed`; });
    const stack = [];
    out.forEach((tk, i) => {
      if (tk.t === '(') stack.push(i);
      else if (tk.t === ')') { if (stack.length) stack.pop(); else { tk.k = 'bad'; tk.d = 'this ")" has no matching "("'; } }
    });
    stack.forEach(i => { out[i].k = 'bad'; out[i].d = 'this branch is never closed with ")"'; });
    return out;
  }

  function bracket(t) {
    const m = /^\[(\d+)?([A-Z][a-z]?|[a-z][a-z]?|\*)(@@|@)?(H\d?)?([+-]\d*|[+-]+)?(:\d+)?\]$/.exec(t);
    if (!m) return 'bracket atom (special atom written explicitly)';
    const parts = [`${m[2]} atom written explicitly`];
    if (m[1]) parts.push(`isotope ${m[1]}`);
    if (m[3]) parts.push(m[3] === '@' ? 'stereocentre, neighbours anticlockwise (@)' : 'stereocentre, neighbours clockwise (@@)');
    if (m[4]) parts.push(`${m[4] === 'H' ? 1 : m[4].slice(1)} attached H`);
    if (m[5]) parts.push(`charge ${m[5]}`);
    return parts.join(' · ');
  }

  function initPlayground() {
    const input = $('pg-input');
    if (!input) return;
    const toks = $('pg-tokens'), expl = $('pg-explain');
    const colors = ['#ffbf00', '#ff7eb6', '#7ec8ff', '#b28dff', '#98ebc4', '#ffa36b'];
    let seq = 0, timer = null;

    const render = () => {
      const s = input.value.trim();
      const list = tokenize(s);
      toks.innerHTML = list.map((tk, i) => {
        const style = tk.k === 'ring' && tk.pair !== undefined ? ` style="color:${colors[tk.pair % colors.length]};border-color:${colors[tk.pair % colors.length]}"` : '';
        return `<span class="tk tk-${tk.k}" data-i="${i}" tabindex="0"${style}>${esc(tk.t)}</span>`;
      }).join('');
      const show = (i) => {
        const tk = list[i];
        toks.querySelectorAll('.tk').forEach(e => e.classList.toggle('on', Number(e.dataset.i) === i ||
          (tk.k === 'ring' && list[Number(e.dataset.i)]?.pair === tk.pair && list[Number(e.dataset.i)]?.k === 'ring')));
        expl.innerHTML = `<code>${esc(tk.t)}</code> ${esc(tk.d)}`;
      };
      toks.querySelectorAll('.tk').forEach(e => {
        const i = Number(e.dataset.i);
        e.addEventListener('mouseenter', () => show(i));
        e.addEventListener('focus', () => show(i));
        e.addEventListener('click', () => show(i));
      });
      expl.textContent = list.some(t => t.k === 'bad') ? 'Something here is not valid SMILES (marked in red).' : 'Hover or tap a character above.';
      clearTimeout(timer);
      timer = setTimeout(() => draw(s), 350);
    };

    const draw = async (s) => {
      const my = ++seq;
      const box = $('pg-draw'), facts = $('pg-facts');
      if (!s) { box.innerHTML = ''; facts.innerHTML = ''; return; }
      try {
        const [svg, info] = await Promise.all([
          fetch('/api/draw2d', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ smiles: s }) })
            .then(r => r.ok ? r.text() : null),
          fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ smiles: s }) })
            .then(r => r.json().then(d => ({ ok: r.ok, d }))),
        ]);
        if (my !== seq) return;
        box.innerHTML = svg || '';
        const sv = box.querySelector('svg');
        if (sv) { sv.removeAttribute('width'); sv.removeAttribute('height'); sv.setAttribute('preserveAspectRatio', 'xMidYMid meet'); }
        if (info.ok) {
          const d = info.d;
          const stereo = (d.stereocenters || []).length;
          facts.innerHTML = `<div><b>${esc(d.formula)}</b> · ${Number(d.mol_weight).toFixed(2)} g/mol</div>
            <div>${d.heavy_atoms} heavy atoms, ${d.atoms_with_h} with H</div>
            <div>${d.rings} ring${d.rings === 1 ? '' : 's'} (${d.aromatic_rings} aromatic)</div>
            <div>${d.rotatable_bonds} rotatable bond${d.rotatable_bonds === 1 ? '' : 's'}</div>
            <div>${stereo} stereocentre${stereo === 1 ? '' : 's'}</div>
            <div class="pg-canon">canonical: <code>${esc(d.canonical_smiles)}</code></div>`;
        } else {
          facts.innerHTML = `<div class="pg-err">✗ ${esc(info.d.error || 'invalid SMILES')}</div>`;
        }
      } catch (e) {
        if (my === seq) facts.innerHTML = '<div class="pg-err">The server is not reachable right now.</div>';
      }
    };

    input.addEventListener('input', render);
    document.querySelectorAll('#smiles-playground .pg-chips button').forEach(b => b.addEventListener('click', () => {
      input.value = b.dataset.smi;
      render();
    }));
    $('pg-open')?.addEventListener('click', () => {
      const main = $('smiles');
      document.querySelector('a[href="#explore"]')?.click();
      const single = document.querySelector('input[name="input-method"][value="single"]');
      if (single && !single.checked) { single.checked = true; single.dispatchEvent(new Event('change', { bubbles: true })); }
      if (main) {
        main.value = input.value.trim();
        main.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => main.focus(), 300);
      }
    });
    render();
  }

  // ------------------------------------------------------------------ butane explorer
  // V(φ) = V1/2(1+cos φ) + V2/2(1−cos 2φ) + V3/2(1+cos 3φ), φ = C1-C2-C3-C4 dihedral (anti = 180°).
  // V1 = 1.2, V2 = 0, V3 = 3.3 kcal/mol reproduce anti 0, gauche 0.9, eclipsed 3.6, syn 4.5.
  const V = (deg) => { const p = deg * Math.PI / 180; return 0.6 * (1 + Math.cos(p)) + 1.65 * (1 + Math.cos(3 * p)); };
  const R = 0.0019872;      // kcal/(mol·K)

  function initButane() {
    const newman = $('bt-newman'), curve = $('bt-curve');
    if (!newman || !curve) return;
    const phiIn = $('bt-phi'), tIn = $('bt-temp');
    const X = (d) => d, Y = (e) => 180 - e * 34;                  // plot: 0..360 deg, 0..5 kcal/mol
    let path = '';
    for (let d = 0; d <= 360; d += 3) path += `${d ? 'L' : 'M'}${X(d)},${Y(V(d)).toFixed(1)}`;
    const labels = [[0, 'syn'], [60, 'gauche'], [120, 'eclipsed'], [180, 'anti'], [240, 'eclipsed'], [300, 'gauche'], [360, 'syn']];
    curve.innerHTML = `
      <line x1="0" y1="180" x2="360" y2="180" class="bt-axis"/>
      ${[1, 2, 3, 4].map(e => `<line x1="0" y1="${Y(e)}" x2="360" y2="${Y(e)}" class="bt-grid"/><text x="2" y="${Y(e) - 3}" class="bt-tick">${e}</text>`).join('')}
      <path d="${path}" class="bt-path"/>
      ${labels.map(([d, t]) => `<text x="${d}" y="196" class="bt-lab" text-anchor="${d === 0 ? 'start' : d === 360 ? 'end' : 'middle'}">${t}</text>`).join('')}
      <text x="358" y="12" text-anchor="end" class="bt-tick">kcal/mol</text>
      <line id="bt-cursor" x1="180" y1="0" x2="180" y2="180" class="bt-cursor"/>
      <circle id="bt-dot" cx="180" cy="${Y(0)}" r="6" class="bt-dot"/>`;

    const drawNewman = (phi) => {
      // front carbon: CH3 up (90°), H at 210° and 330°. Back carbon rotated so the CH3–CH3 angle is phi.
      const front = [[90, 'CH₃', true], [210, 'H'], [330, 'H']];
      const back = [[90 - phi, 'CH₃', true], [210 - phi, 'H'], [330 - phi, 'H']];
      const pt = (a, r) => [Math.cos(a * Math.PI / 180) * r, -Math.sin(a * Math.PI / 180) * r];
      const sub = (a, label, me, r0, r1, rl, cls) => {
        const [x0, y0] = pt(a, r0), [x1, y1] = pt(a, r1), [xl, yl] = pt(a, rl);
        return `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" class="${cls}"/>
                <text x="${xl.toFixed(1)}" y="${(yl + 4).toFixed(1)}" text-anchor="middle" class="nm-lab ${me ? 'nm-me' : ''} ${cls}-lab">${label}</text>`;
      };
      // back bonds are longer and labelled further out, so eclipsed groups stay readable
      newman.innerHTML = `${back.map(([a, l, m]) => sub(a, l, m, 46, 92, 108, 'nm-back')).join('')}
        <circle cx="0" cy="0" r="46" class="nm-circle"/>
        ${front.map(([a, l, m]) => sub(a, l, m, 0, 62, 77, 'nm-front')).join('')}
        <circle cx="0" cy="0" r="4" class="nm-center"/>`;
    };

    const update = () => {
      const phi = Number(phiIn.value) % 360, T = Number(tIn.value);
      const e = V(phi);
      $('bt-angle').textContent = `${phi}°`;
      $('bt-temp-val').textContent = `${T} K`;
      const name = (phi > 150 && phi < 210) ? 'anti (staggered)' : ((phi > 30 && phi < 90) || (phi > 270 && phi < 330)) ? 'gauche (staggered)'
        : (phi <= 30 || phi >= 330) ? 'syn (fully eclipsed)' : 'eclipsed';
      $('bt-readout').innerHTML = `<b>${e.toFixed(2)} kcal/mol</b> above anti · ${name}`;
      const dot = $('bt-dot'), cur = $('bt-cursor');
      dot.setAttribute('cx', X(phi)); dot.setAttribute('cy', Y(e));
      cur.setAttribute('x1', X(phi)); cur.setAttribute('x2', X(phi));
      drawNewman(phi);
      const g = 2 * Math.exp(-0.9 / (R * T));
      const pa = 1 / (1 + g), pg = g / (1 + g);
      $('bt-pop-anti').style.width = `${(pa * 100).toFixed(1)}%`;
      $('bt-pop-anti').textContent = `anti ${(pa * 100).toFixed(0)} %`;
      $('bt-pop-gauche').style.width = `${(pg * 100).toFixed(1)}%`;
      $('bt-pop-gauche').textContent = `gauche ${(pg * 100).toFixed(0)} %`;
    };
    phiIn.addEventListener('input', update);
    tIn.addEventListener('input', update);
    document.querySelectorAll('#butane-lab .bt-snaps [data-phi]').forEach(b => b.addEventListener('click', () => { phiIn.value = b.dataset.phi; update(); }));
    let spin = null;
    $('bt-play')?.addEventListener('click', (e) => {
      if (spin) { clearInterval(spin); spin = null; e.target.textContent = '▶ rotate'; return; }
      e.target.textContent = '⏸ stop';
      spin = setInterval(() => { phiIn.value = (Number(phiIn.value) + 2) % 361; update(); }, 40);
    });
    update();
  }

  // ------------------------------------------------------------------ GLOMOS stepper
  const STEPS = [
    { t: 'Seeds', art: '  SMILES ──► RDKit ──► 3D\n    [stereo ✓] [bonds ✓]',
      b: 'A few 3D starting structures are embedded from your SMILES. Their stereochemistry and bonds are checked: GLOMOS never changes what the SMILES says, only the shape.',
      p: 'Automatic.' },
    { t: 'Find the rotors', art: '   H   H\n   |   |\n ──C ↻ C──\n   |   |',
      b: 'Every single bond that can twist and changes the shape becomes a "gene". Bonds inside rings, to terminal atoms like CH₃ symmetric tops, and amide bonds are treated specially or skipped.',
      p: 'Shown as "Rotors" in the GLOMOS panel.' },
    { t: 'Random population', art: ' [ 60°|180°|300°]\n [180°|180°| 60°]\n [300°| 60°|180°]',
      b: 'The first generation sets each rotor to random angles: a diverse set of candidate shapes.',
      p: 'Initial pop. = how many random candidates.' },
    { t: 'Relax with ANI', art: '  E\n  |\\       ___\n  | \\_   _/\n  |   \\_/  ← minimum\n  └─────────── shape',
      b: 'Each candidate rolls downhill on the ANI energy landscape (L-BFGS optimisation, all candidates of a generation in one batch). Structures whose bonds or stereochemistry broke are discarded.',
      p: 'ANI model and Screening.' },
    { t: 'Select and deduplicate', art: ' #1  0.00  ✓ keep\n #2  0.31  ✓ keep\n #3  0.31  ✗ same shape\n #4  7.20  ✗ above Ecut',
      b: 'Candidates are ranked by energy. Two structures with the same shape (USR shape descriptors) and nearly the same energy count once — the lower one stays. Anything too high in energy is dropped.',
      p: 'Ecut (kcal/mol) = energy window · Keep best = population size.' },
    { t: 'Mate and mutate', art: ' parent A  [ 60|180|300]\n parent B  [180|180| 60]\n child     [ 60|180| 60]  mating\n mutant    [ 60|300|300]  mutation',
      b: 'New candidates are made by mixing the rotor angles of two good parents (mating) and by re-rolling some angles of one (mutation). They are relaxed and selected like before — one generation.',
      p: 'Matings, Mutants, Generations.' },
    { t: 'Stop, polish, rank', art: ' gen 1 ▓▓▓▓\n gen 2 ▓▓▓▓▓▓\n gen 3 ▓▓▓▓▓▓ (no change)\n → final tight optimisation',
      b: 'The search stops after the set number of generations, when the best structures stop changing, or at the time limit. The survivors are re-optimised tightly, ranked, and given Boltzmann populations and rotational constants.',
      p: 'Time limit (min) · Random seed reproduces a run.' },
  ];

  function initStepper() {
    const rail = document.querySelector('#glomos-stepper .st-rail');
    if (!rail) return;
    let i = 0;
    rail.innerHTML = STEPS.map((s, k) => `<button type="button" role="tab" data-k="${k}"><span>${k + 1}</span>${esc(s.t)}</button>`).join('');
    const show = (k) => {
      i = Math.max(0, Math.min(STEPS.length - 1, k));
      const s = STEPS[i];
      $('st-art').textContent = s.art;
      $('st-title').textContent = `${i + 1}. ${s.t}`;
      $('st-body').textContent = s.b;
      $('st-param').innerHTML = `<span class="kbd">GLOMOS panel</span> ${esc(s.p)}`;
      $('st-count').textContent = `${i + 1} / ${STEPS.length}`;
      $('st-prev').disabled = i === 0;
      $('st-next').disabled = i === STEPS.length - 1;
      rail.querySelectorAll('button').forEach(b => {
        const on = Number(b.dataset.k) === i;
        b.classList.toggle('active', on);
        b.classList.toggle('done', Number(b.dataset.k) < i);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        if (on) {   // keep the active pill visible in the scrollable rail, without scrolling the page
          const l = b.offsetLeft - rail.offsetLeft, r = l + b.offsetWidth;
          if (l < rail.scrollLeft) rail.scrollLeft = l - 8;
          else if (r > rail.scrollLeft + rail.clientWidth) rail.scrollLeft = r - rail.clientWidth + 8;
        }
      });
    };
    window.elayaShowStep = show;
    rail.querySelectorAll('button').forEach(b => b.addEventListener('click', () => show(Number(b.dataset.k))));
    $('st-prev').addEventListener('click', () => show(i - 1));
    $('st-next').addEventListener('click', () => show(i + 1));
    show(0);
  }

  // ------------------------------------------------------------------ quiz
  const QUIZ = [
    { q: 'What does C1CCCCC1 describe?', a: ['A chain of six carbons', 'A ring of six carbons', 'Benzene'], ok: 1,
      why: 'The two "1" close a ring. It is cyclohexane; benzene would be aromatic: c1ccccc1.' },
    { q: 'Two conformers of a molecule differ in…', a: ['which atoms are bonded', 'the rotation around single bonds', 'their molecular formula'], ok: 1,
      why: 'Same atoms, same bonds, same formula; only the twist around single bonds changes.' },
    { q: 'Why is anti-butane more stable than syn-butane?', a: ['The CH₃ groups are as far apart as possible', 'It has a double bond', 'It has more hydrogens'], ok: 0,
      why: 'In anti the methyl groups point away from each other; in syn they bump into each other (steric strain).' },
    { q: 'In GLOMOS, a "mutation" is…', a: ['changing an atom of the molecule', 're-rolling some torsion angles of a candidate', 'changing the ANI model'], ok: 1,
      why: 'Only torsion angles change; the molecule itself is never modified.' },
    { q: 'A conformer with ΔE = 4 kcal/mol at room temperature is…', a: ['very populated', 'rarely populated', 'impossible'], ok: 1,
      why: 'With RT ≈ 0.59 kcal/mol, e^(−4/0.59) ≈ 0.1 % relative to the best conformer.' },
  ];

  function initQuiz() {
    const box = $('learn-quiz');
    if (!box) return;
    const answers = {};
    box.innerHTML = QUIZ.map((x, k) => `
      <div class="qz" data-k="${k}">
        <div class="qz-q"><span>${k + 1}</span>${esc(x.q)}</div>
        <div class="qz-a">${x.a.map((t, j) => `<button type="button" data-j="${j}">${esc(t)}</button>`).join('')}</div>
        <div class="qz-why" hidden></div>
      </div>`).join('') + '<div class="qz-score" id="qz-score"></div>';
    box.querySelectorAll('.qz').forEach(q => {
      const k = Number(q.dataset.k);
      q.querySelectorAll('.qz-a button').forEach(b => b.addEventListener('click', () => {
        if (answers[k] !== undefined) return;
        const j = Number(b.dataset.j);
        answers[k] = j === QUIZ[k].ok;
        q.querySelectorAll('.qz-a button').forEach(x => {
          x.disabled = true;
          if (Number(x.dataset.j) === QUIZ[k].ok) x.classList.add('right');
        });
        if (j !== QUIZ[k].ok) b.classList.add('wrong');
        const why = q.querySelector('.qz-why');
        why.hidden = false;
        why.innerHTML = `${answers[k] ? '✓ Correct.' : '✗ Not quite.'} ${esc(QUIZ[k].why)}`;
        const n = Object.keys(answers).length;
        if (n === QUIZ.length) {
          course.markRead('c-quiz');
          const good = Object.values(answers).filter(Boolean).length;
          $('qz-score').innerHTML = `You got <b>${good}/${QUIZ.length}</b>. ${good === QUIZ.length ? 'Ready to run GLOMOS like a pro. 🎉' : 'Revisit the lessons above and try the explorer.'}
            <button type="button" id="qz-retry">Try again</button>`;
          $('qz-retry').addEventListener('click', initQuiz);
        }
      }));
    });
  }


  // ------------------------------------------------------------------ contact: guided report + citation
  const REPO = 'https://github.com/GabrielaVidales/Elaya_SMILES';
  let appVersion = '';

  async function copyText(text, statusEl) {
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { ok = document.execCommand('copy'); } catch (e2) { ok = false; }
      ta.remove();
    }
    if (statusEl) {
      statusEl.textContent = ok ? '✓ Copied' : 'Select the text and copy it manually';
      setTimeout(() => { statusEl.textContent = ''; }, 2500);
    }
  }

  function settingsSummary() {
    const val = (id) => { const el = $(id); return el ? (el.value || '') : ''; };
    const sel = (id) => { const el = $(id); return el && el.selectedOptions && el.selectedOptions[0] ? el.selectedOptions[0].textContent.trim() : val(id); };
    const lines = [`- Method: ${sel('conversion-method')}`, `- Force field: ${sel('force-field')}`, `- Post-optimization: ${sel('post-optimization')}`];
    if (val('post-optimization') === 'glomos') {
      lines.push(`- GLOMOS: preset ${val('glomos-preset')}, initpop ${val('glomos-initpop')}, matings ${val('glomos-matings')}, mutants ${val('glomos-mutants')}, ` +
        `generations ${val('glomos-generations')}, Ecut ${val('glomos-ecut')}, keep ${val('glomos-keep')}, ANI ${val('glomos-ani')}, ` +
        `screening ${val('glomos-screening')}, minutes ${val('glomos-minutes')}, seed ${val('glomos-seed') || 'random'}`);
    }
    return lines.join('\n');
  }

  function buildReport() {
    const what = ($('rb-what')?.value || '').trim();
    const exp = ($('rb-expected')?.value || '').trim();
    const smi = ($('rb-smiles')?.value || '').trim();
    const area = $('rb-area')?.value || '';
    const title = `[${area}] ${what.split('\n')[0].slice(0, 70) || 'Problem report'}`;
    const body = `### What happened\n${what || '_(describe the problem)_'}\n\n### What I expected\n${exp || '_(optional)_'}\n\n` +
      `### Input\n\`${smi || '(none)'}\`\n\n### Settings\n${settingsSummary()}\n\n` +
      `### Environment\n- ELAYA version: ${appVersion || 'unknown'}\n- Browser: ${navigator.userAgent}\n- Screen: ${window.innerWidth}×${window.innerHeight}\n- Page: ${location.origin}\n`;
    return { title, body };
  }

  function initContact() {
    if (!$('report-builder')) return;
    fetch('/api/health').then(r => r.json()).then(d => {
      appVersion = d.version || '';
      if (appVersion && $('cite-version')) $('cite-version').textContent = appVersion;
      refresh();
    }).catch(() => {});

    const refresh = () => { const r = buildReport(); $('rb-preview').textContent = `${r.title}\n\n${r.body}`; };
    ['rb-what', 'rb-expected', 'rb-smiles', 'rb-area'].forEach(id => $(id)?.addEventListener('input', refresh));
    $('rb-area')?.addEventListener('change', (e) => { e.target.dataset.touched = '1'; refresh(); });

    // prefill the SMILES from the explorer each time Contact is opened
    document.querySelector('a[href="#contact"]')?.addEventListener('click', () => {
      const cur = window.ELAYA_CONFORMERS?.smiles || $('smiles')?.value || $('smiles-file')?.files?.[0]?.name || '';
      if (cur && !$('rb-smiles').value) $('rb-smiles').value = cur;
      const area = $('rb-area');
      if (area && !area.dataset.touched) area.value = $('post-optimization')?.value === 'glomos' ? 'GLOMOS conformer search' : '3D conversion';
      refresh();
    });

    $('rb-open').addEventListener('click', () => {
      const what = $('rb-what');
      if (!what.value.trim()) {
        what.classList.add('rb-missing'); what.focus();
        $('rb-status').textContent = 'Please describe what happened first.';
        setTimeout(() => what.classList.remove('rb-missing'), 1600);
        return;
      }
      const r = buildReport();
      let url = `${REPO}/issues/new?labels=bug&title=${encodeURIComponent(r.title)}&body=${encodeURIComponent(r.body)}`;
      if (url.length > 7500) url = `${REPO}/issues/new?labels=bug&title=${encodeURIComponent(r.title)}&body=${encodeURIComponent(r.body.slice(0, 5000))}`;
      window.open(url, '_blank', 'noopener');
    });
    $('rb-copy').addEventListener('click', () => { const r = buildReport(); copyText(`${r.title}\n\n${r.body}`, $('rb-status')); });
    $('cite-copy')?.addEventListener('click', () => copyText($('cite-bibtex').textContent, $('cite-status')));
    document.querySelectorAll('#contact-section [data-scroll]').forEach(a => a.addEventListener('click', (e) => {
      e.preventDefault();
      const t = $(a.dataset.scroll);
      if (t) window.scrollTo({ top: t.getBoundingClientRect().top + window.scrollY - NAV_OFFSET, behavior: 'smooth' });
      if (a.dataset.scroll === 'report-builder') setTimeout(() => $('rb-what')?.focus({ preventScroll: true }), 500);
    }));
    refresh();
  }

  function init() {
    initToc();
    initFlow();
    initSearch();
    initPlayground();
    initButane();
    initStepper();
    initQuiz();
    initContact();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
