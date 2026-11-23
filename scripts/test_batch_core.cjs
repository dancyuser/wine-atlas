#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
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
