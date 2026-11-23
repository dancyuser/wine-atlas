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
  let offerEvidenceComplete=true;
  const MAX_PRODUCTS=32, MAX_OFFERS=24, MAX_SCRIPTS=40;
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
      }).slice(0,MAX_OFFERS).map(o=>({
        '@type':'Offer',url:typeof o.url==='string'?privacyUrl(o.url):null,
        priceCurrency:trim(o.priceCurrency,8),
        price:typeof o.price==='number'||typeof o.price==='string'?o.price:null,
        availability:trim(o.availability,120),
        oldPrice:o.oldPrice??null,previousPrice:o.previousPrice??null,
        originalPrice:o.originalPrice??null
      }))
    };
    if(offers.filter(o=>{
      const types=Array.isArray(o?.['@type'])?o['@type']:[o?.['@type']];
      return types.some(t=>String(t||'').toLowerCase().split('/').pop()==='offer');
    }).length>MAX_OFFERS)offerEvidenceComplete=false;
    if(output.name){
      if(products.length<MAX_PRODUCTS)products.push(output);
      else offerEvidenceComplete=false;
    }
  };
  const scripts=[...document.querySelectorAll('script[type="application/ld+json"]')];
  if(scripts.length>MAX_SCRIPTS)offerEvidenceComplete=false;
  for(const script of scripts.slice(0,MAX_SCRIPTS)){
    if((script.textContent||'').length>150000){offerEvidenceComplete=false;continue;}
    try{unpack(JSON.parse(script.textContent));}catch{offerEvidenceComplete=false;}
  }
  // WineStyle places its actual price and store inventory in the MAIN product
  // panel, not Product/Offer JSON-LD. Never read recommendations, sticky
  // teasers or generic price elements outside this product panel.
  const visibleOffer=(()=>{
    if(location.hostname.toLowerCase()!=='spb.winestyle.ru')return null;
    const root=document.querySelector('.o-productpage-info__price .m-productpage-price');
    if(!root)return null;
    const parseRub=raw=>{
      const line=trim(raw,90);
      const match=line.match(/^(\d[\d \u00a0\u202f]*)\s*(?:₽|руб\.?)$/iu);
      if(!match)return null;
      const value=Number(match[1].replace(/[\s\u00a0\u202f]/g,''));
      return Number.isInteger(value)&&value>=100&&value<=1000000?value:null;
    };
    const prices=[...root.querySelectorAll('p.price')];
    const current=prices.filter(el=>!el.classList?.contains('price--old')&&!el.classList?.contains('price--strikethrough'));
    if(!current.length||current.length>3)return null;
    const amounts=current.map(el=>parseRub(el.innerText||el.textContent));
    if(amounts.some(v=>v==null)||new Set(amounts).size!==1)return null;
    const displayed=trim(current[0].innerText||current[0].textContent,90);
    const oldRows=prices.filter(el=>el.classList?.contains('price--old')||el.classList?.contains('price--strikethrough'));
    const oldValues=oldRows.map(el=>parseRub(el.innerText||el.textContent));
    // A discount may be recorded only from a separate, explicit crossed-out
    // old-price element in the same product panel, never a generic "from" price.
    const regular=oldValues.length===1&&oldValues[0]>amounts[0]?oldValues[0]:null;
    const availableTexts=[...root.querySelectorAll('.m-productpage-price__in-stock-shops')].map(el=>
      trim(el.innerText||el.textContent,180)).filter(s=>/^в наличии\b/iu.test(s));
    const rootText=trim(root.innerText||root.textContent,1200);
    const outOfStockMatch=rootText.match(/ожидаем поступление|нет в наличии|товар отсутствует/iu);
    const stock=(availableTexts.length && !outOfStockMatch)?'in_stock':
      outOfStockMatch && !availableTexts.length?'out_of_stock':'unknown';
    const stockEvidence=stock==='in_stock'?availableTexts[0]:
      stock==='out_of_stock'?outOfStockMatch[0]:null;
    return {
      method:'visible_main_product_price',
      scope:'winestyle_primary_product_panel',
      price_rub:amounts[0],price_evidence:displayed,
      regular_price_rub:regular,
      regular_price_evidence:regular===null?null:trim(oldRows[0].innerText||oldRows[0].textContent,90),
      price_currency:'RUB',availability:stock,availability_evidence:stockEvidence
    };
  })();
  const mainURL=privacyUrl(location.href);
  // Prevent accidental extraction from sign-in, bot, error or checkout pages.
  const blocked=/(?:captcha|access denied|just a moment|доступ ограничен|войдите в аккаунт)/i.test(
    document.title+' '+rootName);
  const imageMeta=document.querySelector('meta[property="og:image"]')?.content;
  const image=imageMeta?privacyUrl(imageMeta):null;
  return {
    source_url:mainURL,canonical_url:canonical?trim(canonical,1000):null,
    page_title:trim(document.title,260),h1:rootName,
    captured_at:new Date().toISOString(),
    fields,products,visible_offer:visibleOffer,offer_evidence_complete:offerEvidenceComplete,
    image_candidate:image?{url:image,rights:'unverified_not_for_publication'}:null,
    blocked,
    extraction:{type:'active_product_tab_visible_labels_prices_and_jsonld',raw_html_saved:false}
  };
}
