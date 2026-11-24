'use strict';
const $=id=>document.getElementById(id);
const fmt=new Intl.NumberFormat('ru-RU');
const state={records:[],ratingRecords:{},unrated:{},snapshots:{},snapshotDate:null,researchedPhotos:{},fullDescriptions:{},sourcePairings:{},pairingLabels:{},favorites:new Set(),scope:'all'};
const options={country:'country',grape:'grapes',type:'type',pairing:'pairings'};
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cleanUrl=s=>{try{const u=new URL(s);return u.protocol==='https:'?u.href:null}catch{return null}};
const date=s=>{if(!s||!/^\d{4}-\d{2}-\d{2}$/.test(s))return '—';const a=s.split('-');return a[2]+'.'+a[1]+'.'+a[0]};
const num=x=>Number.isInteger(x)?String(x):fmt.format(x);
const money=x=>fmt.format(x)+' ₽';
function isWineStyleRating(x){
  try { return /(^|\.)winestyle\.ru$/i.test(new URL(x.source_url).hostname); }
  catch { return false; }
}
function ratingsFor(r){
  const all=(state.ratingRecords[r.id]||[]).filter(x=>x&&typeof x.source==='string'&&Number.isFinite(x.score)&&!isWineStyleRating(x)&&((x.scale===100&&x.score>=0&&x.score<=100)||(x.scale===5&&x.score>=1&&x.score<=5)));
  return all.filter(x=>x.scope==='all_vintages'||x.scope==='vintage'&&x.vintage===r.year);
}
// Scores shown by a retailer are third-party critics' publications,
// NOT customer ratings from that retailer. Vintage attribution is unverified.
const criticNames=new Set(['wine spectator','wine enthusiast','james suckling','robert parker','jancis robinson','vinous','decanter','tim atkin','falstaff','luca maroni','james halliday']);
function criticRatingsFor(r){
 const store=(r.stores||[]).find(s=>s.enrichment_status?.status==='verified'&&s.product_details?.source_url===s.url);
 const rows=store?.product_details?.ratings||[];
 const found=new Map();
 for(const x of rows){
  const name=String(x.source||'').trim().toLocaleLowerCase('en');
  if(!criticNames.has(name)||x.reported_by!=='WineStyle'||x.source_url!==store.url)continue;
  if(!Number.isFinite(x.score)||!((x.scale===100&&x.score>0&&x.score<=100)||(x.scale===20&&x.score>0&&x.score<=20)))continue;
  if(!found.has(name))found.set(name,x);
 }
 return [...found.values()];
}
function retailerVivinoFor(r){
 // Fallback only: seller quotes Vivino, but does not prove score vintage.
 const store=(r.stores||[]).find(s=>s.enrichment_status?.status==='verified'&&s.product_details?.source_url===s.url);
 const entry=store?.product_details?.ratings?.find(x=>x?.source==='Vivino'&&x.reported_by==='WineStyle'&&x.source_url===store.url&&x.scale===5&&Number.isFinite(x.score)&&x.score>=1&&x.score<=5);
 if(!entry)return null;
 return {source:'Vivino',score:entry.score,scale:5,scope:'all_vintages',
  vintage:null,ratings_count:null,source_url:store.url,source_kind:'retailer_reported_vivino',
  observed_on:entry.observed_on||store.product_details.checked_at,
  note:'Оценка Vivino указана WineStyle; год рейтинга не подтверждён'};
}
function metrics(r){
 const all=ratingsFor(r);
 const exact=all.filter(x=>x.scope==='vintage');
 const independentlyVerified=new Map();
 for(const x of exact){const key=x.source.toLocaleLowerCase('ru');if(!independentlyVerified.has(key))independentlyVerified.set(key,x)}
 const items=[...independentlyVerified.values()];
 const critics=criticRatingsFor(r);
 // Independently verified vintage scores take precedence over retailer-reported scores.
 const chosen=new Map(independentlyVerified);
 for(const x of critics){
  const key=x.source.toLocaleLowerCase('ru');
  if(!chosen.has(key))chosen.set(key,x);
 }
 const vivino=all.find(x=>x.source==='Vivino'&&x.scope==='vintage')||all.find(x=>x.source==='Vivino'&&x.scope==='all_vintages')||retailerVivinoFor(r);
 // Include Vivino at most once, including a scope-all-vintages estimate.
 if(vivino&&!chosen.has('vivino'))chosen.set('vivino',vivino);
 const scaled=[...chosen.values()].map(x=>x.scale===5?50+10*x.score:x.scale===20?5*x.score:x.score);
 const summary=scaled.length?Math.round(10*scaled.reduce((a,b)=>a+b,0)/scaled.length)/10:null;
 const exactScaled=items.map(x=>x.scale===5?50+10*x.score:x.score);
 const index=exactScaled.length?Math.round(10*exactScaled.reduce((a,b)=>a+b,0)/exactScaled.length)/10:null;
 const ranking=summary===null?null:Math.round(10*(summary-8/Math.sqrt(chosen.size)))/10;
 return {all,exact:items,index,summary,ranking,summaryCount:chosen.size,critics,vivino,count:items.length,hasUnverifiedVintage:critics.length>0||(vivino?.scope==='all_vintages')};
}

function snapshotFor(r){
 const s=r.stores?.[0],v=state.snapshots[r.id];
 if(!s||!v||!/^https:\/\/spb\.winestyle\.ru\/products\//i.test(s.url))return null;
 if(!Number.isInteger(v[0])||v[0]<100||v[0]>1000000||typeof v[1]!=='string'||!/^\d{4,6}$/.test(v[1]))return null;
 return {price:v[0],photo:'https://s2.wine.style/images_gen/'+v[1].slice(0,3)+'/'+v[1]+'/0_0_695x600.webp',source:s.url};
}
function liveOfferFor(r){
 const store=r.stores?.[0], offer=store?.live_offer, review=r.publication_review;
 if(!offer||!['exact_jsonld_product','exact_main_product_visible_price'].includes(offer.verification_method)||review?.status==='excluded')return null;
 const reviewed=review?.status==='verified';
 const manualArchive=['user_confirmed_active_browser_tab','automated_browser_batch'].includes(offer.capture_method)&&
    store?.enrichment_status?.status==='verified'&&store?.product_details?.source_url===store.url;
 if(!reviewed&&!manualArchive)return null;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(offer.observed_on||''))return null;
 const reviewedAt=reviewed?review.checked_at:store.enrichment_status.checked_at;
 if(!reviewedAt||offer.observed_on<reviewedAt || (store.price_checked_at&&offer.observed_on<store.price_checked_at))return null;
 if(!Number.isInteger(offer.price_rub)||offer.price_rub<=0)return null;
 try {
  const a=new URL(store.url),b=new URL(offer.source_url),c=new URL(reviewed?review.final_url:store.enrichment_status.source_url);
  const normalized=u=>u.hostname.toLowerCase()+decodeURIComponent(u.pathname).replace(/\/$/,'')+u.search;
  if(a.protocol!=='https:'||b.protocol!=='https:'||normalized(a)!==normalized(b)||normalized(b)!==normalized(c))return null;
 }catch{return null}
 return offer;
}
function isPublished(r){
 if(r.availability?.status==='out_of_stock'||r.publication_review?.status==='excluded')return false;
 const live=liveOfferFor(r);
 return !(live?.availability==='out_of_stock'&&live.observed_on>=(r.availability?.observed_on||'0000-00-00'));
}
function priceValue(r){
 const store=r.stores?.[0]||{},live=liveOfferFor(r),snap=snapshotFor(r);
 if(live&&(!snap||live.observed_on>=state.snapshotDate))return live.price_rub;
 return snap?.price??store.price_rub??store.reference_price_rub??null;
}
// Classify each stated dish separately: red fish is not generic fish;
// game is not generic meat; lettuce salad is not a vegetable synonym.
// Pairing categories come from exact product source data, not a semantic classifier.
function retailerDetails(r){
 const s=r.stores?.[0];
 if(!s)return null;
 const archive=s.enrichment_status?.status==='verified'&&s.product_details?.source_url===s.url?s.product_details:null;
 // Manual research is separately attributed and never overwrites the verified
 // retailer archive; the overlay fills only fields absent in that archive.
 const candidate=s.research_details;
 const sellerDetails=candidate?.source_url===s.url?.split('#')[0]&&
  ['primary_retailer_product_description','manual_verified_original_seller','automated_verified_original_seller'].includes(candidate.source_kind);
 const producerProfile=candidate?.source_kind==='producer_style_profile'&&candidate.scope==='all_vintages'&&
  candidate.producer&&cleanUrl(candidate.source_url);
 const research=(sellerDetails||producerProfile)?candidate:null;
 if(!archive)return research;
 if(!research)return archive;
 const supplemental=Object.keys(research).some(k=>
  !['source_kind','source_url','checked_at','full_name','field_checked_at'].includes(k)&&
  research[k]!=null&&research[k]!==''&&(archive[k]==null||archive[k]===''));
 const combined={...research};
 const fieldDates={...(archive.field_checked_at||{})};
 for(const [key,value] of Object.entries(archive)){
  if(value!=null&&value!=='')combined[key]=value;
  else if(!(key in combined))combined[key]=value;
 }
 for(const [key,value] of Object.entries(research.field_checked_at||{})){
  if((archive[key]==null||archive[key]==='')&&combined[key]===research[key])fieldDates[key]=value;
 }
 return {...combined,field_checked_at:fieldDates,
  supplemental_checked_at:supplemental?
   Object.values(research.field_checked_at||{}).sort().at(-1)||research.checked_at:null};
}
// Retailers use multiple spellings for the SAME grape variety. Normalize the
// filter and visible metadata without altering the archival source fields.
const grapeAliases=new Map([
 ['сира','Сира / Шираз'],['шираз','Сира / Шираз'],['сира / шираз','Сира / Шираз'],
 ['сузео','Сузао'],['сузао','Сузао'],
 ['турига франсеса/турига франка','Турига Франка'],
 ['турига франка','Турига Франка'],
 ['тинта рориз','Темпранильо / Тинта Рориш'],
 ['тинта рориш','Темпранильо / Тинта Рориш'],
 ['темпранильо','Темпранильо / Тинта Рориш'],
 ['тинто фино','Темпранильо / Тинта Рориш'],
 ['турбиана','Турбиана / Треббьяно ди Лугана'],
 ['треббьяно ди лугана','Турбиана / Треббьяно ди Лугана'],
 ['монастрель','Мурведр / Монастрель'],
 ['мурведр','Мурведр / Монастрель'],
 ['масуэло','Кариньяно / Масуэло'],
 ['кариньяно','Кариньяно / Масуэло'],
 ['красные сорта винограда',null],['другие сорта',null]
]);
function normalizeGrape(grape){
 const raw=String(grape||'').trim().replace(/\s+/g,' ');
 if(!raw)return null;
 const k=raw.toLocaleLowerCase('ru');
 return grapeAliases.has(k)?grapeAliases.get(k):raw;
}
function grapeValues(r){
 const d=retailerDetails(r),raw=r.grapes?.length?r.grapes:(d?.grapes?d.grapes.split(','):[]);
 return [...new Set(raw.map(normalizeGrape).filter(Boolean))];
}
function countryValue(r){return r.country||retailerDetails(r)?.country?.split(',')[0]?.trim()||null}
function sourcePairing(r){
 const item=state.sourcePairings[r.id],store=r.stores?.[0];
 if(!item||item.url!==store?.url||item.year!==(r.year??null)||!Array.isArray(item.codes))return null;
 if(item.codes.some(code=>!Object.hasOwn(state.pairingLabels,code)))return null;
 return item;
}
function literalPairingValues(note){
 const text=String(note||'').trim();
 if(!text)return [];
 // A prose recommendation is retained as prose, not turned into speculative categories.
 if(/[.!?](?:\s|$)/u.test(text)||/^(?:это вино|вино |составит |прекрасно |хорошо |идеально |сочетается )/iu.test(text))return [];
 const items=text.split(/[,;]/).map(s=>s.trim().replace(/\s+/g,' ')).filter(Boolean);
 if(items.some(s=>s.length>100))return [];
 return [...new Set(items.map(s=>s[0].toLocaleUpperCase('ru')+s.slice(1)))];
}
function pairingValues(r){
 const item=sourcePairing(r);
 if(item)return [...new Set(item.codes)].map(code=>state.pairingLabels[code]);
 const note=retailerDetails(r)?.pairing_notes;
 // Outside a verified icon list, use only explicitly stated labels, preserving slash aliases.
 if(note)return literalPairingValues(note);
 return [...new Set((r.pairings||[]).filter(Boolean))];
}
function pairingProse(r){
 const item=sourcePairing(r);
 if(item)return item.note||'';
 const note=retailerDetails(r)?.pairing_notes;
 return note&&!literalPairingValues(note).length?String(note).trim():'';
}
function distinct(k){return [...new Set(state.records.flatMap(r=>k==='grapes'?grapeValues(r):
  k==='country'?[countryValue(r)].filter(Boolean):k==='pairings'?pairingValues(r):
  Array.isArray(r[k])?r[k]:(r[k]?[r[k]]:[])))].sort((a,b)=>a.localeCompare(b,'ru'))}
function favoriteButton(id){const yes=state.favorites.has(id);return '<button type="button" class="save-btn'+(yes?' saved':'')+'" data-fav="'+safe(id)+'" aria-label="'+(yes?'Убрать из избранного':'Добавить в избранное')+'" aria-pressed="'+yes+'" title="Избранное">'+(yes?'♥':'♡')+'</button>'}
function typeDot(t){return {'Красное':'red','Белое':'white','Розовое':'rose','Игристое':'sparkling','Оранжевое':'orange','Портвейн':'port'}[t]||''}
function priceBlock(r){
 const store=r.stores[0]||{},snap=snapshotFor(r),live=liveOfferFor(r);
 if(live&&(!snap||live.observed_on>=state.snapshotDate)){
  const old=live.regular_price_rub>live.price_rub?' <del>'+money(live.regular_price_rub)+'</del>':'';
  const stock=live.availability==='in_stock'?' · наличие подтверждено':live.availability==='out_of_stock'?' · нет в наличии':' · наличие не подтверждено';
  return '<div class="price-main">'+money(live.price_rub)+old+'</div><div class="price-note">Проверка предложения · '+date(live.observed_on)+stock+'</div>';
 }
 if(snap)return '<div class="price-main">'+money(snap.price)+'</div><div class="price-note">Цена в архиве · '+date(state.snapshotDate)+'</div>';
 if(store.price_rub!=null&&store.price_checked_at)return '<div class="price-main">'+money(store.price_rub)+(store.regular_price_rub>store.price_rub?' <del>'+money(store.regular_price_rub)+'</del>':'')+'</div><div class="price-note">Архивное наблюдение · '+date(store.price_checked_at)+'</div>';
 if(store.reference_price_rub!=null)return '<div class="price-main">'+money(store.reference_price_rub)+(store.reference_regular_price_rub>store.reference_price_rub?' <del>'+money(store.reference_regular_price_rub)+'</del>':'')+'</div><div class="price-note">Цена на '+date(store.reference_date)+' (архив)</div>';
 return '<div class="price-main">Цена неизвестна</div><div class="price-note">Не проверена</div>';
}
function vivinoUnavailable(r){
 const u=state.unrated[r.id]||{};
 const labels={insufficient_ratings:'Мало оценок',unverified_score:'Число не подтверждено',ambiguous_product:'Не определён вариант вина',no_verified_match:'Совпадение не подтверждено'};
 return {label:labels[u.status]||'Оценка не подтверждена',url:cleanUrl(u.source_url)||'https://www.vivino.com/search/wines?q='+encodeURIComponent(r.title),reason:u.reason||''};
}

function metricRow(m,r){
 const aggregate=m.summary===null?'—':num(m.summary);
 const cv=m.vivino?num(m.vivino.score):'—';
 const unavailable=vivinoUnavailable(r);
 const detail=m.vivino?(m.vivino.source_kind==='retailer_reported_vivino'?'По данным WineStyle · год не проверен':m.vivino.scope==='all_vintages'?'Общая оценка · все урожаи':(m.vivino.ratings_count?fmt.format(m.vivino.ratings_count)+' оценок':'Оценка винтажа')):unavailable.label;
 return '<div class="rating-box">'+
 '<div class="rating-cell"><span class="rating-label">Сводный рейтинг</span><div class="rating-value">'+aggregate+'<span class="rating-unit">/ 100</span></div><span class="rating-sub">'+(m.summaryCount?m.summaryCount+' ист. · '+(m.hasUnverifiedVintage?'год оценок может отличаться':'винтаж подтверждён'):'Пока нет оценок')+'</span>'+(m.ranking!==null?'<span class="rating-sub">Индекс сортировки: '+num(m.ranking)+'</span>':'')+'</div>'+
 '<div class="rating-cell"><span class="rating-label">Vivino</span><div class="rating-value">'+cv+'<span class="rating-unit">/ 5</span></div><span class="rating-sub">'+safe(detail)+'</span></div>'+
 '</div>';
}
function ratingsDetails(r,m){
 const independent=m.all.map(x=>{
  const url=cleanUrl(x.source_url);
  const suffix=x.scope==='all_vintages'?' · все урожаи':' · '+String(x.vintage||'год не указан');
  return '<li><span>'+(url?'<a href="'+safe(url)+'" target="_blank" rel="noopener noreferrer">'+safe(x.source)+'</a>':safe(x.source))+safe(suffix)+'</span><strong>'+num(x.score)+' / '+x.scale+'</strong></li>';
 }).join('');
 const published=m.critics.map(x=>'<li><span>'+safe(x.source)+'</span><strong>'+num(x.score)+' / '+x.scale+'</strong></li>').join('');
 const un=vivinoUnavailable(r);
 const fallback=!m.vivino?'<p class="rating-hint">'+safe(un.label)+' · <a href="'+safe(un.url)+'" target="_blank" rel="noopener noreferrer">Проверить на Vivino</a></p>':m.vivino.source_kind==='retailer_reported_vivino'?'<p class="rating-hint">Vivino: '+num(m.vivino.score)+'/5, по сведениям WineStyle · винтаж не установлен · <a href="'+safe(cleanUrl(m.vivino.source_url)||'#')+'" target="_blank" rel="noopener noreferrer">Источник</a></p>':'';
 return '<details class="rating-details score-details"><summary>Оценки и источники ('+(m.all.length+m.critics.length)+')</summary>'+
 (independent?'<h4>Независимо подтверждённые</h4><ul>'+independent+'</ul>':'')+
 (published?'<h4>Оценки критиков, опубликованные WineStyle</h4><ul>'+published+'</ul><p class="rating-hint">Не являются оценками покупателей WineStyle. Первоисточники и принадлежность к винтажу отдельно не проверены.</p>':'')+
 (!independent&&!published?'<p class="rating-hint">Проверенных оценок пока нет.</p>':'')+fallback+'</details>';
}

function fullDescription(r){
 const d=retailerDetails(r),item=state.fullDescriptions[r.id],store=r.stores?.[0];
 if(item&&item.url===store?.url&&item.year===(r.year??null)&&typeof item.description==='string'&&item.description.trim())
  return {text:item.description.trim(),complete:true,observed_on:item.observed_on};
 const text=String(d?.description_excerpt||'').trim();
 return {text,complete:false,observed_on:d?.checked_at};
}
function completeSentences(text){
 // Avoid cutting on initials, decimals or incomplete final source fragments.
 return String(text||'').trim().split(/(?<=[.!?])\s+(?=[А-ЯЁA-Z«"“])/u).map(s=>s.trim()).filter(s=>/[.!?]["»”)]?$/u.test(s));
}
function concisePreview(r){
 const d=retailerDetails(r);
 if(!d)return '';
 const desc=fullDescription(r).text;
 const candidates=completeSentences(desc);
 const informative=candidates.find(s=>s.length>=35&&s.length<=155&&/вкус|аромат|нот|оттен|купаж|виноград|выдерж|сорт|свеж|слад|сух|танин/i.test(s));
 if(informative)return informative;
 const sentence=candidates.find(s=>s.length>=25&&s.length<=155);
 if(sentence)return sentence;
 const taste=String(d.taste||'').trim();
 const tastingSentence=completeSentences(taste).find(s=>s.length<=155);
 if(tastingSentence)return tastingSentence;
 if(taste&&!/[.!?]/.test(taste)&&taste.length<=135)return 'Вкус: '+taste.replace(/[;,:]+$/,'')+'.';
 // Comma-delimited tasting descriptors are independent phrases, not clipped prose.
 const tags=taste.split(',').map(s=>s.trim()).filter(Boolean);
 if(tags.length>2&&tags.every(s=>s.length<=42&&!/[.!?]/.test(s))){
  const selected=[];for(const tag of tags){if(selected.length>=5||selected.join(', ').length+tag.length>110)break;selected.push(tag)}
  if(selected.length)return 'Вкус: '+selected.join(', ')+'.';
 }
 const style=String(d.wine_style||'').trim().replace(/\s*,\s*/g,', ');
 return style?'Стиль: '+style.replace(/[.!?]+$/,'')+'.':'';
}
function stockMarkup(r,d){
 const observed=r.availability;
 const stockNote=observed?.status==='in_stock'?'Доступно к заказу':observed?.status==='out_of_stock'?'Нет в наличии':
  ['Ожидаем поступление','Нет в наличии'].includes(d?.availability_note)?d.availability_note:
  d?.availability_spb===true?'Наличие подтверждалось в СПб':d?.availability_spb===false?'Нет в наличии в СПб':'';
 const stockDate=observed?.observed_on||(d?.availability_note?(d.field_checked_at?.availability_note||d.checked_at):(d?.field_checked_at?.availability_spb||d?.checked_at));
 return stockNote?'<p class="availability-note">'+safe(stockNote)+' · '+date(stockDate)+'</p>':'';
}
function metaText(r){
 return [countryValue(r),...grapeValues(r),r.year?String(r.year):null,r.volume_l?(r.volume_l<1?Math.round(r.volume_l*1000)+' мл':fmt.format(r.volume_l)+' л'):null].filter(Boolean).join(' · ');
}
function pairingText(r){
 const pairs=pairingValues(r);return pairs.length?'Подходит к: '+pairs.join(', '):pairingProse(r)||'Сочетания не указаны';
}
// Research supplement 2026-11-24; identity-checked sources, no inferred expiry from absent dates.
const storageEvidence = {
  "2f1b26d235e4": {
    "year": 2019,
    "url": "https://spb.winestyle.ru/products/Graham-s-Late-Bottled-Vintage-LBV-2019-gift-tube.html",
    "kind": "bottling",
    "min": 2,
    "max": 3,
    "scope": "vintage",
    "source": "Slijterij Kuijpers",
    "source_url": "https://www.slijterijkuijpers.nl/a-106552376/late-bottled-vintage/graham-s-port-lbv-2019/",
    "note": "2–3 года после розлива; год розлива конкретной бутылки неизвестен.",
    "source_year": null
  },
  "c9f63273980c": {
    "year": 2018,
    "url": "https://ast.wine/catalog/product/dow_s_late_bottled_vintage_port_5608309002876_43233/",
    "kind": "window",
    "min": null,
    "max": 2031,
    "scope": "vintage",
    "source": "Premium Port Wines / Dow’s",
    "source_url": "https://www.premiumport.com/portfolio/dows/dows_late_bottled_vintage/dows_late_bottled_vintage_2018",
    "note": "Готово к употреблению; дальнейшее созревание не требуется.",
    "source_year": null
  },
  "060e3c866e44": {
    "year": 2018,
    "url": "https://ladogawine.ru/catalog/wine/kopke_leyt_bottled_vintedzh_porto_075/#",
    "kind": "window",
    "min": 2022,
    "max": 2027,
    "scope": "vintage",
    "source": "Dagens Næringsliv / Smak",
    "source_url": "https://www.dn.no/smak/vin/kopke-lbv/4-1-164095?zephr_sso_ott=BytSh1",
    "note": "",
    "source_year": null
  },
  "bdbf5d0327dc": {
    "year": 2017,
    "url": "https://spb.winestyle.ru/products/Tement-Ehrenhausen-Muschelkalk-2017-375.html",
    "kind": "window",
    "min": 2018,
    "max": 2024,
    "scope": "vintage",
    "source": "Weinfurore",
    "source_url": "https://www.weinfurore.de/sauvignon-blanc-ehrenhausen-2017-manfred-tement-suedsteiermark",
    "note": "Источник не уточняет формат 0,375 л; маленькая бутылка может стареть быстрее.",
    "source_year": null
  },
  "1fc33a9c0505": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Vina-Cobos-Felino-Chardonnay-2023.html",
    "kind": "duration",
    "min": 3,
    "max": 5,
    "scope": "vintage",
    "source": "Декантер",
    "source_url": "https://decanter.ru/product/vina-cobos-felino-chardonnay-2023-id259020",
    "note": "",
    "source_year": null
  },
  "cbc96de28176": {
    "year": 2016,
    "url": "https://spb.winestyle.ru/products/Wente-Morning-Fog-Chardonnay-2016.html",
    "kind": "window",
    "min": 2017,
    "max": 2020,
    "scope": "vintage",
    "source": "Decanter",
    "source_url": "https://www.decanter.com/wine-reviews/usa/california/wente-san-francisco-bay-livermore-morning-fog-chardonnay-14047/",
    "note": "",
    "source_year": null
  },
  "209d7a6d9fe0": {
    "year": null,
    "url": "https://spb.winestyle.ru/products/Loimer-Gluegglich.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "cuvee",
    "source": "Loimer",
    "source_url": "https://www.loimer.at/en/shop/gluegglich-nv/",
    "note": "Производитель указывает готовность к употреблению до 2028 года для текущей партии NV; без идентификации партии не применяю календарный предел.",
    "source_year": null
  },
  "91f9214b514c": {
    "year": 2013,
    "url": "https://spb.winestyle.ru/products/Huia-Pinot-Noir-2013.html",
    "kind": "window",
    "min": null,
    "max": 2022,
    "scope": "vintage",
    "source": "Wine.com / опубликованная оценка",
    "source_url": "https://www.wine.com/product/huia-pinot-noir-2013/353610",
    "note": "",
    "source_year": null
  },
  "2d98b7c07c09": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Pyramid-Scheme-Pinot-Noir-2023.html",
    "kind": "duration",
    "min": 3,
    "max": 5,
    "scope": "vintage",
    "source": "Декантер",
    "source_url": "https://spb.decanter.ru/product/pyramid-scheme-pinot-noir-2023-id270091",
    "note": "В заголовке продавца ошибка цвета, но описание и название идентифицируют красный Pinot Noir.",
    "source_year": null
  },
  "8fb6ff3a814f": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Undurraga-Sibaris-Pinot-Noir-Gran-Reserva-Leyda-Valley-DO-2023.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "style",
    "source": "Gilbert & Gaillard",
    "source_url": "https://gilbertgaillard.com/en/resultats/valle-de-san-antonio-leyda",
    "note": "Для вин долины Лейда рекомендованы первые годы; более концентрированные Pinot Noir могут выиграть от нескольких лет выдержки. Точный срок Sibaris 2023 не установлен.",
    "source_year": null
  },
  "aa6da0a65a5d": {
    "year": 2021,
    "url": "https://spb.winestyle.ru/products/Bestheim-Alsace-Grand-Cru-Schlossberg-Riesling-AOC-2021.html",
    "kind": "duration",
    "min": 5,
    "max": 10,
    "scope": "cuvee",
    "source": "Bestheim",
    "source_url": "https://www.bestheim.com/en/grand-cru-wines/10-riesling-grand-cru-schlossberg.html",
    "note": "Рекомендация производителя для кюве.",
    "source_year": null
  },
  "426bd971c45a": {
    "year": 2021,
    "url": "https://spb.winestyle.ru/products/d-Arenberg-The-Stump-Jump-White-2021.html",
    "kind": "window",
    "min": 2021,
    "max": 2026,
    "scope": "vintage",
    "source": "Perfecte Wijn",
    "source_url": "https://perfectewijn.nl/en/collections/wijnhuis-d-arenberg/products/the-stump-jump-darenberg-white-blend",
    "note": "",
    "source_year": null
  },
  "62988f645654": {
    "year": 2024,
    "url": "https://spb.winestyle.ru/products/Tesch-Unplugged-Riesling-2024.html",
    "kind": "window",
    "min": 2025,
    "max": 2029,
    "scope": "vintage",
    "source": "Lobenbergs",
    "source_url": "https://www.gute-weine.de/produkt/weingut-tesch-riesling-unplugged-2024-74193h/",
    "note": "",
    "source_year": null
  },
  "a1faf8b0af1d": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Canti-Moscato-D-Asti-DOCG-2023.html",
    "kind": "duration",
    "min": 0,
    "max": 2,
    "scope": "style",
    "source": "Caviste",
    "source_url": "https://cavisteapp.com/appellations/moscato-d-asti.html",
    "note": "Общий ориентир для Moscato d’Asti, не оценка Canti 2023.",
    "source_year": null
  },
  "46622f963eaa": {
    "year": null,
    "url": "https://spb.winestyle.ru/products/Montelliana-Prosecco-Treviso-DOC-Extra-Dry.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "style",
    "source": "Consorzio Tutela Prosecco DOC",
    "source_url": "https://www.prosecco.wine/en/five-things-you-didnt-know-about-prosecco-doc/",
    "note": "Предпочтительно пить в году, следующем за урожаем; год неизвестен.",
    "source_year": null
  },
  "5427ef8902aa": {
    "year": null,
    "url": "https://spb.winestyle.ru/products/Pitars-Prosecco-DOC.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "style",
    "source": "Consorzio Tutela Prosecco DOC",
    "source_url": "https://www.prosecco.wine/en/five-things-you-didnt-know-about-prosecco-doc/",
    "note": "Предпочтительно пить в году, следующем за урожаем; год неизвестен.",
    "source_year": null
  },
  "f97f2ccc67b8": {
    "year": null,
    "url": "https://spb.winestyle.ru/products/Grande-Alberone-Moscato-Spumante-Dolce.html",
    "kind": "duration",
    "min": 1,
    "max": 2,
    "scope": "cuvee",
    "source": "ALDI Suisse",
    "source_url": "https://www.aldi-now.ch/it/grande-alberone-moscato-spumante-dolce/333042",
    "note": "Невинтажное вино; дата производства не установлена.",
    "source_year": null
  },
  "7c836f833ee2": {
    "year": null,
    "url": "https://spb.winestyle.ru/products/Lucien-Albrecht-Brut-Cremant-d-Alsace-AOC.html",
    "kind": "duration",
    "min": 0,
    "max": 3,
    "scope": "cuvee",
    "source": "Lucien Albrecht",
    "source_url": "https://www.lucien-albrecht.com/wp-content/uploads/2021/03/Cremant-dAlsace-Lucien-Albrecht-Brut-WE_e.pdf",
    "note": "Техлист: пить сразу или хранить до трёх лет; партия NV и начало отсчёта не идентифицированы.",
    "source_year": null
  },
  "9ddeb3cfb445": {
    "year": 2011,
    "url": "https://spb.winestyle.ru/products/Church-Block-Cabernet-Shiraz-Merlot-2011.html",
    "kind": "duration",
    "min": null,
    "max": 10,
    "scope": "cuvee",
    "source": "Waitrose",
    "source_url": "https://www.waitrose.com/ecom/products/wirra-wirra-church-block-mclaren-vale/450265-63440-63441",
    "note": "Общий ориентир для Church Block, не конкретный урожай 2011.",
    "source_year": null
  },
  "b2276984217f": {
    "year": 2019,
    "url": "https://spb.winestyle.ru/products/Tenuta-Poggio-ai-Mandorli-Chianti-Classico-Gran-Selezione-DOCG-2019.html",
    "kind": "duration",
    "min": null,
    "max": 7,
    "scope": "other_vintage",
    "source": "Wine Enthusiast",
    "source_url": "https://www.wineenthusiast.com/buying-guide/poggio-ai-mandorli-2012-gran-selezione-chianti-classico/",
    "note": "Для урожая 2012 указан предел 2019. Это лишь ориентир, не оценка 2019.",
    "source_year": 2012
  },
  "9830fcbfa909": {
    "year": 2024,
    "url": "https://spb.winestyle.ru/products/Domaine-Laffitte-Rose-Cotes-de-Gascogne-IGP-2024.html",
    "kind": "duration",
    "min": 1,
    "max": 2,
    "scope": "other_vintage",
    "source": "Domaine Laffitte (техлист 2022)",
    "source_url": "https://static1.squarespace.com/static/5f341de3ca1c301eef3c4e4b/t/657b68f87ed61168f77844e8/1702586616778/ROSE%2BDomaine%2BLaffitte%2BTech%2BSheet%2B2022.pdf",
    "note": "Для 2024 отдельного срока не найдено.",
    "source_year": 2022
  },
  "0d2ee38169c9": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Mare-Magnum-The-Chocolate-Tube-Primitivo-Puglia-IGT-2023.html",
    "kind": "duration",
    "min": 3,
    "max": 4,
    "scope": "cuvee",
    "source": "Mare Magnum",
    "source_url": "https://www.terramaremagnum.com/GenerateProductPdf.aspx?url=chocolate-tube-primitivo-alberello",
    "note": "Техлист того же кюве; урожай не указан.",
    "source_year": null
  },
  "8a9950e9e3c4": {
    "year": 2013,
    "url": "https://spb.winestyle.ru/products/Capo-di-Stato-Colli-Trevigiani-IGT-2013.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "vintage",
    "source": "Vinhuset NoFra",
    "source_url": "https://vinhusetnofra.no/vin/loredan-gasparini-capo-di-stato/",
    "note": "2013: готово к употреблению, допускается ещё восемь лет хранения; дата исходной оценки не установлена.",
    "source_year": null
  },
  "de91d5c1fa5e": {
    "year": 2024,
    "url": "https://spb.winestyle.ru/products/Long-Barn-Zinfandel-2024.html",
    "kind": "duration",
    "min": 3,
    "max": 5,
    "scope": "vintage",
    "source": "Декантер",
    "source_url": "https://ivn.decanter.ru/product/long-barn-zinfandel-2023-id266724",
    "note": "На странице указан 2024, несмотря на 2023 в адресе.",
    "source_year": null
  },
  "9fb448b8f505": {
    "year": 2021,
    "url": "https://spb.winestyle.ru/products/Apollonio-Mani-del-Sud-Rosso-Salice-Salentino-DOP-2021.html",
    "kind": "duration",
    "min": 3,
    "max": 5,
    "scope": "other_vintage",
    "source": "Декантер",
    "source_url": "https://ivn.decanter.ru/product/apollonio-mani-del-sud-rosso-2020-id250774",
    "note": "Ориентир по урожаю 2020.",
    "source_year": 2020
  },
  "5b8fb4a0202e": {
    "year": 2018,
    "url": "https://spb.winestyle.ru/products/Felline-Cicala-Rose-Salento-IGT-2018.html",
    "kind": "duration",
    "min": 3,
    "max": 5,
    "scope": "other_vintage",
    "source": "Декантер",
    "source_url": "https://decanter.ru/product/felline-cicala-rose-2015-id159287",
    "note": "Ориентир по урожаю 2015.",
    "source_year": 2015
  },
  "bab581b955b0": {
    "year": 2022,
    "url": "https://spb.winestyle.ru/products/Parajes-del-Valle-Monastrell-Ecologico-Jumilla-DOP-2022.html",
    "kind": "window",
    "min": 2024,
    "max": 2025,
    "scope": "vintage",
    "source": "Decanter",
    "source_url": "https://www.decanter.com/wine-reviews/spain/murcia/parajes-del-valle-monastrell-ecologico-jumilla-2022-84357/",
    "note": "",
    "source_year": null
  },
  "bb252388600c": {
    "year": 2015,
    "url": "https://spb.winestyle.ru/products/Tedeschi-Capitel-San-Rocco-Valpolicella-Ripasso-DOC-Superiore-2015.html",
    "kind": "duration",
    "min": 12,
    "max": 15,
    "scope": "cuvee",
    "source": "Tedeschi",
    "source_url": "https://tedeschiwines.com/wp-content/uploads/2026/01/EN_Ripasso-San-Rocco.pdf",
    "note": "Общий потенциал кюве.",
    "source_year": null
  },
  "a748bd657f0a": {
    "year": 2021,
    "url": "https://spb.winestyle.ru/products/Atzei-Saragat-Cannonau-di-Sardegna-DOC-2021.html",
    "kind": "window",
    "min": null,
    "max": 2027,
    "scope": "vintage",
    "source": "Vineshop24",
    "source_url": "https://www.vineshop24.de/en/worldwide-wines/italy/sardinia/atzei-saragat-cannonau-di-sardegna-doc",
    "note": "В карточке продавца указан потенциал до 2027; сухость указана иначе, чем в каталоге.",
    "source_year": null
  },
  "2f06acc1cf43": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Hito-Ribera-Del-Duero-DO-2023.html",
    "kind": "duration",
    "min": 8,
    "max": 10,
    "scope": "vintage",
    "source": "SimpleWine",
    "source_url": "https://simplewine.ru/catalog/product/hito_2023_075_153218/",
    "note": "",
    "source_year": null
  },
  "f0c33d420f2f": {
    "year": 2024,
    "url": "https://spb.winestyle.ru/products/Marius-Peyol-Coteaux-d-Aix-en-Provence-AOC-2024.html",
    "kind": "duration",
    "min": 1,
    "max": 3,
    "scope": "other_vintage",
    "source": "Cdiscount",
    "source_url": "https://www.cdiscount.com/vin-champagne/vin-rose/marius-peyol-coteaux/f-12936-aaadv85533.html",
    "note": "Ориентир по урожаю 2021.",
    "source_year": 2021
  },
  "e5af8c73633f": {
    "year": 2018,
    "url": "https://spb.winestyle.ru/products/Miraval-Rose-Cotes-de-Provence-AOC-2018-375.html",
    "kind": "window",
    "min": 2019,
    "max": 2024,
    "scope": "vintage",
    "source": "Woodland Hills Wine Company",
    "source_url": "https://whwc.com/miraval-cotes-de-provence-rose-2018/",
    "note": "Berry Bros. & Rudd даёт более короткое окно; взята более поздняя граница. Формат 0,375 л может стареть быстрее.",
    "source_year": null
  },
  "75ea3ee23df9": {
    "year": 2020,
    "url": "https://spb.winestyle.ru/products/Chateau-La-Tour-de-L-Eveque-Petale-de-Rose-Cotes-de-Provence-AOC-2020.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "vintage",
    "source": "WineStyle (архив описания)",
    "source_url": "https://spb.winestyle.ru/products/Chateau-La-Tour-de-L-Eveque-Petale-de-Rose-Cotes-de-Provence-AOC-2020.html",
    "note": "В описании: может хорошо храниться в течение следующих 1–2 лет; дата исходной оценки не указана.",
    "source_year": null
  },
  "2b85a6978520": {
    "year": 2022,
    "url": "https://spb.winestyle.ru/products/Mezzacorona-Pinot-Grigio-Trentino-DOC-2022.html",
    "kind": "window",
    "min": 2024,
    "max": 2026,
    "scope": "vintage",
    "source": "Natalie MacLean",
    "source_url": "https://www.nataliemaclean.com/wine-reviews/mezzacorona-pinot-grigio-2022/344943",
    "note": "",
    "source_year": null
  },
  "060a331fa324": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Gaintza-Txakolina-2023.html",
    "kind": "duration",
    "min": 1,
    "max": 2,
    "scope": "style",
    "source": "Wine Champ",
    "source_url": "https://winechamp.co.uk/regions/txakoli-basque-coast/",
    "note": "Ориентир для молодого Getariako Txakolina. У того же кюве 2022 другой продавец указывает 2023–2028, поэтому точный предел 2023 не установлен.",
    "source_year": null
  },
  "5740739d992b": {
    "year": 2018,
    "url": "https://spb.winestyle.ru/products/Recanati-Yasmin-White-kosher-mevushal-2018.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "cuvee",
    "source": "Recanati Winery",
    "source_url": "https://www.recanati-winery.com/en/home-series/",
    "note": "Линейка Yasmin рассчитана на молодое вино, числовой срок не указан.",
    "source_year": null
  },
  "f32c8d6cae2b": {
    "year": 2018,
    "url": "https://spb.winestyle.ru/products/Protos-Verdejo-2018.html",
    "kind": "window",
    "min": null,
    "max": 2024,
    "scope": "vintage",
    "source": "Wine.com / опубликованная оценка",
    "source_url": "https://www.wine.com/product/protos-verdejo-2018/525768",
    "note": "",
    "source_year": null
  },
  "4bdac639abe7": {
    "year": 2020,
    "url": "https://spb.winestyle.ru/products/Taboadella-Villae-Branco-Dao-DOC-2020.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "vintage",
    "source": "Wine Enthusiast",
    "source_url": "https://www.wineenthusiast.com/buying-guide/quinta-da-taboadella-2020-villae-white-dao/",
    "note": "По обзору от 31.12.2021 вино готово к употреблению; верхняя граница не указана.",
    "source_year": null
  },
  "995b5447875b": {
    "year": 2017,
    "url": "https://spb.winestyle.ru/products/Azienda-Agricola-Ottella-Lugana-Ottella-2017.html",
    "kind": "duration",
    "min": 3,
    "max": 5,
    "scope": "other_vintage",
    "source": "WineStyle (Lugana 2024)",
    "source_url": "https://spb.winestyle.ru/products/Ottella-Lugana-DOC-2024-750.html",
    "note": "Ориентир по урожаю 2024.",
    "source_year": 2024
  },
  "321ec8a9b417": {
    "year": 2024,
    "url": "https://spb.winestyle.ru/products/Azienda-Agricola-Ottella-Le-Creete-Lugana-DOC-2024.html",
    "kind": "duration",
    "min": 5,
    "max": 8,
    "scope": "vintage",
    "source": "Декантер",
    "source_url": "https://decanter.ru/product/ottella-lugana-le-creete-2024-id263567",
    "note": "",
    "source_year": null
  },
  "5039c04e5d73": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Batasiolo-Granee-Gavi-del-Comune-di-Gavi-DOCG-2023.html",
    "kind": "duration",
    "min": 1,
    "max": 4,
    "scope": "other_vintage",
    "source": "Perfecte Wijn",
    "source_url": "https://perfectewijn.be/en/products/batasiolo-gavi-di-gavi-granee",
    "note": "Для урожая 2024 окно 2025–2028; пересчёт на 2023 — ориентир.",
    "source_year": 2024
  },
  "47bef620896d": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Chanzy-Les-Fortunes-Aligote-Bourgogne-AOC-2023.html",
    "kind": "duration",
    "min": 2,
    "max": 4,
    "scope": "cuvee",
    "source": "Domaine & Maison Chanzy",
    "source_url": "https://www.chanzy.com/en/produit/bourgogne-aligote",
    "note": "Общий срок производителя.",
    "source_year": null
  },
  "e6beca8a8172": {
    "year": 2023,
    "url": "https://spb.winestyle.ru/products/Mar-de-Frades-Albarino-Rias-Baixas-DO-2023.html",
    "kind": "window",
    "min": 2025,
    "max": 2030,
    "scope": "vintage",
    "source": "Vinous",
    "source_url": "https://vinous.com/wines/mar-de-frades-albarino/2023",
    "note": "",
    "source_year": null
  },
  "15b856b072fd": {
    "year": 2024,
    "url": "https://spb.winestyle.ru/products/Torres-Vina-Esmeralda-Rose-Catalunya-DO-2024.html",
    "kind": "duration",
    "min": 3,
    "max": 3,
    "scope": "vintage",
    "source": "edelrausch",
    "source_url": "https://www.edelrausch.de/torres-vina-esmeralda-rosado-2024",
    "note": "Потенциал хранения 3 года по продавцу; не гарантия сохранности.",
    "source_year": null
  },
  "19c9dff352b3": {
    "year": 2021,
    "url": "https://spb.winestyle.ru/products/La-Bioca-Sterma-Nebbiolo-d-Alba-DOC-Superiore-2021.html",
    "kind": "window",
    "min": 2023,
    "max": 2028,
    "scope": "vintage",
    "source": "Decanter",
    "source_url": "https://www.decanter.com/wine-reviews/italy/piedmont/la-bioca-sterma-nebbiolo-dalba-superiore-2021-73948/",
    "note": "",
    "source_year": null
  },
  "4123b553c232": {
    "year": 2024,
    "url": "https://spb.winestyle.ru/products/Lapostolle-Le-Rose-2024.html",
    "kind": "window",
    "min": null,
    "max": 2026,
    "scope": "vintage",
    "source": "Wine Access",
    "source_url": "https://www.wineaccess.com/catalog/2024-lapostolle-le-rose-chile_20009344/",
    "note": "Рекомендация пить сейчас и до 2026; другие оценки могут отличаться.",
    "source_year": null
  },
  "d41d680aacec": {
    "year": 2022,
    "url": "https://spb.winestyle.ru/products/Fattoria-Le-Pupille-Poggio-Argentato-IGT-2022.html",
    "kind": "duration",
    "min": null,
    "max": 4,
    "scope": "other_vintage",
    "source": "Grandcruwijnen",
    "source_url": "https://www.grandcruwijnen.nl/en/2022-fattoria-le-pupille-poggio-argentato",
    "note": "На странице указан урожай 2023 с окном 2024–2027. Четыре года от урожая — только ориентир для 2022.",
    "source_year": 2023
  },
  "160221740978": {
    "year": 2013,
    "url": "https://spb.winestyle.ru/products/Bodegas-Ramon-Bilbao-Crianza-Rioja-DOC-2013-1500.html",
    "kind": "note",
    "min": null,
    "max": null,
    "scope": "other_vintage",
    "source": "Perfecte Wijn",
    "source_url": "https://perfectewijn.nl/en/products/ramon-bilbao-crianza-magnum",
    "note": "Для магнума 2020 в архивной версии страницы указано окно 2026–2034; оценка меняется по версии страницы. Не переношу календарный предел на урожай 2013.",
    "source_year": 2020
  }
};
function agingFor(r,year=new Date().getFullYear()){
 const d=retailerDetails(r),store=r.stores?.[0],item=storageEvidence[r.id];
 const overlay=item&&item.url===store?.url&&item.year===(r.year??null)?item:null;
 const raw=String(d?.aging_potential||'').trim();
 let data=overlay;
 if(!data&&raw){
  const m=raw.match(/^(\d+)(?:\s*[-–—]\s*(\d+))?\s*(лет|год(?:а|ов)?)$/iu);
  data={kind:m?'duration':'note',min:m?Number(m[1]):null,max:m?Number(m[2]||m[1]):null,scope:'vintage',source:store?.name||'WineStyle',source_url:d.source_url,raw,note:'Расчёт от урожая; это не окно оптимальной зрелости.'};
 }
 if(!data)data={kind:'unknown',scope:'unknown',note:'Подтверждённый срок не найден.'};
 let end=null,start=null;
 if(data.kind==='window'){end=data.max;start=data.min;}
 if(data.kind==='duration'&&Number.isInteger(r.year)&&Number.isFinite(data.max))end=r.year+data.max;
 const status=end===null?'unknown':year>end?'past':start!==null&&year<start?'early':year===end?'last':'within';
 const approximate=['other_vintage','cuvee','style'].includes(data.scope);
 const scopeText={vintage:'Конкретный урожай',cuvee:'Ориентир для кюве',other_vintage:'Ориентир по другому урожаю',style:'Общий ориентир для стиля',unknown:'Не подтверждено'}[data.scope]||'';
 const range=data.raw||(data.kind==='duration'||data.kind==='bottling'?(data.min==null?'До '+data.max:data.min===data.max?String(data.max):data.min+'–'+data.max)+' лет'+(data.kind==='bottling'?' после розлива':''):data.kind==='window'?(start===null?'До '+end:start+'–'+end):data.kind==='unknown'?'Не установлено':'Числовой срок не установлен');
 return {...data,end,start,status,approximate,scopeText,range};
}
function agingStatus(x){
 if(x.status==='past')return (x.approximate?'Возможно за пределами ориентира':'За пределами указанного срока')+' · до '+x.end;
 if(x.status==='early')return 'До начала окна потребления · с '+x.start;
 if(x.status==='last')return (x.approximate?'Последний расчётный год':'Последний указанный год')+' · '+x.end;
 if(x.status==='within')return (x.approximate?'Ориентир до ':'Расчётный предел: ')+x.end;
 return 'Календарный предел не установлен';
}
function agingMarkup(r){
 const x=agingFor(r),url=cleanUrl(x.source_url);
 return '<section class="wine-detail-section"><h3>Потенциал хранения</h3><p><strong>'+safe(x.kind==='window'?'Окно потребления: '+x.range:x.range)+'</strong></p><p class="aging-status">'+safe(agingStatus(x))+'</p><p class="detail-note">'+safe(x.scopeText)+(x.source_year?' · источник: урожай '+x.source_year:'')+(x.note?' · '+safe(x.note):'')+(url?' · <a href="'+safe(url)+'" target="_blank" rel="noopener noreferrer">'+safe(x.source||'Источник')+'</a>':'')+'</p></section>';
}
function agingPreview(r){
 const x=agingFor(r);
 return '<p class="card-pairings card-aging">'+(x.status==='past'?'<strong>':'')+safe(x.kind==='unknown'?'Потенциал хранения не подтверждён':agingStatus(x))+(x.status==='past'?'</strong>':'')+'</p>';
}
function fullWineMarkup(r){
 const d=retailerDetails(r),s=r.stores?.[0],url=cleanUrl(s?.url),m=metrics(r),description=fullDescription(r);
 const facts=[['Стиль',d?.wine_style],['Регион',d?.region],['Крепость',d?.alcohol_percent],['Объём',d?.volume_l],['Производитель',d?.producer],['Насыщенность',d?.body]].filter(([,value])=>value!=null&&value!=='');
 const tasting=[['Вкус',d?.taste],['Аромат',d?.aroma],['Цвет',d?.color]].filter(([,value])=>value!=null&&value!=='');
 const source=cleanUrl(d?.source_url);
 const sourceLabel=d?.source_kind==='producer_style_profile'?'производителя (описание линейки, не проверка винтажа)':s?.name||'продавца';
 const paragraphs=description.text.split(/\n+/).map(x=>x.trim()).filter(Boolean).map(x=>'<p>'+safe(x)+'</p>').join('');
 const descMarkup=description.text?'<section class="wine-detail-section wine-description"><h3>Описание</h3>'+paragraphs+(!description.complete?'<p class="detail-note">В архиве доступен только сохранённый фрагмент. '+(source?'<a href="'+safe(source)+'" target="_blank" rel="noopener noreferrer">Полное описание в источнике ↗</a>':'Полный текст не подтверждён.')+'</p>':'')+'</section>':'';
 return '<div class="wine-detail-hero">'+photoMarkup(r)+'<div class="wine-detail-heading"><span class="type-tag"><i aria-hidden="true" class="type-dot '+typeDot(r.type)+'"></i>'+safe(r.type||'Вино')+'</span>'+
 '<h2 id="wine-dialog-title">'+safe(r.title)+'</h2><p class="card-meta">'+safe(metaText(r))+'</p>'+stockMarkup(r,d)+
 '<div class="wine-detail-price"><div>'+priceBlock(r)+'</div>'+favoriteButton(r.id)+(url?'<a class="store-link" href="'+safe(url)+'" target="_blank" rel="noopener noreferrer">У продавца ↗</a>':'')+'</div></div></div>'+
 metricRow(m,r)+
 (facts.length?'<section class="wine-detail-section"><h3>Характеристики</h3><div class="wine-facts">'+facts.map(([label,value])=>'<div class="wine-fact"><span>'+safe(label)+'</span><p>'+safe(value)+'</p></div>').join('')+'</div></section>':'')+
 (tasting.length?'<section class="wine-detail-section"><h3>Дегустационный профиль</h3><div class="wine-tasting">'+tasting.map(([label,value])=>'<div><h4>'+safe(label)+'</h4><p>'+safe(value)+'</p></div>').join('')+'</div></section>':'')+
 '<section class="wine-detail-section"><h3>Гастрономические сочетания</h3><p>'+safe(pairingText(r))+'</p>'+ (pairingValues(r).length&&pairingProse(r)?'<p>'+safe(pairingProse(r))+'</p>':'')+'</section>'+
 agingMarkup(r)+descMarkup+
 '<section class="wine-detail-section wine-detail-ratings"><h3>Оценки и источники</h3>'+ratingsDetails(r,m).replace('<details class="rating-details score-details">','<details class="rating-details score-details" open>')+'</section>'+
 (d?'<p class="rating-hint detail-note">Данные '+safe(sourceLabel)+' на '+date(d.checked_at)+(d.supplemental_checked_at?' · Дополнено ручной проверкой '+date(d.supplemental_checked_at):'')+(source?' · <a href="'+safe(source)+'" target="_blank" rel="noopener noreferrer">Источник</a>':'')+'</p>':'');
}
function photoMarkup(r){
 const snap=snapshotFor(r),p=r.photo||{},raw=state.researchedPhotos[r.id];
 const researched=raw&&raw.year===r.year?raw:null;
 const url=snap?.photo||cleanUrl(researched?.url)||cleanUrl(p.url);
 const source=snap?.source||cleanUrl(researched?.source_url)||cleanUrl(p.source_url);
 const backup=(snap||researched)?cleanUrl(p.url):null;
 const alt='Бутылка '+r.title+(r.year?' '+r.year:'');
 const placeholder='<div class="bottle-placeholder'+(url?' hidden-photo-placeholder':'')+'" aria-hidden="true"><span class="bottle-silhouette"></span></div>';
 const visual=url?'<button type="button" class="bottle-view" data-bottle-view aria-label="Увеличить фото: '+safe(r.title)+'">'+
  '<img class="bottle-photo" src="'+safe(url)+'"'+(backup?' data-fallback="'+safe(backup)+'"':'')+
  ' alt="'+safe(alt)+'" loading="lazy" decoding="async" referrerpolicy="no-referrer">'+placeholder+'</button>':placeholder;
 return '<div class="bottle-media">'+visual+
 (source&&url?'<a class="photo-credit" href="'+safe(source)+'" target="_blank" rel="noopener noreferrer">Фото: '+(snap?'WineStyle':researched?safe(researched.source):safe(p.source||'источник'))+'</a>':'<span class="photo-credit photo-missing">Фото не найдено</span>')+
 '</div>';
}

function card(r){
 const m=metrics(r),synopsis=concisePreview(r);
 return '<article class="wine-card" data-wine-id="'+safe(r.id)+'"><div class="card-head"><span class="type-tag"><i aria-hidden="true" class="type-dot '+typeDot(r.type)+'"></i>'+safe(r.type||'Вино')+'</span>'+favoriteButton(r.id)+'</div>'+
 '<div class="card-intro">'+photoMarkup(r)+'<div class="card-intro-copy"><h3 class="card-title"><button type="button" class="wine-title-button" data-wine-open="'+safe(r.id)+'">'+safe(r.title)+'</button></h3><p class="card-meta">'+safe(metaText(r))+'</p>'+(synopsis?'<p class="card-description">'+safe(synopsis)+'</p>':'')+'</div></div>'+
 metricRow(m,r)+agingPreview(r)+'<p class="card-pairings">'+safe(pairingText(r))+'</p>'+
 '<div class="card-bottom"><div class="price-block">'+priceBlock(r)+'</div><button type="button" class="store-link wine-open" data-wine-open="'+safe(r.id)+'">Карточка вина</button></div></article>';
}
function withinPriceRange(r,minimum,maximum){
 const min=minimum===''?null:Number(minimum),max=maximum===''?null:Number(maximum);
 if(min===null&&max===null)return true;
 const price=priceValue(r);
 if(!Number.isFinite(price)||price<=0)return false;
 if(min!==null&&Number.isFinite(min)&&price<min)return false;
 if(max!==null&&Number.isFinite(max)&&price>max)return false;
 return true;
}
function matched(r){
 if(!isPublished(r))return false;
 const term=$('search').value.trim().toLocaleLowerCase('ru');
 if(term&&!([r.title,countryValue(r),r.section,String(r.year||''),...grapeValues(r),...pairingValues(r)].join(' ').toLocaleLowerCase('ru').includes(term)))return false;
 if($('country').value&&countryValue(r)!==$('country').value)return false;
 if($('grape').value&&!grapeValues(r).includes($('grape').value))return false;
 if($('type').value&&r.type!==$('type').value)return false;
 if($('pairing').value&&!pairingValues(r).includes($('pairing').value))return false;
 if(!withinPriceRange(r,$('price-min').value,$('price-max').value))return false;
 if(state.scope==='saved'&&!state.favorites.has(r.id))return false;
 return true;
}
function sortRecords(rs,mode){
 if(mode==='rating-desc')rs.sort((a,b)=>(metrics(b).ranking??-Infinity)-(metrics(a).ranking??-Infinity)||
  (metrics(b).summary??-Infinity)-(metrics(a).summary??-Infinity)||a.title.localeCompare(b.title,'ru'));
 else if(mode==='vivino-desc')rs.sort((a,b)=>(metrics(b).vivino?.score??-1)-(metrics(a).vivino?.score??-1));
 else if(mode==='alpha')rs.sort((a,b)=>a.title.localeCompare(b.title,'ru'));
 else if(mode==='price-asc')rs.sort((a,b)=>(priceValue(a)??Infinity)-(priceValue(b)??Infinity));
 else if(mode==='price-desc')rs.sort((a,b)=>(priceValue(b)??-1)-(priceValue(a)??-1));
 else if(mode==='year-desc')rs.sort((a,b)=>(b.year??0)-(a.year??0));
 return rs;
}
function render(){
 const rs=sortRecords(state.records.filter(matched),$('sort').value);
 $('cards').innerHTML=rs.map(card).join('');
 $('empty').hidden=!!rs.length;
 $('result-count').textContent='Найдено: '+fmt.format(rs.length)+' из '+fmt.format(state.records.length);
 $('saved-count').textContent=state.records.filter(r=>state.favorites.has(r.id)).length;
}
function reset(){
 $('search').value='';$('sort').value='rating-desc';
 $('price-min').value='';$('price-max').value='';
 for(const key of Object.keys(options))$(key).value='';
 state.scope='all';document.querySelectorAll('#scope button').forEach(b=>{const yes=b.dataset.scope==='all';b.classList.toggle('active',yes);b.setAttribute('aria-pressed',String(yes))});
 render();
}
function setup(){
 for(const [id,key] of Object.entries(options)){for(const val of distinct(key))$(id).add(new Option(val,val));$(id).addEventListener('change',render)}
 $('search').addEventListener('input',render);$('sort').addEventListener('change',render);
 $('price-min').addEventListener('input',render);$('price-max').addEventListener('input',render);
 $('reset').addEventListener('click',reset);$('empty-reset').addEventListener('click',reset);
 document.querySelectorAll('#scope button').forEach(b=>b.addEventListener('click',()=>{state.scope=b.dataset.scope;document.querySelectorAll('#scope button').forEach(btn=>{const on=btn===b;btn.classList.toggle('active',on);btn.setAttribute('aria-pressed',String(on))});render()}));
 const detailDialog=$('wine-dialog');
 let lastWineTrigger=null;
 function openWine(id,trigger){
  const wine=state.records.find(r=>r.id===id);if(!wine||!detailDialog)return;
  lastWineTrigger=trigger;
  $('wine-dialog-content').innerHTML=fullWineMarkup(wine);
  detailDialog.showModal();detailDialog.scrollTop=0;
  $('wine-dialog-close').focus();
 }
 function onPhotoLoad(e){
  const img=e.target;
  if(!img.classList?.contains('bottle-photo'))return;
  // Most WineStyle images are wide canvases with a centrally positioned bottle.
  // Cropping side margins makes the bottle fill its tall display rather than
  // shrinking it into a short landscape thumbnail.
  img.classList.toggle('landscape-source',img.naturalWidth>=img.naturalHeight*.9);
 }
 function onPhotoError(e){
  const img=e.target;
  if(!img.classList?.contains('bottle-photo'))return;
  if(img.dataset.fallback&&!img.dataset.triedFallback){
    img.dataset.triedFallback='1';
    img.src=img.dataset.fallback;
    return;
  }
  img.hidden=true;
  const media=img.closest('.bottle-media');
  media?.querySelector('.bottle-placeholder')?.classList.remove('hidden-photo-placeholder');
  const button=img.closest('button[data-bottle-view]');
  if(button){button.disabled=true;button.setAttribute('aria-disabled','true')}
  const credit=media?.querySelector('.photo-credit');
  if(credit)credit.textContent='Фото недоступно';
 }
 function onWineClick(e){
  const photoButton=e.target.closest('button[data-bottle-view]');
  if(photoButton){
    const img=photoButton.querySelector('img.bottle-photo');
    if(!img||img.hidden||photoButton.disabled)return;
    const dialog=$('bottle-dialog');
    if(dialog&&typeof dialog.showModal==='function'){
      const full=$('bottle-dialog-image'),caption=$('bottle-dialog-title');
      full.src=img.currentSrc||img.src;
      full.alt=img.alt;
      caption.textContent=img.alt;
      dialog.showModal();
    }else window.open(img.currentSrc||img.src,'_blank','noopener,noreferrer');
    return;
  }
  const b=e.target.closest('button[data-fav]');
  if(!b){
    const trigger=e.target.closest('button[data-wine-open]');
    if(trigger){openWine(trigger.dataset.wineOpen,trigger);return;}
    if(e.target.closest('a,button,input,select,summary'))return;
    const tile=e.target.closest('.wine-card[data-wine-id]');
    if(tile)openWine(tile.dataset.wineId,tile.querySelector('[data-wine-open]'));
    return;
  }
  const id=b.dataset.fav;
  if(state.favorites.has(id))state.favorites.delete(id);else state.favorites.add(id);
  try{localStorage.setItem('wine-atlas-favorites',JSON.stringify([...state.favorites]))}catch{}
  if(detailDialog?.open&&b.closest('#wine-dialog')){const yes=state.favorites.has(id);b.classList.toggle('saved',yes);b.setAttribute('aria-pressed',String(yes));b.setAttribute('aria-label',yes?'Убрать из избранного':'Добавить в избранное');b.textContent=yes?'♥':'♡';}
  render();
 }
 for(const root of [$('cards'),$('wine-dialog-content')].filter(Boolean)){
  root.addEventListener('load',onPhotoLoad,true);root.addEventListener('error',onPhotoError,true);root.addEventListener('click',onWineClick);
 }
 if(detailDialog){
  $('wine-dialog-close').addEventListener('click',()=>detailDialog.close());
  detailDialog.addEventListener('click',e=>{if(e.target===detailDialog)detailDialog.close()});
  detailDialog.addEventListener('close',()=>{const id=lastWineTrigger?.dataset.wineOpen;$('wine-dialog-content').innerHTML='';if(lastWineTrigger?.isConnected)lastWineTrigger.focus();else if(id)Array.from($('cards').querySelectorAll('[data-wine-open]')).find(x=>x.dataset.wineOpen===id)?.focus();lastWineTrigger=null});
 }
 const dialog=$('bottle-dialog');
 if(dialog){
  $('bottle-dialog-close')?.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
  dialog.addEventListener('close',()=>{$('bottle-dialog-image')?.removeAttribute('src')});
 }
}
async function init(){
 try{
  const response=await fetch('./data/wines.json',{cache:'no-cache'});if(!response.ok)throw Error('Catalog HTTP '+response.status);
  const catalog=await response.json();if(!Array.isArray(catalog.records))throw Error('Invalid catalog');
  state.records=catalog.records.filter(isPublished);
  try{const response=await fetch('./data/source-pairings.json',{cache:'no-cache'});if(response.ok){const data=await response.json();if(data.version===1&&data.records&&data.labels){state.sourcePairings=data.records;state.pairingLabels=data.labels;}}}catch(e){console.warn('Source pairing categories unavailable',e)}
  try{const response=await fetch('./data/full-descriptions.json',{cache:'no-cache'});if(response.ok){const data=await response.json();if(data.version===1&&data.records&&typeof data.records==='object')state.fullDescriptions=data.records;}}catch(e){console.warn('Full descriptions unavailable',e)}
  try{
    const snapshots=await fetch('./data/verified-snapshot-2026-11-23.json',{cache:'no-cache'});
    if(snapshots.ok){
      const d=await snapshots.json();
      if(d.version===1&&d.source_archive_sha256==='6a25aaf5b393b0e19c909cef7f44532b6bd6b65972c2c1bfa052bf78fe53f26e'&&Object.keys(d.records||{}).length===114){
        state.snapshots=d.records;state.snapshotDate=d.as_of;
      }else console.warn('Invalid product snapshot manifest');
    }
  }catch(e){console.warn('Price/photo snapshot unavailable',e)}
  try{
    const extraPhotos=await fetch('./data/researched-photos-2026-11-23.json',{cache:'no-cache'});
    if(extraPhotos.ok){
      const d=await extraPhotos.json();
      if(d.version===1&&Object.keys(d.records||{}).length===8)state.researchedPhotos=d.records;
      else console.warn('Invalid supplementary photo catalog');
    }
  }catch(e){console.warn('Supplementary photos unavailable',e)}
  try{const extra=await fetch('./data/ratings.json',{cache:'no-cache'});if(extra.ok){const o=await extra.json();state.ratingRecords=o.records||{};state.unrated=o.unrated||{}}}catch(e){console.warn('Ratings unavailable',e)}
  try{const saved=JSON.parse(localStorage.getItem('wine-atlas-favorites')||'[]');if(Array.isArray(saved))state.favorites=new Set(saved.filter(s=>typeof s==='string'))}catch{}
  $('stat-total').textContent=state.records.length;
  $('stat-countries').textContent=new Set(state.records.map(r=>r.country).filter(Boolean)).size;
  $('stat-rated').textContent=state.records.filter(r=>metrics(r).vivino!==null).length;
  $('update-tag').textContent='Проверка: '+date(catalog.publication_review_snapshot?.checked_at||catalog.inventory_snapshot?.observed_on)+' · исключено '+(catalog.records.length-state.records.length)+' недоступных / несовпадающих';
  setup();render();
 }catch(e){console.error(e);$('result-count').textContent='Ошибка загрузки';$('error').hidden=false}
}
init();
