/* Runs in an explicitly chosen browser tab. All extracted claims need review. */
'use strict';
function captureWineResearch() {
  const cleanUrl = value => {
    try {
      const u = new URL(value, location.href);
      if (u.protocol !== 'https:' || u.username || u.password) return null;
      for (const key of [...u.searchParams.keys()]) {
        if (!/^(?:page|pagen_\d+)$/i.test(key) || !/^\d+$/.test(u.searchParams.get(key))) u.searchParams.delete(key);
      }
      u.hash = '';
      return u.href;
    } catch { return null; }
  };
  const url = cleanUrl(location.href);
  const title = (document.querySelector('h1')?.innerText || document.querySelector('h2')?.innerText || '').trim().slice(0, 500);
  const body = document.body?.innerText || '';
  const host = location.hostname.replace(/^www\./, '');
  const path = new URL(location.href).pathname;
  const blocked = /captcha|cloudflare ray id|access denied|доступ запрещ[её]н|подтвердите,? что вы не робот|verify you are human|sign in to continue|subscribe to read/i.test(body.slice(0, 5000));
  const relevant = /\b(?:rating|points?|score|vintage|drink(?:ing)?|enjoy|cellar|price|availability|stock|producer|winery|grape|year|tasted|review|read more|punkte|jahrgang|trinkreife|lagerung|preis)\b|рейтинг|балл|оценк|урожа|винтаж|хранени|употреб|потенциал|цен[аы]|наличи|винотек|поставщик|санкт.петербург|объем|объём|производител|сорт|дегустац/i;
  const lines = body.split(/\n+/).map(x => x.trim()).filter(Boolean);
  const excerpts = [];
  if (!blocked) for (let i = 0; i < lines.length && excerpts.length < 12; i++) {
    if (!relevant.test(lines[i])) continue;
    const excerpt = lines.slice(Math.max(0, i - 1), Math.min(lines.length, i + 2)).join(' | ').slice(0, 240);
    if (!excerpts.includes(excerpt)) excerpts.push(excerpt);
  }
  const links = [];
  const detailURLs = new Set();
  const nextURLs = new Set();
  // Keep catalogue navigation separate from links to individual bottles.
  const detailPaths = {
    'wineenthusiast.com': /^\/buying-guide\/[^/]+\/?$/,
    'top100.winespectator.com': /^\/20\d{2}\/wine\/[^/]+\/?$/,
    'winespectator.com': /^\/wine\/detail\/[^/]+\/?$/,
    'falstaff.com': /^\/[^/]+\/(?:wines|weine)\/[^/]+\/?$/,
    'decanter.com': /^\/wine-reviews\/(?!search\/)(?:[^/]+\/)+[^/]+-\d+\/?$/,
    'spb.winestyle.ru': /^\/products\/[^/]+\.html$/i,
    'spb.luding.ru': /^\/collection\/item\/[^/]+(?:\/\d+)?\/?$/,
    'luding.ru': /^\/collection\/item\/[^/]+(?:\/\d+)?\/?$/,
    'simplewine.ru': /^\/catalog\/product\/[^/]+\/?$/,
    'ast.wine': /^\/catalog\/product\/[^/]+\/?$/,
    'amwine.ru': /^\/catalog\/(?:product\/[^/]+|vino\/[^/]+_[^/]+)\/?$/,
    'winelab.ru': /^\/(?:catalog\/)?product\/[^/]+\/?$/,
    'joia.ru': /^\/product\/[^/]+\/?$/,
    'sabonis.ru': /^\/productDetail\/[^/]+\/?$/i,
    'vinissimo.biz': /^\/catalog\/wine\/[^/]+-\d+\/?$/,
    'vinous.com': /^\/wines\/(?!lists(?:\/|$))[^/]+(?:\/\d{4})?\/?$/,
    'jancisrobinson.com': /^\/tastings\/\d+\/?$/
  };
  const pagination = u => {
    const route = u.pathname.match(/\/page(?:\/)?(\d+)(?=\/|$)/i);
    const query = [...u.searchParams.entries()].find(([key]) => /^(?:page|pagen_\d+)$/i.test(key));
    return {section: u.pathname.replace(/\/page(?:\/)?\d+(?=\/|$)/i, '').replace(/\/$/, ''),
      page: Number(route?.[1] || query?.[1] || 1)};
  };
  const here = pagination(new URL(url || location.href));
  if (!blocked) for (const a of document.querySelectorAll('a[href]')) {
    const href = cleanUrl(a.href), label = (a.innerText || a.querySelector('img')?.alt || '').trim().slice(0, 200);
    if (!href || !label || href === url || new URL(href).hostname !== location.hostname) continue;
    const p = new URL(href);
    const candidate = pagination(p);
    const next = a.rel === 'next' || (candidate.section === here.section && candidate.page === here.page + 1);
    const detail = (detailPaths[host] || /\/(?:wines?|weine|wine-reviews|tasting-notes|product(?:s|detail)?|item|detail|reviews?)\/.+/i).test(p.pathname);
    const seen = next ? nextURLs : detailURLs;
    if ((!next && !detail) || seen.has(href)) continue;
    seen.add(href);
    if (next || seen.size <= 150) links.push({url: href, label, kind: next ? 'next' : 'detail'});
  }
  // Capture small, attributable blocks used by the offline parser. Read rendered
  // text only: metadata prices on these sites can belong to another region.
  const blocks = {};
  if (!blocked) {
    const put = (key, value) => { if (value) blocks[key] = value.trim().slice(0, 7000); };
    if (host === 'wineenthusiast.com' && path.startsWith('/buying-guide/')) {
      put('review', (document.querySelector('#review-wrapper, .review-wrapper, main')?.innerText || body).split(/What Is Blind Tasting\?/i)[0]);
    } else if (host === 'top100.winespectator.com' && detailPaths[host].test(path)) {
      put('review', (document.querySelector('main, article')?.innerText || body).split(/\n(?:More Wines|See Also|Related Articles)\b/i)[0]);
    } else if (/falstaff\.com$/.test(host) && /\/(?:wines|weine)\/.+/.test(path)) {
      put('producer', document.querySelector('main h2')?.innerText);
      put('review', (document.querySelector('main')?.innerText || body).split(/Other Vintages|Andere Jahrgänge/i)[0]);
    } else if (host === 'vinous.com' && detailPaths[host].test(path)) {
      put('review', (document.querySelector('main')?.innerText || body).split(/Similar Wines|Related Articles/i)[0]);
    } else if (host === 'botti.no' && path.startsWith('/smaksnotater-')) {
      const facts = lines.filter(line => /^(?:Varenr|Vin|Pris|Poeng)\s*:/i.test(line));
      put('review', facts.join('\n'));
    } else if (/^(?:decanter\.com|results\.decanter\.com|iwsc\.net|jamessuckling\.com|jancisrobinson\.com)$/.test(host) &&
      /(?:\/tastings\/|\/tasting-notes\/|\/detail\/|\/wine-reviews\/(?!search\/)[^/]+\/.*\d)/.test(path)) {
      put('review', (document.querySelector('main article, article, main')?.innerText || '').split(/Related wines|Similar wines|You may also like/i)[0]);
    } else if (host === 'sabonis.ru' && /^\/productDetail\//i.test(path)) {
      put('product', body.split(/Рекомендованные товары/i)[0]);
      put('document_title', document.title);
    } else if (host === 'vinissimo.biz' && /^\/catalog\/wine\/.+-\d+\//.test(path)) {
      const lines = body.split('\n').map(line => line.trim()).filter(Boolean);
      const index = lines.findIndex(line => line === title);
      put('product', index >= 0 ? lines.slice(index, index + 135).join('\n') : '');
      put('document_title', document.title);
      put('city', lines.slice(0, index).find(line => /^(?:Санкт-Петербург|Москва)$/.test(line)));
    } else if (host === 'spb.winestyle.ru' && /^\/products\//.test(path)) {
      put('price_stock', document.querySelector('.o-productpage-info__price .m-productpage-price')?.innerText);
      put('document_title', document.title);
    } else if (/^(?:spb\.)?luding\.ru$/.test(host) && /^\/collection\/item\//.test(path)) {
      const page = body.split(/Похожие товары/i)[0];
      const fromTitle = page.indexOf(title);
      put('product', fromTitle >= 0 ? page.slice(fromTitle) : '');
      put('document_title', document.title);
      // The city is chosen in the header. Footer city links are irrelevant.
      const city = page.split('\n').map(line => line.trim()).find(line => /^(?:Санкт-Петербург|Москва)$/.test(line));
      put('city', city);
    } else if (['winelab.ru', 'amwine.ru', 'simplewine.ru', 'ast.wine', 'joia.ru'].includes(host) &&
               detailPaths[host].test(path)) {
      const index = lines.indexOf(title);
      if (index >= 0) {
        const section = lines.slice(index);
        const next = section.findIndex(line => /^(?:Похожие товары|С этим покупают|Рекомендуем также|Вам может понравиться)$/i.test(line));
        const product = section.slice(0, next >= 0 ? next : undefined);
        if (host === 'simplewine.ru') {
          const experts = product.findIndex(line => /^Рейтинги экспертов$/i.test(line));
          if (experts >= 0) {
            const following = product.slice(experts + 1, experts + 25);
            const end = following.findIndex(line => /^(?:Особенности|Мнение эксперта|Отзывы|Характеристики|Гастрономия)$/i.test(line));
            put('critic_hints', following.slice(0, end >= 0 ? end : undefined).join('\n'));
          }
        }
        const header = lines.slice(0, index);
        const cities = new Set(header.map(line => line.match(/^(?:г\.\s*)?(Санкт-Петербург|Москва)$/i)?.[1]).filter(Boolean));
        // Only an unambiguous city before the product is part of the current selection.
        if (cities.size === 1) put('city', [...cities][0]);
        else if (host === 'amwine.ru' && cities.size === 0) {
          const chosen = header.join('\n').match(/Выбран магазин[^\n]*\n(?:[^\n]*\n){0,2}[^\n]*\bг\.\s*Санкт-Петербург/i);
          if (chosen) put('city', 'Санкт-Петербург');
        }
        const facts = (host === 'joia.ru'
          ? (document.querySelector('#solo.js__product-card')?.innerText || '').split(/\n+/)
          : product).slice(0, 85);
        if (host === 'ast.wine') {
          const selected = document.querySelector('a.vintage_item.current');
          if (selected && cleanUrl(selected.href) === url) put('selected_variant', selected.innerText?.trim().split('\n', 1)[0]);
          const prices = new Set([...document.querySelectorAll('.product-price__wrap')]
            .map(el => el.innerText?.trim()).filter(Boolean));
          if (prices.size === 1) put('offer_price', [...prices][0]);
          const shops = [...document.querySelectorAll('.stock-list-short__item')].map(el => {
            if (!el.getClientRects().length) return '';
            const address = el.querySelector('.stock-list-short__item-address')?.innerText?.trim();
            const stock = el.querySelector('span:not(.favorite-store-badge)')?.innerText?.trim();
            return address && stock ? address + ' | ' + stock : '';
          });
          put('local_shops', [...new Set(shops.filter(Boolean))].join('\n'));
        } else if (host === 'joia.ru') {
          const selected = document.querySelector('#solo input[name="milezim"]:checked + label');
          if (selected) put('selected_variant', selected.innerText);
        }
        put('product', facts.join('\n'));
        put('document_title', document.title);
      }
    }
  }
  return {url, observed_at: new Date().toISOString(), title, status: blocked ? 'blocked' : title ? 'needs_review' : 'no_heading',
    excerpts, links, blocks, visible_links: {details: detailURLs.size, next: nextURLs.size}};
}
if (typeof module !== 'undefined') module.exports = {captureWineResearch};
