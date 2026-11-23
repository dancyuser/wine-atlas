/* Wine Atlas one-click batch capture. MV3 classic service worker.
 * Automatic navigation uses regular Chrome tabs with explicit site permissions.
 * It never bypasses a blocked page, authentication, CAPTCHA or a redirect.
 * Progress and all observations survive popup and worker lifecycle restarts.
 */
'use strict';
importScripts('capture.js','batch_core.js');
const STORE='wineAtlasBatchV2';
const ALARM='wineAtlasBatchRecover';
const MIN_GAP_MS=4500;
const AFTER_LOAD_MS=1500;
const LOAD_TIMEOUT_MS=80000;
let busy=false;
let pendingTimer=null;
let targetCache=null;

async function targets(){
 if(targetCache)return targetCache;
 const response=await fetch(chrome.runtime.getURL('targets.json'));
 if(!response.ok)throw Error('Не удалось прочитать встроенный каталог');
 const file=await response.json();
 const list=WineAtlasBatch.validateTargets(file);
 targetCache={list,sha:file.catalog_blob_sha};
 return targetCache;
}
async function read(){return (await chrome.storage.local.get(STORE))[STORE]||null;}
async function save(job){await chrome.storage.local.set({[STORE]:job});}
function schedule(ms=0){
 if(pendingTimer!==null)clearTimeout(pendingTimer);
 pendingTimer=setTimeout(()=>{pendingTimer=null;void tick();},Math.max(0,Math.min(ms,25000)));
}
function summary(job){
 if(!job)return {status:'idle',cursor:0,total:0,exact:0,needs_review:0,errors:0,download_status:null};
 return {status:job.status,cursor:job.cursor,total:job.total,exact:job.exact,
   needs_review:job.needs_review,errors:job.errors.length,
   started_at:job.started_at,finished_at:job.finished_at||null,
   current:job.current?.index??null,download_status:job.download_status||null,
   download_error:job.download_error||null,last:job.last||null};
}
async function badge(job){
 try{
  const count=job?.cursor||0;
  const label=job?.status==='running'?String(count):job?.status==='completed'?'OK':'';
  await chrome.action.setBadgeText({text:label});
  await chrome.action.setBadgeBackgroundColor({color:'#245b42'});
 }catch{}
}
async function download(job){
 const latest=await read();
 if(!latest || latest.run_id!==job.run_id || latest.download_status==='success')return;
 try{
  const bundle=WineAtlasBatch.exportBundle(latest);
  // No transfer to a server: a data URI is downloaded by the browser itself.
  const payload=JSON.stringify(bundle,null,2)+'\n';
  if(payload.length>8_000_000)throw Error('JSON превышает предельный размер автоскачивания');
  const url='data:application/json;charset=utf-8,'+encodeURIComponent(payload);
  const date=new Date().toISOString().slice(0,10);
  const filename='wine-atlas-capture-'+date+'-'+latest.run_id+'.json';
  const id=await chrome.downloads.download({url,filename,saveAs:false,conflictAction:'uniquify'});
  if(typeof id!=='number')throw Error('Браузер не подтвердил создание загрузки');
  latest.download_status='success';
  latest.download_id=id;
  latest.download_error=null;
 }catch(error){
  latest.download_status='failed';
  latest.download_error=String(error?.message||error).slice(0,240);
 }
 await save(latest);
}
async function complete(job,status='completed'){
 const latest=await read();
 if(!latest||latest.run_id!==job.run_id || latest.status!=='running')return;
 latest.status=status;
 latest.current=null;
 latest.finished_at=new Date().toISOString();
 latest.download_status='pending';
 await save(latest);
 await chrome.alarms.clear(ALARM);
 await badge(latest);
 await download(latest);
}
async function start(){
 const existing=await read();
 if(existing?.status==='running'){
  schedule(0);
  return summary(existing);
 }
 const catalog=await targets();
 const job={
  schema_version:2,run_id:String(Date.now()),
  catalog_blob_sha:catalog.sha,total:catalog.list.length,
  started_at:new Date().toISOString(),finished_at:null,
  status:'running',cursor:0,current:null,next_allowed_at:0,
  exact:0,needs_review:0,errors:[],observations:[],last:null,
  download_status:null,download_id:null,download_error:null
 };
 await save(job);
 await chrome.alarms.create(ALARM,{periodInMinutes:0.5});
 await badge(job);
 schedule(0);
 return summary(job);
}
async function stop(){
 const job=await read();
 if(!job || job.status!=='running')return summary(job);
 const owned=job.current?.tab_id;
 job.status='stopped';job.finished_at=new Date().toISOString();
 job.current=null;job.download_status='pending';
 await save(job);
 await chrome.alarms.clear(ALARM);
 await badge(job);
 if(typeof owned==='number')try{await chrome.tabs.remove(owned);}catch{}
 await download(job);
 return summary(await read());
}
async function resume(){
 const job=await read();
 if(!job || job.status!=='stopped')return summary(job);
 job.status='running';job.finished_at=null;job.download_status=null;job.download_error=null;
 await save(job);
 await chrome.alarms.create(ALARM,{periodInMinutes:0.5});
 schedule(0);
 return summary(job);
}
async function result(job,record){
 const fresh=await read();
 if(!fresh || fresh.run_id!==job.run_id||fresh.status!=='running'
      ||fresh.current?.index!==job.current?.index)return;
 if(record.observation){
  fresh.observations.push(record.observation);
  if(record.verification.status==='exact')fresh.exact+=1;
  else fresh.needs_review+=1;
 }else{
  fresh.errors.push({target_id:record.target.id,target_url:record.target.url,
   title:record.target.title,index:job.current.index,
   status:record.verification.status,reason:record.verification.reason,
   captured_at:new Date().toISOString()});
 }
 fresh.last={title:record.target.title,status:record.verification.status,
   reason:record.verification.reason,index:job.current.index};
 const tabId=fresh.current.tab_id;
 fresh.cursor=job.current.index+1;
 fresh.current=null;
 fresh.next_allowed_at=Date.now()+MIN_GAP_MS;
 await save(fresh); // clear ownership before Chrome fires tabs.onRemoved
 await badge(fresh);
 if(typeof tabId==='number')try{await chrome.tabs.remove(tabId);}catch{}
 if(fresh.cursor>=fresh.total)await complete(fresh);
 else schedule(MIN_GAP_MS);
}
async function inspect(job,tab,target){
 const expected=WineAtlasBatch.identityUrl(target.url);
 const actual=WineAtlasBatch.identityUrl(tab.url);
 if(actual!==expected){
  await result(job,{target,verification:{status:'error',reason:'redirect_or_inaccessible_final_url'}});
  return;
 }
 await new Promise(resolve=>setTimeout(resolve,AFTER_LOAD_MS));
 const latest=await read();
 if(latest?.run_id!==job.run_id||latest.status!=='running'
   ||latest.current?.tab_id!==tab.id)return;
 try{
  let raw=await chrome.scripting.executeScript({
   target:{tabId:tab.id,allFrames:false},func:captureWineAtlasPage
  });
  let capture=raw?.[0]?.result;
  // Modern product pages may hydrate their h1/structured data late.
  if(!capture?.h1&&!capture?.blocked){
   await new Promise(resolve=>setTimeout(resolve,2200));
   raw=await chrome.scripting.executeScript({
    target:{tabId:tab.id,allFrames:false},func:captureWineAtlasPage
   });
   capture=raw?.[0]?.result;
  }
  if(!capture){
   await result(job,{target,verification:{status:'error',reason:'no_page_capture'}});
   return;
  }
  const verification=WineAtlasBatch.check(target,capture);
  if(verification.status==='blocked'){
   await result(job,{target,verification});
   return;
  }
  if(verification.status==='rejected'&&verification.reason==='redirect_or_query_variant'){
   await result(job,{target,verification});
   return;
  }
  const observation={
   schema_version:2,target_id:target.id,target_url:target.url,
   target_title:target.title,target_year:target.year,target_volume_l:target.volume_l,
   capture_method:'automated_browser_batch',reviewer_confirmed:false,
   verification,capture
  };
  await result(job,{target,verification,observation});
 }catch(error){
  await result(job,{target,verification:{status:'error',
   reason:'script_injection_failed: '+String(error?.message||error).slice(0,160)}});
 }
}
async function tick(){
 if(busy)return;
 busy=true;
 try{
  const job=await read();
  if(!job||job.status!=='running')return;
  const catalog=await targets();
  if(job.total!==catalog.list.length||job.catalog_blob_sha!==catalog.sha){
   await complete(job,'failed_catalog_mismatch');
   return;
  }
  if(job.cursor>=job.total&&!job.current){await complete(job);return;}
  if(job.current){
   const target=catalog.list[job.current.index];
   if(!target){
    await result(job,{target:{id:'unknown',url:'',title:'unknown'},
      verification:{status:'error',reason:'missing_target'}});
    return;
   }
   let tab;
   try{tab=await chrome.tabs.get(job.current.tab_id);}
   catch{
    await result(job,{target,verification:{status:'error',reason:'temporary_tab_closed'}});
    return;
   }
   if(tab.status!=='complete'){
    if(Date.now()-(job.current.opened_at||0)>LOAD_TIMEOUT_MS)
      await result(job,{target,verification:{status:'error',reason:'navigation_timeout'}});
    return;
   }
   await inspect(job,tab,target);
   return;
  }
  const pause=job.next_allowed_at-Date.now();
  if(pause>0){schedule(pause);return;}
  const target=catalog.list[job.cursor];
  if(!target){await complete(job);return;}
  try{
   // One temporary tab at a time, never active and never touching user tabs.
   const tab=await chrome.tabs.create({url:target.url,active:false});
   const latest=await read();
   if(!latest||latest.run_id!==job.run_id||latest.status!=='running'){
    if(tab?.id)try{await chrome.tabs.remove(tab.id);}catch{}
    return;
   }
   latest.current={index:job.cursor,tab_id:tab.id,opened_at:Date.now()};
   await save(latest);
   schedule(1300); // handles pages finishing before the onUpdated event
  }catch(error){
   const fake={...job,current:{index:job.cursor,tab_id:null}};
   // Chrome cannot create the tab; record and continue.
   const latest=await read();
   if(latest?.run_id===job.run_id&&latest.status==='running'){
    latest.current={index:job.cursor,tab_id:null};
    await save(latest);
    await result(latest,{target,verification:{
     status:'error',reason:'tab_create_failed: '+String(error?.message||error).slice(0,160)}});
   }
  }
 }catch(error){
  const job=await read();
  if(job?.status==='running'){
   job.last={title:'Сбой фоновой задачи',status:'error',reason:String(error?.message||error).slice(0,180)};
   await save(job);
  }
 }finally{busy=false;}
}
chrome.runtime.onMessage.addListener((request,sender,reply)=>{
 if(!request || !['wa_start','wa_stop','wa_resume','wa_status','wa_export'].includes(request.type))return;
 const task=async()=>{
  if(request.type==='wa_start')return await start();
  if(request.type==='wa_stop')return await stop();
  if(request.type==='wa_resume')return await resume();
  if(request.type==='wa_export'){
   const job=await read();
   if(!job)return summary(job);
   // Explicit user request may re-download even if prior auto-download succeeded.
   job.download_status=null;await save(job);await download(job);
   return summary(await read());
  }
  return summary(await read());
 };
 task().then(reply,error=>reply({status:'error',message:String(error?.message||error)}));
 return true;
});
chrome.tabs.onUpdated.addListener((tabId,change)=>{
 if(change.status==='complete')void tick();
});
chrome.tabs.onRemoved.addListener(tabId=>{
 // Recovery alarm will notice if the browser or user closed an owned tab.
 void tick();
});
chrome.alarms.onAlarm.addListener(alarm=>{
 if(alarm.name===ALARM)void tick();
});
chrome.runtime.onStartup.addListener(()=>{
 void (async()=>{
  const job=await read();
  if(job?.status==='running'){
   await chrome.alarms.create(ALARM,{periodInMinutes:0.5});
   schedule(0);
  }else if(job?.download_status==='pending')await download(job);
 })();
});
chrome.runtime.onInstalled.addListener(()=>{
 void (async()=>{
  const job=await read();
  if(job?.status==='running'){
   await chrome.alarms.create(ALARM,{periodInMinutes:0.5});
   schedule(0);
  }
 })();
});
