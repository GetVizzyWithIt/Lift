// The Review page (GET /api/review/inbox, /api/review/item/<queue>/<id>; app/review_inbox.py).
// The inbox lists the questions every automatic check left unsettled. Each question opens to one screen:
// the bars in question drawn from the answer key (bar highlighted as it plays), the chart page itself,
// the recording parked on the right spot with the key as soft tones, and answer buttons that fit it.

const audio = $('#audio');
const S = {inbox: null, item: null, notes: null, tapAt: null, barEls: [], loopOn: true};
const clock = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const itemApi = it => `/api/review/item/${encodeURIComponent(it.queue)}/${encodeURIComponent(it.id)}`;

function el(tag, attrs = {}, kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'on') for (const [ev, fn] of Object.entries(v)) e.addEventListener(ev, fn);
    else if (v != null && v !== false) e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of [].concat(kids ?? [])) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return e;
}

// ---- inbox

async function loadInbox() {
  try { S.inbox = await (await fetch('/api/review/inbox')).json(); } catch (_) { S.inbox = {left: 0, items: [], done: 0, minutes: 0}; }
  return S.inbox;
}

function renderInbox() {
  const I = S.inbox;
  $('#inbox').hidden = false; $('#item').hidden = true;
  document.title = I.left ? `Review (${I.left}) · Saxscribe` : 'Review · Saxscribe';
  $('#inboxHead').textContent = I.left === 0 ? 'Nothing needs your ears right now'
    : I.left === 1 ? '1 thing needs your ears' : `${I.left} things need your ears`;
  $('#inboxSub').textContent = I.left
    ? `About ${I.minutes} minute${I.minutes === 1 ? '' : 's'}. Each one is a single question, with the chart bars and the right moment of the recording lined up.`
    : (I.done ? `You've answered ${I.done}. New questions show up here when the Mac scripts can't settle one on their own.`
      : 'New questions show up here when the Mac scripts can’t settle one on their own.');
  const list = $('#inboxList'); list.replaceChildren();
  for (const [i, it] of I.items.entries()) {
    list.append(el('a', {class: 'rv-item card', href: `#${encodeURIComponent(it.queue)}/${encodeURIComponent(it.id)}`}, [
      el('div', {class: 'rv-meta'}, [el('span', {class: 'rv-kind'}, it.kind), el('span', {class: 'quiet small'}, `about ${it.seconds < 60 ? it.seconds + ' s' : Math.round(it.seconds / 60) + ' min'}`)]),
      el('div', {class: 'rv-body'}, [el('strong', {}, it.question), it.song ? el('span', {}, it.song) : '',
        it.why ? el('span', {class: 'quiet small'}, `Why you: ${it.why}`) : '']),
      el('span', {class: 'button primary'}, i === 0 ? 'Start' : 'Open'),
    ]));
  }
}

// ---- one question

async function openItem(queue, id) {
  stopTones(); audio.pause();
  const r = await fetch(`/api/review/item/${encodeURIComponent(queue)}/${encodeURIComponent(id)}`);
  if (!r.ok) { toast('That question is no longer waiting.'); location.hash = ''; return; }
  const it = S.item = await r.json();
  S.notes = null; S.tapAt = null; S.barEls = [];
  $('#inbox').hidden = true; $('#item').hidden = false;
  window.scrollTo(0, 0);
  const pos = S.inbox.items.findIndex(x => x.queue === queue && x.id === id);
  $('#pos').textContent = pos >= 0 ? `(${pos + 1} of ${S.inbox.items.length})` : '';
  $('#kind').textContent = it.kind;
  $('#song').textContent = it.song;
  $('#question').textContent = it.question;
  $('#listenFor').textContent = it.listen_for ? `Listen for: ${it.listen_for}` : '';
  $('#listenFor').hidden = !it.listen_for;
  document.title = `${it.kind} · Review · Saxscribe`;

  // what the machines tried
  $('#triedCard').hidden = !(it.why || it.tried.length);
  $('#why').textContent = it.why ? `Why you: ${it.why}` : '';
  $('#tried').replaceChildren(...it.tried.map(t => el('li', {}, t)));

  renderBars(it);
  renderPage(it);
  setupAudio(it);
  renderAnswers(it);
}

async function renderBars(it) {
  const card = $('#barsCard'), box = $('#bars');
  card.hidden = !it.bars; box.replaceChildren();
  if (!it.bars) return;
  $('#barRange').textContent = it.bars[0] === it.bars[1] ? it.bars[0] : `${it.bars[0]} to ${it.bars[1]}`;
  $('#barsNote').textContent = it.horn && it.horn !== 'concert' ? `${HORN_NAMES[it.horn] || it.horn}, written pitch` : '';
  $('#barsHelp').textContent = '';
  if (!it.can_draw) { box.append(el('p', {class: 'quiet small'}, 'No answer key to draw these bars from; the page below shows them.')); return; }
  box.append(el('p', {class: 'quiet small'}, 'Drawing the bars…'));
  const r = await fetch(`${itemApi(it)}/bars`);
  if (S.item !== it) return;
  if (!r.ok) {
    let msg = 'These bars could not be drawn.'; try { msg = (await r.json()).detail || msg; } catch (_) {}
    box.replaceChildren(el('p', {class: 'quiet small'}, `${msg} The page below shows them.`)); return;
  }
  const d = await r.json();
  box.innerHTML = d.svg;
  S.barEls = [...box.querySelectorAll('g.measure')].map((g, i) => ({g, bar: d.bars[i]}));
  for (const {g, bar} of S.barEls) {
    if (bar == null) continue;
    g.classList.add('rv-bar');
    if (bar === it.focus_bar) g.classList.add('rv-focus');
    g.addEventListener('click', () => barClicked(bar));
  }
  $('#barsHelp').textContent = it.bar_times.length
    ? 'Tap a bar to play from it. The bar that’s sounding is shaded as it plays. Drawn from the answer key; the page below is the original.'
    : 'Drawn from the answer key; the page below is the original.';
}

function barClicked(bar) {
  if (!$('#barWrong').hidden) { $('#wrongBar').value = bar; return; }
  const t = S.item.bar_times.find(b => b.bar === bar);
  if (t) { audio.currentTime = Math.max(0, t.start - 0.3); audio.play(); }
}

function showBarAt(t) {
  if (!S.barEls.length || !S.item) return;
  const now = S.item.bar_times.filter(b => b.start <= t + 0.02).pop();
  const bar = now && t <= now.end + 1.5 ? now.bar : null;
  for (const {g, bar: b} of S.barEls) g.classList.toggle('rv-now', b === bar);
}

let page = {n: 1, crop: null};
function renderPage(it) {
  $('#pageCard').hidden = !it.pages;
  if (!it.pages) return;
  page = {n: it.page.page, crop: it.page.crop};
  $('#openPdf').href = `${itemApi(it)}/pdf`;
  $('#pager').hidden = it.pages < 2;
  $('#pageAll').hidden = !it.page.crop;
  showPage(it);
}

function showPage(it) {
  const g = it.page;
  const q = page.crop ? `?top=${page.crop.top}&bottom=${page.crop.bottom}` : '';
  const img = $('#pageImg');
  img.src = `${itemApi(it)}/page/${page.n}${q}`;
  img.alt = `Chart page ${page.n} of ${it.pages}`;
  $('#pageNo').textContent = `Page ${page.n} of ${it.pages}`;
  const where = it.bars ? (it.bars[0] === it.bars[1] ? `bar ${it.bars[0]}` : `bars ${it.bars[0]} to ${it.bars[1]}`) : '';
  $('#pageHead').textContent = page.n === g.page && where
    ? (g.exact ? `The page: ${where}` : `The page (${where} should be ${g.at < 0.34 ? 'near the top' : g.at < 0.67 ? 'about halfway down' : 'near the bottom'})`)
    : 'The page';
  // park the scroll box near where the bars should be on a whole page
  img.onload = () => {
    const box = $('#pageBox');
    box.scrollTop = !page.crop && page.n === g.page && g.at != null ? Math.max(0, g.at * img.clientHeight - box.clientHeight / 3) : 0;
  };
}
$('#pagePrev').addEventListener('click', () => { if (page.n > 1) { page.n--; page.crop = null; $('#pageAll').hidden = true; showPage(S.item); } });
$('#pageNext').addEventListener('click', () => { if (page.n < S.item.pages) { page.n++; page.crop = null; $('#pageAll').hidden = true; showPage(S.item); } });
$('#pageAll').addEventListener('click', () => { page.crop = null; $('#pageAll').hidden = true; showPage(S.item); });

// ---- the recording

function setupAudio(it) {
  $('#noAudio').hidden = it.has_audio; audio.hidden = !it.has_audio;
  for (const id of ['#playLoop', '#loopOn', '#speed']) $(id).disabled = !it.has_audio;
  $('#which').hidden = !it.has_stem;
  $('#which').querySelectorAll('button').forEach((b, i) => b.classList.toggle('on', i === 0));
  $('#tonesLabel').hidden = !it.has_key;
  $('#tones').checked = it.plugin !== 'listen';
  if (!it.has_audio) { audio.removeAttribute('src'); audio.load(); drawTimeline(); return; }
  audio.src = `${itemApi(it)}/audio/record`;
  audio.addEventListener('loadedmetadata', () => {
    audio.currentTime = spot().start; setSpeed(); drawTimeline();
  }, {once: true});
  const L = it.loop;
  $('#loopOn').checked = !!L; $('#loopOn').disabled = !L;
  $('#loopNote').textContent = L ? `The spot: ${clock(L.start)} to ${clock(L.end)}${it.plugin === 'start_point' ? '' : ', looped'}.` : '';
  $('#startTools').hidden = it.plugin !== 'start_point';
  if (it.plugin === 'start_point') setupStart(it);
}

// where "Play the spot" starts and stops: the loop, else the first guess, else the top
function spot() {
  const it = S.item;
  if (it.loop) return it.loop;
  if (it.guesses.length) return {start: Math.max(0, it.guesses[0].time - 2), end: null};
  return {start: 0, end: null};
}

function drawTimeline() {
  const wave = $('#wave'), marks = $('#marks'); wave.replaceChildren(); marks.replaceChildren();
  const it = S.item, dur = audio.duration;
  if (!it || !(dur > 0)) { wave.hidden = true; return; }
  wave.hidden = false;
  const at = t => `${Math.max(0, Math.min(100, 100 * t / dur))}%`;
  if (it.loop) wave.append(el('span', {class: 'rv-loop', style: `left:${at(it.loop.start)};width:calc(${at(it.loop.end)} - ${at(it.loop.start)})`}));
  for (const g of it.guesses) {
    wave.append(el('span', {class: 'rv-guess', style: `left:${at(g.time)}`}, el('b', {}, g.label)));
  }
  if (S.tapAt != null) wave.append(el('span', {class: 'rv-tapmark', style: `left:${at(S.tapAt)}`}, el('b', {}, 'You')));
  wave.append(el('span', {class: 'rv-head', id: 'playhead', style: `left:${at(audio.currentTime)}`}));
  marks.append(el('span', {}, '0:00'), el('span', {}, clock(dur)));
}

$('#wave').addEventListener('click', e => {
  const r = e.currentTarget.getBoundingClientRect();
  if (audio.duration > 0) audio.currentTime = audio.duration * (e.clientX - r.left) / r.width;
});

function setSpeed() { audio.playbackRate = Number($('#speed').value); audio.preservesPitch = true; audio.webkitPreservesPitch = true; }
$('#speed').addEventListener('change', setSpeed);

function playSpot() {
  const s = spot();
  audio.currentTime = s.start;
  audio.play();
}
$('#playLoop').addEventListener('click', () => { if (!audio.paused && S.item.loop) { audio.pause(); return; } playSpot(); });

audio.addEventListener('timeupdate', () => {
  const it = S.item; if (!it) return;
  const L = it.loop;
  if (L && $('#loopOn').checked && it.plugin !== 'start_point' && audio.currentTime >= L.end) {
    audio.currentTime = L.start; startTones();
  }
  showBarAt(audio.currentTime);
  const ph = $('#playhead'); if (ph && audio.duration > 0) ph.style.left = `${100 * audio.currentTime / audio.duration}%`;
});
audio.addEventListener('play', () => { $('#playLoop').textContent = S.item && S.item.loop ? 'Pause' : 'Play the spot'; });
audio.addEventListener('pause', () => { $('#playLoop').textContent = 'Play the spot'; });

segment($('#which'), v => {
  const t = audio.currentTime, playing = !audio.paused;
  audio.src = `${itemApi(S.item)}/audio/${v}`;
  audio.addEventListener('loadedmetadata', () => { audio.currentTime = t; setSpeed(); drawTimeline(); if (playing) audio.play(); }, {once: true});
});

// ---- the answer key as soft sine tones, scheduled against the recording's clock (and speed)
let actx = null, timer = null, voices = [];
function stopTones() { clearInterval(timer); timer = null; voices.forEach(v => { try { v.stop(); } catch (_) {} }); voices = []; }
async function startTones() {
  stopTones();
  const it = S.item;
  if (!it || !it.has_key || !$('#tones').checked || audio.paused) return;
  if (!S.notes) { try { S.notes = (await (await fetch(`${itemApi(it)}/key`)).json()).notes || []; } catch (_) { S.notes = []; } }
  if (S.item !== it || audio.paused) return;
  actx = actx || new (window.AudioContext || window.webkitAudioContext)();
  if (actx.state === 'suspended') await actx.resume();
  const notes = S.notes;
  let next = notes.findIndex(n => n.offset > audio.currentTime);
  if (next < 0) return;
  const tick = () => {
    const now = audio.currentTime, rate = audio.playbackRate || 1, ahead = now + 0.6 * rate;
    while (next < notes.length && notes[next].onset < ahead) {
      const n = notes[next++];
      const t0 = actx.currentTime + Math.max(0, (n.onset - now) / rate), t1 = actx.currentTime + Math.max(0.05, (n.offset - now) / rate);
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = 'sine'; o.frequency.value = 440 * Math.pow(2, (n.pitch - 69) / 12);
      g.gain.setValueAtTime(0, t0); g.gain.linearRampToValueAtTime(0.12, t0 + 0.02);
      g.gain.setValueAtTime(0.12, Math.max(t0 + 0.02, t1 - 0.04)); g.gain.linearRampToValueAtTime(0, t1);
      o.connect(g).connect(actx.destination); o.start(t0); o.stop(t1 + 0.02);
      voices.push(o); o.onended = () => { voices = voices.filter(v => v !== o); };
    }
  };
  tick(); timer = setInterval(tick, 200);
}
for (const ev of ['play', 'seeked', 'ratechange']) audio.addEventListener(ev, startTones);
for (const ev of ['pause', 'ended', 'emptied']) audio.addEventListener(ev, stopTones);
$('#tones').addEventListener('change', startTones);

// ---- where it starts: play each guess, or tap the moment yourself
function setupStart(it) {
  const box = $('#guessPlay'); box.replaceChildren();
  for (const g of it.guesses) {
    box.append(el('button', {type: 'button', on: {click: () => { audio.currentTime = Math.max(0, g.time - 2); audio.play(); }}},
      `Play from ${g.label} (${clock(g.time)})`));
  }
  $('#tapAt').textContent = '';
}
function setTap(t) {
  S.tapAt = Math.max(0, t);
  $('#tapAt').textContent = `Your tap: ${clock(S.tapAt)}.${String(Math.round((S.tapAt % 1) * 10))}`;
  drawTimeline(); renderAnswers(S.item);
}
$('#tap').addEventListener('click', () => { if (!audio.paused || audio.currentTime > 0) setTap(audio.currentTime); });
$('#nudgeBack').addEventListener('click', () => { if (S.tapAt != null) { setTap(S.tapAt - 0.5); audio.currentTime = S.tapAt; } });
$('#nudgeOn').addEventListener('click', () => { if (S.tapAt != null) { setTap(S.tapAt + 0.5); audio.currentTime = S.tapAt; } });

// ---- answers

function answerButtons(it) {
  if (it.plugin === 'start_point') {
    const out = it.guesses.map(g => ({value: 'guess', label: `It's ${g.label} (${clock(g.time)})`, extra: {time: g.time, choice: g.label}}));
    if (S.tapAt != null) out.push({value: 'tap', label: `Use my tap (${clock(S.tapAt)})`, extra: {time: S.tapAt}});
    out.push({value: 'not_here', label: 'Not on this recording', tone: 'bad'}, {value: 'cant_tell', label: "Can't tell", tone: 'quiet'});
    return out;
  }
  return it.choices.map((c, i) => ({...c, tone: c.value === 'cant_tell' ? 'quiet' : c.value === 'different' ? 'bad'
    : i === 0 ? 'good' : ''}));
}

function renderAnswers(it) {
  const box = $('#answers'); box.replaceChildren();
  const prev = it.answered;
  answerButtons(it).forEach((a, i) => {
    const on = prev && prev.answer === a.value && (a.extra?.choice == null || a.extra.choice === prev.choice);
    box.append(el('button', {type: 'button', class: `rv-ans ${a.tone || ''}${on ? ' on' : ''}`, 'data-n': i + 1,
      on: {click: () => choose(a)}}, [el('kbd', {}, String(i + 1)), a.label]));
  });
  $('#barWrong').hidden = true;
  $('#note').value = prev?.note || '';
  $('#answeredNote').textContent = prev ? `You answered this ${new Date(prev.time).toLocaleString()}.` : '';
  $('#undo').hidden = !prev;
}

function choose(a) {
  if (a.value === 'bar_wrong') {
    $('#barWrong').hidden = false;
    if (S.item.focus_bar) $('#wrongBar').value = S.item.focus_bar;
    $('#wrongBar').focus();
    return;
  }
  send(a.value, a.extra || {});
}
$('#saveBarWrong').addEventListener('click', () => {
  const bar = parseInt($('#wrongBar').value, 10);
  if (!(bar > 0)) { toast('Type the bar number, or tap the bar in the chart.'); return; }
  send('bar_wrong', {bar});
});
$('#undo').addEventListener('click', () => send('undo', {}));

async function send(answer, extra) {
  const it = S.item;
  try {
    const r = await fetch(`${itemApi(it)}/answer`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({answer, note: $('#note').value, extra})});
    if (!r.ok) { let m = 'Could not save.'; try { m = (await r.json()).detail || m; } catch (_) {} toast(m); return; }
    const d = await r.json();
    S.inbox = d.inbox;
    if (answer === 'undo') { toast('Answer taken back.'); openItem(it.queue, it.id); return; }
    toast('Saved.');
    audio.pause();
    const nextItem = S.inbox.items[0];
    location.hash = nextItem ? `#${encodeURIComponent(nextItem.queue)}/${encodeURIComponent(nextItem.id)}` : '';
  } catch (e) { toast(`Could not save: ${e.message}`); }
}

// ---- keys and routing

document.addEventListener('keydown', e => {
  if ($('#item').hidden || e.target.closest('input, textarea, select')) return;
  if (e.key === ' ') { e.preventDefault(); if (audio.paused) playSpot(); else audio.pause(); }
  else if (e.key === 'Escape') location.hash = '';
  else if (/^[1-9]$/.test(e.key)) { const b = $(`#answers button[data-n="${e.key}"]`); if (b) b.click(); }
});
$('#back').addEventListener('click', e => { e.preventDefault(); location.hash = ''; });

async function route() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (!S.inbox) await loadInbox();
  const slash = h.indexOf('/');
  if (h && slash > 0) { openItem(h.slice(0, slash), h.slice(slash + 1)); return; }
  stopTones(); audio.pause(); S.item = null;
  await loadInbox(); renderInbox();
}
window.addEventListener('hashchange', route);
route();
