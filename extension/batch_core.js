/* Pure audit helpers shared by the MV3 background worker and offline tests. */
const WineAtlasBatch = (() => {
  'use strict';
  const HOSTS = new Set(['spb.winestyle.ru','ast.wine','ladogawine.ru','vinissimo.biz']);
  const identityUrl = value => {
    try {
      const u = new URL(value);
      if (u.protocol !== 'https:' || u.username || u.password || !HOSTS.has(u.hostname.toLowerCase())) return null;
      return u.hostname.toLowerCase() + decodeURIComponent(u.pathname).replace(/\/$/,'') + u.search;
    } catch { return null; }
  };
  const words = raw => {
    const normalized = String(raw || '').normalize('NFKD').replace(/[\u0300-\u036f]/g,'')
      .toLocaleLowerCase('ru').replace(/ё/g,'е').replace(/[’]/g,"'");
    const stop = new Set(['wine','вино','port','porto','портвейн','late','bottled','vintage',
      'reserve','reserva','the','of','and','de','la','do','doc','docg','aoc','aop','igt']);
    const tokens = new Set((normalized.match(/[a-zа-я]{3,}/g)||[]).filter(t=>!stop.has(t)));
    if (/\blate\s+bottled\s+vintage\b/.test(normalized)) tokens.add('lbv');
    return tokens;
  };
  // Conservative automatic identity: every distinctive name token must be
  // represented. Matching only producer tokens can misidentify another cuvée
  // or grape from the same producer, even at an unchanged retailer URL.
  const genericTitleTokens=new Set(['aoc','aop','doc','docg','doca','igt','igp','doq','ava','wo']);
  function exactProductName(target,h1){
    const shown=words(h1);
    const candidates=[target.title,target.expected_product_name].filter(Boolean);
    for(const candidate of candidates){
      const expected=[...words(candidate)].filter(t=>!genericTitleTokens.has(t));
      if(expected.length>=2&&expected.every(t=>shown.has(t)))return true;
    }
    return false;
  }
  const volumeMls = raw => {
    const values = new Set(), normalized=String(raw||'').replace(/,/g,'.');
    const re=/(?<![\d.])(\d+(?:\.\d+)?)\s*(мл|ml|л|l)(?!\w)/gi;
    for (const m of normalized.matchAll(re)) {
      const ml=Math.round(Number(m[1])*(['мл','ml'].includes(m[2].toLowerCase())?1:1000));
      if (ml>=50 && ml<=30000) values.add(ml);
    }
    return [...values];
  };
  const years = raw => [...new Set((String(raw||'').match(/(?<!\d)(?:19\d{2}|20\d{2})(?!\d)/g)||[]).map(Number))];
  function check(target, capture) {
    if (!capture || capture.blocked) return {status:'blocked',reason:'page_blocked'};
    if (identityUrl(capture.source_url)!==identityUrl(target.url))
      return {status:'rejected',reason:'redirect_or_query_variant'};
    if (!capture.h1) return {status:'rejected',reason:'missing_main_product'};
    if (!exactProductName(target,capture.h1))
      return {status:'rejected',reason:'product_name_mismatch'};
    // Use only matching primary Product nodes where the product URL is absent
    // or equals the exact target, never unrelated recommendation nodes.
    const products=(capture.products||[]).filter(p=>p && (!p.url||identityUrl(p.url)===identityUrl(target.url)));
    const names=[capture.h1,...products.map(p=>p.name||'')];
    const allYears = [...new Set(years(names.join(' ')+' '+(capture.fields?.vintage?.value||'')))];
    if (target.year==null)
      return {status:'needs_review',reason:'catalog_vintage_unspecified'};
    if (allYears.length!==1 || allYears[0]!==target.year)
      return {status:'needs_review',reason:'missing_or_conflicting_vintage'};
    const sizes=new Set([
      ...names.flatMap(volumeMls),
      ...volumeMls(capture.fields?.volume_l?.value),
      ...products.flatMap(p=>volumeMls(p.size))
    ]);
    if (!target.volume_l||sizes.size!==1||!sizes.has(Math.round(target.volume_l*1000)))
      return {status:'needs_review',reason:'missing_or_conflicting_volume'};
    return {status:'exact',reason:'verified_url_title_vintage_volume'};
  }
  function validateTargets(value) {
    if (!value || value.schema_version!==1||!Array.isArray(value.targets)||value.targets.length<1
       ||value.targets.length>250 || value.total!==value.targets.length) throw Error('Недействительный встроенный каталог');
    const ids=new Set(), urls=new Set();
    for(const target of value.targets) {
      if(typeof target.id!=='string'||!target.id||typeof target.title!=='string'||!target.title
          ||!identityUrl(target.url)) throw Error('Некорректная запись URL или названия');
      if(ids.has(target.id)||urls.has(identityUrl(target.url)))throw Error('Дубли в исходном каталоге');
      ids.add(target.id);urls.add(identityUrl(target.url));
    }
    return value.targets;
  }
  function exportBundle(job) {
    return {
      schema_version:2,source:'wine_atlas_automated_browser_extension',
      exported_at:new Date().toISOString(),catalog_blob_sha:job.catalog_blob_sha,
      run_id:job.run_id,run_status:job.status,targets_total:job.total,
      completed:job.cursor,exact_matches:job.exact,needs_review:job.needs_review,
      errors:job.errors.length,started_at:job.started_at,finished_at:job.finished_at||null,
      observations:job.observations,failures:job.errors
    };
  }
  return {identityUrl,words,exactProductName,volumeMls,years,check,validateTargets,exportBundle};
})();
