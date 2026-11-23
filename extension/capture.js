// This pure function is injected only after the user presses "Capture".
// It reads the current visible product document; no fetch, network interception,
// cookies, raw DOM/HTML, storage, hidden frames, recommendations or screenshots.
function captureWineAtlasPage() {
  const trim = (s, max=450) => String(s == null ? '' : s).replace(/\s+/g, ' ').trim().slice(0,max);
  // Do not persist query parameters: they can carry sessions/tracking tokens.
  // An unexpected query disables the exact-target check instead of stripping
  // a real product variant and silently treating it as the original wine.
  const privacyUrl = (raw) => {
    try {
      const u=new URL(String(raw),location.href);
      if(u.protocol!=='https:')return null;
      return u.origin+u.pathname+(u.search?'?query_redacted=1':'');
    }catch{return null}
  };
  const labelDefs = [
    ['volume_l',/^(?:объ[её]м|volume|bottle size)$/i],
    ['alcohol_percent',/^(?:крепость|алкоголь|alcohol|abv)$/i],
    ['grapes',/^(?:сорта винограда|виноград|grapes?|variet(?:y|ies))$/i],
    ['producer',/^(?:производитель|producer|winery)$/i],
    ['region',/^(?:регион|region|appellation)$/i],
    ['country',/^(?:страна производства|страна|country)$/i],
    ['wine_style',/^(?:вино|тип вина|wine type|style)$/i],
    ['color',/^(?:цвет|характеристики цвета|цвет вина)$/i],
    ['color_intensity',/^(?:глубина цвета|интенсивность цвета)$/i],
    ['body',/^(?:насыщенность|тело вина|body)$/i],
    ['aging_potential',/^(?:потенциал хранения|потенциал выдержки|aging potential|cellaring)$/i],
    ['pairing_notes',/^(?:подходит к|сочетания|гастрономические сочетания|food pairings)$/i],
    ['aroma',/^(?:аромат|ароматы|aroma|nose)$/i],
    ['taste',/^(?:вкус|taste|palate)$/i],
    ['vintage',/^(?:винтаж|год урожая|год производства|vintage)$/i]
  ];
  const fields = {};
  const nodes = [...document.querySelectorAll(
    'main tr,main dt,main dl,main [class*="characteristic"],main [class*="property"],'+
    'main [class*="specification"],main li,article tr,article dt,article li,table tr,dl dt'
  )].slice(0,2000);
  const collect = (label, value, evidence) => {
    label=trim(label,70).replace(/:$/,'').trim();
    value=trim(value,650).replace(/^[\s:]+/,'');
    if(!value||value.length>600||value===label)return;
    for(const [field,re] of labelDefs)if(re.test(label)&&!fields[field]){
      fields[field]={value:value.slice(0,field==='taste'||field==='aroma'?450:250),
        evidence:trim(evidence,650),method:'visible_product_label'};
      break;
    }
  };
  for(const el of nodes){
    const text=trim(el.innerText||el.textContent,700);
    if(!text||text.length>650)continue;
    if(el.tagName==='DT'){
      const next=el.nextElementSibling;
      if(next)collect(el.innerText,next.innerText||next.textContent,
        trim(el.innerText,80)+': '+trim(next.innerText||next.textContent,450));
      continue;
    }
    const parts=String(el.innerText||el.textContent||'').split(/\n+/).map(x=>trim(x)).filter(Boolean);
    // Consecutive visible label-value pairs, never free text or neighboring products.
    if(parts.length===2)collect(parts[0],parts[1],text);
    const colon=text.match(/^([^:]{2,60}):\s*(.{1,600})$/s);
    if(colon)collect(colon[1],colon[2],text);
    if(el.tagName==='TR'){
      const cells=[...el.querySelectorAll('th,td')].map(c=>trim(c.innerText||c.textContent,300));
      if(cells.length===2)collect(cells[0],cells[1],text);
    }
  }
  const canonical = (()=>{const a=document.querySelector('link[rel="canonical"]');return a?.href?privacyUrl(a.href):null})();
  const rootName = trim(document.querySelector('main h1,article h1,h1')?.innerText||
    document.querySelector('meta[property="og:title"]')?.content||'',260);
  const products=[];
  const unpack=(v)=>{
    if(Array.isArray(v)){for(const x of v)unpack(x);return;}
    if(!v||typeof v!=='object')return;
    if(Array.isArray(v['@graph']))unpack(v['@graph']);
    const types=Array.isArray(v['@type'])?v['@type']:[v['@type']];
    if(!types.some(t=>String(t||'').toLowerCase().split('/').pop()==='product'))return;
    const offers=Array.isArray(v.offers)?v.offers:[v.offers];
    const output={
      '@context':'https://schema.org','@type':'Product',name:trim(v.name,260),
      description:trim(v.description,500),size:trim(v.size||v.weight,70),
      url:typeof v.url==='string'?privacyUrl(v.url):null,
      offers:offers.filter(o=>{
        if(!o||typeof o!=='object')return false;
        const types=Array.isArray(o['@type'])?o['@type']:[o['@type']];
        return types.some(t=>String(t||'').toLowerCase().split('/').pop()==='offer');
      }).slice(0,4).map(o=>({
        '@type':'Offer',url:typeof o.url==='string'?privacyUrl(o.url):null,
        priceCurrency:trim(o.priceCurrency,8),
        price:typeof o.price==='number'||typeof o.price==='string'?o.price:null,
        availability:trim(o.availability,120),
        oldPrice:o.oldPrice??null,previousPrice:o.previousPrice??null,
        originalPrice:o.originalPrice??null
      }))
    };
    if(output.name)products.push(output);
  };
  for(const script of [...document.querySelectorAll('script[type="application/ld+json"]')].slice(0,40)){
    if((script.textContent||'').length>150000)continue;
    try{unpack(JSON.parse(script.textContent));}catch{}
  }
  const mainURL=privacyUrl(location.href);
  // Prevent accidental extraction from sign-in, bot, error or checkout pages.
  const blocked=/(?:captcha|access denied|just a moment|доступ ограничен|войдите в аккаунт)/i.test(
    document.title+' '+rootName);
  const image=privacyUrl(document.querySelector('meta[property="og:image"]')?.content||'');
  return {
    source_url:mainURL,canonical_url:canonical?trim(canonical,1000):null,
    page_title:trim(document.title,260),h1:rootName,
    captured_at:new Date().toISOString(),
    fields,products:products.slice(0,4),
    image_candidate:image?{url:image,rights:'unverified_not_for_publication'}:null,
    blocked,
    extraction:{type:'manual_active_tab_visible_labels_and_jsonld',raw_html_saved:false}
  };
}
