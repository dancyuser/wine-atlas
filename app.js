'use strict';
const $=id=>document.getElementById(id);
const fmt=new Intl.NumberFormat('ru-RU');
const state={records:[],ratingRecords:{},favorites:new Set(),scope:'all'};
const options={country:'country',grape:'grapes',type:'type',pairing:'pairings'};
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cleanUrl=s=>{try{const u=new URL(s);return u.protocol==='https:'?u.href:null}catch{return null}};
const date=s=>{if(!s||!/^\d{4}-\d{2}-\d{2}$/.test(s))return '—';const a=s.split('-');return a[2]+'.'+a[1]+'.'+a[0]};
const num=x=>Number.isInteger(x)?String(x):fmt.format(x);
const money=x=>fmt.format(x)+' ₽';
function ratingsFor(r){
  const all=(state.ratingRecords[r.id]||[]).filter(x=>x&&typeof x.source==='string'&&Number.isFinite(x.score)&&((x.scale===100&&x.score>=0&&x.score<=100)||(x.scale===5&&x.score>=1&&x.score<=5)));
  return all.filter(x=>x.scope==='all_vintages'||x.scope==='vintage'&&x.vintage===r.year);
}
function metrics(r){
  const all=ratingsFor(r);
  const exact=all.filter(x=>x.scope==='vintage');
  const once=new Map();
  for(const x of exact){const key=x.source.toLocaleLowerCase('ru');if(!once.has(key))once.set(key,x)}
  const items=[...once.values()];
  const scaled=items.map(x=>x.scale===5?50+10*x.score:x.score);
  const vivino=all.find(x=>x.source==='Vivino'&&x.scope==='vintage')||all.find(x=>x.source==='Vivino'&&x.scope==='all_vintages')||null;
  const avg=scaled.length?Math.round(10*scaled.reduce((a,b)=>a+b,0)/scaled.length)/10:null;
  return {all,exact:items,index:avg,vivino,count:items.length};
}
function priceValue(r){const s=r.stores[0]||{};return s.price_rub??s.reference_price_rub??null}
function distinct(k){return [...new Set(state.records.flatMap(r=>Array.isArray(r[k])?r[k]:(r[k]?[r[k]]:[])))].sort((a,b)=>a.localeCompare(b,'ru'))}
function favoriteButton(id){const yes=state.favorites.has(id);return '<button type="button" class="save-btn'+(yes?' saved':'')+'" data-fav="'+safe(id)+'" aria-label="'+(yes?'Убрать из избранного':'Добавить в избранное')+'" aria-pressed="'+yes+'" title="Избранное">'+(yes?'♥':'♡')+'</button>'}
function typeDot(t){return {'Красное':'red','Белое':'white','Розовое':'rose','Игристое':'sparkling','Оранжевое':'orange','Портвейн':'port'}[t]||''}
function priceBlock(r){
 const s=r.stores[0]||{};
 if(s.price_rub!=null&&s.price_checked_at){return '<div class="price-main">'+money(s.price_rub)+(s.regular_price_rub>s.price_rub?' <del>'+money(s.regular_price_rub)+'</del>':'')+'</div><div class="price-note">Проверено '+date(s.price_checked_at)+'</div>'}
 if(s.reference_price_rub!=null){return '<div class="price-main">'+money(s.reference_price_rub)+(s.reference_regular_price_rub>s.reference_price_rub?' <del>'+money(s.reference_regular_price_rub)+'</del>':'')+'</div><div class="price-note">Цена на '+date(s.reference_date)+' (архив)</div>'}
 return '<div class="price-main">Цена неизвестна</div><div class="price-note">Не проверена</div>';
}
function metricRow(m,r){
 const aggregate=m.index===null?'—':num(m.index);
 const cv=m.vivino?num(m.vivino.score):'—';
 const detail=m.vivino?(m.vivino.scope==='all_vintages'?'Все урожаи; вне индекса':(m.vivino.ratings_count?fmt.format(m.vivino.ratings_count)+' оценок':'Год подтверждён')):'Не проверено · поиск по Vivino';
 return '<div class="rating-box"><div class="rating-cell"><span class="rating-label">Общий индекс</span><div class="rating-value">'+aggregate+'<span class="rating-unit">/ 100</span></div><span class="rating-sub">'+(m.count?m.count+' ист. · расчётный':'Недостаточно данных')+'</span></div><div class="rating-cell"><span class="rating-label">Vivino</span><div class="rating-value">'+cv+'<span class="rating-unit">/ 5</span></div><span class="rating-sub">'+(m.vivino?safe(detail):'<a href="https://www.vivino.com/search/wines?q='+encodeURIComponent(r.title)+'" target="_blank" rel="noopener noreferrer">Найти на Vivino ↗</a>')+'</span></div></div>';
}
function ratingsDetails(r,m){
 const list=m.all.map(x=>{
   const url=cleanUrl(x.source_url);
   const label=safe(x.source);
   const title=url?'<a href="'+safe(url)+'" target="_blank" rel="noopener noreferrer">'+label+'</a>':label;
   const extra=x.scope==='all_vintages'?' (все урожаи)':'';
   return '<li><span>'+title+safe(extra)+'</span><strong>'+num(x.score)+' / '+x.scale+'</strong></li>';
 }).join('');
 const fallback=!m.vivino?'<li><span><a target="_blank" rel="noopener noreferrer" href="https://www.vivino.com/search/wines?q='+encodeURIComponent(r.title)+'">Поиск на Vivino</a></span><span>Без подтверждённой оценки</span></li>':'';
 const body=(list||fallback)?'<ul>'+list+fallback+'</ul>':'<p class="rating-hint">Подтверждённых оценок пока нет. <a href="https://www.vivino.com/search/wines?q='+encodeURIComponent(r.title)+'" target="_blank" rel="noopener noreferrer">Найти на Vivino</a></p>';
 return '<details class="rating-details"><summary>Оценки и источники ('+m.all.length+')</summary>'+body+'<p class="rating-hint">Оценки из исходной подборки - срез 14.11.2026. Общий индекс условный, по оценкам того же винтажа.</p></details>';
}
function card(r){
 const m=metrics(r),s=r.stores[0]||{},url=cleanUrl(s.url);
 const grape=r.grapes.length?r.grapes.join(', '):'сорт не указан';
 const meta=[r.country||'страна не указана',grape,r.year?String(r.year):''].filter(Boolean).join(' · ');
 const pairs=(r.pairings||[]).length?'Подходит к: '+r.pairings.join(', '):'Сочетания не указаны';
 return '<article class="wine-card"><div class="card-head"><span class="type-tag"><i aria-hidden="true" class="type-dot '+typeDot(r.type)+'"></i>'+safe(r.type||'Вино')+'</span>'+favoriteButton(r.id)+'</div><h3 class="card-title">'+safe(r.title)+'</h3><p class="card-meta">'+safe(meta)+'</p>'+metricRow(m,r)+ratingsDetails(r,m)+'<p class="card-pairings">'+safe(pairs)+'</p><div class="card-bottom"><div class="price-block">'+priceBlock(r)+'</div>'+(url?'<a class="store-link" href="'+safe(url)+'" target="_blank" rel="noopener noreferrer">Карточка вина ↗</a>':'')+'</div></article>';
}
function matched(r){
 const term=$('search').value.trim().toLocaleLowerCase('ru');
 if(term&&!([r.title,r.country,r.section,String(r.year||''),...(r.grapes||[]),...(r.pairings||[])].join(' ').toLocaleLowerCase('ru').includes(term)))return false;
 if($('country').value&&r.country!==$('country').value)return false;
 if($('grape').value&&!r.grapes.includes($('grape').value))return false;
 if($('type').value&&r.type!==$('type').value)return false;
 if($('pairing').value&&!r.pairings.includes($('pairing').value))return false;
 if(state.scope==='wishlist'&&!r.wishlist)return false;
 if(state.scope==='research'&&!r.research)return false;
 if(state.scope==='saved'&&!state.favorites.has(r.id))return false;
 return true;
}
function render(){
 const rs=state.records.filter(matched),mode=$('sort').value;
 if(mode==='rating-desc')rs.sort((a,b)=>(metrics(b).index??-1)-(metrics(a).index??-1)||a.title.localeCompare(b.title,'ru'));
 else if(mode==='vivino-desc')rs.sort((a,b)=>(metrics(b).vivino?.scope==='vintage'?metrics(b).vivino.score:-1)-(metrics(a).vivino?.scope==='vintage'?metrics(a).vivino.score:-1));
 else if(mode==='alpha')rs.sort((a,b)=>a.title.localeCompare(b.title,'ru'));
 else if(mode==='price-asc')rs.sort((a,b)=>(priceValue(a)??Infinity)-(priceValue(b)??Infinity));
 else if(mode==='price-desc')rs.sort((a,b)=>(priceValue(b)??-1)-(priceValue(a)??-1));
 else if(mode==='year-desc')rs.sort((a,b)=>(b.year??0)-(a.year??0));
 else rs.sort((a,b)=>Number(b.research)-Number(a.research)||a.title.localeCompare(b.title,'ru'));
 $('cards').innerHTML=rs.map(card).join('');
 $('empty').hidden=!!rs.length;
 $('result-count').textContent='Найдено: '+fmt.format(rs.length)+' из '+fmt.format(state.records.length);
 $('saved-count').textContent=state.favorites.size;
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
 $('cards').addEventListener('click',e=>{const b=e.target.closest('button[data-fav]');if(!b)return;const id=b.dataset.fav;if(state.favorites.has(id))state.favorites.delete(id);else state.favorites.add(id);try{localStorage.setItem('wine-atlas-favorites',JSON.stringify([...state.favorites]))}catch{}render()});
}
async function init(){
 try{
  const response=await fetch('./data/wines.json',{cache:'no-cache'});if(!response.ok)throw Error('Catalog HTTP '+response.status);
  const catalog=await response.json();if(!Array.isArray(catalog.records))throw Error('Invalid catalog');
  state.records=catalog.records;
  try{const extra=await fetch('./data/ratings.json',{cache:'no-cache'});if(extra.ok){const o=await extra.json();state.ratingRecords=o.records||{}}}catch(e){console.warn('Ratings unavailable',e)}
  try{const saved=JSON.parse(localStorage.getItem('wine-atlas-favorites')||'[]');if(Array.isArray(saved))state.favorites=new Set(saved.filter(s=>typeof s==='string'))}catch{}
  $('stat-total').textContent=state.records.length;
  $('stat-countries').textContent=new Set(state.records.map(r=>r.country).filter(Boolean)).size;
  $('stat-rated').textContent=state.records.filter(r=>metrics(r).vivino!==null).length;
  $('update-tag').textContent='Исторические цены: '+date(catalog.historical_as_of);
  setup();render();
 }catch(e){console.error(e);$('result-count').textContent='Ошибка загрузки';$('error').hidden=false}
}
init();
