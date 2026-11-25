'use strict';
const status=document.getElementById('status');
const ALLOWED=['wineenthusiast.com','winespectator.com','decanter.com','jamessuckling.com','robertparker.com','falstaff.com','timatkin.com','jancisrobinson.com','lucamaroni.it','vinous.com','wineandspiritsmagazine.com','iwsc.net','concoursmondial.com','botti.no','kenswineguide.com','winelab.ru','amwine.ru','vinissimo.biz','sabonis.ru','winestyle.ru','simplewine.ru','ast.wine','joia.ru','joiastore.ru','luding.ru'];
const allowed=h=>ALLOWED.some(d=>h===d||h.endsWith('.'+d));
async function message(action,details={}){const r=await chrome.runtime.sendMessage({action,...details});if(r.error)throw Error(r.error);status.textContent=r.text;}
document.getElementById('capture').onclick=async()=>{try{
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true}), u=new URL(tab.url);
 if(u.protocol!=='https:'||!allowed(u.hostname))throw Error('Сайт не входит в список источников.');
 const [{result}]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:captureWineResearch});
 await message('record',{row:result});
}catch(e){status.textContent=String(e.message||e);}};
async function startBatch(scope){try{
 const sources=[...SOURCES,...RECHECK].filter(([name])=>
  scope==='critics'?!RETAILERS.has(name):scope==='retailers'?RETAILERS.has(name):true);
 const origins=[...new Set(sources.map(x=>new URL(x[1]).origin+'/*'))];
 if(!await chrome.permissions.request({origins}))throw Error('Разрешение на источники не предоставлено.');
 await message('start',{scope});
}catch(e){status.textContent=String(e.message||e);}}
document.getElementById('batch').onclick=()=>startBatch('all');
document.getElementById('critics').onclick=()=>startBatch('critics');
document.getElementById('retailers').onclick=()=>startBatch('retailers');
document.getElementById('resume').onclick=()=>message('resume').catch(e=>status.textContent=e.message);
document.getElementById('pause').onclick=()=>message('pause').catch(e=>status.textContent=e.message);
document.getElementById('export').onclick=()=>message('export').catch(e=>status.textContent=e.message);
document.getElementById('clear').onclick=()=>{if(confirm('Удалить сохранённые наблюдения? Сначала скачайте JSON.'))message('clear').catch(e=>status.textContent=e.message);};
message('status').catch(()=>{});
