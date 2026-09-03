(() => {
  const DB = window.BRIDGE_DB;
  const RANKS = ['A', 'R', 'D', 'V', '10', '9', '8', '7', '6', '5', '4', '3', '2'];
  const LOW_RANKS = new Set(['9', '8', '7', '6', '5', '4', '3', '2']);
  const ORDER = new Map([...RANKS, 'x'].map((r, i) => [r, i]));
  const $ = id => document.getElementById(id);
  const els = {
    h1: $('hand1'), h2: $('hand2'), p1: $('hand1Preview'), p2: $('hand2Preview'),
    validation: $('validation'), rankButtons: $('rankButtons'), analyze: $('analyzeBtn'),
    clear: $('clearBtn'), swap: $('swapBtn'), result: $('resultSection'), noResult: $('noResult'),
    matchHolding: $('matchHolding'), matchBadge: $('matchBadge'), safetyResults: $('safetyResults'),
    maxResults: $('maxResults'), safetyPanel: $('safetyPanel'), maxPanel: $('maxPanel'), stats: $('dbStats')
  };

  let activeInput = els.h1;
  els.stats.textContent = `${DB.meta.records.toLocaleString('fr-FR')} entrées indexées`;

  // IMPORTANT : la casse de x/X a un sens dans l'entrée utilisateur.
  // X = 10 ; x = petite carte quelconque du 2 au 9.
  function normalizeUser(s) {
    return String(s || '')
      .replace(/♠|♥|♦|♣/g, '')
      .replace(/K/g, 'R').replace(/Q/g, 'D').replace(/J/g, 'V').replace(/T/g, '10')
      .replace(/X/g, '10')
      .replace(/[\s,;_.-]/g, '');
  }

  function tokUser(s) {
    const t = normalizeUser(s);
    if (!t) return [];
    const out = [];
    let i = 0;
    while (i < t.length) {
      if (t.startsWith('10', i)) { out.push('10'); i += 2; continue; }
      const c = t[i];
      if (c === 'x') { out.push('x'); i++; continue; }
      if ('ARDV98765432'.includes(c)) { out.push(c); i++; continue; }
      throw Error(`Carte non reconnue : « ${c} ». Utilise X pour le 10 et x pour une petite carte.`);
    }
    const exact = out.filter(c => c !== 'x');
    const dup = exact.find((r, idx) => exact.indexOf(r) !== idx);
    if (dup) throw Error(`La carte ${dup} apparaît deux fois dans la même main.`);
    return out.sort((a, b) => ORDER.get(a) - ORDER.get(b));
  }

  function normalizeDb(s) {
    return String(s || '')
      .replace(/♠|♥|♦|♣/g, '')
      .replace(/K/g, 'R').replace(/Q/g, 'D').replace(/J/g, 'V').replace(/T/g, '10')
      .replace(/[\s,;_-]/g, '');
  }

  function tokDbExact(s) {
    const t = normalizeDb(s).replace(/\./g, '');
    if (!t || t === '—') return [];
    const out = [];
    let i = 0;
    while (i < t.length) {
      if (t.startsWith('10', i)) { out.push('10'); i += 2; continue; }
      const c = t[i];
      if ('ARDV98765432'.includes(c)) { out.push(c); i++; continue; }
      // nExact/sExact doivent être concrets : un x éventuel ne peut pas donner un match exact.
      if (c === 'x') return [];
      i++;
    }
    return out.sort((a, b) => ORDER.get(a) - ORDER.get(b));
  }

  const txt = cards => cards.length ? cards.map(c => c === '10' ? '10' : c).join('') : '—';
  const inputTxt = cards => cards.length ? cards.map(c => c === '10' ? 'X' : c).join('') : '';

  function validatePair(h1, h2) {
    if (!h1.length || !h2.length) throw Error('Entre les deux mains de la couleur.');
    const e1 = h1.filter(c => c !== 'x');
    const e2 = h2.filter(c => c !== 'x');
    const common = e1.filter(c => e2.includes(c));
    if (common.length) throw Error(`La carte ${common[0]} ne peut pas être dans les deux mains.`);
    if (h1.length + h2.length > 13) throw Error('Une couleur ne peut contenir que 13 cartes.');

    // Les x ne peuvent représenter que des cartes distinctes du 2 au 9.
    const knownLow = new Set([...e1, ...e2].filter(c => LOW_RANKS.has(c)));
    const wildcardCount = [...h1, ...h2].filter(c => c === 'x').length;
    const freeLow = 8 - knownLow.size;
    if (wildcardCount > freeLow) {
      throw Error(`Trop de « x » : il ne reste que ${freeLow} petite${freeLow > 1 ? 's' : ''} carte${freeLow > 1 ? 's' : ''} disponible${freeLow > 1 ? 's' : ''} entre 2 et 9.`);
    }
  }

  function preview() {
    for (const [input, p] of [[els.h1, els.p1], [els.h2, els.p2]]) {
      try {
        const cards = tokUser(input.value);
        p.textContent = cards.length ? `${txt(cards)}${cards.includes('x') ? '  ·  x = 2–9' : ''}` : '—';
      } catch { p.textContent = '…'; }
    }
    refresh();
  }

  function setCards(input, cards) {
    input.value = inputTxt([...cards].sort((a, b) => ORDER.get(a) - ORDER.get(b)));
    preview();
  }

  function usedExact() {
    try {
      return new Set([...tokUser(els.h1.value), ...tokUser(els.h2.value)].filter(c => c !== 'x'));
    } catch { return new Set(); }
  }

  function refresh() {
    const used = usedExact();
    [...els.rankButtons.querySelectorAll('button')].forEach(b => {
      const token = b.dataset.rank;
      const isWildcard = token === 'x';
      b.classList.toggle('used', !isWildcard && used.has(token));
      b.disabled = !isWildcard && used.has(token);
    });
  }

  // Boutons : X est l'alias d'entrée du 10 ; x reste un joker de petite carte.
  [...RANKS.map(r => ({ token: r, label: r === '10' ? 'X' : r, title: r === '10' ? 'X = 10' : r })),
   { token: 'x', label: 'x', title: 'x = n’importe quelle carte du 2 au 9' }]
    .forEach(({ token, label, title }) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'rank-btn'; b.textContent = label; b.dataset.rank = token; b.title = title;
      if (token === 'x') b.classList.add('wildcard-btn');
      b.onclick = () => {
        let cards = [];
        try { cards = tokUser(activeInput.value); } catch {}
        if (token === 'x') cards.push('x');
        else if (!cards.includes(token)) cards.push(token);
        setCards(activeInput, cards); activeInput.focus();
      };
      els.rankButtons.appendChild(b);
    });

  [els.h1, els.h2].forEach(input => {
    input.onfocus = () => activeInput = input;
    input.oninput = preview;
    input.onkeydown = e => { if (e.key === 'Enter') analyze(); };
  });

  function parsePat(p, len) {
    let s = normalizeDb(p).replace(/…/g, '...');
    if (!s || s === '—') return { tokens: [], expectedLen: len ?? 0 };
    const a = [];
    let i = 0;
    while (i < s.length) {
      if (s.startsWith('x...x', i)) { a.push({ t: 'run' }); i += 5; continue; }
      let f;
      if (s.startsWith('10', i)) { f = '10'; i += 2; }
      else { f = s[i]; i++; }
      if (f === 'x') { a.push({ t: 'wild' }); continue; }
      if (!RANKS.includes(f)) continue;
      if (s[i] === '/') {
        i++;
        let q;
        if (s.startsWith('10', i)) { q = '10'; i += 2; }
        else { q = s[i]; i++; }
        a.push({ t: 'choice', c: [f, q] });
      } else a.push({ t: 'choice', c: [f] });
    }
    const ordinary = a.filter(x => x.t !== 'run').length;
    const run = a.some(x => x.t === 'run') ? Math.max(0, (len ?? ordinary) - ordinary) : 0;
    const expanded = [];
    a.forEach(x => {
      if (x.t === 'run') for (let j = 0; j < run; j++) expanded.push({ t: 'wild' });
      else expanded.push(x);
    });
    return { tokens: expanded, expectedLen: len ?? expanded.length };
  }

  // Un x saisi par l'utilisateur reste générique : il peut remplir un x du motif source,
  // mais il ne prétend pas être un 9/8/etc explicite si cette carte est importante dans le motif.
  function matchPat(p, len, query) {
    const q = parsePat(p, len);
    if (query.length !== q.expectedLen) return null;
    const choices = q.tokens.filter(x => x.t === 'choice');
    const wildcardSlots = q.tokens.filter(x => x.t === 'wild').length;
    const queryExact = query.filter(c => c !== 'x');
    let best = null;

    function dfs(i, selected) {
      if (i === choices.length) {
        if (new Set(selected).size !== selected.length) return;
        if (!selected.every(c => queryExact.includes(c))) return;
        // Tout ce qui n'est pas une carte explicite du motif est absorbé par les x du motif.
        if (query.length - selected.length !== wildcardSlots) return;
        const specificity = selected.length;
        if (!best || specificity > best.specificity) best = { specificity };
        return;
      }
      for (const c of choices[i].c) if (RANKS.includes(c)) dfs(i + 1, [...selected, c]);
    }
    dfs(0, []);
    return best;
  }

  function sameExact(a, b) {
    if (b.includes('x')) return false;
    if (a.length !== b.length) return false;
    const A = [...a].sort((x, y) => ORDER.get(x) - ORDER.get(y));
    const B = [...b].sort((x, y) => ORDER.get(x) - ORDER.get(y));
    return A.every((v, i) => v === B[i]);
  }

  function matchRec(r, h1, h2) {
    if (r.nExact !== undefined && r.sExact !== undefined) {
      // Une ligne concrète du moteur n'est utilisée que si l'utilisateur a fourni toutes les cartes exactes.
      if (h1.includes('x') || h2.includes('x')) return null;
      const n = tokDbExact(r.nExact), s = tokDbExact(r.sExact);
      if (sameExact(n, h1) && sameExact(s, h2)) return { orientation: 'normal', specificity: 50, exact: true };
      if (sameExact(n, h2) && sameExact(s, h1)) return { orientation: 'swapped', specificity: 50, exact: true };
      return null;
    }
    const a = matchPat(r.n, Number.isFinite(r.nlen) ? r.nlen : undefined, h1);
    const b = matchPat(r.s, Number.isFinite(r.slen) ? r.slen : undefined, h2);
    if (a && b) return { orientation: 'normal', specificity: a.specificity + b.specificity, exact: false };
    const c = matchPat(r.n, Number.isFinite(r.nlen) ? r.nlen : undefined, h2);
    const d = matchPat(r.s, Number.isFinite(r.slen) ? r.slen : undefined, h1);
    return c && d ? { orientation: 'swapped', specificity: c.specificity + d.specificity, exact: false } : null;
  }

  function orient(text, orientation) {
    if (!text) return 'Maniement non précisé dans la source.';
    let t = String(text).replace(/Main 1/g, '__M1__').replace(/Main 2/g, '__M2__');
    if (orientation === 'normal') t = t.replace(/Nord/g, 'Main 1').replace(/Sud/g, 'Main 2');
    else t = t.replace(/Nord/g, 'Main 2').replace(/Sud/g, 'Main 1');
    t = t.replace(/__M1__/g, orientation === 'normal' ? 'Main 1' : 'Main 2')
         .replace(/__M2__/g, orientation === 'normal' ? 'Main 2' : 'Main 1');
    return t.replace(/\blow\b/gi, 'petit').replace(/\bto\b/gi, 'vers').replace(/\bthen\b/gi, 'puis')
      .replace(/\bPlay\b/gi, 'Jouer').replace(/\bor\b/gi, 'ou').replace(/\band\b/gi, 'et').replace(/Finesse/gi, 'Impasse');
  }

  const score = (r, m) => (r.priority || 0) * 100 + m.specificity * 10 + (m.exact ? 10000 : 0);
  function matches(mode, h1, h2) {
    const out = [];
    for (const r of DB.records) {
      if (r.mode !== mode) continue;
      const m = matchRec(r, h1, h2);
      if (m) out.push({ rec: r, m, score: score(r, m) });
    }
    return out;
  }

  const esc = s => String(s).replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
  function card(hit) {
    const r = hit.rec, c = document.createElement('article');
    c.className = 'result-card';
    const pct = (r.prob * 100).toLocaleString('fr-FR', { minimumFractionDigits: r.prob < .01 ? 2 : 1, maximumFractionDigits: 2 });
    const q = hit.m.exact ? 'exact' : 'pattern';
    const qt = hit.m.exact ? 'correspondance exacte' : r.kind === 'v12' ? `motif V12 ${r.n} / ${r.s}` : `motif ${r.n} / ${r.s}`;
    const src = r.source ? `<a class="source-link" target="_blank" rel="noopener" href="${r.source}">source</a>` : '';
    c.innerHTML = `<div class="result-number"><span class="target">${r.target} levée${r.target > 1 ? 's' : ''}</span><span class="prob">${pct}<small> %</small></span></div><div><div class="play-title">À jouer</div><div class="play">${esc(orient(r.strategy, hit.m.orientation))}</div><div class="meta"><span class="meta-chip ${q}">${qt}</span><span class="meta-chip">${esc(r.sourceLabel || 'Base validée')}</span>${r.note ? `<span class="meta-chip">${esc(r.note)}</span>` : ''}${src}</div></div>`;
    return c;
  }

  function analyze() {
    els.validation.textContent = '';
    let h1, h2;
    try {
      h1 = tokUser(els.h1.value); h2 = tokUser(els.h2.value);
      validatePair(h1, h2);
    } catch (e) {
      els.validation.textContent = e.message;
      els.result.classList.add('hidden'); els.noResult.classList.add('hidden'); return;
    }

    setCards(els.h1, h1); setCards(els.h2, h2);
    const sf = matches('safety', h1, h2), mx = matches('max', h1, h2);
    if (!sf.length && !mx.length) {
      els.result.classList.add('hidden'); els.noResult.classList.remove('hidden'); return;
    }

    els.noResult.classList.add('hidden'); els.result.classList.remove('hidden');
    els.matchHolding.textContent = `${txt(h1)} / ${txt(h2)}`;
    const all = [...sf, ...mx].sort((a, b) => b.score - a.score);
    els.matchBadge.textContent = all[0].m.exact ? 'EXACT' : (h1.includes('x') || h2.includes('x') ? 'MOTIF AVEC x' : 'MOTIF RECONNU');

    const by = new Map();
    for (const h of sf) {
      const old = by.get(h.rec.target);
      if (!old || h.score > old.score) by.set(h.rec.target, h);
    }
    const best = [...by.values()].sort((a, b) => b.rec.target - a.rec.target);
    els.safetyResults.innerHTML = '';
    best.forEach(h => els.safetyResults.appendChild(card(h)));
    if (!best.length) els.safetyResults.innerHTML = '<p class="lead">Pas de cible de sécurité référencée.</p>';

    els.maxResults.innerHTML = '';
    if (mx.length) {
      mx.sort((a, b) => b.score - a.score || b.rec.target - a.rec.target);
      els.maxResults.appendChild(card(mx[0]));
    } else els.maxResults.innerHTML = '<p class="lead">Le mode max n’est pas encore renseigné.</p>';

    switchMode('safety');
    els.result.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function switchMode(m) {
    const safety = m === 'safety';
    els.safetyPanel.classList.toggle('hidden', !safety); els.maxPanel.classList.toggle('hidden', safety);
    document.querySelectorAll('.mode-tab').forEach(b => {
      const active = b.dataset.mode === m; b.classList.toggle('active', active); b.setAttribute('aria-selected', String(active));
    });
  }

  document.querySelectorAll('.mode-tab').forEach(b => b.onclick = () => switchMode(b.dataset.mode));
  els.analyze.onclick = analyze;
  els.swap.onclick = () => { const a = els.h1.value; els.h1.value = els.h2.value; els.h2.value = a; preview(); analyze(); };
  els.clear.onclick = () => {
    els.h1.value = ''; els.h2.value = ''; els.validation.textContent = '';
    els.result.classList.add('hidden'); els.noResult.classList.add('hidden'); preview(); els.h1.focus();
  };

  preview();
  const qs = new URLSearchParams(location.search);
  if (qs.get('h1') || qs.get('h2')) {
    els.h1.value = qs.get('h1') || ''; els.h2.value = qs.get('h2') || ''; preview(); analyze();
  }
})();
