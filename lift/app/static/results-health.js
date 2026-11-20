// Dataset health tab: every PDF transcription on its way to a confident match with its recording.
// Data: DATA.ledger from /api/results (score/ledger.py): {status, history, pdfs, from}.

const ST = [
  {k: 'matched', name: 'Matched', c: 'var(--st-matched)', means: 'Lined up with its recording and passed every check. Usable.'},
  {k: 'check', name: 'Check', c: 'var(--st-check)', means: 'Lined up, but at lower confidence (a match check, an octave fix pending, few notes placed, or audit flags).'},
  {k: 'wrong_audio', name: 'Wrong recording', c: 'var(--st-wrong)', means: 'The chart reads fine, but our recording is a different take or edit.'},
  {k: 'needs_audio', name: 'Needs a recording', c: 'var(--st-needs)', means: 'No recording yet.'},
  {k: 'unreadable', name: 'Unreadable', c: 'var(--st-unread)', means: 'The page reader failed or misread it. Try another reader, otherwise exclude it.'},
  {k: 'not_started', name: 'Not started', c: 'var(--st-notstarted)', means: 'Chart and recording are both here, but no key has been built yet.'},
  {k: 'unsorted', name: 'Unsorted', c: 'var(--st-unsorted)', means: 'An inbox PDF that hasn’t been identified yet.'},
  {k: 'excluded', name: 'Excluded', c: 'var(--st-excluded)', means: 'Left out on purpose (a copy, an excerpt, or unusable). The reason says why.'},
];
const ST_BY = Object.fromEntries(ST.map(s => [s.k, s]));
const SRC_KINDS = {transcribed: 'Transcribed keys', book_split: 'Books, split per solo', site_pdf: 'Transcription sites',
               excerpt: 'One-page excerpts', youtube_etude: 'Etudes (YouTube)', test_tune: 'Austin’s test tunes',
               loose: 'Loose copies', inbox: 'Inbox, not identified', 'Anderson batch': 'Anderson charts', 'new chart': 'New charts (sites, Steigleder)', other: 'Other instruments'};
const LEDGER_HORNS = {as: 'alto', alto: 'alto', ts: 'tenor', tenor: 'tenor', ss: 'soprano', bs: 'baritone'};
const health = {scale: 'count', kind: '', status: '', q: '', shown: 100};

function kindOf(k) { return /^other instrument/.test(k || '') ? 'other' : (k || 'other'); }
function kindName(k) { return SRC_KINDS[k] || k; }
function pc(n, d) { return d ? `${Math.round(100 * n / d)}%` : '–'; }
function sw(c) { return el('span', {class: 'sw', style: `background:${c}`}); }

function renderHealth() {
  const L = DATA.ledger;
  const has = !!(L && L.status);
  for (const id of ['health-asof', 'health-tiles']) $('#' + id).hidden = !has;
  for (const s of document.querySelectorAll('#tab-health section')) s.hidden = !has;
  $('#health-empty').hidden = has;
  if (!has) return;
  const S = L.status, C = S.counts || {}, total = S.total_pdfs || ST.reduce((a, s) => a + (C[s.k] || 0), 0);
  const resolved = (C.matched || 0) + (C.excluded || 0);
  $('#health-asof').textContent = `Ledger of ${S.generated} (Mac time), from ${L.from}. ${total} PDFs; ` +
    `${S.charts} charts once copies and excerpts are set aside.`;
  healthTiles(C, S, total, resolved);
  healthBar(C, total);
  healthStatusTable(C, total);
  healthSources(S.by_source || {});
  healthHistory(L.history || []);
  healthReasons(S.top_reasons || []);
  healthFilters(L.pdfs || []);
  healthPdfs();
}

function healthTiles(C, S, total, resolved) {
  const tile = (lab, big, small, sub) => {
    const d = el('div', {class: 'tile'});
    d.append(el('div', {class: 'lab'}, lab));
    const b = el('div', {class: 'big'}, big); b.append(el('small', {}, small)); d.append(b);
    d.append(el('div', {class: 'quiet small'}, sub));
    return d;
  };
  const left = total - resolved;
  $('#health-tiles').replaceChildren(
    tile('Charts matched', pc(C.matched || 0, S.charts), `${C.matched || 0} of ${S.charts}`, 'Usable for training and scoring.'),
    tile('PDFs resolved', pc(resolved, total), `${resolved} of ${total}`, 'Matched, or excluded on purpose. The goal is 100%.'),
    tile('Still to resolve', String(left), 'PDFs', `${C.check || 0} to check, ${(C.wrong_audio || 0) + (C.needs_audio || 0)} need the right recording, ` +
      `${C.not_started || 0} not started, ${C.unsorted || 0} unsorted, ${C.unreadable || 0} unreadable.`));
}

// One stacked bar of every PDF, 2px gaps between segments.
function healthBar(C, total) {
  const box = $('#health-bar'), W = Math.max(320, box.clientWidth || 900), H = 40;
  let x = 0, s = `<svg viewBox="0 0 ${W} ${H + 22}" width="${W}" height="${H + 22}" role="img" aria-label="PDFs by status">`;
  for (const st of ST) {
    const n = C[st.k] || 0; if (!n) continue;
    const w = W * n / total;
    s += `<rect class="hseg" x="${x.toFixed(1)}" y="0" width="${Math.max(1, w - 2).toFixed(1)}" height="${H}" rx="4" fill="${st.c}" ` +
         `data-tip="${esc(`${st.name}|${n} of ${total} PDFs (${(100 * n / total).toFixed(1)}%)`)}"/>`;
    if (w > 44) s += `<text x="${(x + w / 2).toFixed(1)}" y="${H + 16}" text-anchor="middle" class="hlab">${n}</text>`;
    x += w;
  }
  box.innerHTML = s + '</svg>';
  segTips(box.querySelector('svg'));
}

function healthStatusTable(C, total) {
  const t = $('#health-status');
  t.replaceChildren();
  const h = el('tr'); for (const c of ['Status', 'What it means', 'PDFs', 'Share of all PDFs']) h.append(el('th', c !== 'Status' && c !== 'What it means' ? {class: 'num'} : {}, c));
  t.append(h);
  for (const st of ST) {
    const tr = el('tr', {class: 'click'});
    const a = el('td'); a.append(sw(st.c), document.createTextNode(' ' + st.name)); tr.append(a);
    tr.append(el('td', {class: 'quiet'}, st.means));
    tr.append(el('td', {class: 'num'}, String(C[st.k] || 0)));
    tr.append(el('td', {class: 'num'}, pc(C[st.k] || 0, total)));
    tr.addEventListener('click', () => { health.status = st.k; health.kind = ''; syncFilters(); healthPdfs(true); });
    t.append(tr);
  }
}

function healthLegend() {
  const lg = $('#health-legend'); lg.replaceChildren();
  for (const st of ST) { const k = el('span', {class: 'key'}); k.append(sw(st.c), document.createTextNode(st.name)); lg.append(k); }
}

function healthSources(bySrc) {
  healthLegend();
  const agg = {};
  const others = {};
  for (const [k, cs] of Object.entries(bySrc)) {
    const g = kindOf(k); agg[g] = agg[g] || {};
    for (const [s, n] of Object.entries(cs)) agg[g][s] = (agg[g][s] || 0) + n;
    if (g === 'other') others[k.replace(/^other instrument:\s*/, '')] = Object.values(cs).reduce((a, b) => a + b, 0);
  }
  const rows = Object.entries(agg).map(([k, cs]) => ({k, cs, n: Object.values(cs).reduce((a, b) => a + b, 0)}))
    .sort((a, b) => b.n - a.n);
  const box = $('#health-sources'), W = Math.max(560, box.clientWidth || 900), LW = 190, RW = 64, bh = 22, gap = 12;
  const max = Math.max(...rows.map(r => r.n), 1), PW = W - LW - RW;
  const H = rows.length * (bh + gap);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="PDFs by source and status">`;
  rows.forEach((r, i) => {
    const y = i * (bh + gap);
    const label = kindName(r.k);
    s += `<g class="hsrc" data-kind="${esc(r.k)}"><text x="${LW - 10}" y="${y + bh / 2 + 5}" text-anchor="end" class="hname">${esc(label)}</text>`;
    let x = LW;
    const scale = health.scale === 'share' ? PW / r.n : PW / max;
    for (const st of ST) {
      const n = r.cs[st.k] || 0; if (!n) continue;
      const w = n * scale;
      const extra = r.k === 'other' ? ` (${Object.entries(others).map(([a, b]) => `${a} ${b}`).join(', ')})` : '';
      s += `<rect class="hseg" x="${x.toFixed(1)}" y="${y}" width="${Math.max(1, w - 2).toFixed(1)}" height="${bh}" rx="4" fill="${st.c}" ` +
           `data-tip="${esc(`${label}${extra}|${st.name}: ${n} of ${r.n} (${Math.round(100 * n / r.n)}%)`)}"/>`;
      x += w;
    }
    const m = r.cs.matched || 0;
    s += `<text x="${(health.scale === 'share' ? LW + PW : x) + 8}" y="${y + bh / 2 + 5}" class="hval">${health.scale === 'share' ? pc(m, r.n) + ' ✓' : r.n}</text></g>`;
  });
  box.innerHTML = s + '</svg>';
  const svg = box.querySelector('svg');
  segTips(svg);
  svg.addEventListener('click', ev => {
    const g = ev.target.closest('.hsrc'); if (!g) return;
    health.kind = g.dataset.kind; health.status = ''; syncFilters(); healthPdfs(true);
  });
}

// Stacked columns, one per ledger run.
function healthHistory(hist) {
  const box = $('#health-history');
  const runs = hist.slice(-40);
  $('#health-history-note').textContent = runs.length < 2
    ? 'Only one ledger run so far, so there is no trend yet. Each new run of pdf_ledger.py adds a column.' : '';
  if (!runs.length) { box.replaceChildren(); return; }
  const W = Math.max(560, box.clientWidth || 900), H = 220, M = {l: 44, r: 8, t: 10, b: 34};
  const tot = r => ST.reduce((a, st) => a + (r.counts[st.k] || 0), 0);
  const max = Math.max(...runs.map(tot), 1);
  const ny = Math.ceil(max / 100) * 100;
  const y = v => M.t + (H - M.t - M.b) * (1 - v / ny);
  const step = (W - M.l - M.r) / Math.max(runs.length, 6), bw = Math.min(48, step * 0.6);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="PDFs by status per ledger run">`;
  for (let v = 0; v <= ny; v += ny / 4) s += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}" class="${v ? 'hgrid' : 'hbase'}"/><text x="${M.l - 6}" y="${y(v) + 4}" text-anchor="end" class="hax">${v}</text>`;
  runs.forEach((r, i) => {
    const x = M.l + step * i + (step - bw) / 2;
    let acc = 0;
    const lines = ST.map(st => `${st.name}: ${r.counts[st.k] || 0}`).join(' · ');
    for (const st of ST) {
      const n = r.counts[st.k] || 0; if (!n) continue;
      const y1 = y(acc + n), y0 = y(acc);
      s += `<rect class="hseg" x="${x.toFixed(1)}" y="${y1.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, y0 - y1 - 2).toFixed(1)}" rx="2" fill="${st.c}" ` +
           `data-tip="${esc(`${r.generated} · ${pc(r.counts.matched || 0, tot(r) - (r.counts.excluded || 0))} of charts matched|${lines}`)}"/>`;
      acc += n;
    }
    s += `<text x="${(x + bw / 2).toFixed(1)}" y="${H - M.b + 16}" text-anchor="middle" class="hax">${esc(r.generated.slice(5, 16))}</text>`;
  });
  box.innerHTML = s + '</svg>';
  segTips(box.querySelector('svg'));
}

function healthReasons(rs) {
  const t = $('#health-reasons');
  t.replaceChildren();
  const h = el('tr'); for (const c of ['Status', 'Reason', 'PDFs']) h.append(el('th', c === 'PDFs' ? {class: 'num'} : {}, c));
  t.append(h);
  for (const r of rs) {
    const st = ST_BY[r.status] || {name: r.status, c: 'var(--line)'};
    const tr = el('tr');
    const a = el('td'); a.append(sw(st.c), document.createTextNode(' ' + st.name)); tr.append(a);
    tr.append(el('td', {}, r.reason));
    tr.append(el('td', {class: 'num'}, String(r.n)));
    t.append(tr);
  }
}

function healthFilters(pdfs) {
  const st = $('#health-st'), kd = $('#health-kind');
  if (st.options.length) return;
  st.append(el('option', {value: ''}, 'Every status'));
  for (const s of ST) st.append(el('option', {value: s.k}, s.name));
  kd.append(el('option', {value: ''}, 'Every source'));
  const kinds = [...new Set(pdfs.map(p => kindOf(p.kind)))].sort((a, b) => kindName(a).localeCompare(kindName(b)));
  for (const k of kinds) kd.append(el('option', {value: k}, kindName(k)));
  st.addEventListener('change', () => { health.status = st.value; healthPdfs(); });
  kd.addEventListener('change', () => { health.kind = kd.value; healthPdfs(); });
  let qt; $('#health-q').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { health.q = e.target.value.trim().toLowerCase(); healthPdfs(); }, 150); });
  $('#health-more').addEventListener('click', () => { health.shown += 200; healthPdfs(false, true); });
}

function syncFilters() { $('#health-st').value = health.status; $('#health-kind').value = health.kind; }

function healthPdfs(scroll = false, keep = false) {
  if (!keep) health.shown = 100;
  const all = (DATA.ledger && DATA.ledger.pdfs) || [];
  const order = Object.fromEntries(ST.map((s, i) => [s.k, i]));
  const rows = all.filter(p => (!health.status || p.status === health.status) && (!health.kind || kindOf(p.kind) === health.kind) &&
    (!health.q || [p.performer, p.tune, p.recording, p.chart_id, p.source].join(' ').toLowerCase().includes(health.q)))
    .sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9) || (a.performer || '').localeCompare(b.performer || '') || (a.tune || '').localeCompare(b.tune || ''));
  $('#health-count').textContent = `${rows.length} of ${all.length} PDFs` + (rows.length > health.shown ? `, first ${health.shown} shown` : '');
  const t = $('#health-pdfs');
  t.replaceChildren();
  const h = el('tr');
  for (const c of ['Player', 'Tune', 'Horn', 'Source', 'Status', 'Reason', 'Heard agree', 'Placed']) h.append(el('th', /agree|Placed/.test(c) ? {class: 'num'} : {}, c));
  t.append(h);
  for (const p of rows.slice(0, health.shown)) {
    const st = ST_BY[p.status] || {name: p.status, c: 'var(--line)'};
    const tr = el('tr');
    tr.append(el('td', {}, p.performer || '–'));
    const tu = el('td', {}, p.tune || p.chart_id || '–');
    if (p.recording) tu.append(el('div', {class: 'quiet small'}, p.recording));
    tr.append(tu);
    tr.append(el('td', {}, LEDGER_HORNS[p.horn] || p.horn || '–'));
    tr.append(el('td', {class: 'quiet'}, kindName(kindOf(p.kind)) + (kindOf(p.kind) === 'other' ? `: ${(p.kind || '').replace(/^other instrument:\s*/, '')}` : '')));
    const a = el('td'); a.append(sw(st.c), document.createTextNode(' ' + st.name)); tr.append(a);
    tr.append(el('td', {class: 'quiet'}, p.reason || ''));
    const num = v => v === '' || v == null ? '–' : (Number(v) <= 1 ? `${Math.round(100 * Number(v))}%` : `${Math.round(Number(v))}%`);
    tr.append(el('td', {class: 'num'}, num(p.heard_agree)));
    tr.append(el('td', {class: 'num'}, num(p.coverage)));
    t.append(tr);
  }
  $('#health-more').hidden = rows.length <= health.shown;
  if (scroll) $('#health-q').closest('section').scrollIntoView({behavior: 'smooth', block: 'start'});
}

segment($('#health-scale'), v => { health.scale = v; if (DATA && DATA.ledger) healthSources(DATA.ledger.status.by_source || {}); });
let hrt; addEventListener('resize', () => { clearTimeout(hrt); hrt = setTimeout(() => { if (!$('#tab-health').hidden && DATA) renderHealth(); }, 150); });
