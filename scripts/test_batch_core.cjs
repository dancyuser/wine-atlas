#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const folder=path.resolve(__dirname,'../extension');
const context={URL,Date,Set,Number,String,Array,decodeURIComponent};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(folder,'batch_core.js'),'utf8')+';this.checks=WineAtlasBatch;',context);
const api=context.checks;
const bundled=JSON.parse(fs.readFileSync(path.join(folder,'targets.json'),'utf8'));
const list=api.validateTargets(bundled);
assert.equal(list.length,124,'All 124 wishlist entries must be bundled, including excluded variants');
assert.equal(list.filter(x=>!x.excluded).length,110);
assert.equal(new Set(list.map(x=>x.id)).size,124);

const dataBytes=fs.readFileSync(path.join(__dirname,'..','data','wines.json'));
const expectedSha=crypto.createHash('sha1').update('blob '+dataBytes.length+'\\0'.replace('\\0','\0')).update(dataBytes).digest('hex');
assert.equal(bundled.catalog_blob_sha,expectedSha,'The bundled queue must match the exact current catalog blob');
const catalog=JSON.parse(dataBytes.toString('utf8'));
const sourceById=new Map(catalog.records.map(r=>[r.id,r]));
for(const target of list){
 const wine=sourceById.get(target.id);
 assert(wine,'Unknown target id: '+target.id);
 const store=wine.stores[0];
 assert.equal(target.url,store.url,'Bundled URL changed for '+wine.title);
 assert.equal(target.title,wine.title,'Bundled title changed');
 assert.equal(target.year,wine.year??null,'Bundled year changed');
 assert.equal(target.volume_l,wine.volume_l??null,'Bundled bottle size changed');
 assert.equal(target.excluded,wine.availability?.status==='out_of_stock'||
   wine.publication_review?.status==='excluded','Bundled exclusion status changed');
 const verifiedName=store.enrichment_status?.status==='verified'&&store.product_details?.source_url===store.url
   ?store.product_details?.full_name:null;
 assert.equal(target.expected_product_name??null,verifiedName??null,
   'Bundled exact-verified retail name changed: '+wine.title);
}

const t={id:'1',title:'Kopke Late Bottled Vintage Port (LBV)',year:2018,volume_l:0.75,
  url:'https://spb.winestyle.ru/products/Kopke-LBV-2018.html'};
const c={
 source_url:t.url,h1:'Kopke LBV Porto 2018, 750 ml',
 products:[{name:'Kopke Late Bottled Vintage Porto 2018, 750 ml',size:'750 ml',url:t.url}],
 fields:{},blocked:false,offer_evidence_complete:true
};
assert.equal(api.check(t,c).status,'exact','Full LBV name may match acronym');
assert.equal(api.check(t,{...c,source_url:t.url.replace('2018','2022')}).reason,'redirect_or_query_variant');
assert.equal(api.check(t,{...c,h1:'Dow LBV Porto 2018, 750 ml'}).reason,'product_name_mismatch');
assert.equal(api.check(t,{...c,h1:'Kopke LBV Porto 2022, 750 ml',products:[]}).reason,'missing_or_conflicting_vintage');
assert.equal(api.check(t,{...c,h1:'Kopke LBV Porto 2018, 1.5 l',products:[]}).reason,'missing_or_conflicting_volume');
assert.equal(api.check(t,{...c,blocked:true}).status,'blocked');
const bichot={id:'bichot',title:'Albert Bichot Origines Chardonnay Bourgogne AOC',
 expected_product_name:'Вино Albert Bichot, Origines Chardonnay, Bourgogne AOC, 2022',
 year:2022,volume_l:0.75,
 url:'https://spb.winestyle.ru/products/Albert-Bichot-Origines-Chardonnay-Bourgogne-AOC-2022.html'};
const replaced={source_url:bichot.url,
 h1:'Albert Bichot Origines Pinot Noir Bourgogne AOC 2022, 750 ml',
 products:[{name:'Albert Bichot Origines Pinot Noir Bourgogne AOC 2022, 750 ml',
 size:'750 ml',url:bichot.url}],fields:{},blocked:false};
assert.equal(api.check(bichot,replaced).reason,'product_name_mismatch',
 'The same producer + same cuvée + same year/size must not substitute Chardonnay with Pinot Noir');
const bichotValid={...replaced,h1:'Albert Bichot Origines Chardonnay Bourgogne AOC 2022, 750 ml',
 products:[{name:'Albert Bichot Origines Chardonnay Bourgogne AOC 2022, 750 ml',
 size:'750 ml',url:bichot.url}]};
assert.equal(api.check(bichot,bichotValid).status,'exact');

assert.equal(api.check({...t,year:null},c).reason,'catalog_vintage_unspecified');
assert.equal(api.identityUrl(t.url+'?session=secret'),api.identityUrl(t.url+'?session=secret'));
assert.notEqual(api.identityUrl(t.url+'?session=secret'),api.identityUrl(t.url));
assert.equal(api.identityUrl('http://spb.winestyle.ru/products/a'),null);
assert.equal(api.identityUrl('https://evil.example.com/products/a'),null);
const bundle=api.exportBundle({run_id:'abc',catalog_blob_sha:bundled.catalog_blob_sha,
  status:'completed',cursor:124,total:124,exact:100,needs_review:10,errors:[{},{}],
  started_at:'2026-11-23T00:00:00Z',finished_at:'2026-11-23T01:00:00Z',
  observations:[{target_id:'1',capture:c}]});
assert.equal(bundle.schema_version,2);
assert.equal(bundle.source,'wine_atlas_automated_browser_extension');
assert.equal(bundle.observations.length,1);
assert.equal(bundle.failures.length,2);
console.log('BATCH CORE TESTS PASSED: 124 bundled wines; strict name, year, volume, redirect, blocked and export');
