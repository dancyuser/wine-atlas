'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const directory = path.join(__dirname, '..', 'research-extension');
const disk = {};
const tabs = new Map();
const downloads = [];
let nextId = 1;
let now = Date.parse('2026-11-24T12:00:00Z');

function worker() {
  let message;
  const context = vm.createContext({
    URL, console, setTimeout: () => {},
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
          const tab = {url, id: nextId++, status: 'complete'};
          tabs.set(tab.id, tab);
          return tab;
        },
        get: async id => tabs.get(id),
        remove: async id => tabs.delete(id),
        onUpdated: {addListener() {}}
      },
      scripting: {executeScript: async ({target}) => {
        const url = tabs.get(target.tabId).url;
        const blocked = url.endsWith('/blocked');
        return [{result: {url, status: blocked ? 'blocked' : 'needs_review', links: []}}];
      }},
      downloads: {download: async request => { downloads.push(request); return 1; }},
      runtime: {onStartup: {addListener() {}}, onMessage: {addListener(listener) {message = listener;}}}
    }
  });
  context.importScripts = (...files) => files.forEach(file => {
    if (file === 'sources.js') {
      vm.runInContext("const SOURCES=[['Critic','https://critic.test/blocked'],['Retailer','https://retailer.test/wine']];const RECHECK=[];const RETAILERS=new Set(['Retailer']);", context);
    } else {
      vm.runInContext(fs.readFileSync(path.join(directory, file), 'utf8'), context);
    }
  });
  vm.runInContext(fs.readFileSync(path.join(directory, 'background.js'), 'utf8'), context);
  return {send: (action, scope) => new Promise(resolve => message({action, scope}, {}, resolve)), tick: () => vm.runInContext('tick()', context)};
}

(async () => {
  let runtime = worker();
  assert.match((await runtime.send('start')).text, /running/);
  await runtime.tick();
  assert.equal(tabs.size, 1);
  runtime = worker(); // Service worker restarted. The popup never opened again.
  await runtime.tick();
  assert.equal(tabs.size, 0);
  await runtime.tick(); // Unrelated event during the cooldown must not open a tab.
  assert.equal(tabs.size, 0);
  now += 5000;
  await runtime.tick();
  assert.equal(tabs.size, 1);
  await runtime.tick();
  now += 5000;
  await runtime.tick();
  assert.equal(downloads.length, 1);
  const result = JSON.parse(decodeURIComponent(downloads[0].url.split(',')[1]));
  assert.deepEqual(result.observations.map(row => row.status), ['blocked', 'needs_review']);
  assert.match((await runtime.send('start', 'critics')).text, /0 из 1/);
  await runtime.tick();
  await runtime.tick();
  now += 5000;
  await runtime.tick();
  const critics = JSON.parse(decodeURIComponent(downloads[1].url.split(',')[1]));
  assert.deepEqual(critics.observations.map(row => row.source), ['Critic']);
  console.log('Research queue resumed without popup and exported both outcomes');
})().catch(error => { console.error(error); process.exitCode = 1; });
