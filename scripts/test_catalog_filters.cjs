#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
assert.doesNotMatch(html,/value="recommended"|В порядке вишлиста/);
assert.match(html,/<option value="rating-desc" selected>/);
for(const id of ['price-min','price-max'])assert.match(html,new RegExp('id="'+id+'"[^>]*type="number"'));
const controls=new Map(['search','country','grape','type','pairing','price-min','price-max','sort'].map(id=>[id,{value:''}]));
controls.get('sort').value='rating-desc';
const doc={getElementById:id=>controls.get(id)||{value:''}};
const sandbox={document:doc,Intl,URL,Set,Map,Number,String,Array,console};
vm.createContext(sandbox);
vm.runInContext(app.replace(/\binit\(\);\s*$/,'')+
 '\nglobalThis.helpers={state,matched,pairingValues,withinPriceRange,sortRecords,metrics};',sandbox);
const {state,matched,pairingValues,withinPriceRange,sortRecords,metrics}=sandbox.helpers;
const url='https://spb.winestyle.ru/products/example.html';
const wine=(id,price,note)=>({id,title:id,year:2023,type:'Красное',country:'Италия',grapes:['Мерло'],section:'Мерло',pairings:['Рыба'],stores:[{url,price_rub:price,price_checked_at:price==null?null:'2026-11-23',enrichment_status:{status:'verified'},product_details:{source_url:url,pairing_notes:note,ratings:[]}}]});
const mixed=wine('mixed',2000,'рыба, лосось/семга, мясо, дичь, красное мясо, салат, овощи, зрелые/выдержанные сыры, сыры');
assert.deepEqual([...pairingValues(mixed)],['Рыба','Лосось/семга','Мясо','Дичь','Красное мясо','Салат','Овощи','Зрелые/выдержанные сыры','Сыры']);
const salmon=wine('salmon',2000,'лосось/семга');
assert.deepEqual([...pairingValues(salmon)],['Лосось/семга']);
const game=wine('game',2000,'дичь, мясо диких животных');
assert.deepEqual([...pairingValues(game)],['Дичь','Мясо диких животных']);
const spicy=wine('spicy',1000,'острые/пряные блюда, азиатская кухня, свинина, утка, мидии');
assert.deepEqual([...pairingValues(spicy)],['Острые/пряные блюда','Азиатская кухня','Свинина','Утка','Мидии']);
assert.deepEqual([...pairingValues(wine('prose',1000,'Вино идеально подходит к блюдам из рыбы.'))],[]);
controls.get('pairing').value='Рыба';
assert.equal(matched(salmon),false,'Salmon cannot be merged into generic fish');
controls.get('pairing').value='Мясо';
assert.equal(matched(game),false,'Game cannot be merged into generic meat');
controls.get('pairing').value='';
const source=JSON.parse(fs.readFileSync(path.join(root,'data','source-pairings.json'),'utf8'));
const catalog=JSON.parse(fs.readFileSync(path.join(root,'data','wines.json'),'utf8'));
const snapshot=JSON.parse(fs.readFileSync(path.join(root,'data','verified-snapshot-2026-11-23.json'),'utf8'));
state.sourcePairings=source.records;state.pairingLabels=source.labels;
const ownerExclusions=JSON.parse(fs.readFileSync(path.join(root,'data','owner-exclusions.json'),'utf8'));
state.ownerExcluded=new Set(Object.keys(ownerExclusions.records));
assert.equal(source.archive_sha256,snapshot.source_archive_sha256);
assert.equal(Object.keys(source.labels).length,30);
assert.equal(new Set(Object.values(source.labels)).size,30,'Source category IDs must not share an umbrella label');
const byId=new Map(catalog.records.map(r=>[r.id,r]));
for(const [id,row] of Object.entries(source.records)){
 const r=byId.get(id);
 assert(r&&r.year===row.year&&r.stores[0].url===row.url,'Exact source identity must match '+id);
 assert(row.source==='user_screenshot_exact_2023'||Object.hasOwn(snapshot.records,id),'Archived category must be from verified snapshot');
 assert.equal(row.codes.length,new Set(row.codes).size);
 assert(row.codes.every(code=>Object.hasOwn(source.labels,code)));
 assert.deepEqual([...pairingValues(r)],row.codes.map(code=>source.labels[code]),'Category loss at '+id);
 for(const code of row.codes){
  controls.get('pairing').value=source.labels[code];
  if(!state.ownerExcluded.has(id)&&r.availability?.status!=='out_of_stock'&&r.publication_review?.status!=='excluded')assert(matched(r),'Filter must match exact category '+id+' '+code);
 }
}
controls.get('pairing').value='';
const maturana=byId.get('5b9b46b0b3e6');
assert.deepEqual([...pairingValues(maturana)],['Свинина','Морепродукты','Пернатая дичь','Острые блюда']);
controls.get('pairing').value='Птица';assert(!matched(maturana));
controls.get('pairing').value='Блюда из мяса';assert(!matched(maturana));
controls.get('pairing').value='';
assert.deepEqual([...pairingValues(byId.get('745a343dcdc1'))],['Блюда из мяса','Дичь','Красная рыба']);
assert.deepEqual([...pairingValues(byId.get('a1faf8b0af1d'))],['Аперитив','Десерты','Фрукты и ягоды']);
assert.deepEqual([...pairingValues(byId.get('42b87c5124ce'))],[]);
assert.equal(Object.keys(source.records).length,115);
assert.equal(state.ownerExcluded.size,45);
assert.equal(catalog.records.filter(matched).length,65);
assert(catalog.records.filter(matched).every(r=>Number.isInteger(r.year)&&r.year>0));
for(const year of [null,undefined,0,'2024'])assert(!matched({...wine('new-undated',1000,'рыба'),year}));
for(const id of state.ownerExcluded)assert(!matched(byId.get(id)),'Owner-excluded wine matched: '+id);
const cheap=wine('cheap',1000,'рыба'),expensive=wine('expensive',5000,'рыба'),unknown=wine('unknown',null,'рыба');
assert(withinPriceRange(unknown,'',''),'No range must retain unpriced cards');
assert(!withinPriceRange(unknown,'1',''),'Priced ranges must exclude unknown prices');
assert(withinPriceRange(cheap,'1000','1000'),'Endpoints must be inclusive');
assert(!withinPriceRange(cheap,'1001',''));
assert(!withinPriceRange(expensive,'','4000'));
controls.get('price-min').value='1000';controls.get('price-max').value='3000';
assert(matched(cheap));assert(!matched(expensive));assert(!matched(unknown));
assert(!matched(wine('too-cheap',999,'рыба')));
assert(!withinPriceRange(cheap,'3000','1000'),'Reversed range cannot match');
controls.get('price-min').value='';controls.get('price-max').value='';
const one=wine('one',1000,'рыба'),many=wine('many',1000,'рыба');
state.ratingRecords.one=[{source:'Decanter',score:90,scale:100,scope:'vintage',vintage:2023,source_url:'https://www.decanter.com'}];
state.ratingRecords.many=[
 {source:'Decanter',score:90,scale:100,scope:'vintage',vintage:2023,source_url:'https://www.decanter.com'},
 {source:'Falstaff',score:90,scale:100,scope:'vintage',vintage:2023,source_url:'https://www.falstaff.com'},
 {source:'Wine Enthusiast',score:90,scale:100,scope:'vintage',vintage:2023,source_url:'https://www.wineenthusiast.com'}
];
assert.equal(metrics(one).summary,metrics(many).summary);
assert(metrics(many).ranking>metrics(one).ranking,'More independent critics need higher confidence ranking');
assert.deepEqual([...sortRecords([one,many],'rating-desc').map(x=>x.id)],['many','one']);
assert(metrics(one).ranking<metrics(one).summary,'No bonus should inflate a low-confidence mean');
console.log('CATALOG FILTERS PASSED: price boundaries, missing prices, taxonomy and ranking');
