'use strict';

// Public search result pages. The plan supplies a wine name, never an arbitrary URL.
const STORE_SEARCH_ROUTES = {
  'Винлаб': ['/search', 'q'],
  'Ароматный мир': ['/search/', 'q'],
  'Vinissimo': ['/catalog/index.php', 'q'],
  'Sabonis': ['/search/query='],
  'WineStyle': ['/wine/', null, ['input[aria-label*="Искать на Winestyle"]', 'button[aria-label="Кнопка поиска"]']],
  'SimpleWine': ['/search/', 'q'],
  'AST.WINE': ['/search/', 'q'],
  'Joia': ['/search/', 'q'],
  'Luding': ['/collection/', 'q'],
};

const PRODUCT_ROUTES = {
  'Винлаб': /^\/(?:catalog\/)?product\/[^/]+\/?$/,
  'Ароматный мир': /^\/catalog\/(?:product\/[^/]+|vino\/[^/]+_[^/]+)\/?$/,
  'Vinissimo': /^\/catalog\/wine\/[^/]+-\d+\/?$/,
  'Sabonis': /^\/productDetail\/[^/]+\/?$/i,
  'WineStyle': /^\/products\/[^/]+\.html$/i,
  'SimpleWine': /^\/catalog\/product\/[^/]+\/?$/,
  'AST.WINE': /^\/catalog\/product\/[^/]+\/?$/,
  'Joia': /^\/product\/[^/]+\/?$/,
  'Luding': /^\/collection\/item\/[^/]+(?:\/\d+)?\/?$/,
};
const GENERIC_WORDS = new Set(['wine', 'domaine', 'chateau', 'classico', 'chianti', 'crianza',
  'reserva', 'riserva', 'rosso', 'rouge', 'blanc', 'cabernet', 'sauvignon', 'pinot', 'noir', 'rioja']);

function searchTarget(source, seed, lookup) {
  const route = STORE_SEARCH_ROUTES[source];
  const url = new URL(route?.[0] || seed, seed);
  if (route?.[1]) url.searchParams.set(route[1], lookup.term);
  else if (route && !route[2]) url.pathname += encodeURIComponent(lookup.term);
  return {source, url: url.href, lookup,
    ...(route ? {searchPage: 1, ...(route[2] ? {searchInput: route[2]} : {})} : {searchUnavailable: true})};
}

function shorterSearch(item) {
  const {title, term} = item.lookup;
  if (item.searchPage !== 1 || term !== title) return null;
  const words = (title.match(/\p{L}{4,}/gu) || []).filter(word => !GENERIC_WORDS.has(word.toLowerCase()));
  const shorter = words.sort((a, b) => b.length - a.length)[0];
  return shorter && shorter !== title ? searchTarget(item.source, item.url, {...item.lookup, term: shorter}) : null;
}

function matrixProducts(wine, source, seed, lookup) {
  const supplied = wine.products?.[source];
  return Array.isArray(supplied) ? [...new Set(supplied.slice(0, 2))].flatMap(link => {
    try {
      const url = new URL(link);
      if (url.origin === new URL(seed).origin && !url.search && !url.hash &&
          !url.username && !url.password && PRODUCT_ROUTES[source]?.test(url.pathname)) {
        return [{source, url: url.href, lookup: {...lookup, role: 'detail'}}];
      }
    } catch {}
    return [];
  }) : [];
}

function publisherTargets(wine) {
  return Array.isArray(wine.publisher_pages) ? wine.publisher_pages.slice(0, 5).flatMap(page => {
    try {
      const url = new URL(page.url);
      if (page.source === 'James Suckling' && url.origin === 'https://www.jamessuckling.com' &&
          !url.search && !url.hash && !url.username && !url.password && /^\/tasting-notes\/\d+\/[^/]+\/?$/.test(url.pathname)) {
        return [{source: page.source, url: url.href, lookup: {id: wine.id, title: wine.title, year: wine.year, role: 'publisher'}}];
      }
    } catch {}
    return [];
  }) : [];
}

function matrixQueue(plan, sources, retailers) {
  if (plan?.kind !== 'wine_atlas_store_search_plan' || plan.version !== 1 ||
      !Array.isArray(plan.wines) || !plan.wines.length || plan.wines.length > 1500) {
    throw Error('Ожидается JSON пакета поиска Wine Atlas.');
  }
  const ids = new Set();
  for (const wine of plan.wines) {
    if (!/^[0-9a-f]{12}$/.test(wine?.id) || ids.has(wine.id) ||
        !Number.isInteger(wine.year) || wine.year < 1900 || wine.year > 2099 ||
        typeof wine.title !== 'string' || !wine.title.trim() || wine.title.length > 240) {
      throw Error('Неверное название, винтаж или идентификатор в пакете поиска.');
    }
    ids.add(wine.id);
  }
  const stores = sources.filter(([name]) => retailers.has(name));
  const shopTargets = plan.wines.flatMap(wine => stores.flatMap(([source, seed]) => {
    const title = wine.title.trim();
    const lookup = {id: wine.id, title, term: title, year: wine.year, role: 'query'};
    return [searchTarget(source, seed, lookup), ...matrixProducts(wine, source, seed, lookup)];
  }));
  return [...plan.wines.flatMap(publisherTargets), ...shopTargets];
}

function submitRetailerSearch(selectors, title) {
  const input = document.querySelector(selectors[0]);
  const button = document.querySelector(selectors[1]);
  if (!input || !button) return false;
  input.focus();
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, title);
  input.dispatchEvent(new InputEvent('input', {bubbles: true, data: title}));
  button.click();
  return true;
}

if (typeof module !== 'undefined') module.exports = {matrixQueue, shorterSearch};
