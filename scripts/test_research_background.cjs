'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const directory = path.join(__dirname, '..', 'research-extension');
const stateKey = 'wineAtlasResearchJobV1';
const observationsKey = 'wineAtlasResearchObservationsV1';
const disk = {};
const tabs = new Map();
const downloads = [];
const exported = [];
const opened = [];
const shops = Array.from({length: 9}, (_, i) => ['Shop ' + i, 'https://shop' + i + '.test/wine']);
const busyOnce = new Set();
let nextId = 1;
let now = Date.parse('2026-11-24T12:00:00Z');

function worker() {
  let message;
  let exportOpen = false;
  const context = vm.createContext({
    URL, TextEncoder, console, setTimeout: () => 1, clearTimeout: () => {},
    Date: class extends Date {
      constructor() { super(now); }
      static now() { return now; }
    },
    chrome: {
      storage: {local: {
        get: async key => ({[key]: structuredClone(disk[key])}),
        set: async changes => Object.assign(disk, structuredClone(changes))
      }},
      alarms: {create: () => {}, clear: async () => true, onAlarm: {addListener() {}}},
      tabs: {
        create: async ({url, active}) => {
          assert.equal(active, false);
          if (busyOnce.delete(url)) throw Error('Tabs cannot be edited right now (user may be dragging a tab).');
          const domain = new URL(url).hostname;
          assert(![...tabs.values()].some(tab => new URL(tab.url).hostname === domain));
          const tab = {url, id: nextId++, status: url.endsWith('/blocked') ? 'loading' : 'complete'};
          tabs.set(tab.id, tab);
          opened.push({url, time: now});
          return tab;
        },
        get: async id => tabs.get(id),
        remove: async id => tabs.delete(id),
        onUpdated: {addListener() {}}
      },
      scripting: {executeScript: async ({target}) => {
        const {url} = tabs.get(target.tabId);
        const status = url.endsWith('/blocked') ? 'blocked'
          : url.endsWith('/age-gate') ? 'age_gate' : 'needs_review';
        return [{result: {url, status, links: [], observed_at: new Date(now).toISOString()}}];
      }},
      downloads: {
        download: async request => {
          assert(exportOpen && request.url.startsWith('blob:'));
          downloads.push(request);
          return downloads.length;
        },
        search: async () => [{state: 'complete'}],
      },
      offscreen: {
        createDocument: async () => { exportOpen = true; },
        closeDocument: async () => { exportOpen = false; },
      },
      runtime: {
        getURL: path => 'chrome-extension://test/' + path,
        getContexts: async () => exportOpen ? [{}] : [],
        sendMessage: async ({target, payload}) => {
          assert(exportOpen && target === 'research-export');
          exported.push(payload);
          return {url: 'blob:chrome-extension://test/' + exported.length};
        },
        onStartup: {addListener() {}},
        onMessage: {addListener(listener) {message = listener;}},
      },
    }
  });
  context.SOURCES = [
    ['One', 'https://one.test/catalog'], ['Two', 'https://two.test/catalog'], ['Three', 'https://three.test/catalog'],
    ...shops
  ];
  context.RECHECK = [['One', 'https://one.test/blocked']];
  context.RETAILERS = new Set(shops.map(row => row[0]));
  context.importScripts = (...files) => files.filter(file => file !== 'sources.js').forEach(file => {
    vm.runInContext(fs.readFileSync(path.join(directory, file), 'utf8'), context);
  });
  vm.runInContext(fs.readFileSync(path.join(directory, 'background.js'), 'utf8'), context);
  return {send: (action, scope, row) => new Promise(resolve => message({action, scope, row}, {}, resolve)),
    tick: () => vm.runInContext('tick()', context)};
}

const activeURLs = () => [...tabs.values()].map(tab => tab.url);
const payload = i => JSON.parse(exported[i]);

(async () => {
  let runtime = worker();
  assert.match((await runtime.send('start')).text, /running/);
  await runtime.tick();
  assert.deepEqual(activeURLs(), ['https://one.test/blocked', 'https://two.test/catalog']);
  const slowTab = [...tabs.values()][0];
  runtime = worker(); // The service worker restarted with its popup closed.
  await runtime.tick();
  assert.deepEqual(activeURLs(), [slowTab.url]);
  await runtime.tick();
  assert.deepEqual(activeURLs(), [slowTab.url, 'https://three.test/catalog']);
  await runtime.tick();
  assert.deepEqual(activeURLs(), [slowTab.url]);
  assert.equal(opened.some(row => row.url.includes('shop')), false);
  slowTab.status = 'complete';
  await runtime.tick();
  await runtime.tick();
  assert.equal(tabs.size, 0);
  const finishedAt = now;
  now += 4999;
  await runtime.tick();
  assert.equal(tabs.size, 0);
  now++;
  await runtime.tick();
  assert.deepEqual(activeURLs(), ['https://one.test/catalog']);
  assert.equal(opened.at(-1).time - finishedAt, 5000);
  await runtime.tick();
  await runtime.tick();
  assert.deepEqual(activeURLs(), shops.map(row => row[1]));
  await runtime.tick();
  await runtime.tick();
  assert.equal(downloads.length, 1);
  assert.equal(payload(0).observations.length, 13);
  assert.equal(payload(0).observations.filter(row => row.status === 'blocked').length, 1);
  assert.equal(new Set(payload(0).observations.map(row => row.url)).size, 13);

  assert.match((await runtime.send('start', 'retailers')).text, /0 из 9/);
  await runtime.tick();
  assert.equal(tabs.size, 9);
  assert.match((await runtime.send('pause')).text, /paused/);
  runtime = worker();
  await runtime.tick();
  assert.equal(tabs.size, 9);
  assert.match((await runtime.send('resume')).text, /running/);
  await Promise.all([runtime.tick(), runtime.send('record', null, {url: 'https://manual.test', status: 'needs_review'})]);
  await runtime.tick();
  assert.equal(payload(1).observations.length, 10);
  assert.equal(payload(1).observations.filter(row => row.source?.startsWith('Shop ')).length, 9);
  assert.equal(payload(1).observations.filter(row => row.url === 'https://manual.test').length, 1);

  // Retain the recorded rows and an active tab from the serial collector.
  const legacyTab={id: nextId++, url: 'https://two.test/catalog', status: 'complete'};
  tabs.set(legacyTab.id, legacyTab);
  disk[stateKey] = {
    status: 'running', cursor: 1, current:{tabId:legacyTab.id, started:now},
    queue: [{source:'One',url:'https://one.test/catalog'}, {source:'Two',url:legacyTab.url}]
  };
  disk[observationsKey] = [{source:'One',url:'https://one.test/catalog'}];
  runtime = worker();
  await runtime.tick();
  await runtime.tick();
  assert.deepEqual(payload(2).observations.map(row => row.source), ['One','Two']);
  const retryURL = shops[0][1];
  busyOnce.add(retryURL);
  await runtime.send('start', 'retailers');
  await runtime.tick();
  assert.equal(tabs.size, 8);
  await runtime.tick();
  assert.equal(tabs.size, 0);
  assert.equal(disk[observationsKey].length, 8);
  now += 5000;
  await runtime.tick();
  await runtime.tick();
  await runtime.tick();
  const recovered = payload(3).observations.find(row => row.url === retryURL);
  assert.equal(recovered.status, 'needs_review');
  assert.equal(recovered.retries, 1);

  const entry = (shop, suffix, id) => ({source: `Shop ${shop}`,
    url: `https://shop${shop}.test/${suffix}`, searchPage: 1,
    lookup: {id, role: 'query', title: id, term: id}});
  const lane = queue => ({queue, cursor: 0, current: null, next_allowed_at: 0});
  const gated = entry(0, 'age-gate', 'vintage-a');
  const skipped = entry(0, 'skipped', 'vintage-b');
  const available = entry(1, 'vintage-b', 'vintage-b');
  disk[stateKey] = {version: 2, status: 'running', cleanup: [], review_titles: [],
    phases: [{kind: 'retailers', lanes: [lane([gated, skipped]), lane([available])]}]};
  disk[observationsKey] = [];
  await runtime.tick();
  await runtime.tick();
  await runtime.tick();
  assert.equal(opened.some(row => row.url === skipped.url), false);
  const lookupRows = payload(4).observations;
  assert.equal(lookupRows.find(row => row.url === gated.url).status, 'age_gate');
  assert.deepEqual(lookupRows.find(row => row.url === skipped.url).lookup,
    {...skipped.lookup, role: 'skipped'});
  assert.equal(lookupRows.find(row => row.url === skipped.url).access_reason, 'age_gate');
  assert.equal(lookupRows.find(row => row.url === available.url).status, 'needs_review');
  console.log('Parallel research verified: 2 critic domains, 9 stores, cooldown, restart, pause, export, migration and access gates');
})().catch(error => { console.error(error); process.exitCode = 1; });
