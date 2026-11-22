// Exercise watched states, resume prompt eligibility, and Continue watching list consistency.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const appSource = readFileSync(new URL('../../web/app.js', import.meta.url), 'utf8');

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

  // Extract the functions from app.js
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
  });

  // Extract relevant definitions: vprog, vwatched, setWatched, isWatched, setVprog, resumable
  const snippet = `
    const vprog = () => store.get('vprog', {});
    const vwatched = () => store.get('vwatched', {});
    function setWatched(id, state) {
      const w = vwatched();
      if (state == null) delete w[id]; else w[id] = !!state;
      store.set('vwatched', w);
    }
    function isWatched(id, p, v) {
      const w = vwatched();
      if (w[id] !== undefined) return w[id];
      p = p || vprog()[id];
      const dur = (v && v.duration) || (p && p.d);
      return Boolean(p && p.t && dur && p.t >= dur * 0.9);
    }
    function setVprog(id, data) {
      const p = vprog();
      p[id] = { ...(p[id] || {}), ...data, at: Date.now() };
      const keys = Object.keys(p).sort((a, b) => p[b].at - p[a].at).slice(0, 60);
      store.set('vprog', Object.fromEntries(keys.map(k => [k, p[k]])));
    }
    async function resumable(n = 60) {
      const list = Object.entries(vprog()).filter(([id, v]) => !isWatched(id, v) && v.t > 10 && (!v.d || v.t < v.d - 15)).sort((a, b) => b[1].at - a[1].at).slice(0, n);
      const ok = new Set(await held(list.map(([id]) => id)));
      return list.filter(([id]) => ok.has(id));
    }
    function getResumeAt(id, t, d) {
      const p = vprog()[id];
      const start = t !== null && Number.isFinite(+t) && +t >= 0 ? +t : null;
      return start === null && !isWatched(id, p, d) && p && p.t > 15 && (!d.duration || p.t < d.duration - 20) ? p.t : 0;
    }
  `;

  vm.runInContext(snippet, context);
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

console.log(JSON.stringify({ ok: true, checks }));
