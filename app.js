'use strict';
const $=id=>document.getElementById(id);
const fmt=new Intl.NumberFormat('ru-RU');
const state={records:[],ratingRecords:{},unrated:{},snapshots:{},snapshotDate:null,favorites:new Set(),scope:'all'};
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
 const vivino=all.find(x=>x.source==='Vivino'&&x.scope==='vintage')||all.find(x=>x.source==='Vivino'&&x.scope==='all_vintages')||null;
 // Include Vivino at most once, including a scope-all-vintages estimate.
 if(vivino&&!chosen.has('vivino'))chosen.set('vivino',vivino);
 const scaled=[...chosen.values()].map(x=>x.scale===5?50+10*x.score:x.scale===20?5*x.score:x.score);
 const summary=scaled.length?Math.round(10*scaled.reduce((a,b)=>a+b,0)/scaled.length)/10:null;
 const exactScaled=items.map(x=>x.scale===5?50+10*x.score:x.score);
 const index=exactScaled.length?Math.round(10*exactScaled.reduce((a,b)=>a+b,0)/exactScaled.length)/10:null;
 return {all,exact:items,index,summary,summaryCount:chosen.size,critics,vivino,count:items.length,hasUnverifiedVintage:critics.length>0||(vivino?.scope==='all_vintages')};
}

function snapshotFor(r){
 const s=r.stores?.[0],v=state.snapshots[r.id];
 if(!s||!v||!/^https:\/\/spb\.winestyle\.ru\/products\//i.test(s.url))return null;
 if(!Number.isInteger(v[0])||v[0]<100||v[0]>1000000||typeof v[1]!=='string'||!/^\d{4,6}$/.test(v[1]))return null;
 return {price:v[0],photo:'https://s2.wine.style/images_gen/'+v[1].slice(0,3)+'/'+v[1]+'/0_0_695x600.webp',source:s.url};
}
function priceValue(r){const s=r.stores[0]||{};return snapshotFor(r)?.price??s.price_rub??s.reference_price_rub??null}
const pairingGroups=[
  ['Рыба',/рыб|лосос|семг|суши|тунец/i],
  ['Морепродукты',/морепродукт|морски|моллюск|кревет|устриц|кальмар|омар/i],
  ['Птица',/птиц|куриц|цыплен|утк|индейк/i],
  ['Белое мясо',/белое мясо/i],
  ['Красное мясо',/красное мясо|говядин|стейк|баранин/i],
  ['Мясо',/мясо на гриле|жареное мясо|тушеное мясо|(?:^|,\s*)мясо(?:,|$)/i],
  ['Сыры',/сыр/i],['Паста',/паста|макарон|лазанья/i],
  ['Овощи',/овощ|салат|гриб/i],['Десерты',/десерт|шоколад|выпечк|торт/i],
  ['Закуски',/закуск|аперитив|канапе/i],
  ['Пряные блюда',/остр|прян|азиатск/i]
];
function retailerDetails(r){const s=r.stores?.[0];return s?.enrichment_status?.status==='verified'&&s.product_details?.source_url===s.url?s.product_details:null}
function grapeValues(r){const d=retailerDetails(r);return r.grapes?.length?r.grapes:(d?.grapes?d.grapes.split(',').map(s=>s.trim()).filter(Boolean):[])}
function countryValue(r){return r.country||retailerDetails(r)?.country?.split(',')[0]?.trim()||null}
function pairingValues(r){const note=retailerDetails(r)?.pairing_notes;
  if(!note)return r.pairings||[];
  const inferred=pairingGroups.filter(([,pattern])=>pattern.test(note)).map(([name])=>name);
  return inferred.length?inferred:(r.pairings||[])}
function distinct(k){return [...new Set(state.records.flatMap(r=>k==='grapes'?grapeValues(r):
  k==='country'?[countryValue(r)].filter(Boolean):k==='pairings'?pairingValues(r):
  Array.isArray(r[k])?r[k]:(r[k]?[r[k]]:[])))].sort((a,b)=>a.localeCompare(b,'ru'))}
function favoriteButton(id){const yes=state.favorites.has(id);return '<button type="button" class="save-btn'+(yes?' saved':'')+'" data-fav="'+safe(id)+'" aria-label="'+(yes?'Убрать из избранного':'Добавить в избранное')+'" aria-pressed="'+yes+'" title="Избранное">'+(yes?'♥':'♡')+'</button>'}
function typeDot(t){return {'Красное':'red','Белое':'white','Розовое':'rose','Игристое':'sparkling','Оранжевое':'orange','Портвейн':'port'}[t]||''}
function priceBlock(r){
 const s=r.stores[0]||{},snap=snapshotFor(r);
 if(snap)return '<div class="price-main">'+money(snap.price)+'</div><div class="price-note">Цена в архиве · '+date(state.snapshotDate)+'</div>';
 if(s.price_rub!=null&&s.price_checked_at){return '<div class="price-main">'+money(s.price_rub)+(s.regular_price_rub>s.price_rub?' <del>'+money(s.regular_price_rub)+'</del>':'')+'</div><div class="price-note">Проверено '+date(s.price_checked_at)+'</div>'}
 if(s.reference_price_rub!=null){return '<div class="price-main">'+money(s.reference_price_rub)+(s.reference_regular_price_rub>s.reference_price_rub?' <del>'+money(s.reference_regular_price_rub)+'</del>':'')+'</div><div class="price-note">Цена на '+date(s.reference_date)+' (архив)</div>'}
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
 const detail=m.vivino?(m.vivino.scope==='all_vintages'?'Общая оценка · все урожаи':(m.vivino.ratings_count?fmt.format(m.vivino.ratings_count)+' оценок':'Оценка винтажа')):unavailable.label;
 return '<div class="rating-box">'+
 '<div class="rating-cell"><span class="rating-label">Сводный рейтинг</span><div class="rating-value">'+aggregate+'<span class="rating-unit">/ 100</span></div><span class="rating-sub">'+(m.summaryCount?m.summaryCount+' ист. · '+(m.hasUnverifiedVintage?'год оценок может отличаться':'винтаж подтверждён'):'Пока нет оценок')+'</span></div>'+
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
 const fallback=!m.vivino?'<p class="rating-hint">'+safe(un.label)+' · <a href="'+safe(un.url)+'" target="_blank" rel="noopener noreferrer">Проверить на Vivino</a></p>':'';
 return '<details class="rating-details score-details"><summary>Оценки и источники ('+(m.all.length+m.critics.length)+')</summary>'+
 (independent?'<h4>Независимо подтверждённые</h4><ul>'+independent+'</ul>':'')+
 (published?'<h4>Оценки критиков, опубликованные WineStyle</h4><ul>'+published+'</ul><p class="rating-hint">Не являются оценками покупателей WineStyle. Первоисточники и принадлежность к винтажу отдельно не проверены.</p>':'')+
 (!independent&&!published?'<p class="rating-hint">Проверенных оценок пока нет.</p>':'')+fallback+'</details>';
}

function wineStyleMarkup(r){
 const s=(r.stores||[]).find(x=>x.enrichment_status?.status==='verified'&&x.product_details?.source_url===x.url);
 if(!s)return '';
 const d=s.product_details;
 const fields=[['Вкус','taste'],['Аромат','aroma'],['Сочетания','pairing_notes'],['Регион','region'],['Крепость','alcohol_percent'],['Объём','volume_l'],['Производитель','producer'],['Описание','description_excerpt']];
 const rows=fields.filter(([,k])=>d[k]!=null&&d[k]!=='').map(([label,k])=>'<li><span>'+safe(label)+'</span><strong>'+safe(String(d[k]))+'</strong></li>').join('');
 const observed=r.availability;
 const stockNote=observed?.status==='in_stock'?'Доступно к заказу':observed?.status==='out_of_stock'?'Нет в наличии':
  ['Ожидаем поступление','Нет в наличии'].includes(d.availability_note)?d.availability_note:
  d.availability_spb===true?'Наличие подтверждалось в СПб':d.availability_spb===false?'Нет в наличии в СПб':'';
 const stockDate=observed?.observed_on||(
  d.availability_note?(d.field_checked_at?.availability_note||d.checked_at):
  (d.field_checked_at?.availability_spb||d.checked_at));
 if(!rows&&!stockNote)return '';
 return '<details class="rating-details characteristics"><summary>Вкус, наличие и характеристики</summary>'+
 (stockNote?'<p class="availability-note">'+safe(stockNote)+' · '+date(stockDate)+'</p>':'')+
 (rows?'<ul>'+rows+'</ul>':'')+
 '<p class="rating-hint">Данные WineStyle на '+date(d.checked_at)+' · <a href="'+safe(s.url)+'" target="_blank" rel="noopener noreferrer">Источник</a></p></details>';
}
function photoMarkup(r){
 const snap=snapshotFor(r),p=r.photo||{};
 const url=snap?.photo||cleanUrl(p.url),source=snap?.source||cleanUrl(p.source_url);
 const backup=snap?cleanUrl(p.url):null;
 return '<div class="bottle-media">'+
 (url?'<img class="bottle-photo" src="'+safe(url)+'"'+(backup?' data-fallback="'+safe(backup)+'"':'')+' alt="Бутылка '+safe(r.title)+(r.year?' '+r.year:'')+'" loading="lazy" decoding="async" referrerpolicy="no-referrer">':'')+
 '<div class="bottle-placeholder'+(url?' hidden-photo-placeholder':'')+'" aria-hidden="true"><span class="bottle-silhouette"></span></div>'+
 (source&&url?'<a class="photo-credit" href="'+safe(source)+'" target="_blank" rel="noopener noreferrer">Фото: '+(snap?'WineStyle':safe(p.source||'источник'))+'</a>':'<span class="photo-credit photo-missing">Фото не найдено</span>')+
 '</div>';
}

function card(r){
 const m=metrics(r),s=r.stores[0]||{},url=cleanUrl(s.url);
 const details=retailerDetails(r);
 const synopsis=details?.description_excerpt?String(details.description_excerpt).slice(0,190):'';
 const meta=[countryValue(r),...grapeValues(r),r.year?String(r.year):null,r.volume_l?(r.volume_l<1?Math.round(r.volume_l*1000)+' мл':new Intl.NumberFormat('ru-RU').format(r.volume_l)+' л'):null].filter(Boolean).join(' · ');
 const sourcePairings=pairingValues(r);
 const pairs=sourcePairings.length?'Подходит к: '+sourcePairings.join(', '):'Сочетания не указаны';
 return '<article class="wine-card"><div class="card-head"><span class="type-tag"><i aria-hidden="true" class="type-dot '+typeDot(r.type)+'"></i>'+safe(r.type||'Вино')+'</span>'+favoriteButton(r.id)+'</div>'+
 '<div class="card-intro">'+photoMarkup(r)+'<div class="card-intro-copy"><h3 class="card-title">'+safe(r.title)+'</h3><p class="card-meta">'+safe(meta)+'</p>'+(synopsis?'<p class="card-description">'+safe(synopsis)+(details.description_excerpt.length>190?'…':'')+'</p>':'')+'</div></div>'+
 metricRow(m,r)+ratingsDetails(r,m)+wineStyleMarkup(r)+'<p class="card-pairings">'+safe(pairs)+'</p>'+
 '<div class="card-bottom"><div class="price-block">'+priceBlock(r)+'</div>'+(url?'<a class="store-link" href="'+safe(url)+'" target="_blank" rel="noopener noreferrer">Карточка вина ↗</a>':'')+'</div></article>';
}

function matched(r){
 if(r.availability?.status==='out_of_stock')return false;
 const term=$('search').value.trim().toLocaleLowerCase('ru');
 if(term&&!([r.title,countryValue(r),r.section,String(r.year||''),...grapeValues(r),...pairingValues(r)].join(' ').toLocaleLowerCase('ru').includes(term)))return false;
 if($('country').value&&countryValue(r)!==$('country').value)return false;
 if($('grape').value&&!grapeValues(r).includes($('grape').value))return false;
 if($('type').value&&r.type!==$('type').value)return false;
 if($('pairing').value&&!pairingValues(r).includes($('pairing').value))return false;
 if(state.scope==='saved'&&!state.favorites.has(r.id))return false;
 return true;
}
function render(){
 const rs=state.records.filter(matched),mode=$('sort').value;
 if(mode==='rating-desc')rs.sort((a,b)=>(metrics(b).summary??-1)-(metrics(a).summary??-1)||a.title.localeCompare(b.title,'ru'));
 else if(mode==='vivino-desc')rs.sort((a,b)=>(metrics(b).vivino?.score??-1)-(metrics(a).vivino?.score??-1));
 else if(mode==='alpha')rs.sort((a,b)=>a.title.localeCompare(b.title,'ru'));
 else if(mode==='price-asc')rs.sort((a,b)=>(priceValue(a)??Infinity)-(priceValue(b)??Infinity));
 else if(mode==='price-desc')rs.sort((a,b)=>(priceValue(b)??-1)-(priceValue(a)??-1));
 else if(mode==='year-desc')rs.sort((a,b)=>(b.year??0)-(a.year??0));
 else { /* default: preserve Google Docs source order */ }
 $('cards').innerHTML=rs.map(card).join('');
 $('empty').hidden=!!rs.length;
 $('result-count').textContent='Найдено: '+fmt.format(rs.length)+' из '+fmt.format(state.records.length);
 $('saved-count').textContent=state.records.filter(r=>state.favorites.has(r.id)).length;
}
function reset(){
 $('search').value='';$('sort').value='recommended';
 for(const key of Object.keys(options))$(key).value='';
 state.scope='all';document.querySelectorAll('#scope button').forEach(b=>{const yes=b.dataset.scope==='all';b.classList.toggle('active',yes);b.setAttribute('aria-pressed',String(yes))});
 render();
}
function setup(){
 for(const [id,key] of Object.entries(options)){for(const val of distinct(key))$(id).add(new Option(val,val));$(id).addEventListener('change',render)}
 $('search').addEventListener('input',render);$('sort').addEventListener('change',render);
 $('reset').addEventListener('click',reset);$('empty-reset').addEventListener('click',reset);
 document.querySelectorAll('#scope button').forEach(b=>b.addEventListener('click',()=>{state.scope=b.dataset.scope;document.querySelectorAll('#scope button').forEach(btn=>{const on=btn===b;btn.classList.toggle('active',on);btn.setAttribute('aria-pressed',String(on))});render()}));
 $('cards').addEventListener('error',e=>{
  const img=e.target;
  if(!img.classList?.contains('bottle-photo'))return;
  if(img.dataset.fallback&&!img.dataset.triedFallback){
    img.dataset.triedFallback='1';
    img.src=img.dataset.fallback;
    return;
  }
  img.hidden=true;
  img.parentElement.querySelector('.bottle-placeholder')?.classList.remove('hidden-photo-placeholder');
  const credit=img.parentElement.querySelector('.photo-credit');
  if(credit)credit.textContent='Фото недоступно';
 },true);
 $('cards').addEventListener('click',e=>{const b=e.target.closest('button[data-fav]');if(!b)return;const id=b.dataset.fav;if(state.favorites.has(id))state.favorites.delete(id);else state.favorites.add(id);try{localStorage.setItem('wine-atlas-favorites',JSON.stringify([...state.favorites]))}catch{}render()});
}
async function init(){
 try{
  const response=await fetch('./data/wines.json',{cache:'no-cache'});if(!response.ok)throw Error('Catalog HTTP '+response.status);
  const catalog=await response.json();if(!Array.isArray(catalog.records))throw Error('Invalid catalog');
  state.records=catalog.records.filter(r=>r.availability?.status!=='out_of_stock');
  try{
    const snapshots=await fetch('./data/verified-snapshot-2026-11-23.json',{cache:'no-cache'});
    if(snapshots.ok){
      const d=await snapshots.json();
      if(d.version===1&&d.source_archive_sha256==='6a25aaf5b393b0e19c909cef7f44532b6bd6b65972c2c1bfa052bf78fe53f26e'&&Object.keys(d.records||{}).length===116){
        state.snapshots=d.records;state.snapshotDate=d.as_of;
      }else console.warn('Invalid product snapshot manifest');
    }
  }catch(e){console.warn('Price/photo snapshot unavailable',e)}
  try{const extra=await fetch('./data/ratings.json',{cache:'no-cache'});if(extra.ok){const o=await extra.json();state.ratingRecords=o.records||{};state.unrated=o.unrated||{}}}catch(e){console.warn('Ratings unavailable',e)}
  try{const saved=JSON.parse(localStorage.getItem('wine-atlas-favorites')||'[]');if(Array.isArray(saved))state.favorites=new Set(saved.filter(s=>typeof s==='string'))}catch{}
  $('stat-total').textContent=state.records.length;
  $('stat-countries').textContent=new Set(state.records.map(r=>r.country).filter(Boolean)).size;
  $('stat-rated').textContent=state.records.filter(r=>metrics(r).vivino!==null).length;
  $('update-tag').textContent='Наличие: '+date(catalog.inventory_snapshot?.observed_on)+' · исключено '+(catalog.records.length-state.records.length)+' недоступных';
  setup();render();
 }catch(e){console.error(e);$('result-count').textContent='Ошибка загрузки';$('error').hidden=false}
}
init();
