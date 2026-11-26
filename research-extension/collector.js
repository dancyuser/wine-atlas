/* Runs in an explicitly chosen browser tab. All extracted claims need review. */
'use strict';
function captureWineResearch(lookup) {
  const queryMode = lookup?.role === 'query';
  const cleanUrl = value => {
    try {
      const u = new URL(value, location.href);
      if (u.protocol !== 'https:' || u.username || u.password) return null;
      for (const key of [...u.searchParams.keys()]) {
        const page = /^(?:page|pagen_\d+)$/i.test(key) && /^\d+$/.test(u.searchParams.get(key));
        const query = queryMode && /^(?:q|query|search|text|searchText)$/i.test(key);
        if (!page && !query) u.searchParams.delete(key);
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
  const sucklingNote = host === 'jamessuckling.com' && /^\/tasting-notes\/\d+\//.test(path);
  const noteTitle = sucklingNote ? [...document.querySelectorAll('h1')].find(
    heading => /\b(?:19|20)\d{2}\b/.test(heading.innerText))?.innerText : null;
  const exactTitle = noteTitle?.trim().slice(0, 500) || title;
  const blocked = /captcha|cloudflare ray id|access denied|доступ запрещ[её]н|подтвердите,? что вы не робот|verify you are human|sign in to continue|subscribe to read|выполнение проверки безопасности|пожалуйста, подождите, пока ваш запрос будет проверен/i.test(body.slice(0, 5000)) ||
    /^(?:403\s+)?Forbidden$/i.test(title);
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
    'joiastore.ru': /^\/product\/[^/]+\/?$/,
    'sabonis.ru': /^\/productDetail\/[^/]+\/?$/i,
    'vinissimo.biz': /^\/catalog\/wine\/[^/]+-\d+\/?$/,
    'vinous.com': /^\/wines\/(?!lists(?:\/|$))[^/]+(?:\/\d{4})?\/?$/,
    'lucamaroni.it': /^\/vini\/\d+-[^/]+\/?$/,
    'kenswineguide.com': /^\/wine_review\/[^/]+\/?$/,
    'jancisrobinson.com': /^\/tastings\/\d+\/?$/
  };
  const pagination = u => {
    const route = u.pathname.match(/\/page(?:\/)?(\d+)(?=\/|$)/i);
    const query = [...u.searchParams.entries()].find(([key]) => /^(?:page|pagen_\d+)$/i.test(key));
    return {section: u.pathname.replace(/\/page(?:\/)?\d+(?=\/|$)/i, '').replace(/\/$/, ''),
      page: Number(route?.[1] || query?.[1] || 1)};
  };
  const here = pagination(new URL(url || location.href));
  const linkScope = queryMode ? document.querySelector('main, [role="main"]') || document : document;
  if (!blocked) for (const a of linkScope.querySelectorAll('a[href]')) {
    let href = cleanUrl(a.href);
    const label = (a.innerText || a.querySelector('img')?.alt || a.title || '').trim().slice(0, 200);
    if (!href || !label || href === url || new URL(href).hostname !== location.hostname) continue;
    const p = new URL(href);
    const candidate = pagination(p);
    const sameQuery = !queryMode || ['q', 'query', 'search', 'text', 'searchText'].every(
      key => p.searchParams.get(key) === new URL(url).searchParams.get(key));
    const next = sameQuery && (a.rel === 'next' || (candidate.section === here.section && candidate.page === here.page + 1));
    const detail = (detailPaths[host] || /\/(?:wines?|weine|wine-reviews|tasting-notes|product(?:s|detail)?|item|detail|reviews?)\/.+/i).test(p.pathname);
    if (queryMode && !next && detail) {
      p.search = '';
      href = p.href;
    }
    const seen = next ? nextURLs : detailURLs;
    if ((!next && !detail) || seen.has(href)) continue;
    seen.add(href);
    if (next || seen.size <= 150) links.push({url: href, label, kind: next ? 'next' : 'detail'});
  }
  // Capture small, attributable blocks used by the offline parser. Read rendered
  // text only: metadata prices on these sites can belong to another region.
  const blocks = {};
  if (!blocked) {
    const put = (key, value, limit = 7000) => {
      if (!value) return;
      const text = value.trim();
      blocks[key] = text.slice(0, limit);
      if (key === 'review' && text.length > limit) blocks.review_truncated = true;
    };
    const publicArticle = (
      (host === 'jamessuckling.com' && path.startsWith('/wine-tasting-reports/')) ||
      (host === 'content.robertparker.com' && path.startsWith('/best-wines-2019-mark-squires')) ||
      (host === 'timatkin.com' && path.startsWith('/score-ranges/')) ||
      (host === 'billing.vinous.com' && path.startsWith('/articles/vinous-top-100-wines-of-')) ||
      (host === 'iwsc.net' && path.startsWith('/news/wine/results-revealed-iwsc-judging-in-conegliano-valdobbiadene')) ||
      (host === 'decanter.com' && path.includes('/top-20-value-golds-best-wines-under-15-from-dwwa-2024-531852')) ||
      (host === 'wineandspiritsmagazine.com' && path.startsWith('/the-short-list/great-rioja-for-under-25')) ||
      (host === 'jancisrobinson.com' && path.startsWith('/articles/grattamacco-2022-bolgheri-rosso'))
    );
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
      put('review', facts.join('\n'), 24000);
    } else if (sucklingNote && noteTitle) {
      put('review', body.split(/\n(?:Related wines|Similar wines|You may also like)\b/i)[0]);
    } else if (publicArticle) {
      const index = lines.indexOf(title);
      put('review', (index >= 0 ? lines.slice(index).join('\n') : body)
        .split(/\n(?:Related Articles|You may also like)\b/i)[0], 32000);
    } else if (host === 'results.concoursmondial.com' && /^\/(?:fr\/resultats|en\/results)\b/.test(path)) {
      const medalLine = (heading, label) => {
        if (!heading || !/\b(?:19|20)\d{2}$/.test(heading) || heading.length > 160) return '';
        const medal = label?.match(/(?:Grande )?Médaille d['’](?:Or|Argent)|(?:Grand )?Gold Medal|Silver Medal/i)?.[0];
        return medal ? heading + '\t' + medal : '';
      };
      const cards = [...document.querySelectorAll('.card-product')];
      const awards = cards.length ? cards.map(card => medalLine(
        card.querySelector('.card-title')?.innerText?.trim(),
        card.querySelector('.medal-card img')?.alt
      )) : lines.map((heading, i) => medalLine(heading, lines[i + 1]));
      put('medal_leads', [...new Set(awards.filter(Boolean))].join('\n'));
    } else if ((host === 'lucamaroni.it' || host === 'kenswineguide.com') && detailPaths[host].test(path)) {
      put('review', (document.querySelector('main')?.innerText || body).split(/\n(?:Other Vintages|Altre Annate)\b/i)[0]);
      put('document_title', document.title);
    } else if (/^(?:decanter\.com|results\.decanter\.com|iwsc\.net|jamessuckling\.com|jancisrobinson\.com)$/.test(host) &&
      /(?:\/tastings\/|\/tasting-notes\/|\/detail\/|\/wine-reviews\/(?!search\/)[^/]+\/.*\d)/.test(path)) {
      const index = lines.indexOf(title);
      const fallback = index >= 0 ? lines.slice(index).join('\n') : '';
      put('review', (document.querySelector('main article, article, main')?.innerText || fallback)
        .split(/Related wines|Similar wines|You may also like/i)[0]);
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
    } else if (host === 'joiastore.ru' && detailPaths[host].test(path)) {
      const card = document.querySelector('.product.js__product-card');
      const city = document.querySelector('header button.header__city')?.innerText?.trim();
      if (/^(?:Санкт-Петербург|Москва)$/.test(city)) put('city', city);
      if (card) {
        const facts = (card.innerText || '').split(/\n[ \t]*(?:Рейтинги и награды|Описание|Рекомендуем)(?=\s|$)/i)[0];
        put('product', facts);
        put('offer_price', card.querySelector('.product__price-box')?.innerText);
        const selected = card.querySelector('input[name="milezim"]:checked + label');
        if (selected) put('selected_variant', selected.innerText);
      }
      put('document_title', document.title);
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
  const hasContent = title || blocks.review || blocks.medal_leads;
  if (queryMode) {
    const missing = /ничего не найдено|ничего не нашли|не найдено товаров|товары не найдены|нашли 0 товар|найдено 0 товар|no results found|(?:^|\n)[ \t]*0[ \t\u00a0]+товаров(?=\s|$)/mi.test(body);
    const searchHeading = /результат[ы ]*поиска|найден[оы] по запросу|нашли по запросу|найдено\s+\d+\s+товар|search results/i.test(
      [title, document.title, (linkScope.innerText || body).slice(0, 4000)].join('\n'));
    const input = document.querySelector('input[name="q"]');
    const echoed = input?.value?.trim().toLowerCase() === (lookup.term || lookup.title).toLowerCase();
    const status = blocked ? 'blocked' : missing ? 'no_results' : searchHeading || (echoed && detailURLs.size) ? 'needs_review' : 'search_unverified';
    return {url, observed_at: new Date().toISOString(), title, status, links: status === 'needs_review' ? links : [],
      blocks: {}, excerpts: [], visible_links: {details: detailURLs.size, next: nextURLs.size}};
  }
  return {url, observed_at: new Date().toISOString(), title: exactTitle, status: blocked ? 'blocked' : hasContent ? 'needs_review' : 'no_heading',
    excerpts, links, blocks, visible_links: {details: detailURLs.size, next: nextURLs.size}};
}
if (typeof module !== 'undefined') module.exports = {captureWineResearch};
