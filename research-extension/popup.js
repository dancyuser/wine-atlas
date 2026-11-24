'use strict';
const KEY='wineAtlasResearchObservationsV1';
const status=document.getElementById('status');
const ALLOWED=['wineenthusiast.com','winespectator.com','decanter.com','jamessuckling.com','robertparker.com','falstaff.com','timatkin.com','jancisrobinson.com','lucamaroni.it','vinous.com','wineandspiritsmagazine.com','iwsc.net','concoursmondial.com','botti.no','kenswineguide.com','winelab.ru','amwine.ru','vinissimo.biz','sabonis.ru','winestyle.ru','simplewine.ru','ast.wine','joia.ru','luding.ru'];
const allowed=h=>ALLOWED.some(d=>h===d||h.endsWith('.'+d));
async function message(action,scope){const r=await chrome.runtime.sendMessage({action,scope});if(r.error)throw Error(r.error);status.textContent=r.text;}
document.getElementById('capture').onclick=async()=>{try{
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true}), u=new URL(tab.url);
 if(u.protocol!=='https:'||!allowed(u.hostname))throw Error('Сайт не входит в список источников.');
 const [{result}]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:captureWineResearch});
 const saved=(await chrome.storage.local.get(KEY))[KEY]||[];saved.push(result);await chrome.storage.local.set({[KEY]:saved});
 status.textContent=`Сохранено: ${saved.length}; статус: ${result.status}.`;
}catch(e){status.textContent=String(e.message||e);}};
async function startBatch(scope){try{
 const sources=[...SOURCES,...RECHECK].filter(([name])=>scope!=='critics'||!RETAILERS.has(name));
 const origins=[...new Set(sources.map(x=>new URL(x[1]).origin+'/*'))];
 if(!await chrome.permissions.request({origins}))throw Error('Разрешение на источники не предоставлено.');
 await message('start',scope);
}catch(e){status.textContent=String(e.message||e);}}
document.getElementById('batch').onclick=()=>startBatch('all');
document.getElementById('critics').onclick=()=>startBatch('critics');
document.getElementById('resume').onclick=()=>message('resume').catch(e=>status.textContent=e.message);
document.getElementById('pause').onclick=()=>message('pause').catch(e=>status.textContent=e.message);
document.getElementById('export').onclick=()=>message('export').catch(e=>status.textContent=e.message);
document.getElementById('clear').onclick=async()=>{if(confirm('Удалить сохранённые наблюдения? Сначала скачайте JSON.')){await chrome.storage.local.remove(KEY);status.textContent='Наблюдения удалены.';}};
message('status').catch(()=>{});
