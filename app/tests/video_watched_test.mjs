// Exercise watched states, resume prompt eligibility, and Continue watching list consistency.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const appSource = readFileSync(new URL('../../web/app.js', import.meta.url), 'utf8');

// Extract watch progress, watched state, and resumable definitions directly from web/app.js
const progStart = appSource.indexOf('const vprog = () =>');
const progEnd = appSource.indexOf('/* --------------------------------------------------------------- data -- */');
assert.ok(progStart >= 0 && progEnd > progStart, 'watch progress and resumable found in web/app.js');
const storageSnippet = appSource.slice(progStart, progEnd);

// Extract the resume calculation expression from watch() in web/app.js
const resumeExprMatch = appSource.match(/const resumeAt = (start === null && !isWatched[^;]+);/);
assert.ok(resumeExprMatch, 'resumeAt calculation found in web/app.js');
const resumeSnippet = `function getResumeAt(id, t, d) {
  const p = vprog()[id];
  const start = t !== null && Number.isFinite(+t) && +t >= 0 ? +t : null;
  return ${resumeExprMatch[1]};
}`;

// Extract card badge and watched button directly from web/app.js
const btnStart = appSource.indexOf('const watchedButton =');
const btnEnd = appSource.indexOf('\ndocument.addEventListener', btnStart);
assert.ok(btnStart >= 0 && btnEnd > btnStart, 'watchedButton found in web/app.js');
const buttonSnippet = appSource.slice(btnStart, btnEnd);

const vcardStart = appSource.indexOf('function vcard(v, opts = {}) {');
const vcardEnd = appSource.indexOf('\nfunction rail(', vcardStart);
assert.ok(vcardStart >= 0 && vcardEnd > vcardStart, 'vcard found in web/app.js');
const vcardSnippet = appSource.slice(vcardStart, vcardEnd);

function setupEnvironment() {
  const memory = new Map();
  const storage = {
    getItem(k) { return memory.has(k) ? memory.get(k) : null },
    setItem(k, v) { memory.set(k, String(v)) },
    removeItem(k) { memory.delete(k) },
  };
  const store = {
    get(k, fallback) {
      const raw = storage.getItem('sg.' + k);
      return raw ? JSON.parse(raw) : fallback;
    },
    set(k, v) { storage.setItem('sg.' + k, JSON.stringify(v)) },
  };

  let clock = 10000;
  const context = vm.createContext({
    store,
    fetch: async () => ({ status: 200, ok: true }),
    encodeURIComponent,
    Boolean,
    Object,
    Date: { now: () => ++clock },
    Math,
    HELD: {},
    held: async ids => ids,
    ico: n => '<svg>' + n + '</svg>',
    clock: s => String(s),
    esc: s => String(s ?? ''),
    fromQ: () => '',
    fileUrl: p => '/' + p,
  });

  vm.runInContext(storageSnippet, context);
  vm.runInContext(resumeSnippet, context);
  vm.runInContext(buttonSnippet, context);
  vm.runInContext(vcardSnippet, context);

  context.vprog = vm.runInContext('vprog', context);
  context.vwatched = vm.runInContext('vwatched', context);
  context.watchedButton = vm.runInContext('watchedButton', context);

  return { context, store, memory };
}

let checks = 0;

// Test 1: Partly watched video appears in resumable() and offers resumeAt
{
  const { context } = setupEnvironment();
  context.setVprog('vid-1', { t: 30, d: 100, title: 'Video 1' });

  assert.equal(context.isWatched('vid-1'), false, 'new in-progress video is not watched');
  assert.equal(context.getResumeAt('vid-1', null, { duration: 100 }), 30, 'offers resumeAt 30');

  const list = await context.resumable();
  assert.equal(list.length, 1, 'in-progress video is listed in resumable');
  assert.equal(list[0][0], 'vid-1');

  const card = context.vcard({ id: 'vid-1', title: 'Video 1', duration: 100 });
  assert.ok(!card.includes('class="vcheck"'), 'in-progress card has no checkmark');
  const btn = context.watchedButton('vid-1', { duration: 100 });
  assert.ok(btn.includes('aria-pressed="false"'), 'watched button is unpressed');
  assert.ok(btn.includes('Mark watched'), 'button label is Mark watched');
  checks++;
}

// Test 2: Marking partly watched video as watched removes it from resumable() and suppresses resume prompt
{
  const { context, store } = setupEnvironment();
  context.setVprog('vid-1', { t: 30, d: 100, title: 'Video 1' });

  // User manually marks watched
  context.setWatched('vid-1', true);
  assert.equal(context.isWatched('vid-1'), true, 'video is now watched');
  assert.equal(context.getResumeAt('vid-1', null, { duration: 100 }), 0, 'resumeAt is suppressed when watched');

  const list = await context.resumable();
  assert.equal(list.length, 0, 'watched video is excluded from resumable list');

  // Verify stored progress position was NOT destroyed
  const prog = store.get('vprog', {});
  assert.equal(prog['vid-1'].t, 30, 'saved position is preserved in vprog');

  const card = context.vcard({ id: 'vid-1', title: 'Video 1', duration: 100 });
  assert.ok(card.includes('class="vcheck"'), 'watched card displays vcheck badge');
  const btn = context.watchedButton('vid-1', { duration: 100 });
  assert.ok(btn.includes('aria-pressed="true"'), 'watched button is pressed');
  assert.ok(btn.includes('Watched'), 'button label is Watched');
  checks++;
}

// Test 3: Marking video unwatched again restores it in resumable() and restores resume prompt
{
  const { context } = setupEnvironment();
  context.setVprog('vid-1', { t: 30, d: 100, title: 'Video 1' });
  context.setWatched('vid-1', true);

  // User marks unwatched again
  context.setWatched('vid-1', false);
  assert.equal(context.isWatched('vid-1'), false, 'video is unwatched again');
  assert.equal(context.getResumeAt('vid-1', null, { duration: 100 }), 30, 'resumeAt prompt is restored');

  const list = await context.resumable();
  assert.equal(list.length, 1, 'video reappears in resumable list');
  assert.equal(list[0][0], 'vid-1');
  assert.equal(list[0][1].t, 30, 'saved timestamp is intact');

  const card = context.vcard({ id: 'vid-1', title: 'Video 1', duration: 100 });
  assert.ok(!card.includes('class="vcheck"'), 'unmarked card removes vcheck badge');
  const btn = context.watchedButton('vid-1', { duration: 100 });
  assert.ok(btn.includes('aria-pressed="false"'), 'watched button is unpressed again');
  assert.ok(btn.includes('Mark watched'), 'button label is Mark watched again');
  checks++;
}

// Test 4: Watched choices survive beyond vprog's 60-video limit
{
  const { context, store } = setupEnvironment();
  context.setVprog('target-vid', { t: 50, d: 100, title: 'Target Video', at: 1000 });
  context.setWatched('target-vid', true);

  // Push 65 more videos to exceed the 60-video limit
  for (let i = 1; i <= 65; i++) {
    context.setVprog('filler-' + i, { t: 20, d: 100, title: 'Filler ' + i, at: 2000 + i });
  }

  const prog = store.get('vprog', {});
  assert.equal(prog['target-vid'], undefined, 'target video was pruned from vprog (exceeded 60 items)');
  assert.equal(context.isWatched('target-vid'), true, 'watched status survived independently in vwatched');
  checks++;
}

// Test 5: Reaching 90% auto-completes and removes from resumable()
{
  const { context } = setupEnvironment();
  context.setVprog('auto-vid', { t: 92, d: 100, title: 'Auto Complete Video' });

  assert.equal(context.isWatched('auto-vid'), true, 'auto-detected as watched past 90%');
  const list = await context.resumable();
  assert.equal(list.length, 0, 'auto-completed video is excluded from resumable');
  checks++;
}

// Test 6: Confirm that omitting the watched filter from resumable causes the acceptance check to fail
{
  const { context } = setupEnvironment();
  context.setVprog('filter-test-vid', { t: 40, d: 100, title: 'Filter Test Video' });
  context.setWatched('filter-test-vid', true);

  // Shipped resumable correctly excludes watched
  const shippedList = await context.resumable();
  assert.equal(shippedList.length, 0, 'shipped resumable excludes watched video');

  // Synthetic unpatched resumable (without !isWatched filter) reproduces maintainer scratch scenario:
  const unpatchedResumable = async (n = 60) => {
    const list = Object.entries(context.vprog()).filter(([id, v]) => v.t > 10 && (!v.d || v.t < v.d - 15)).sort((a, b) => b[1].at - a[1].at).slice(0, n);
    const ok = new Set(await context.held(list.map(([id]) => id)));
    return list.filter(([id]) => ok.has(id));
  };
  const unpatchedList = await unpatchedResumable();
  assert.equal(unpatchedList.length, 1, 'resumable without isWatched filter includes watched video');
  checks++;
}

console.log(JSON.stringify({ ok: true, checks }));
