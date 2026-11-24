#!/usr/bin/env node
'use strict';
// Regression check using the production app.js helpers (no browser/network needed).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const original = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');
assert.match(original, /\binit\(\);\s*$/);
const selectors = new Map(['search','country','grape','type','pairing'].map(id=>[id,{value:''}]));
const sandbox = {
  document:{getElementById:id=>selectors.get(id)||{value:''}},
  Intl, URL, Set, Map, Number, String, Array, console
};
vm.createContext(sandbox);
vm.runInContext(original.replace(/\binit\(\);\s*$/, '')+
  '\nglobalThis.helpers={countryValue,grapeValues,pairingValues,distinct,matched,card,fullWineMarkup,fullDescription,concisePreview,agingFor,agingMarkup,storageEvidence,mergeSimpleWine,state,metrics,criticRatingsFor,snapshotFor,priceValue,priceBlock,liveOfferFor,isPublished,retailerDetails};',sandbox);
const h=sandbox.helpers;
const sample={
 id:'fixture',title:'Test Chardonnay',country:null,grapes:[],type:'Белое',
 section:'Шардоне',year:2023,volume_l:0.75,pairings:['Паста'],
 stores:[{url:'https://spb.winestyle.ru/products/Synthetic-2023.html',
   price_rub:3590,price_checked_at:'2026-11-22',
   regular_price_rub:null,enrichment_status:{status:'verified'},
   product_details:{
     checked_at:'2026-11-22',
     source_url:'https://spb.winestyle.ru/products/Synthetic-2023.html',
     grapes:'Шардоне, Пино Гриджио', country:'Франция, Бургундия',
     pairing_notes:'рыба, морепродукты/дары моря, белое мясо',
     description_excerpt:'Вино с ароматом цитрусов',
     aroma:'Цитрусовые',taste:'Свежий',
     ratings:[{source:'Wine Enthusiast',score:92,scale:100,
       source_url:'https://spb.winestyle.ru/products/Synthetic-2023.html',
       reported_by:'WineStyle',observed_on:'2026-11-22'}]
   }}]
};
h.state.records=[sample];
assert.equal(h.countryValue(sample),'Франция');
assert.deepEqual([...h.grapeValues(sample)],['Шардоне','Пино Гриджио']);
assert.deepEqual([...h.pairingValues(sample)],['Рыба','Морепродукты/дары моря','Белое мясо']);
assert([...h.distinct('grapes')].includes('Пино Гриджио'));
selectors.get('grape').value='Пино Гриджио';
assert.equal(h.matched(sample),true);
selectors.get('grape').value='Каберне Совиньон';
assert.equal(h.matched(sample),false);
selectors.get('grape').value='';
selectors.get('pairing').value='Рыба';
assert.equal(h.matched(sample),true);
selectors.get('pairing').value='';
selectors.get('country').value='Франция';
assert.equal(h.matched(sample),true);
selectors.get('country').value='';
const synonyms={...sample,grapes:['Сира','Шираз','Сира / Шираз','Сузео','Сузао','Турига Франсеса/Турига Франка','Турига Франка','Красные сорта винограда','Другие сорта','Корвина','Корвиноне']};
assert.deepEqual([...h.grapeValues(synonyms)],['Сира / Шираз','Сузао','Турига Франка','Корвина','Корвиноне']);
h.state.records=[synonyms];
assert.deepEqual([...h.distinct('grapes')],['Корвина','Корвиноне','Сира / Шираз','Сузао','Турига Франка']);
selectors.get('grape').value='Сира / Шираз';
assert.equal(h.matched(synonyms),true,'Alias choice must still filter the underlying wine');
selectors.get('grape').value='Корвиноне';
assert.equal(h.matched({...synonyms,grapes:['Корвина']}),false,'Corvina and Corvinone are distinct cultivars');
selectors.get('grape').value='';
h.state.records=[sample];
const reviewExcluded={...sample,publication_review:{status:'excluded',reason:'redirect_vintage_mismatch'}};
assert.equal(h.matched(reviewExcluded),false,'Redirected wine must not remain visible');
const reviewApproved={...sample,publication_review:{status:'verified',reason:'same_product_in_stock'}};
assert.equal(h.matched(reviewApproved),true,'Exact matched wine should remain visible');

const preview=h.card(sample);
assert(preview.includes('data-wine-open')&&!preview.includes('Дегустационный профиль'));
assert(!preview.includes('rating-details score-details'));
const card=h.fullWineMarkup(sample);
assert(card.includes('Вино с ароматом цитрусов'));
assert(card.includes('Wine Enthusiast'),
  'Named expert scores published by WineStyle must be rendered');
assert(card.includes('92 / 100'),
  'The original critic score and scale must be preserved');
assert(!card.includes('Оценка покупателей WineStyle'),
  'Retailer customer ratings must not appear');
// WineStyle can quote Vivino as a last-resort source, but only if there is
// no direct Vivino value and the retailer product URL is exact-verified.
sample.stores[0].product_details.ratings.push({
 source:'Vivino',score:4.1,scale:5,
 reported_by:'WineStyle',source_url:sample.stores[0].url,
 observed_on:'2026-11-22'
});
const fallbackRating=h.metrics(sample);
assert.equal(fallbackRating.vivino.score,4.1);
assert.equal(fallbackRating.vivino.source_kind,'retailer_reported_vivino');
assert.equal(fallbackRating.vivino.scope,'all_vintages');
assert.equal(fallbackRating.index,null,'Unverified vintage must not yield vintage-only score');
const fallbackCard=h.fullWineMarkup(sample);
assert(fallbackCard.includes('По данным WineStyle'));
assert(fallbackCard.includes('винтаж не установлен'));
sample.stores[0].product_details.ratings.pop();
h.state.ratingRecords.fixture=[
 {source:'Vivino',score:4.2,scale:5,scope:'vintage',vintage:2023,
   source_url:'https://www.vivino.com/wines/123'},
 {source:'Wine Spectator',score:91,scale:100,scope:'vintage',vintage:2023,
   source_url:'https://spb.winestyle.ru/products/Synthetic-2023.html'},
 {source:'Decanter',score:92,scale:100,scope:'vintage',vintage:2023,
   source_url:'https://www.decanter.com/wine/123'}
];
const ratedCard=h.fullWineMarkup(sample);
assert(ratedCard.includes('Vivino') && ratedCard.includes('Decanter'),
 'Independently sourced ratings must remain');
assert(!ratedCard.includes('Wine Spectator'),
 'WineStyle links in independently curated scores must still be excluded to avoid double counting');
assert(ratedCard.includes('Оценки критиков, опубликованные WineStyle'));
assert(ratedCard.includes('Первоисточники и принадлежность к винтажу отдельно не проверены.'));
assert.equal(h.state.ratingRecords.fixture.length,3);
const metric=h.metrics(sample);
assert.equal(metric.critics.length,1);
assert.equal(metric.summary,92, 'Summary must mix exact Vivino, exact independent Decanter and WineStyle-published critic without counting WineStyle duplicates');
assert.equal(metric.index,92, 'Exact vintage-only index should remain separately available');
const unavailable={...sample,availability:{status:'out_of_stock',observed_on:'2026-11-23'}};
assert.equal(h.matched(unavailable),false,
 'Products confirmed unavailable must not appear in any filter');
assert.equal(h.matched({...sample,availability:{status:'in_stock',observed_on:'2026-11-23'}}),true);
assert.equal(h.matched({...sample,availability:undefined}),true,
 'Unknown stock must not be misreported as sold out');

assert(card.includes('Морепродукты'));
sample.stores[0].product_details.availability_spb=false;
sample.stores[0].product_details.field_checked_at={availability_spb:'2026-11-21'};
const noStockCard=h.fullWineMarkup(sample);
assert(noStockCard.includes('Нет в наличии в СПб'),
       'Explicit negative stock must be visible');
assert(noStockCard.includes('21.11.2026'),
       'Retained availability must show its own observation date, not the newer snapshot date');
sample.stores[0].product_details.availability_note='Ожидаем поступление';
sample.stores[0].product_details.field_checked_at.availability_note='2026-11-20';
const oldNoteCard=h.fullWineMarkup(sample);
assert(oldNoteCard.includes('20.11.2026'),
       'Retained availability note must show its own observation date');

const latest={...sample,availability:{status:'in_stock',observed_on:'2026-11-23'}};
assert(h.fullWineMarkup(latest).includes('Доступно к заказу'));
assert(h.fullWineMarkup(latest).includes('23.11.2026'));
assert(!h.fullWineMarkup(latest).includes('Ожидаем поступление'),
 'New stock observation must override stale historic status');

h.state.snapshots.fixture=[3990,'272012'];
h.state.snapshotDate='2026-11-23';
const enrichedCard=h.fullWineMarkup(sample);
assert(enrichedCard.includes(new Intl.NumberFormat('ru-RU').format(3990)),
  'Snapshot price should use production locale formatting');
assert(enrichedCard.includes('images_gen/272/272012/0_0_695x600.webp'));
assert(enrichedCard.includes('Цена в архиве'));
assert(enrichedCard.includes('data-bottle-view'), 'Photo must have keyboard-focusable zoom button');
assert(enrichedCard.includes('Увеличить фото:'), 'Zoom button needs an accessible name');
h.state.snapshots={};
h.state.researchedPhotos.fixture={
  year:2023,url:'https://photos.example.com/bottle.jpg',
  source_url:'https://shop.example.com/products/bottle-2023',
  source:'Example merchant'
};
const researched=h.fullWineMarkup(sample);
assert(researched.includes('https://photos.example.com/bottle.jpg'));
assert(researched.includes('Фото: Example merchant'));
h.state.researchedPhotos={};
assert(card.includes('3\u00a0590')||card.includes('3 590'));
const unmatchedPairings={
  ...sample,
  pairings:['Рыба','Морепродукты','Птица'],
  stores:[{
    ...sample.stores[0],
    product_details:{
      ...sample.stores[0].product_details,
      pairing_notes:'сытные блюда, австрийская кухня'
    }
  }]
};
assert.deepEqual([...h.pairingValues(unmatchedPairings)],['Сытные блюда','Австрийская кухня'],
  'Literal source categories override generic curated labels');
selectors.get('pairing').value='Австрийская кухня';
assert.equal(h.matched(unmatchedPairings),true);
selectors.get('pairing').value='';
assert(h.fullWineMarkup(unmatchedPairings).includes('Подходит к: Сытные блюда, Австрийская кухня'));

const curated={...sample,grapes:['Семильон'],pairings:['Сыры'],country:'Португалия'};
assert.deepEqual([...h.grapeValues(curated)],['Семильон']);
assert.equal(h.countryValue(curated),'Португалия');
const noRetail={...sample,stores:[{url:sample.stores[0].url}]};
assert.deepEqual([...h.pairingValues(noRetail)],['Паста']);
// A later verified retailer observation must outrank a preserved old snapshot,
// and only explicit exact-identified out-of-stock can hide a reviewed product.
h.state.snapshots.fixture=[3990,'272012'];
h.state.snapshotDate='2026-11-23';
const reviewed={
 ...sample, publication_review:{status:'verified',checked_at:'2026-11-23',
    final_url:sample.stores[0].url},
 stores:[{...sample.stores[0],live_offer:{
  price_rub:2890,regular_price_rub:null,availability:'in_stock',
  source_url:sample.stores[0].url,observed_on:'2026-11-24',
  product_name:'Test Chardonnay 2023 750 ml',
  verification_method:'exact_jsonld_product'
 }}]
};
assert.equal(h.liveOfferFor(reviewed).price_rub,2890);
assert.equal(h.priceValue(reviewed),2890,'New observation must override the static archive');
assert(h.priceBlock(reviewed).includes('2\u00a0890')||h.priceBlock(reviewed).includes('2 890'));
assert(h.priceBlock(reviewed).includes('24.11.2026'));
assert(!h.priceBlock(reviewed).includes('Цена в архиве'));
assert.equal(h.isPublished(reviewed),true);
const soldOut={...reviewed,stores:[{...reviewed.stores[0],
 live_offer:{...reviewed.stores[0].live_offer,availability:'out_of_stock'}}]};
assert.equal(h.isPublished(soldOut),false,'Reviewed current out-of-stock must be excluded');
const unknown={...reviewed,stores:[{...reviewed.stores[0],
 live_offer:{...reviewed.stores[0].live_offer,availability:'unknown'}}]};
assert.equal(h.isPublished(unknown),true,'Unknown stock must not be converted to out-of-stock');
const redirected={...reviewed,stores:[{...reviewed.stores[0],
 live_offer:{...reviewed.stores[0].live_offer,
    source_url:'https://spb.winestyle.ru/products/Another-Wine-2025.html'}}]};
assert.equal(h.liveOfferFor(redirected),null,'Unmatched live offer URL cannot affect displayed price');
assert.equal(h.priceValue(redirected),3990);
h.state.snapshots={};
h.state.snapshotDate=null;
// Non-WineStyle seller evidence must be displayed and attributed to its seller.
const port={
 ...sample,id:'verified-port',title:"Dow's Late Bottled Vintage Port (LBV)",
 year:2018,volume_l:0.75,grapes:['Турига Насьональ'],country:'Португалия',
 stores:[{name:'ast.wine',url:'https://ast.wine/catalog/product/dows_lbv_2018/',
   research_details:{
    source_kind:'primary_retailer_product_description',
    source_url:'https://ast.wine/catalog/product/dows_lbv_2018/',
    checked_at:'2026-11-23',producer:"Dow's",volume_l:'0.75 л',
    color:'Насыщенный рубиновый',aroma:'Чёрные ягоды',alcohol_percent:'20 %',
    aging_potential:'Не требуется',wine_style:'Портвейн, сладкое',
    description_excerpt:'Портвейн региона Дору урожая 2018 года'
   }}]
};
const manualDetailsPort={...port,stores:[{...port.stores[0],
 research_details:{...port.stores[0].research_details,source_kind:'manual_verified_original_seller'}}]};
assert(h.fullWineMarkup(manualDetailsPort).includes('Насыщенный рубиновый'),
  'Imported manual original-seller metadata must be displayed');
// New observations complement, but never replace, the archived source.
const mixed={...sample,stores:[{...sample.stores[0],
 research_details:{
  source_kind:'manual_verified_original_seller',
  source_url:sample.stores[0].url,checked_at:'2026-11-23',
  full_name:'Test Chardonnay 2023 750 ml',
  field_checked_at:{color:'2026-11-23',aroma:'2026-11-23'},
  color:'Ярко-золотистый',aroma:'Противоречивый аромат'
 }}]};
const merged=h.retailerDetails(mixed);
assert.equal(merged.aroma,'Цитрусовые',
 'Archived seller tasting notes take precedence over supplementary observations');
assert.equal(merged.color,'Ярко-золотистый',
 'Verified manual color fills the blank field without erasing source data');
assert.equal(merged.supplemental_checked_at,'2026-11-23');
const mixedCard=h.fullWineMarkup(mixed);
assert(mixedCard.includes('Ярко-золотистый'));
assert(mixedCard.includes('Цитрусовые'));
assert(!mixedCard.includes('Противоречивый аромат'));
assert(mixedCard.includes('Дополнено ручной проверкой 23.11.2026'));
const emptyArchive={...mixed,stores:[{...mixed.stores[0],
 product_details:{...mixed.stores[0].product_details,color:null,body:''},
 research_details:{...mixed.stores[0].research_details,
  body:'Полнотелое',field_checked_at:{color:'2026-11-23',body:'2026-11-23'}}}]};
assert.equal(h.retailerDetails(emptyArchive).color,'Ярко-золотистый',
 'A null archival field must not shadow verified manual evidence');
assert.equal(h.retailerDetails(emptyArchive).body,'Полнотелое',
 'An empty archival field must not shadow verified manual evidence');
assert(h.fullWineMarkup(emptyArchive).includes('Полнотелое'));

const portCard=h.fullWineMarkup(port);
assert(portCard.includes('Насыщенный рубиновый'));
assert(portCard.includes('Портвейн региона Дору'));
assert(portCard.includes('Потенциал хранения'));
assert(portCard.includes('Данные ast.wine'));
assert(!portCard.includes('Данные WineStyle'),'The external seller cannot be mislabeled');

// A manually captured, exact-verified WineStyle offer can be used without
// rewriting the original immutable publication-review snapshot.
h.state.snapshots.fixture=[3990,'272012'];
h.state.snapshotDate='2026-11-23';
const manual={
 ...sample,publication_review:undefined,
 stores:[{...sample.stores[0],
  enrichment_status:{...sample.stores[0].enrichment_status,checked_at:'2026-11-22',source_url:sample.stores[0].url},
  live_offer:{price_rub:2990,regular_price_rub:null,availability:'in_stock',
   verification_method:'exact_jsonld_product',
   capture_method:'user_confirmed_active_browser_tab',
   observed_on:'2026-11-24',source_url:sample.stores[0].url,
   product_name:'Test Chardonnay 2023 750ml'}}]
};
assert.equal(h.liveOfferFor(manual).price_rub,2990);
assert.equal(h.priceValue(manual),2990);
assert.equal(h.isPublished({...manual,stores:[{...manual.stores[0],
 live_offer:{...manual.stores[0].live_offer,availability:'out_of_stock'}}]}),false);
const sourcedVisible={...manual,stores:[{...manual.stores[0],
 live_offer:{...manual.stores[0].live_offer,
  price_rub:4840,verification_method:'exact_main_product_visible_price',
  capture_method:'automated_browser_batch',price_evidence:'4 840 ₽',
  availability_evidence:'В наличии в 1 магазине'}}]};
assert.equal(h.liveOfferFor(sourcedVisible)?.price_rub,4840);
assert.equal(h.priceValue(sourcedVisible),4840);
const notAvailable={...sourcedVisible,stores:[{...sourcedVisible.stores[0],
 live_offer:{...sourcedVisible.stores[0].live_offer,
 availability:'out_of_stock',availability_evidence:'Ожидаем поступление'}}]};
assert.equal(h.isPublished(notAvailable),false);
h.state.snapshots={};
h.state.snapshotDate=null;
console.log('WINESTYLE UI TESTS PASSED: derived filters, merged grape synonyms, excluded redirected wines, source display, curated preservation, fallback');

const fullData=JSON.parse(fs.readFileSync(path.join(__dirname,'..','data','full-descriptions.json'),'utf8'));
assert.equal(fullData.version,1);
const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'..','data','wines.json'),'utf8'));
const catalogById=new Map(catalog.records.map(r=>[r.id,r]));
for(const [id,d] of Object.entries(fullData.records)){
 const r=catalogById.get(id);
 assert(r&&r.year===d.year&&r.stores[0].url===d.url,'Full description identity mismatch: '+id);
 assert(d.description.startsWith(r.stores[0].product_details.description_excerpt),'Description must preserve archived exact-product prefix');
}
h.state.fullDescriptions=fullData.records;
const capo=catalogById.get('8a9950e9e3c4');
assert(h.fullDescription(capo).complete);
assert(h.fullDescription(capo).text.length>1800);
assert(h.fullWineMarkup(capo).includes('Глава государства'));
assert(h.concisePreview(capo).length<=155&&/[.!?]["»”)]?$/.test(h.concisePreview(capo)));
assert(!h.card(capo).includes('Глава государства'));
assert(!h.fullDescription({...capo,year:2024}).complete);
assert(h.fullWineMarkup({...capo,year:2024}).includes('сохранённый фрагмент'));
assert(!h.card(capo).includes('…'));
console.log('FULL WINE DETAIL PASSED: verified identity, full archive, complete preview and missing-source disclosure');

const visibleAging=catalog.records.filter(h.isPublished);
assert.equal(Object.keys(h.storageEvidence).length,48);
for(const [id,row] of Object.entries(h.storageEvidence)){
 const r=catalogById.get(id);
 assert(r&&r.year===row.year&&r.stores[0].url===row.url,'Storage evidence identity mismatch: '+id);
 assert(/^https:\/\//.test(row.source_url));
}
for(const r of visibleAging){
 assert(h.agingFor(r,2026).range);
 assert(h.fullWineMarkup(r).includes('Потенциал хранения'));
}
assert.equal(h.agingFor(catalogById.get('cbc96de28176'),2026).status,'past');
assert.equal(h.agingFor(catalogById.get('cbc96de28176'),2026).end,2020);
assert.equal(h.agingFor(catalogById.get('2b85a6978520'),2026).status,'last');
assert.equal(h.agingFor(catalogById.get('2f1b26d235e4'),2026).end,2027);
assert.equal(h.agingFor(catalogById.get('8fb6ff3a814f'),2026).end,2029);
assert(h.agingMarkup(catalogById.get('2f1b26d235e4')).includes('Дополнительный источник'));
assert.equal(h.agingFor(catalogById.get('5b8fb4a0202e'),2026).approximate,true);
assert.equal(h.agingFor(catalogById.get('5b8fb4a0202e'),2026).status,'past');
assert.equal(h.agingFor(catalogById.get('056c6f909a24'),2026).end,2024);
assert.equal(h.agingFor({...catalogById.get('cbc96de28176'),year:2025},2026).status,'unknown');
assert.equal(h.agingFor(catalogById.get('19c9dff352b3'),2026).end,2028);
assert.equal(h.agingFor(catalogById.get('4123b553c232'),2026).status,'last');
assert.equal(h.agingFor(catalogById.get('160221740978'),2026).end,2021);
assert.equal(h.agingFor(catalogById.get('75ea3ee23df9'),2026).end,2023);
assert.equal(h.agingFor(catalogById.get('5740739d992b'),2026).end,2023);
assert.equal(h.agingFor(catalogById.get('4bdac639abe7'),2026).end,2025);
assert.equal(h.agingFor(catalogById.get('8a9950e9e3c4'),2026).end,null);
assert(h.agingMarkup(catalogById.get('19c9dff352b3')).includes('Окно потребления: 2023–2028'));
assert.equal(h.agingFor(catalogById.get('2f6a9b761e1f'),2026).kind,'unknown');
console.log('AGING EVIDENCE PASSED: all published cards, identity, exact versus approximate, NV and expiration');

const ownerExclusions=JSON.parse(fs.readFileSync(path.join(__dirname,'..','data','owner-exclusions.json'),'utf8'));
h.state.ownerExcluded=new Set(Object.keys(ownerExclusions.records));
assert.equal(h.state.ownerExcluded.size,50);
for(const [id,row] of Object.entries(ownerExclusions.records)){
 const wine=catalogById.get(id);assert(wine&&wine.year===row.year&&wine.stores[0].url===row.url);
 const age=h.agingFor(wine,2026);
 assert.equal(row.reason,wine.year==null?'no_vintage':age.kind==='unknown'?'unknown':age.status==='last'?'last':age.status==='past'?(age.approximate?'risk':'past'):age.end===null?'no_calendar':'unexpected');
 assert.equal(h.isPublished(wine),false);
}
assert.equal(catalog.records.filter(h.isPublished).length,60);
for(const wine of catalog.records.filter(h.isPublished)){
 const age=h.agingFor(wine,2026);
 assert(Number.isInteger(age.end)&&age.end>2026,'Missing or expired calendar limit: '+wine.id);
}
assert(catalog.records.filter(h.isPublished).every(r=>Number.isInteger(r.year)&&r.year>0));
assert.equal(catalog.records.filter(r=>r.year==null&&ownerExclusions.records[r.id]?.reason==='no_vintage').length,7);
assert(!h.isPublished({...sample,id:'new-nv',year:null}));
console.log('OWNER SELECTION PASSED: 50 exact exclusions, 60 vintage wines with calendar limits remaining');

const simple=JSON.parse(fs.readFileSync(path.join(__dirname,'..','data','simplewine-catalog.json'),'utf8'));
const simpleMerged=h.mergeSimpleWine(catalog,simple);
assert.equal(simple.source_count,31);
assert.equal(simple.records.length,26);
assert.equal(Object.keys(simple.excluded).length,5);
assert.equal(simpleMerged.records.filter(h.isPublished).length,86);
assert.equal(new Set(simple.records.map(r=>r.stores[0].url)).size,26);
for(const r of simple.records){
 const age=h.agingFor(r,2026);
 assert(Number.isInteger(age.end)&&age.end>2026);
 assert(h.isPublished(r));
 assert(h.fullWineMarkup(r).includes('Потенциал хранения'));
 assert(h.fullWineMarkup(r).includes('SimpleWine'));
 assert(h.fullWineMarkup(r).includes('остатки в СПб не проверены'));
 assert.equal(h.retailerDetails(r).source_kind,'indexed_retailer_card');
 assert(h.card(r).includes('SimpleWine'));
 assert.deepEqual([...h.pairingValues(r)],r.pairings);
}
const sw=Object.fromEntries(simple.records.map(r=>[r.id,r]));
assert.equal(h.agingFor(sw['sw-162380'],2026).end,2027);
assert.equal(h.agingFor(sw['sw-159818'],2026).end,2032);
assert.equal(h.metrics(sw['sw-155172']).critics[0].score,91);
assert.equal(h.metrics(sw['sw-159818']).vivino.score,4);
assert(h.fullWineMarkup(sw['sw-159818']).includes('Оценки критиков, опубликованные SimpleWine'));
assert(h.fullWineMarkup(sw['sw-159818']).includes('по сведениям SimpleWine'));
assert(!h.fullWineMarkup(sw['sw-159818']).includes('по сведениям WineStyle'));
assert.throws(()=>h.mergeSimpleWine(catalog,{...simple,records:[...simple.records,simple.records[0]],source_count:32}));
console.log('SIMPLEWINE PASSED: 31 reviewed, 26 imported, 5 excluded, 86 public cards');
