#!/usr/bin/env node
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'app.js'), 'utf8').replace(/\binit\(\);\s*$/, '');
const data = JSON.parse(fs.readFileSync(path.join(root, 'data/discovered-wines.json'), 'utf8'));
const exclusions = JSON.parse(fs.readFileSync(path.join(root, 'data/owner-exclusions.json'), 'utf8'));
const sandbox = {document:{getElementById:()=>({value:''})}, Intl, URL, Set, Map, Number, String, Array, Date, console};
vm.createContext(sandbox);
vm.runInContext(app + '\nglobalThis.helpers={state,isDiscovered,agingFor,metrics,priceValue,card};', sandbox);
const {state,isDiscovered,agingFor,metrics,priceValue,card} = sandbox.helpers;
state.ownerExcluded = new Set(Object.keys(exclusions.records));
assert.equal(data.version, 1);
assert.ok(data.records.length);
const seen = new Set();
for(const wine of data.records){
 assert.ok(!seen.has(wine.id)); seen.add(wine.id);
 assert.ok(isDiscovered(wine, 2026));
 assert.ok(Number.isInteger(wine.year));
 assert.equal(wine.availability.status, 'in_stock');
 assert.equal(wine.availability.source_url, wine.stores[0].url);
 assert.ok(wine.stores[0].price_rub > 0 && wine.stores[0].price_rub <= 5000);
 assert.ok(wine.drinking_window.max >= 2027);
 assert.equal(wine.drinking_window.scope, 'vintage');
 assert.ok(wine.drinking_window.source_url.startsWith('https://'));
 state.ratingRecords[wine.id] = wine.critic_ratings;
 assert.equal(agingFor(wine, 2026).end, wine.drinking_window.max);
 assert.equal(priceValue(wine), wine.stores[0].price_rub);
 assert.ok(metrics(wine).index >= 85);
 assert.ok(card(wine).includes(wine.title));
 assert.ok(!Object.values(exclusions.records).some(x => x.year === wine.year && x.url === wine.stores[0].url));
}
const example=data.records[0];
for(const [score,scale,expected] of [[17,20,85],[89,99,89.9]]){
 const ratings=[{...example.critic_ratings[0],score,scale}];
 const wine={...example,id:'test-rating-'+scale,critic_ratings:ratings};
 state.ratingRecords[wine.id]=ratings;
 assert.ok(isDiscovered(wine,2026));
 assert.equal(metrics(wine).index,expected);
}
console.log('DISCOVERY VERIFIED',data.records.length);
