#!/usr/bin/env node
'use strict';
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'..','extension','capture.js'),'utf8');
function collect(title='Kopke LBV 2018'){
 const sourceUrl='https://shop.example.com/bottle/2018';
 const dom={
  title,
  querySelector(selector){
   if(selector.includes('h1'))return {innerText:'Kopke LBV 2018, 750 ml'};
   return null;
  },
  querySelectorAll(selector){
   if(selector.includes('application/ld+json')){
    return [{textContent:JSON.stringify({
     '@context':'https://schema.org','@type':'Product',
     name:'Kopke Late Bottled Vintage Port 2018, 750 ml',url:sourceUrl,
     offers:[
      {'@type':'Offer',price:'6348',priceCurrency:'RUB',availability:'https://schema.org/InStock'},
      {'@type':'AggregateOffer',lowPrice:'300',highPrice:'8000',price:'4500',priceCurrency:'RUB'}
     ]
    })}];
   }
   return [
    {tagName:'DIV',innerText:'Цвет\nРубиновый'},
    {tagName:'DIV',innerText:'Потенциал хранения\n5 лет'},
    {tagName:'DIV',innerText:'Объем\n0.75 л'},
    {tagName:'DIV',innerText:'Рекомендованные товары: другие вина'}
   ];
  }
 };
 Object.defineProperty(dom,'cookie',{get(){throw Error('Must never read cookies')}});
 const sandbox={document:dom,location:{href:sourceUrl},Date,JSON,URL,Set,Array,Number,String,console};
 vm.createContext(sandbox);
 vm.runInContext(source+'\nthis.captureResult=captureWineAtlasPage();',sandbox);
 return JSON.parse(JSON.stringify(sandbox.captureResult));
}
const result=collect();
assert.equal(result.fields.color.value,'Рубиновый');
assert.equal(result.fields.aging_potential.value,'5 лет');
assert.equal(result.fields.volume_l.value,'0.75 л');
assert.equal(result.products.length,1);
assert.equal(result.products[0].offers.length,1,'AggregateOffer must be rejected');
assert.equal(result.products[0].offers[0].price,'6348');
assert.equal(result.source_url,'https://shop.example.com/bottle/2018');
assert.equal(result.extraction.raw_html_saved,false);
assert.equal(result.blocked,false);
assert.equal(collect('Captcha | Access denied').blocked,true);
assert(!JSON.stringify(result).includes('cookie'));
console.log('MV3 CAPTURE TESTS PASSED: visible label parsing, exact Offer filtering, no session access');
