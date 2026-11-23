'use strict';
const $=id=>document.getElementById(id);
const state={targets:[],observations:[],candidate:null,targetId:null};
const status=text=>{$('status').textContent=text;};
const urlId=value=>{
 try{const u=new URL(value);return u.protocol==='https:'?u.hostname.toLowerCase()+u.pathname.replace(/\/$/,'')+u.search:null;}
 catch{return null;}
};
const text=(value)=>String(value==null?'':value);
const today=()=>new Date().toISOString().slice(0,10);
function gapLabels(record){
 const d=record.details||{};
 const missing=[];
 if(!d.aging_potential)missing.push('выдержка');
 if(!d.color)missing.push('цвет');
 if(!d.pairing_notes)missing.push('сочетания');
 if(!d.wine_style)missing.push('стиль');
 if(!d.aroma)missing.push('аромат');
 if(!d.taste)missing.push('вкус');
 if(!d.alcohol_percent)missing.push('крепость');
 missing.push('актуальная цена/наличие','цена до скидки');
 return missing;
}
function render(){
 const list=$('target');
 const selected=state.targetId;
 list.replaceChildren();
 if(!state.targets.length){
  const item=document.createElement('option');item.textContent='Загрузите каталог';list.append(item);list.disabled=true;
 }else{
  list.disabled=false;
  for(const r of state.targets){
   const o=document.createElement('option');o.value=r.id;
   o.textContent=r.title+(r.year?' · '+r.year:' · год не установлен')+
       ' ('+gapLabels(r).slice(0,3).join(', ')+')';
   list.append(o);
  }
  list.value=state.targets.some(x=>x.id===selected)?selected:state.targets[0].id;
  state.targetId=list.value;
 }
 $('open').disabled=!state.targets.length;
 $('capture').disabled=!state.targets.length;
 $('export').disabled=!state.observations.length;
 $('loaded').textContent='В каталоге: '+state.targets.length+' видимых вин';
 $('progress').textContent='Сохранено: '+state.observations.length+' · разные вина: '+
   new Set(state.observations.map(o=>o.target_id)).size;
}
async function persist(){
 await chrome.storage.local.set({targets:state.targets,observations:state.observations,targetId:state.targetId});
}
async function restore(){
 try{
  const s=await chrome.storage.local.get(['targets','observations','targetId']);
  state.targets=Array.isArray(s.targets)?s.targets:[];
  state.observations=Array.isArray(s.observations)?s.observations:[];
  state.targetId=s.targetId||null;
 }catch(e){status('Не удалось прочитать локальное хранилище: '+e.message);}
 render();
}
$('catalog').addEventListener('change',async e=>{
 const file=e.target.files?.[0];if(!file)return;
 try{
  if(file.size>8_000_000)throw Error('Слишком большой JSON-файл');
  const document=JSON.parse(await file.text());
  if(!Array.isArray(document.records))throw Error('Требуется data/wines.json с records');
  const targets=document.records.filter(x=>x.availability?.status!=='out_of_stock'&&
    x.publication_review?.status!=='excluded').map(x=>{
    const s=x.stores?.[0];
    if(!s?.url||!x.id||!x.title)throw Error('Некорректная запись каталога');
    return {id:x.id,title:x.title,year:x.year??null,volume_l:x.volume_l??null,
      store_url:s.url,details:s.product_details||s.research_details||{}};
  });
  if(!targets.length||new Set(targets.map(x=>x.id)).size!==targets.length)throw Error('Нет уникальных видимых вин');
  state.targets=targets;state.targetId=targets[0].id;
  state.candidate=null;$('preview').hidden=true;
  await persist();render();status('Каталог загружен локально. Файл никуда не отправляется.');
 }catch(err){status('Ошибка импорта: '+err.message);}
});
$('target').addEventListener('change',async e=>{
 state.targetId=e.target.value;state.candidate=null;$('preview').hidden=true;
 await persist();
});
$('open').addEventListener('click',async ()=>{
 const r=state.targets.find(x=>x.id===state.targetId);
 if(r)await chrome.tabs.create({url:r.store_url});
});
const numericVolumes=value=>{
 const all=[...text(value).replace(/,/g,'.').matchAll(/(?<![\d.])(\d+(?:\.\d+)?)\s*(мл|ml|л|l)(?!\w)/gi)];
 return all.map(m=>Math.round(Number(m[1])*(m[2].toLowerCase()==='мл'||m[2].toLowerCase()==='ml'?1:1000)));
};
function candidateEvidence(target,capture){
 const sameProducts=capture.products.filter(p=>!p.url||urlId(p.url)===urlId(capture.source_url));
 const names=[capture.h1,...sameProducts.map(x=>x.name)];
 const year=target.year;
 const years=[...new Set(names.join(' ').match(/(?<!\d)(?:19\d\d|20\d\d)(?!\d)/g)||[])];
 const dedicated=text(capture.fields.vintage?.value);
 const yearConfirmed=year==null?false:years.includes(String(year))||dedicated===String(year);
 const yearConflict=year!=null&&years.some(x=>x!==String(year));
 const volumeParts=[...names,capture.fields.volume_l?.value,...sameProducts.map(x=>x.size)];
 const volumes=volumeParts.flatMap(numericVolumes);
 const volumeConfirmed=target.volume_l!=null&&volumes.includes(Math.round(target.volume_l*1000));
 const volumeConflict=target.volume_l!=null&&volumes.some(x=>x!==Math.round(target.volume_l*1000));
 return {url_match:urlId(capture.source_url)===urlId(target.store_url),
  year_confirmed:yearConfirmed,year_conflict:yearConflict,
  volume_confirmed:volumeConfirmed,volume_conflict:volumeConflict,
  manual_review_required:true};
}
$('capture').addEventListener('click',async ()=>{
 const target=state.targets.find(x=>x.id===state.targetId);
 if(!target)return;
 try{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  if(!tab?.id||!tab.url?.startsWith('https://'))throw Error('Откройте карточку HTTPS в обычной вкладке');
  const result=await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:false},
    func:captureWineAtlasPage});
  const capture=result?.[0]?.result;
  if(!capture)throw Error('Нет результатов извлечения');
  const verification=candidateEvidence(target,capture);
  state.candidate={schema_version:1,target_id:target.id,target_url:target.store_url,
    target_title:target.title,target_year:target.year,target_volume_l:target.volume_l,
    capture,verification,reviewer_confirmed:false};
  const schema=capture.products[0];
  $('summary').textContent=[
   'Выбрано: '+target.title+(target.year?' '+target.year:''),
   'URL: '+capture.source_url,'Заголовок: '+capture.h1,
   'Статус страницы: '+(capture.blocked?'проверка/блокировка':'страница прочитана'),
   'URL совпадает: '+verification.url_match,'Год подтверждён: '+verification.year_confirmed,
   'Объём подтверждён: '+verification.volume_confirmed,
   'JSON-LD: '+(schema?schema.name:'нет Product'),
   'Поля: '+Object.keys(capture.fields).join(', '),
   'Цена JSON-LD: '+text(schema?.offers?.[0]?.price||'не найдена')
  ].join('\n');
  const warnings=[];
  if(!verification.url_match)warnings.push('URL отличается от выбранной карточки: сохранение запрещено.');
  if(capture.blocked)warnings.push('Страница недоступна или содержит проверку доступа.');
  if(capture.offer_evidence_complete!==true)warnings.push('Неполная разметка JSON-LD: импорт цены и наличия запрещён.');
  if(verification.year_conflict||verification.volume_conflict)warnings.push('Другой винтаж или объём: не сохраняйте данные.');
  if(!verification.year_confirmed&&target.year!=null)warnings.push('Год не подтверждён заголовком или отдельным полем. Импортер отвергнет обновление.');
  if(!verification.volume_confirmed)warnings.push('Объём не подтверждён. Импортер отвергнет обновление.');
  $('warnings').textContent=warnings.join(' ');
  $('confirmed').checked=false;
  $('preview').hidden=false;
  $('save').disabled=true;
  status('Предпросмотр получен. Подтверждение выполняется вручную.');
 }catch(err){status('Снимок не получен: '+err.message);}
});
$('confirmed').addEventListener('change',e=>{
 const c=state.candidate;
 $('save').disabled=!(c&&e.target.checked&&c.verification.url_match&&!c.capture.blocked&&
  !c.verification.year_conflict&&!c.verification.volume_conflict);
});
$('save').addEventListener('click',async ()=>{
 const c=state.candidate;if(!c||!$('confirmed').checked||!c.verification.url_match)return;
 if(c.capture.blocked||c.verification.year_conflict||c.verification.volume_conflict)return;
 c.reviewer_confirmed=true;
 state.observations.push(c);
 await persist();render();
 $('preview').hidden=true;$('confirmed').checked=false;
 status('Наблюдение сохранено локально. Для безопасного импорта потребуются явные доказательства года и объёма.');
});
$('export').addEventListener('click',()=>{
 if(!state.observations.length)return;
 const output={schema_version:1,source:'wine_atlas_manual_extension',
  exported_at:new Date().toISOString(),observations:state.observations};
 const blob=new Blob([JSON.stringify(output,null,2)+'\n'],{type:'application/json'});
 const url=URL.createObjectURL(blob);
 const a=document.createElement('a');a.href=url;a.download='wine-atlas-manual-'+today()+'.json';
 document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),3000);
 status('Файл сохранён на компьютер; он не загружен в GitHub автоматически.');
});
$('clear').addEventListener('click',async ()=>{
 if(!confirm('Удалить все локальные наблюдения? Предварительно экспортируйте нужные записи.'))return;
 state.observations=[];state.candidate=null;
 await persist();render();$('preview').hidden=true;status('Наблюдения очищены');
});
restore();
