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
  '\nglobalThis.helpers={countryValue,grapeValues,pairingValues,distinct,matched,card,state,metrics,criticRatingsFor,snapshotFor,priceValue,priceBlock,liveOfferFor,isPublished};',sandbox);
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
assert.deepEqual([...h.pairingValues(sample)],['Рыба','Морепродукты','Белое мясо']);
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

const card=h.card(sample);
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
const fallbackCard=h.card(sample);
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
const ratedCard=h.card(sample);
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
const noStockCard=h.card(sample);
assert(noStockCard.includes('Нет в наличии в СПб'),
       'Explicit negative stock must be visible');
assert(noStockCard.includes('21.11.2026'),
       'Retained availability must show its own observation date, not the newer snapshot date');
sample.stores[0].product_details.availability_note='Ожидаем поступление';
sample.stores[0].product_details.field_checked_at.availability_note='2026-11-20';
const oldNoteCard=h.card(sample);
assert(oldNoteCard.includes('20.11.2026'),
       'Retained availability note must show its own observation date');

const latest={...sample,availability:{status:'in_stock',observed_on:'2026-11-23'}};
assert(h.card(latest).includes('Доступно к заказу'));
assert(h.card(latest).includes('23.11.2026'));
assert(!h.card(latest).includes('Ожидаем поступление'),
 'New stock observation must override stale historic status');

h.state.snapshots.fixture=[3990,'272012'];
h.state.snapshotDate='2026-11-23';
const enrichedCard=h.card(sample);
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
const researched=h.card(sample);
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
assert.deepEqual([...h.pairingValues(unmatchedPairings)],['Рыба','Морепродукты','Птица'],
  'Unclassified WineStyle food notes must not discard curated pairings');
selectors.get('pairing').value='Птица';
assert.equal(h.matched(unmatchedPairings),true);
selectors.get('pairing').value='';
assert(h.card(unmatchedPairings).includes('Подходит к: Рыба, Морепродукты, Птица'));

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
const portCard=h.card(port);
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
  enrichment_status:{...sample.stores[0].enrichment_status,checked_at:'2026-11-22'},
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
h.state.snapshots={};
h.state.snapshotDate=null;
console.log('WINESTYLE UI TESTS PASSED: derived filters, merged grape synonyms, excluded redirected wines, source display, curated preservation, fallback');
