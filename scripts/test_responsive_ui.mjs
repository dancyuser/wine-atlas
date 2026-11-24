#!/usr/bin/env node
'use strict';
// Verify fluid layout and early reading-size preference bootstrap.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
const css=fs.readFileSync(new URL('../responsive.css',import.meta.url),'utf8');
const app=fs.readFileSync(new URL('../app.js',import.meta.url),'utf8');
assert.match(html,/name="viewport" content="width=device-width, initial-scale=1"/);
assert.match(html,/<link rel="stylesheet" href="\.\/responsive\.css">/);
assert.match(html,/<dialog id="bottle-dialog"/);
assert.match(html,/<dialog id="wine-dialog"/);
assert.match(app,/detailDialog\.showModal\(\)/);
assert.match(css,/\.wine-dialog\{width:min\(1020px/);
assert.doesNotMatch(css,/-webkit-line-clamp/);
assert.match(css,/\.wine-dialog\{width:100%;max-height:100dvh/);
assert.match(html,/<button type="button" id="bottle-dialog-close"/);
assert.match(html,/<select id="reading-select"/);
assert.match(app,/data-bottle-view/);
assert.match(app,/landscape-source/);
assert.match(app,/dialog\.showModal\(\)/);
assert.match(app,/dialog\.addEventListener\('close'/);

for(const needle of [
  'min(\u0063alc(100% - clamp(28px,5vw,128px)),2240px)',
  '@media(min-width:1800px)',
  '@media(max-width:1120px)',
  '@media(max-width:800px)',
  '@media(max-width:580px)',
  '@media(max-width:380px)',
  '.wine-grid{grid-template-columns:repeat(3,minmax(0,1fr))}',
  '.wine-grid{grid-template-columns:1fr}',
  'font-size:calc(clamp(',
  '.bottle-photo.landscape-source{object-fit:cover',
  '.image-dialog::backdrop',
  '@media(prefers-reduced-motion:reduce)'
])assert.ok(css.includes(needle),'Missing adaptive rule: '+needle);
assert.ok(!css.includes('min-width:1050px'));
// The characteristics section must use a stable label/value grid, unlike the
// separate critic rating list where a justified flex row is intentional.
const detailRules=css.match(/\.characteristics li\{[^}]+\}/g)||[];
assert.ok(detailRules.some(rule=>/display:grid/.test(rule)&&/grid-template-columns:minmax\(112px,30%\) minmax\(0,1fr\)/.test(rule)),
  'Desktop detail values must share a fixed start edge');
assert.match(css,/\.characteristics li strong\{[^}]*max-width:none;[^}]*text-align:left;/,
  'Detail values must never be pushed to the far right');
assert.match(css,/@media\(max-width:580px\)\{[\s\S]*?\.characteristics li\{grid-template-columns:minmax\(0,1fr\);row-gap:4px\}/,
  'Mobile descriptions must stack without squeezing the value column');

// Text preference is applied before the first stylesheet paints.
const match=html.match(/<script data-reading-bootstrap>([\s\S]*?)<\/script>/);
assert.ok(match);
assert.ok(html.indexOf('data-reading-bootstrap')<html.indexOf('rel="stylesheet"'));
function bootstrap(saved,storageBroken=false){
 const handlers={},selectHandlers={},writes=[];
 const document={
  documentElement:{dataset:{}},
  addEventListener(type,fn){handlers[type]=fn},
  getElementById(id){assert.equal(id,'reading-select');return {
   value:selectValue,
   get value(){return selectValue},
   set value(x){selectValue=x},
   addEventListener(type,fn){selectHandlers[type]=fn}
  }}
 };
 let selectValue='';
 const storage={
  getItem(key){assert.equal(key,'wine-atlas-reading-size');if(storageBroken)throw Error('Storage blocked');return saved},
  setItem(key,value){assert.equal(key,'wine-atlas-reading-size');if(storageBroken)throw Error('Storage blocked');writes.push(value)}
 };
 vm.runInNewContext(match[1],{document,localStorage:storage});
 handlers.DOMContentLoaded();
 return {document,writes,getSelected(){return selectValue},select(v){selectValue=v;selectHandlers.change()}};
}
const original=bootstrap(null);
assert.equal(original.document.documentElement.dataset.readingSize,'normal');
assert.equal(original.getSelected(),'normal');
const large=bootstrap('large');
assert.equal(large.document.documentElement.dataset.readingSize,'large');
large.select('xlarge');
assert.equal(large.document.documentElement.dataset.readingSize,'xlarge');
assert.deepEqual(large.writes,['xlarge']);
large.select('invalid');
assert.equal(large.document.documentElement.dataset.readingSize,'normal');
const blocked=bootstrap('xlarge',true);
assert.equal(blocked.document.documentElement.dataset.readingSize,'normal');
blocked.select('large');
assert.equal(blocked.document.documentElement.dataset.readingSize,'large');
console.log('RESPONSIVE UI TESTS PASSED: fluid breakpoints, image zoom, no-flash text size, persistence and fallback');
