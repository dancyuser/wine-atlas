'use strict';
const $=id=>document.getElementById(id);
const fmt=new Intl.NumberFormat('ru-RU');
const state={records:[],ratingRecords:{},unrated:{},snapshots:{},snapshotDate:null,researchedPhotos:{},fullDescriptions:{},favorites:new Set(),scope:'all'};
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
const pairingRules=[
 ['Красная рыба',/лосос|с[её]мг|форел|горбуш|красн(?:ая|ой|ую) рыб/i],
 ['Голубая рыба',/голубая рыба/i],
 ['Суши и сашими',/суши|сашими/i],
 ['Рыба',/рыб|тунец|лещ|барабульк|морск.*окун|сибас/i],
 ['Морепродукты',/морепродукт|дар(?:ы|ов) моря|моллюск|кревет|устриц|кальмар|омар|лобстер|мидии|лангуст|гребешк/i],
 ['Дичь',/дичь|мясо диких животн|оленин|кабанин/i],
 ['Белое мясо',/белое мясо/i],
 ['Красное мясо',/красное мясо|говядин|баранин|ягнятин|телятин|стейк|ростбиф/i],
 ['Птица',/птиц|куриц|цыплен|утк|индейк|цесарк/i],
 ['Мясо',/мясо|свинин|ветчин|прошутто|салями|колбасн|котлет|шницел|жаркое/i],
 ['Выдержанные сыры',/выдержан.*сыр|зрел.*сыр/i],
 ['Сыры с плесенью',/голуб(?:ой|ые) сыр|сыр.*плесен/i],
 ['Мягкие сыры',/мягк.*сыр|сливочн.*сыр/i],
 ['Твёрдые сыры',/тверд.*сыр|твёрд.*сыр/i],
 ['Козий сыр',/козий сыр/i],
 ['Сыры',/сыр/i],
 ['Ризотто',/ризотто/i],
 ['Паста',/паст|макарон|лазан|лапш/i],
 ['Грибы',/гриб/i],
 ['Салаты',/салат/i],
 ['Овощи',/овощ|вегетарианск|картофел/i],
 ['Фрукты',/фрукт/i],
 ['Десерты',/десерт|шоколад|выпечк|торт|пирог|суфле|сорбет|кулич/i],
 ['Супы',/суп|первые блюда/i],
 ['Закуски',/закуск|тапас|канапе|паштет|фуа-гра/i],
 ['Аперитив',/аперитив/i],
 ['Пряные блюда',/остр|прян|карри|азиатск|тайск|индийск|марокканск/i]
];
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
function pairingValues(r){
 const note=retailerDetails(r)?.pairing_notes;
 if(!note)return r.pairings||[];
 const found=new Set();
 for(const item of String(note).split(/[;,]/).flatMap(s=>s.split(/\s+(?:и|или)\s+|[/／]/)).map(s=>s.trim()).filter(Boolean)){
  const match=pairingRules.find(([,pattern])=>pattern.test(item));
  if(match)found.add(match[0]);
 }
 return found.size?[...found]:(r.pairings||[]);
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
 const pairs=pairingValues(r);return pairs.length?'Подходит к: '+pairs.join(', '):'Сочетания не указаны';
}
function fullWineMarkup(r){
 const d=retailerDetails(r),s=r.stores?.[0],url=cleanUrl(s?.url),m=metrics(r),description=fullDescription(r);
 const facts=[['Стиль',d?.wine_style],['Регион',d?.region],['Крепость',d?.alcohol_percent],['Объём',d?.volume_l],['Производитель',d?.producer],['Насыщенность',d?.body],['Потенциал хранения',d?.aging_potential]].filter(([,value])=>value!=null&&value!=='');
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
 '<section class="wine-detail-section"><h3>Гастрономические сочетания</h3><p>'+safe(pairingText(r))+'</p>'+ (d?.pairing_notes?'<p class="detail-note">'+safe(d.pairing_notes)+'</p>':'')+'</section>'+
 descMarkup+
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
 metricRow(m,r)+'<p class="card-pairings">'+safe(pairingText(r))+'</p>'+
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
