'use strict';
importScripts('sources.js','collector.js');
const KEY='wineAtlasResearchObservationsV1', JOB='wineAtlasResearchJobV1', ALARM='wineAtlasResearchRecover';
let busy=false;
async function read(){return (await chrome.storage.local.get(JOB))[JOB];}
async function write(job){await chrome.storage.local.set({[JOB]:job});}
function wake(delay=1000){setTimeout(()=>void tick(),delay);chrome.alarms.create(ALARM,{delayInMinutes:0.5});}
const words = value => new Set(value.normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().match(/[a-z]{4,}/g)||[]);
function selectDetails(links, titles){
 const reviews=titles.map(words);
 const ranked=links.map(link=>{
  const tokens=words(link.label+' '+new URL(link.url).pathname.replace(/[_-]/g,' '));
  const score=Math.max(0,...reviews.map(review=>[...review].filter(word=>tokens.has(word)).length));
  return {link,score};
 });
 return ranked.sort((a,b)=>b.score-a.score).slice(0,10).map(x=>x.link);
}
async function download(){
 const observations=(await chrome.storage.local.get(KEY))[KEY]||[];
 const payload=JSON.stringify({version:1,kind:'wine_atlas_research_capture',exported_at:new Date().toISOString(),observations});
 if(payload.length>5000000)throw Error('Выгрузка превышает 5 МБ.');
 await chrome.downloads.download({url:'data:application/json;charset=utf-8,'+encodeURIComponent(payload),filename:'wine-atlas-research-'+Date.now()+'.json',saveAs:false});
}
async function tick(){
 if(busy)return;busy=true;
 try{
  let job=await read();if(!job||job.status!=='running')return;
  if(!job.current && job.next_allowed_at && Date.now()<job.next_allowed_at){wake(job.next_allowed_at-Date.now());return;}
  if(job.cursor>=job.queue.length){job.status='complete';await write(job);await chrome.alarms.clear(ALARM);try{await download();}catch(e){job.download_error=String(e.message||e);await write(job);}return;}
  if(!job.current){
   const item=job.queue[job.cursor],tab=await chrome.tabs.create({url:item.url,active:false});
   job.current={tabId:tab.id,started:Date.now()};await write(job);wake(3000);return;
  }
  const item=job.queue[job.cursor];let result, tab;
  try{
   tab=await chrome.tabs.get(job.current.tabId);
   if(tab.status!=='complete' && Date.now()-job.current.started<60000){wake(3000);return;}
   if(tab.status!=='complete')throw Error('load_timeout');
   const [{result:observed}]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:captureWineResearch});
   result=observed;
   if(!result.url||new URL(result.url).origin!==new URL(item.url).origin)throw Error('redirect_to_other_origin');
   if(!RETAILERS.has(item.source)&&result.blocks?.review&&result.title){
    job.review_titles=[...(job.review_titles||[]),result.title].slice(-250);
   }
   if(item.depth!==undefined&&result.status!=='blocked'){
    const links=result.links.filter(x=>new URL(x.url).origin===new URL(item.url).origin);
    const details=selectDetails(links.filter(x=>x.kind==='detail'), RETAILERS.has(item.source)?job.review_titles||[]:[]);
    const next=item.depth<2?links.find(x=>x.kind==='next'):null;
    const entries=details.map(link=>({source:item.source,url:link.url}));
    if(next)entries.push({source:item.source,url:next.url,depth:item.depth+1});
    const unseen=entries.filter(entry=>!job.queue.some(q=>q.url===entry.url));
    job.queue.splice(job.cursor+1,0,...unseen);
   }
  }catch(e){result={url:item.url,status:'error',error:String(e.message||e),observed_at:new Date().toISOString(),excerpts:[],links:[]};}
  const saved=(await chrome.storage.local.get(KEY))[KEY]||[];
  saved.push({...result,links:item.depth===undefined?[]:result.links.slice(0,20),source:item.source,requested_url:item.url});
  await chrome.storage.local.set({[KEY]:saved});
  if(tab?.id)await chrome.tabs.remove(tab.id).catch(()=>{});
  job.cursor++;job.current=null;job.last={source:item.source,status:result.status};job.next_allowed_at=Date.now()+5000;
  // Do not overwrite a pause requested while the page was loading.
  const latest=await read();if(latest?.status==='paused')job.status='paused';
  await write(job);if(job.status==='running')wake(5000);
 }catch(e){console.error('research collection error',e);wake(30000);}finally{busy=false;}
}
chrome.alarms.onAlarm.addListener(a=>{if(a.name===ALARM)void tick();});
chrome.tabs.onUpdated.addListener((id,change)=>{if(change.status==='complete')void tick();});
chrome.runtime.onStartup.addListener(()=>void tick());
chrome.runtime.onMessage.addListener((msg,sender,respond)=>{
 (async()=>{
  let job=await read();
  if(msg.action==='start'){
   if(job && job.status!=='complete')throw Error('Уже есть незавершённое задание; продолжите его.');
   const queue=[];
   for(const retail of msg.scope==='critics'?[false]:[false,true]){
    for(const [source,url] of RECHECK.filter(([name])=>RETAILERS.has(name)===retail))queue.push({source,url});
    for(const [source,url] of SOURCES.filter(([name])=>RETAILERS.has(name)===retail))queue.push({source,url,depth:0});
   }
   await chrome.storage.local.set({[KEY]:[]});
   job={status:'running',cursor:0,current:null,queue,started_at:new Date().toISOString()};await write(job);wake();
  }else if(msg.action==='pause'){if(job){job.status='paused';await write(job);}}
  else if(msg.action==='resume'){if(!job)throw Error('Нет сохранённого задания.');job.status='running';await write(job);wake();}
  else if(msg.action==='export')await download();
  return {text:job?`Состояние: ${job.status}; обработано ${job.cursor} из ${job.queue.length}. ${job.last?.source||''} ${job.last?.status||''}`:'Готово к сбору.'};
 })().then(respond).catch(e=>respond({error:String(e.message||e)}));return true;
});
