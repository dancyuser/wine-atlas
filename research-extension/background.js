'use strict';
importScripts('sources.js', 'collector.js');

const KEY = 'wineAtlasResearchObservationsV1';
const JOB = 'wineAtlasResearchJobV1';
const ALARM = 'wineAtlasResearchRecover';
const COOLDOWN = 5000;
const LOAD_TIMEOUT = 60000;
const LIMITS = {critics: 2, retailers: RETAILERS.size};

let busy = false;
let storageTail = Promise.resolve();
let timer;
let wakeAt = Infinity;

function serialize(task) {
  const done = storageTail.then(task);
  storageTail = done.catch(() => {});
  return done;
}

function wake(delay = 1000) {
  if (Date.now() + delay < wakeAt) {
    clearTimeout(timer);
    wakeAt = Date.now() + delay;
    timer = setTimeout(() => {
      wakeAt = Infinity;
      void tick();
    }, delay);
  }
  chrome.alarms.create(ALARM, {delayInMinutes: 0.5});
}

async function stopWake() {
  clearTimeout(timer);
  wakeAt = Infinity;
  await chrome.alarms.clear(ALARM);
}

function phasesFor(queue) {
  const groups = {critics: new Map(), retailers: new Map()};
  for (const item of queue) {
    const kind = RETAILERS.has(item.source) ? 'retailers' : 'critics';
    const hostname = new URL(item.url).hostname.replace(/^www\./, '');
    const group = groups[kind];
    if (!group.has(hostname)) group.set(hostname, {queue: [], cursor: 0, current: null, next_allowed_at: 0});
    group.get(hostname).queue.push(item);
  }
  return Object.entries(groups).map(([kind, lanes]) => ({kind, lanes: [...lanes.values()]}));
}

function migrate(job) {
  if (!job || job.version === 2) return job;
  const phases = phasesFor(job.queue || []);
  const completed = new Set((job.queue || []).slice(0, job.cursor));
  const active = job.queue?.[job.cursor];
  for (const lane of phases.flatMap(phase => phase.lanes)) {
    lane.cursor = lane.queue.filter(item => completed.has(item)).length;
    if (job.current && lane.queue[lane.cursor] === active) lane.current = job.current;
    lane.next_allowed_at = job.next_allowed_at || 0;
  }
  return {version: 2, status: job.status, phases, cleanup: [], last: job.last,
    started_at: job.started_at, review_titles: job.review_titles || []};
}

async function readJob() {
  return migrate((await chrome.storage.local.get(JOB))[JOB]);
}

const activePhase = job => job.phases.find(phase => phase.lanes.some(lane => lane.cursor < lane.queue.length));
const words = value => new Set(value.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().match(/\p{L}{4,}/gu) || []);

function selectDetails(links, titles, limit) {
  const reviews = titles.map(words);
  const ranked = links.map(link => {
    const tokens = words(link.label + ' ' + new URL(link.url).pathname.replace(/[_-]/g, ' '));
    const score = Math.max(0, ...reviews.map(review => [...review].filter(word => tokens.has(word)).length));
    return {link, score};
  });
  return ranked.sort((a, b) => b.score - a.score).slice(0, limit).map(row => row.link);
}

async function download() {
  const observations = (await chrome.storage.local.get(KEY))[KEY] || [];
  const payload = JSON.stringify({version: 1, kind: 'wine_atlas_research_capture', exported_at: new Date().toISOString(), observations});
  if (new TextEncoder().encode(payload).length > 5000000) throw Error('Выгрузка превышает 5 МБ.');
  const documentUrl = chrome.runtime.getURL('export.html');
  const open = await chrome.runtime.getContexts({contextTypes: ['OFFSCREEN_DOCUMENT'], documentUrls: [documentUrl]});
  if (!open.length) {
    await chrome.offscreen.createDocument({url: 'export.html', reasons: ['BLOBS'],
      justification: 'Create a Blob URL to download the research JSON without the data URL size limit.'});
  }
  try {
    const {url} = await chrome.runtime.sendMessage({target: 'research-export', payload});
    const id = await chrome.downloads.download({url, filename: 'wine-atlas-research-' + Date.now() + '.json', saveAs: false});
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      const [file] = await chrome.downloads.search({id});
      if (file?.state === 'complete') return;
      if (file?.state === 'interrupted') throw Error('Скачивание прервано (' + (file.error || 'неизвестная причина') + ').');
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    throw Error('Браузер не подтвердил скачивание JSON.');
  } finally {
    await chrome.offscreen.closeDocument();
  }
}

async function stepDomain(lane, reviewTitles) {
  const item = lane.queue[lane.cursor];
  const current = lane.current;
  let result;
  let discovery;
  try {
    if (!current) {
      const tab = await chrome.tabs.create({url: item.url, active: false});
      lane.current = {tabId: tab.id, started: Date.now()};
      return {changed: true};
    }
    const tab = await chrome.tabs.get(current.tabId);
    if (tab.status !== 'complete') {
      if (Date.now() - current.started < LOAD_TIMEOUT) return {changed: false};
      throw Error('load_timeout');
    }
    const [{result: observed}] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: captureWineResearch});
    result = observed;
    const origin = new URL(item.url).origin;
    if (new URL(result.url).origin !== origin) throw Error('redirect_to_other_origin');
    if (item.depth !== undefined && result.status !== 'blocked') {
      const links = result.links.filter(link => new URL(link.url).origin === origin);
      const pageLimit = 3;
      const detailLimit = item.profile === 'rated' ? 25 : item.source === 'Wine Spectator' ? 30 : 10;
      const seen = new Set(lane.queue.map(row => row.url));
      const detailLinks = links.filter(link => link.kind === 'detail' && !seen.has(link.url));
      const details = selectDetails(detailLinks, RETAILERS.has(item.source) ? reviewTitles : [], detailLimit);
      const next = links.find(link => link.kind === 'next' && !seen.has(link.url));
      const followNext = next && item.depth + 1 < pageLimit;
      const entries = details.map(link => ({source: item.source, url: link.url}));
      if (followNext) entries.push({source: item.source, url: next.url, depth: item.depth + 1, profile: item.profile});
      const added = [];
      for (const entry of entries) {
        if (seen.has(entry.url)) continue;
        seen.add(entry.url);
        added.push(entry);
      }
      lane.queue.splice(lane.cursor + 1, 0, ...added);
      discovery = {page: item.depth + 1, page_limit: pageLimit, detail_limit: detailLimit,
        visible_details: result.visible_links?.details ?? links.filter(link => link.kind === 'detail').length,
        eligible_details: detailLinks.length, queued_details: added.filter(row => row.depth === undefined).length,
        next_found: Boolean(next), next_queued: Boolean(followNext)};
    }
  } catch (error) {
    result = {url: item.url, status: 'error', error: String(error.message || error),
      observed_at: new Date().toISOString(), excerpts: [], links: []};
  }
  lane.cursor++;
  lane.current = null;
  lane.next_allowed_at = Date.now() + COOLDOWN;
  const row = {...result, links: item.depth === undefined ? [] : result.links.slice(0, 20),
    source: item.source, requested_url: item.url, ...(discovery ? {discovery} : {})};
  return {changed: true, row, close: current?.tabId};
}

async function closeFinishedTabs(job) {
  if (!job.cleanup.length) return;
  await Promise.all(job.cleanup.map(id => chrome.tabs.remove(id).catch(() => {})));
  job.cleanup = [];
  await chrome.storage.local.set({[JOB]: job});
}

async function runRound() {
  const job = await readJob();
  if (!job || job.status !== 'running') return;
  await closeFinishedTabs(job);
  const phase = activePhase(job);
  if (!phase) {
    job.status = 'complete';
    await chrome.storage.local.set({[JOB]: job});
    await stopWake();
    try { await download(); }
    catch (error) {
      job.download_error = String(error.message || error);
      await chrome.storage.local.set({[JOB]: job});
    }
    return;
  }

  const open = phase.lanes.filter(lane => lane.current);
  const ready = phase.lanes.filter(lane => !lane.current && lane.cursor < lane.queue.length && lane.next_allowed_at <= Date.now());
  const selected = [...open, ...ready.slice(0, Math.max(0, LIMITS[phase.kind] - open.length))];
  const steps = await Promise.all(selected.map(lane => stepDomain(lane, job.review_titles)));
  if (steps.some(step => step.changed)) {
    const rows = steps.flatMap(step => step.row ? [step.row] : []);
    const titles = rows.filter(row => !RETAILERS.has(row.source) && row.blocks?.review && row.title).map(row => row.title);
    job.review_titles = [...new Set([...job.review_titles, ...titles])].slice(-250);
    job.cleanup = steps.flatMap(step => step.close === undefined ? [] : [step.close]);
    if (rows.length) {
      const saved = (await chrome.storage.local.get(KEY))[KEY] || [];
      job.last = {source: rows.at(-1).source, status: rows.at(-1).status};
      await chrome.storage.local.set({[JOB]: job, [KEY]: [...saved, ...rows]});
      await closeFinishedTabs(job);
    } else {
      await chrome.storage.local.set({[JOB]: job});
    }
  }

  const upcoming = activePhase(job);
  if (!upcoming) {
    wake(0);
    return;
  }
  const working = upcoming.lanes.filter(lane => lane.current).length;
  const waits = upcoming.lanes.filter(lane => !lane.current && lane.cursor < lane.queue.length)
    .map(lane => Math.max(0, lane.next_allowed_at - Date.now()));
  const nextOpen = working < LIMITS[upcoming.kind] ? Math.min(...waits) : Infinity;
  wake(Math.min(working ? 3000 : Infinity, nextOpen));
}

async function tick() {
  if (busy) return;
  busy = true;
  try { await serialize(runRound); }
  catch (error) {
    console.error('research collection error', error);
    wake(30000);
  } finally {
    busy = false;
  }
}

chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === ALARM) void tick(); });
chrome.tabs.onUpdated.addListener((id, change) => { if (change.status === 'complete') void tick(); });
chrome.runtime.onStartup.addListener(() => {
  void serialize(async () => {
    const job = await readJob();
    if (!job || job.status === 'complete') return;
    // Tab IDs are only valid until the browser exits. Retry these pages in new tabs.
    for (const phase of job.phases) for (const lane of phase.lanes) lane.current = null;
    job.cleanup = [];
    await chrome.storage.local.set({[JOB]: job});
    if (job.status === 'running') wake();
  }).catch(error => console.error('research startup error', error));
});

function statusText(job) {
  if (!job) return 'Готово к сбору.';
  const lanes = job.phases.flatMap(phase => phase.lanes);
  const processed = lanes.reduce((n, lane) => n + lane.cursor, 0);
  const total = lanes.reduce((n, lane) => n + lane.queue.length, 0);
  const open = lanes.filter(lane => lane.current).length;
  return 'Состояние: ' + job.status + '; обработано ' + processed + ' из ' + total +
    '. Вкладок: ' + open + '. ' + (job.last?.source || '') + ' ' + (job.last?.status || '') +
    (job.download_error ? ' Ошибка скачивания: ' + job.download_error : '');
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.target === 'research-export') return false;
  serialize(async () => {
    let job = await readJob();
    if (message.action === 'start') {
      if (job && job.status !== 'complete') throw Error('Уже есть незавершённое задание; продолжите его.');
      const queue = [
        ...RECHECK.map(([source, url, profile]) => profile ? {source, url, depth: 0, profile} : {source, url}),
        ...SOURCES.map(([source, url]) => ({source, url, depth: 0}))
      ].filter(item => message.scope === 'critics' ? !RETAILERS.has(item.source) :
        message.scope === 'retailers' ? RETAILERS.has(item.source) : true);
      const reviewTitles = message.scope === 'retailers' ? job?.review_titles || [] : [];
      job = {version: 2, status: 'running', phases: phasesFor(queue), cleanup: [],
        started_at: new Date().toISOString(), review_titles: reviewTitles};
      await chrome.storage.local.set({[JOB]: job, [KEY]: []});
      wake();
    } else if (message.action === 'pause' && job?.status === 'running') {
      job.status = 'paused';
      await chrome.storage.local.set({[JOB]: job});
      await stopWake();
    } else if (message.action === 'resume') {
      if (!job) throw Error('Нет сохранённого задания.');
      if (job.status === 'paused') {
        job.status = 'running';
        await chrome.storage.local.set({[JOB]: job});
      }
      if (job.status === 'running') wake();
    } else if (message.action === 'export') {
      await download();
      if (job?.download_error) {
        delete job.download_error;
        await chrome.storage.local.set({[JOB]: job});
      }
    } else if (message.action === 'record') {
      const observations = (await chrome.storage.local.get(KEY))[KEY] || [];
      await chrome.storage.local.set({[KEY]: [...observations, message.row]});
      return {text: 'Сохранено: ' + (observations.length + 1) + '; статус: ' + message.row.status + '.'};
    } else if (message.action === 'clear') {
      await chrome.storage.local.set({[KEY]: []});
      return {text: 'Наблюдения удалены.'};
    }
    return {text: statusText(job)};
  }).then(respond).catch(error => respond({error: String(error.message || error)}));
  return true;
});
