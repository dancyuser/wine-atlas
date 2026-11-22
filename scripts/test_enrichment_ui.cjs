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
  '\nglobalThis.helpers={countryValue,grapeValues,pairingValues,distinct,matched,card,state};',sandbox);
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
const card=h.card(sample);
assert(card.includes('Вино с ароматом цитрусов'));
assert(card.includes('Wine Enthusiast'));
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
console.log('WINESTYLE UI TESTS PASSED: derived filters, source display, curated preservation, fallback');
