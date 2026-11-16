// The Library (GET /api/library, app/catalog.py): matched answer keys plus finished takes,
// with search, a horn and source filter, group by, sort, and cards or a list.

const PREF = 'saxscribe.library';
const st = Object.assign({q: '', src: '', horn: '', group: 'player', sort: 'title', view: 'cards', closed: []},
  (() => { try { return JSON.parse(localStorage.getItem(PREF)) || {}; } catch (e) { return {}; } })());
function save() { try { localStorage.setItem(PREF, JSON.stringify({...st, q: ''})); } catch (e) {} }
let LIB = null;

const USE = {training: 'In training', benchmark: 'Benchmark'};
const SOURCE = {key: 'Answer key', saxscribe: 'My take'};
const GROUPS = {
  player: s => s.player || 'Unknown player',
  horn: s => HORN_NAMES[s.horn] || 'Horn not set',
  decade: s => s.decade || 'Year unknown',
  source: s => SOURCE[s.source],
  use: s => s.source !== 'key' ? 'My take' : USE[s.use] || 'Neither (not used by the model yet)',
  kind: s => s.kind_name || 'Other',
};
const LAST = /^(Unknown|Horn not set|Year unknown|Neither)/;   // these groups go at the end

function text(s) { return [s.title, s.player, s.played_by, s.book, s.record, s.style, s.year].filter(Boolean).join(' ').toLowerCase(); }
function by(key) {
  const t = (a, b) => a.title.localeCompare(b.title, undefined, {numeric: true});
  const yr = d => (a, b) => (a.year == null) - (b.year == null) || d * ((a.year || 0) - (b.year || 0)) || t(a, b);
  return {title: t, player: (a, b) => (a.player || '~').localeCompare(b.player || '~') || t(a, b),
          new: yr(-1), old: yr(1), heard: (a, b) => (b.heard ?? -1) - (a.heard ?? -1) || t(a, b)}[key] || t;
}
function pct(v) { return v == null ? '' : `${Math.round(100 * v)}%`; }

function meta(s) {
  const one = [s.player, s.year, HORN_NAMES[s.horn] && HORN_NAMES[s.horn].toLowerCase()].filter(Boolean).join(' · ');
  const two = s.source === 'saxscribe' ? `${s.kind_name}${s.added ? ' · ' + s.added.slice(0, 10) : ''}`
    : s.played_by ? `Played by ${s.played_by}${s.book ? ' · ' + s.book : ''}` : s.record || s.kind_name;
  return [one, two];
}
function chips(s) {
  const c = [`<span class="chip ${s.source === 'key' ? 'key' : 'made'}">${SOURCE[s.source]}</span>`];
  if (s.use) c.push(`<span class="chip">${USE[s.use]}</span>`);
  if (s.heard != null) c.push(`<span class="chip">Key heard ${pct(s.heard)}</span>`);
  return c.join('');
}
// The record's cover when `python -m lift covers` found one; otherwise (and for your own takes) the Lift icon.
const LOGO = '/static/brand/app-icon.svg';
function art(s) {
  const src = s.cover || LOGO;
  return `<img class="art" src="${esc(src)}" alt="" loading="lazy" width="64" height="64"` +
    (s.cover ? ` onerror="this.onerror=null;this.src='${LOGO}'"` : '') + '>';
}
function card(s) {
  const [a, b] = meta(s);
  const inner = art(s) + `<div class="body"><div class="t">${esc(s.title)}</div><div class="small quiet">${esc(a)}</div>` +
    (b ? `<div class="small quiet">${esc(b)}</div>` : '') + `<div class="chips">${chips(s)}</div></div>`;
  return s.href ? `<a class="song link" href="${esc(s.href)}">${inner}</a>` : `<div class="song">${inner}</div>`;
}
function row(s) {
  const [a, b] = meta(s);
  const name = s.href ? `<a href="${esc(s.href)}">${esc(s.title)}</a>` : esc(s.title);
  return `<tr><td class="t">${name}</td><td>${esc(a)}</td><td class="quiet">${esc(b || '')}</td><td class="chips">${chips(s)}</td></tr>`;
}

function render() {
  if (!LIB) return;
  const q = st.q.trim().toLowerCase();
  const shown = LIB.songs.filter(s => (!st.src || s.source === st.src) && (!st.horn || s.horn === st.horn) &&
    (!q || q.split(/\s+/).every(w => text(s).includes(w)))).sort(by(st.sort));
  const C = LIB.counts;
  $('#shown').textContent = `${shown.length} of ${LIB.songs.length} songs shown` + (q || st.src || st.horn ? '' : '.');
  const box = $('#shelf');
  if (!shown.length) { box.innerHTML = `<p class="quiet">${LIB.songs.length ? 'Nothing matches. Try fewer words or another filter.' : 'Nothing here yet.'}</p>`; return; }
  const key = GROUPS[st.group];
  const groups = new Map();
  for (const s of shown) { const g = key ? key(s) : ''; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(s); }
  const names = [...groups.keys()].sort((a, b) => LAST.test(a) - LAST.test(b) ||
    (st.group === 'player' ? groups.get(b).length - groups.get(a).length : 0) || a.localeCompare(b, undefined, {numeric: true}));
  box.innerHTML = names.map(g => {
    const list = groups.get(g);
    const body = st.view === 'list'
      ? `<div class="scroll"><table class="songlist">${list.map(row).join('')}</table></div>`
      : `<div class="songs">${list.map(card).join('')}</div>`;
    if (!key) return body;
    const open = !st.closed.includes(`${st.group}:${g}`);
    return `<details class="grp" data-g="${esc(`${st.group}:${g}`)}"${open ? ' open' : ''}><summary><b>${esc(g)}</b><span class="quiet small">${list.length}</span></summary>${body}</details>`;
  }).join('');
}

$('#shelf').addEventListener('toggle', e => {
  const d = e.target.closest('details.grp'); if (!d) return;
  st.closed = st.closed.filter(x => x !== d.dataset.g).concat(d.open ? [] : [d.dataset.g]); save();
}, true);
$('#q').addEventListener('input', e => { st.q = e.target.value; render(); });
for (const [id, k] of [['group', 'group'], ['sort', 'sort']]) {
  $('#' + id).value = st[k];
  $('#' + id).addEventListener('change', e => { st[k] = e.target.value; save(); render(); });
}
for (const k of ['src', 'horn', 'view']) {
  $('#' + k).querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === st[k]));
  segment($('#' + k), v => { st[k] = v; save(); render(); });
}

function header() {
  const C = LIB.counts, L = LIB.ledger;
  const bar = $('#readyBar');
  if (L && C.charts) {
    $('#ready').textContent = `${C.keys} of ${C.charts} charts are matched to their recording and ready` +
      `${C.takes ? `, plus ${C.takes} of your own transcription${C.takes > 1 ? 's' : ''}` : ''}. ` +
      `The rest show up here as the matching work finishes. Ledger of ${L.generated}, from ${L.from}.`;
    bar.hidden = false; bar.firstElementChild.style.width = `${Math.min(100, 100 * C.keys / C.charts)}%`;
  } else {
    $('#ready').textContent = 'No chart ledger found yet, so only your own transcriptions are listed.';
  }
  const hid = C.hidden_missing + C.hidden_changed;
  $('#hiddenNote').hidden = !hid;
  if (hid) $('#hiddenNote').textContent = `${hid} matched chart${hid > 1 ? 's are' : ' is'} left out: ` +
    [C.hidden_missing && `${C.hidden_missing} PDF${C.hidden_missing > 1 ? 's' : ''} not found where the ledger says`,
     C.hidden_changed && `${C.hidden_changed} PDF${C.hidden_changed > 1 ? 's' : ''} changed since matching`].filter(Boolean).join(', ') +
    '. Rerunning the ledger brings them back.';
}

fetch('/api/library').then(r => r.json()).then(d => { LIB = d; header(); render(); })
  .catch(() => { $('#ready').textContent = 'The Library could not be loaded from the Mac.'; });
