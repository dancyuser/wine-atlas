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
  if (!blocked) for (const a of document.querySelectorAll('a[href]')) {
    const href = cleanUrl(a.href), label = (a.innerText || a.querySelector('img')?.alt || '').trim().slice(0, 200);
    if (!href || !label || href === url || new URL(href).hostname !== location.hostname) continue;
    const p = new URL(href);
    const next = a.rel === 'next' || (/^(?:next|следующая|weiter)$/i.test(label) && /page|pagen/i.test(p.search));
    const detail = host === 'wineenthusiast.com' ? /^\/buying-guide\/[^/]+\/?$/.test(p.pathname) :
      host === 'falstaff.com' ? /^\/[^/]+\/(?:wines|weine)\/[^/]+\/?$/.test(p.pathname) :
      /\/(?:wines?|weine|wine-reviews|tasting-notes|product(?:s|detail)?|item|detail|reviews?)\/.+|\/catalog\/wine\/[^/]+-\d+/i.test(p.pathname);
    if ((next || detail) && !links.some(x => x.url === href)) links.push({url: href, label, kind:next?'next':'detail'});
    if (links.length >= 150) break;
  }
  // Capture small, attributable blocks used by the offline parser. Read rendered
  // text only: metadata prices on these sites can belong to another region.
  const blocks = {};
  if (!blocked) {
    const put = (key, value) => { if (value) blocks[key] = value.trim().slice(0, 7000); };
    if (host === 'wineenthusiast.com' && path.startsWith('/buying-guide/')) {
      put('review', (document.querySelector('#review-wrapper, .review-wrapper, main')?.innerText || body).split(/What Is Blind Tasting\?/i)[0]);
    } else if (/falstaff\.com$/.test(host) && /\/(?:wines|weine)\/.+/.test(path)) {
      put('producer', document.querySelector('main h2')?.innerText);
      put('review', (document.querySelector('main')?.innerText || body).split(/Other Vintages|Andere Jahrgänge/i)[0]);
    } else if (host === 'vinous.com' && path.startsWith('/wines/')) {
      put('review', (document.querySelector('main')?.innerText || body).split(/Similar Wines|Related Articles/i)[0]);
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
    }
  }
  return {url, observed_at: new Date().toISOString(), title, status: blocked ? 'blocked' : title ? 'needs_review' : 'no_heading', excerpts, links, blocks};
}
if (typeof module !== 'undefined') module.exports = {captureWineResearch};
