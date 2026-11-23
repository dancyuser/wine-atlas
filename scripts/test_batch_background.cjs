#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const assert=require('node:assert/strict');
const root=path.join(__dirname,'..','extension');
const bundled=JSON.parse(fs.readFileSync(path.join(root,'targets.json'),'utf8'));
const ids=['2f1b26d235e4','209d7a6d9fe0','c9f63273980c','060e3c866e44'];
const chosen=ids.map(id=>bundled.targets.find(t=>t.id===id));
assert(chosen.every(Boolean));
const file={...bundled,total:chosen.length,targets:chosen};
const memory={},tabMap=new Map(),downloads=[];
let onDownload=null;
const clone=value=>value===undefined?undefined:JSON.parse(JSON.stringify(value));
const event=()=>({listeners:[],addListener(fn){this.listeners.push(fn)}});
let clock=0,nextId=10;
class FakeDate extends Date {
 static now(){clock+=7000;return Date.now()+clock;}
}
const chrome={
 runtime:{getURL:p=>'chrome-extension://example/'+p,
  onMessage:event(),onStartup:event(),onInstalled:event()},
 storage:{local:{
  async get(k){
   if(Array.isArray(k))return Object.fromEntries(k.map(key=>[key,clone(memory[key])]));
   return {[k]:clone(memory[k])};
  },
  async set(v){for(const [key,value] of Object.entries(v))memory[key]=clone(value);}},
  onChanged:event()},
 tabs:{
  onUpdated:event(),onRemoved:event(),
  async create({url,active}){
   assert.equal(active,false,'Never activate scraping tabs');
   const tab={id:nextId++,url,status:'complete'};
   tabMap.set(tab.id,tab);return tab;
  },
  async get(id){if(!tabMap.has(id))throw Error('missing temporary tab');return tabMap.get(id)},
  async remove(id){tabMap.delete(id);}
 },
 scripting:{
  async executeScript({target,func}){
   assert.equal(target.allFrames,false);
   const tab=tabMap.get(target.tabId);
   const t=chosen.find(x=>x.url===tab.url);
   const year=t.year??null,size=t.volume_l??0.75;
   const label=t.title+' '+(year||'NV')+', '+Math.round(size*1000)+' ml';
   return [{result:{source_url:t.url,h1:label,
    captured_at:new Date().toISOString(),blocked:false,
    products:[{name:label,url:t.url,size:Math.round(size*1000)+' ml',
      '@type':'Product',offers:[{'@type':'Offer',price:'2000',priceCurrency:'RUB',
        availability:'https://schema.org/InStock'}]}],
    fields:{},offer_evidence_complete:true}}];
  }
 },
 action:{async setBadgeText(){},async setBadgeBackgroundColor(){}},
 alarms:{onAlarm:event(),async create(){},async clear(){return true}},
 downloads:{async download({url,filename,saveAs}){
  if(onDownload)await onDownload();
  assert.equal(saveAs,false);
  assert(url.startsWith('data:application/json;charset=utf-8,'));
  const payload=JSON.parse(decodeURIComponent(url.split(',').slice(1).join(',')));
  downloads.push({filename,payload});
  return downloads.length;
 }}
};
const context=vm.createContext({
 console,JSON,URL,Date:FakeDate,Set,Map,Array,Math,Promise,Number,String,
 decodeURIComponent,encodeURIComponent,chrome,
 setTimeout:(cb)=>setTimeout(cb,0),clearTimeout:clearTimeout,
 fetch:async()=>({ok:true,json:async()=>file}),
 importScripts:(...files)=>{
  for(const name of files){
   if(name==='capture.js')continue; // executeScript is replaced by a deterministic tab.
   const src=fs.readFileSync(path.join(root,name),'utf8');
   vm.runInContext(src,context);
  }
 },
 captureWineAtlasPage:()=>({})
});
vm.runInContext(fs.readFileSync(path.join(root,'background.js'),'utf8'),context);
async function run(){
 const task=await vm.runInContext('start()',context);
 assert.equal(task.status,'running');
 const end=Date.now()+2500;
 let job;
 while(Date.now()<end){
  await new Promise(resolve=>setTimeout(resolve,8));
  job=memory.wineAtlasBatchV2;
  if(job?.status==='completed'&&downloads.length)break;
 }
 assert.equal(job?.status,'completed',JSON.stringify({cursor:job?.cursor,last:job?.last}));
 assert.equal(job.cursor,4);
 assert.equal(job.total,4);
 assert.equal(job.exact,4);
 assert.equal(job.needs_review,0,'Strictly identified undated products should be accepted without manufacturing vintages');
 assert.equal(job.errors.length,0);
 assert.equal(job.observations.length,4);
 assert.equal(tabMap.size,0,'Temporary tabs must be closed');
 assert.equal(downloads.length,1);
 assert.equal(downloads[0].payload.completed,4);
 assert.equal(downloads[0].payload.observations.length,4);
 assert.equal(downloads[0].payload.source,'wine_atlas_automated_browser_extension');
 // Simulate popup closure: storage alone must retain the finished run.
 const snapshot=JSON.parse(JSON.stringify(job));
 assert.equal(snapshot.observations.length,4);
 // Reproduce a concurrent capture completing during an export. The storage
 // mock clones values like Chrome, so stale whole-job writes lose data.
 const racing=clone(memory.wineAtlasBatchV2);
 racing.status='running';racing.cursor=1;
 racing.observations=racing.observations.slice(0,1);
 racing.download_status=null;
 memory.wineAtlasBatchV2=racing;
 onDownload=async()=>{
   await new Promise(resolve=>setTimeout(resolve,2));
   const newer=clone(memory.wineAtlasBatchV2);
   newer.cursor=2;
   newer.observations.push({target_id:'captured_during_export'});
   memory.wineAtlasBatchV2=newer;
 };
 await vm.runInContext('(async()=>download(await read(),true))()',context);
 const after=memory.wineAtlasBatchV2;
 assert.equal(after.cursor,2,'Download metadata cannot revert capture progress');
 assert.equal(after.observations.length,2,'Download metadata cannot erase observations');
 assert.equal(after.observations[1].target_id,'captured_during_export');
 assert.equal(memory.wineAtlasBatchDownloadV2.status,'success');
 console.log('BACKGROUND BATCH TESTS PASSED: 4 tabs, undated identity, auto export, concurrent-write integrity');
}
run().catch(e=>{console.error(e);process.exitCode=1});
