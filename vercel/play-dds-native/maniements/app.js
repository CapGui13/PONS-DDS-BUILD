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

  // Runtime parity patch: the production loader still reads the frozen V1 DB chunks.
  // Apply the 20 audited Wave1-G data corrections before any matching/indexing.
  const DB_PATCHES = [
    ['4-RV-008','safety',5,'prob',0.007],['4-RV-018','safety',3,'prob',0.007],
    ['4-RV-020','safety',3,'prob',0.005],['4-RV-004','safety',3,'prob',0.002],
    ['4-RV-018','max',3,'prob',0.007],['3-R-002','max',5,'prob',0.007],
    ['4-RV-004','max',3,'prob',0.002],['4-RV-020','max',3,'prob',0.005],
    ['4-RV-008','max',5,'prob',0.007],['4-RV-001','max',4,'prob',0.003],
    ['3-R-002','safety',5,'prob',0.007],['3-R-001','max',4,'prob',0.003],
    ['3-R-001','safety',4,'prob',0.003],['4-RV-006','max',3,'prob',0.002],
    ['4-RV-001','safety',4,'prob',0.003],['4-RV-006','safety',3,'prob',0.002],
    ['4-RV-025','max',4,'strategy','Faire l’impasse au Valet et au 10 ; si elle perd, faire ensuite l’impasse au Roi.'],
    ['4-RV-025','safety',3,'strategy','Répéter l’impasse au Valet et au 10.'],
    ['4-RV-025','safety',4,'strategy','Faire l’impasse au Valet et au 10 ; si elle perd, faire ensuite l’impasse au Roi.'],
    ['4-RV-025','safety',2,'strategy','Soit répéter l’impasse au Valet et au 10, soit faire cette impasse puis, si elle perd, l’impasse au Roi.']
  ];
  for (const [id,mode,target,field,value] of DB_PATCHES) {
    const r=DB.records.find(x=>x.id===id&&x.mode===mode&&x.target===target); if(r) r[field]=value;
  }
  DB.meta.version='V2 HARDENED · WAVE1-G';
  DB.meta.wave1G={publishedProbabilityRecordsCorrected:16,publishedStrategyRecordsCorrected:4,auditWorkers:6};

  let activeInput = els.h1;
  els.stats.textContent = `${DB.meta.records.toLocaleString('fr-FR')} entrées indexées`;

  // IMPORTANT : la casse de x/X a un sens dans l'entrée utilisateur.
  // X = 10 ; x = petite carte quelconque du 2 au 9.
  function validateSuitSymbols(a, b) {
    const suits = [...String(a || '') + String(b || '')].filter(c => '♠♥♦♣'.includes(c));
    if (new Set(suits).size > 1) throw Error('Une analyse doit concerner une seule couleur : les symboles de couleur saisis sont contradictoires.');
  }

  function normalizeUser(s) {
    return String(s || '')
      .replace(/♠|♥|♦|♣/g, '')
      // Honneurs insensibles à la casse ; seule la paire X/x garde volontairement deux sens.
      .replace(/[Aa]/g, 'A').replace(/[RrKk]/g, 'R').replace(/[DdQq]/g, 'D').replace(/[VvJj]/g, 'V')
      .replace(/[Tt]/g, '10')
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
      // Dans la table source, l'unique X de DB est une spot-card, pas le 10 (déjà écrit 10).
      .replace(/X/g, 'x')
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
    if (!h1.length && !h2.length) throw Error('Entre au moins une carte de la couleur. Une main vide est acceptée pour une chicane.');
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

  function invalidateResult() {
    els.result.classList.add('hidden');
    els.noResult.classList.add('hidden');
  }

  function preview() {
    invalidateResult();
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
        const remaining = [...queryExact];
        for (const c of selected) {
          const at = remaining.indexOf(c);
          if (at < 0) return;
          remaining.splice(at, 1);
        }
        // Invariant V2 : un x de motif est une petite carte 2–9, jamais A/R/D/V/10.
        if (remaining.some(c => !LOW_RANKS.has(c))) return;
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
    return t.replace(/Vouer/g, 'Jouer')
      .replace(/\blow\b/gi, 'petit').replace(/\bto\b/gi, 'vers').replace(/\bthen\b/gi, 'puis')
      .replace(/\bPlay\b/gi, 'Jouer').replace(/\bLead\b/gi, 'Partir de').replace(/\bor\b/gi, 'ou').replace(/\band\b/gi, 'et')
      .replace(/\bif\b/gi, 'si').replace(/\bEast\b/gi, 'Est').replace(/\bWest\b/gi, 'Ouest')
      .replace(/\brepeatedly\b/gi, 'à répétition').replace(/\bvice versa\b/gi, 'ou inversement')
      .replace(/\bcover(?:ed)?\b/gi, 'couvrir').replace(/\btowards?\b/gi, 'vers').replace(/Finesse/gi, 'Impasse');
  }

  const score = (r, m) => (r.priority || 0) * 100 + m.specificity * 10 + (m.exact ? 10000 : 0);
  // Incohérences physiques/source prouvées par les audits indépendants A/B/C.
  const SOURCE_SUSPECT_IDS = new Set(['3-R-024', '3-R-065', '4-A-024', '3-R-005', '6-AD-010']);
  // Ces IDs gardent leurs probabilités mais leur texte publié est signalé, car la relation cible→remarque a été aplatie à l'import.
  const STRATEGY_SUSPECT_IDS = new Set(['2-D-027','2-D-029','3-DV-012','3-DV-020','3-R-055','3-R-056','3-R-061','3-R-063','4-RV-054','4-RV-055','4-RV-056','4-RV-066','4-RV-071','4-RV-086','4-RV-089','4-RV-091','4-RV-099','4-RV-101','5-AV-010','5-AV-015','5-AV-025','5-AV-027','5-AV-032','5-RD-019','5-RD-020','5-RD-025','5-RD-039','5-RD-060','6-AD-008','7-AR-023','7-AR-032','8-ARV-018']);

  const LEN_INDEX = { safety: new Map(), max: new Map() };
  function recLengths(r) {
    if (r.nExact !== undefined && r.sExact !== undefined) return [tokDbExact(r.nExact).length, tokDbExact(r.sExact).length];
    const a = Number.isFinite(r.nlen) ? r.nlen : parsePat(r.n).expectedLen;
    const b = Number.isFinite(r.slen) ? r.slen : parsePat(r.s).expectedLen;
    return [a,b];
  }
  for (const r of DB.records) {
    if (!LEN_INDEX[r.mode]) continue;
    const [a,b] = recLengths(r), key = [a,b].sort((x,y)=>x-y).join('-');
    if (!LEN_INDEX[r.mode].has(key)) LEN_INDEX[r.mode].set(key, []);
    LEN_INDEX[r.mode].get(key).push(r);
  }

  function matches(mode, h1, h2) {
    const out = [], key = [h1.length,h2.length].sort((a,b)=>a-b).join('-');
    const candidates = LEN_INDEX[mode].get(key) || [];
    for (const r of candidates) {
      if (r.kind === 'published' && SOURCE_SUSPECT_IDS.has(r.id)) continue;
      const m = matchRec(r, h1, h2);
      if (m) out.push({ rec: r, m, score: score(r, m) });
    }
    return out;
  }

  const esc = s => String(s).replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
  function safeSourceUrl(value) {
    if (!value) return '';
    try { const u = new URL(value, location.href); return ['http:','https:'].includes(u.protocol) ? u.href : ''; } catch { return ''; }
  }
  function card(hit) {
    const r = hit.rec, c = document.createElement('article');
    c.className = 'result-card';
    const pct = (r.prob * 100).toLocaleString('fr-FR', { minimumFractionDigits: r.prob < .01 ? 2 : 1, maximumFractionDigits: 2 });
    const q = hit.m.exact ? 'exact' : 'pattern';
    const qt = hit.m.exact ? 'correspondance exacte' : r.kind === 'v12' ? `motif V12 ${r.n} / ${r.s}` : `motif ${r.n} / ${r.s}`;
    const href = safeSourceUrl(r.source);
    const src = href ? `<a class="source-link" target="_blank" rel="noopener" href="${esc(href)}" aria-label="Ouvrir la source de ${esc(r.id)} dans un nouvel onglet">Source ↗</a>` : '';
    const strategySuspect = r.kind === 'published' && STRATEGY_SUSPECT_IDS.has(r.id);
    const play = strategySuspect ? 'Stratégie publiée en cours d’arbitrage : la probabilité est conservée, mais l’app ne présente pas une ligne de jeu potentiellement mal rattachée à cette cible.' : orient(r.strategy, hit.m.orientation);
    const playTitle = r.kind === 'motor' ? (String(r.strategy || '').includes(' ou ') ? 'Premiers coups optimaux' : 'Premier coup optimal') : 'Ligne de jeu';
    const motorNote = r.kind === 'motor' ? '<span class="meta-chip">Sortie moteur : premier coup, continuation non affichée</span>' : '';
    const warning = strategySuspect ? '<span class="meta-chip warning-chip">STRATÉGIE À ARBITRER</span>' : '';
    c.innerHTML = `<div class="result-number"><span class="target">${r.target} levée${r.target > 1 ? 's' : ''}</span><span class="prob">${pct}<small> %</small></span></div><div><div class="play-title">${esc(playTitle)}</div><div class="play">${esc(play)}</div><div class="meta"><span class="meta-chip ${q}">${esc(qt)}</span><span class="meta-chip">${esc(r.sourceLabel || 'Base validée')}</span>${warning}${motorNote}${r.note ? `<span class="meta-chip">${esc(r.note)}</span>` : ''}${src}</div></div>`;
    return c;
  }

  function ambiguityCard(target, hits) {
    const c = document.createElement('article'); c.className = 'result-card ambiguity-card';
    const ids = [...new Set(hits.map(h => h.rec.id))];
    const label = Number.isFinite(target) ? `${target} levée${target > 1 ? 's' : ''}` : 'Mode max';
    c.innerHTML = `<div class="result-number"><span class="target">${esc(label)}</span><span class="prob">AMBIGU</span></div><div><div class="play-title">Arbitrage requis</div><div class="play">Plusieurs lignes de même priorité donnent des réponses différentes. L’app refuse de choisir selon l’ordre du fichier.</div><div class="meta"><span class="meta-chip warning-chip">${ids.map(esc).join(' · ')}</span></div></div>`;
    return c;
  }
  function topTies(hits) { if (!hits.length) return []; const top=Math.max(...hits.map(h=>h.score)); return hits.filter(h=>h.score===top); }
  function divergent(hits) { return new Set(hits.map(h => `${h.rec.target}|${Number(h.rec.prob).toPrecision(15)}|${h.rec.strategy}`)).size > 1; }

  function chooseSubsets(arr, k, start = 0, pick = [], out = []) {
    if (pick.length === k) { out.push([...pick]); return out; }
    const need = k - pick.length;
    for (let i = start; i <= arr.length - need; i++) {
      pick.push(arr[i]); chooseSubsets(arr, k, i + 1, pick, out); pick.pop();
    }
    return out;
  }

  function expandWildcardWorlds(h1, h2) {
    const n1 = h1.filter(c => c === 'x').length, n2 = h2.filter(c => c === 'x').length;
    if (!n1 && !n2) return [];
    const fixed1 = h1.filter(c => c !== 'x'), fixed2 = h2.filter(c => c !== 'x');
    const knownLow = new Set([...fixed1, ...fixed2].filter(c => LOW_RANKS.has(c)));
    const free = [...LOW_RANKS].filter(c => !knownLow.has(c));
    if (n1 + n2 > free.length) return [];
    const worlds = [];
    for (const a of chooseSubsets(free, n1)) {
      const aset = new Set(a), rest = free.filter(c => !aset.has(c));
      for (const b of chooseSubsets(rest, n2)) {
        worlds.push({
          h1: [...fixed1, ...a].sort((x, y) => ORDER.get(x) - ORDER.get(y)),
          h2: [...fixed2, ...b].sort((x, y) => ORDER.get(x) - ORDER.get(y))
        });
      }
    }
    return worlds;
  }

  function effectivePlay(hit) {
    const r = hit.rec;
    return r.kind === 'published' && STRATEGY_SUSPECT_IDS.has(r.id)
      ? '__STRATEGY_SUSPECT__'
      : orient(r.strategy, hit.m.orientation);
  }

  function resolvedMode(mode, h1, h2) {
    const hs = matches(mode, h1, h2);
    if (!hs.length) return { status: 'missing', signature: 'MISSING', selected: [] };
    if (mode === 'safety') {
      const byTarget = new Map();
      for (const h of hs) { if (!byTarget.has(h.rec.target)) byTarget.set(h.rec.target, []); byTarget.get(h.rec.target).push(h); }
      const selected = [];
      for (const target of [...byTarget.keys()].sort((a, b) => b - a)) {
        const ties = topTies(byTarget.get(target));
        if (divergent(ties)) return { status: 'ambiguous', signature: 'AMBIGU', selected: [] };
        selected.push(ties[0]);
      }
      const signature = selected.map(h => `${h.rec.target}|${Number(h.rec.prob).toPrecision(15)}|${effectivePlay(h)}`).join('||');
      return { status: 'resolved', signature, selected };
    }
    const ties = topTies(hs);
    if (divergent(ties)) return { status: 'ambiguous', signature: 'AMBIGU', selected: [] };
    const chosen = [...ties].sort((a, b) => b.rec.target - a.rec.target)[0];
    return {
      status: 'resolved',
      signature: `${chosen.rec.target}|${Number(chosen.rec.prob).toPrecision(15)}|${effectivePlay(chosen)}`,
      selected: [chosen]
    };
  }

  function consensusMode(mode, worlds) {
    if (!worlds.length) return { compatible: false, selected: [], status: 'empty' };
    const first = resolvedMode(mode, worlds[0].h1, worlds[0].h2);
    if (first.status === 'ambiguous') return { compatible: false, selected: [], status: 'ambiguous' };
    for (let i = 1; i < worlds.length; i++) {
      const cur = resolvedMode(mode, worlds[i].h1, worlds[i].h2);
      if (cur.status === 'ambiguous' || cur.signature !== first.signature) {
        return { compatible: false, selected: [], status: 'varies' };
      }
    }
    return { compatible: true, selected: first.selected, status: first.status };
  }

  function wildcardConsensus(h1, h2) {
    const worlds = expandWildcardWorlds(h1, h2);
    return {
      worlds,
      safety: consensusMode('safety', worlds),
      max: consensusMode('max', worlds)
    };
  }

  function robustCard(hit, worldCount) {
    const c = card(hit);
    const q = c.querySelector('.meta-chip.exact, .meta-chip.pattern');
    if (q) {
      q.classList.remove('exact'); q.classList.add('pattern');
      q.textContent = `Résultat identique sur ${worldCount} réalisation${worldCount > 1 ? 's' : ''}`;
    }
    [...c.querySelectorAll('.meta-chip')].forEach(chip => {
      if (/^Exact pour les petites cartes/i.test(chip.textContent || '')) chip.remove();
    });
    return c;
  }

  function setNoResultMessage(title, text) {
    const h = els.noResult.querySelector('h2'), p = els.noResult.querySelector('p');
    if (h) h.textContent = title;
    if (p) p.textContent = text;
  }

  function setInvalid(flag) {
    els.h1.setAttribute('aria-invalid', String(flag)); els.h2.setAttribute('aria-invalid', String(flag));
  }
  function moveTo(section) {
    const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    section.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    try { section.focus({ preventScroll: true }); } catch { section.focus(); }
  }

  function analyze() {
    els.validation.textContent = ''; setInvalid(false);
    let h1, h2;
    try {
      validateSuitSymbols(els.h1.value, els.h2.value);
      h1 = tokUser(els.h1.value); h2 = tokUser(els.h2.value);
      validatePair(h1, h2);
    } catch (e) {
      els.validation.textContent = e.message; setInvalid(true);
      invalidateResult(); return;
    }

    // Canonicalise without leaving a stale result: set values directly, then refresh buttons/previews after result construction.
    els.h1.value = inputTxt(h1); els.h2.value = inputTxt(h2);

    // Avec un x utilisateur, ne jamais choisir un motif sur une hypothèse implicite.
    // On énumère toutes les petites cartes concrètes possibles et on n'affiche que ce qui est invariant.
    if (h1.includes('x') || h2.includes('x')) {
      const wc = wildcardConsensus(h1, h2), count = wc.worlds.length;
      const safetyHas = wc.safety.compatible && wc.safety.selected.length > 0;
      const maxHas = wc.max.compatible && wc.max.selected.length > 0;
      const params = new URLSearchParams(); if (h1.length) params.set('h1', inputTxt(h1)); if (h2.length) params.set('h2', inputTxt(h2));
      history.replaceState(null, '', params.toString() ? `${location.pathname}?${params}` : location.pathname);

      if (!safetyHas && !maxHas) {
        els.result.classList.add('hidden'); els.noResult.classList.remove('hidden');
        if (!count) {
          setNoResultMessage('Pas de réalisation possible', 'Les x ne peuvent pas être remplacés par des petites cartes distinctes du 2 au 9 avec les cartes déjà indiquées.');
        } else if (!wc.safety.compatible || !wc.max.compatible) {
          setNoResultMessage('Résultat dépendant des petites cartes exactes', `Les ${count} réalisations possibles des x ne conduisent pas toutes au même maniement. Précise une ou plusieurs petites cartes pour obtenir un résultat fiable.`);
        } else {
          setNoResultMessage('Pas de résultat robuste', `Les ${count} réalisations possibles ont été vérifiées, mais aucune conclusion commune n’est couverte par la base.`);
        }
        refresh(); moveTo(els.noResult); return;
      }

      els.noResult.classList.add('hidden'); els.result.classList.remove('hidden');
      els.matchHolding.textContent = `${txt(h1)} / ${txt(h2)}`;
      els.matchBadge.textContent = `ROBUSTE · ${count} CAS`;
      els.safetyResults.innerHTML = '';
      if (wc.safety.compatible) {
        if (wc.safety.selected.length) wc.safety.selected.forEach(h => els.safetyResults.appendChild(robustCard(h, count)));
        else els.safetyResults.innerHTML = '<p class="lead">Aucune cible de sécurité commune n’est référencée pour toutes les réalisations.</p>';
      } else {
        els.safetyResults.innerHTML = `<p class="lead">La ligne de sécurité dépend des petites cartes exactes parmi les ${count} réalisations possibles.</p>`;
      }
      els.maxResults.innerHTML = '';
      if (wc.max.compatible) {
        if (wc.max.selected.length) els.maxResults.appendChild(robustCard(wc.max.selected[0], count));
        else els.maxResults.innerHTML = '<p class="lead">Aucun résultat Max commun n’est référencé pour toutes les réalisations.</p>';
      } else {
        els.maxResults.innerHTML = `<p class="lead">Le jeu pour le maximum dépend des petites cartes exactes parmi les ${count} réalisations possibles.</p>`;
      }
      refresh(); switchMode(safetyHas ? 'safety' : 'max'); moveTo(els.result); return;
    }

    const sf = matches('safety', h1, h2), mx = matches('max', h1, h2);
    if (!sf.length && !mx.length) {
      setNoResultMessage('Pas de résultat fiable', 'Cette combinaison n’est pas référencée, ou les seules données disponibles sont actuellement mises en quarantaine. Aucun résultat incertain n’est choisi silencieusement.');
      els.result.classList.add('hidden'); els.noResult.classList.remove('hidden');
      const params = new URLSearchParams(); if (h1.length) params.set('h1', inputTxt(h1)); if (h2.length) params.set('h2', inputTxt(h2));
      history.replaceState(null, '', params.toString() ? `${location.pathname}?${params}` : location.pathname);
      refresh(); moveTo(els.noResult); return;
    }

    els.noResult.classList.add('hidden'); els.result.classList.remove('hidden');
    els.matchHolding.textContent = `${txt(h1)} / ${txt(h2)}`;
    const all = [...sf, ...mx].sort((a, b) => b.score - a.score);
    els.matchBadge.textContent = all[0].m.exact ? 'EXACT' : (h1.includes('x') || h2.includes('x') ? 'MOTIF AVEC x' : 'MOTIF RECONNU');

    const byTarget = new Map();
    for (const h of sf) { if (!byTarget.has(h.rec.target)) byTarget.set(h.rec.target, []); byTarget.get(h.rec.target).push(h); }
    const targets = [...byTarget.keys()].sort((a,b)=>b-a);
    els.safetyResults.innerHTML = '';
    for (const target of targets) {
      const ties=topTies(byTarget.get(target));
      els.safetyResults.appendChild(divergent(ties) ? ambiguityCard(target,ties) : card(ties[0]));
    }
    if (!targets.length) els.safetyResults.innerHTML = '<p class="lead">Pas de cible de sécurité référencée.</p>';

    els.maxResults.innerHTML = '';
    if (mx.length) {
      const ties=topTies(mx);
      els.maxResults.appendChild(divergent(ties) ? ambiguityCard(null,ties) : card(ties.sort((a,b)=>b.rec.target-a.rec.target)[0]));
    } else els.maxResults.innerHTML = '<p class="lead">Le mode max n’est pas encore renseigné.</p>';

    const params = new URLSearchParams(); if (h1.length) params.set('h1', inputTxt(h1)); if (h2.length) params.set('h2', inputTxt(h2));
    history.replaceState(null, '', params.toString() ? `${location.pathname}?${params}` : location.pathname);
    refresh(); switchMode('safety'); moveTo(els.result);
  }

  function switchMode(m) {
    const safety = m === 'safety';
    els.safetyPanel.classList.toggle('hidden', !safety); els.maxPanel.classList.toggle('hidden', safety);
    els.safetyPanel.setAttribute('aria-hidden', String(!safety)); els.maxPanel.setAttribute('aria-hidden', String(safety));
    document.querySelectorAll('.mode-tab').forEach(b => {
      const active = b.dataset.mode === m; b.classList.toggle('active', active); b.setAttribute('aria-selected', String(active)); b.tabIndex = active ? 0 : -1;
    });
  }

  const tabs = [...document.querySelectorAll('.mode-tab')];
  tabs.forEach((b,i) => {
    b.onclick = () => switchMode(b.dataset.mode);
    b.onkeydown = e => {
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
      e.preventDefault();
      let n = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length-1 : e.key === 'ArrowRight' ? (i+1)%tabs.length : (i-1+tabs.length)%tabs.length;
      switchMode(tabs[n].dataset.mode); tabs[n].focus();
    };
  });
  els.analyze.onclick = analyze;
  els.swap.onclick = () => { const a = els.h1.value; els.h1.value = els.h2.value; els.h2.value = a; preview(); analyze(); };
  els.clear.onclick = () => {
    els.h1.value = ''; els.h2.value = ''; els.validation.textContent = ''; setInvalid(false);
    invalidateResult(); history.replaceState(null, '', location.pathname); preview(); els.h1.focus();
  };

  preview();
  const qs = new URLSearchParams(location.search);
  if (qs.get('h1') || qs.get('h2')) {
    els.h1.value = qs.get('h1') || ''; els.h2.value = qs.get('h2') || ''; preview(); analyze();
  }
})();
