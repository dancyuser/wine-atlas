#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const assert=require('node:assert/strict');
const code=fs.readFileSync(path.join(__dirname,'..','extension','capture.js'),'utf8');
function wineStyleCapture(options={}){
 const url=options.url||'https://spb.winestyle.ru/products/Luca-Winery-G-Lot-Pinot-Noir-Tupungato-2022.html';
 const priceText=options.price??'4\u00a0840\u00a0₽';
 const current=options.conflicting?[priceText,'7\u00a0450\u00a0₽']:[priceText];
 const currentNodes=current.map(v=>({innerText:v,classList:{contains:()=>false}}));
 const old=options.old?[{innerText:options.old,classList:{contains:x=>x==='price--old'}}]:[];
 const stock=options.stock===undefined?'В наличии остался в 1 магазине':options.stock;
 const root={
  innerText:'Артикул в256182 Цена '+priceText+' Добавить в корзину '+stock,
  querySelectorAll(query){
   if(query==='p.price')return [...currentNodes,...old];
   if(query==='.m-productpage-price__in-stock-shops')
    return stock.startsWith('В наличии')?[{innerText:stock}]:[];
   return [];
  }
 };
 const dom={
  title:'Luca Winery G Lot Pinot Noir 2022 0.75 л',
  querySelector(sel){
   if(sel==='.o-productpage-info__price .m-productpage-price')return options.withoutRoot?null:root;
   if(sel.includes('h1'))return {innerText:'Luca Winery G Lot Pinot Noir Tupungato 2022 750 ml'};
   return null;
  },
  querySelectorAll(query){
   if(query.includes('application/ld+json'))return [];
   return [];
  }
 };
 Object.defineProperty(dom,'cookie',{get(){throw Error('Forbidden cookie access')}});
 const ctx={document:dom,location:{href:url,hostname:new URL(url).hostname},Date,JSON,URL,Set,Array,Number,String,console};
 vm.createContext(ctx);
 vm.runInContext(code+'\nthis.captureResult=captureWineAtlasPage();',ctx);
 return JSON.parse(JSON.stringify(ctx.captureResult));
}
const exact=wineStyleCapture();
assert.deepEqual({price:exact.visible_offer.price_rub,stock:exact.visible_offer.availability},
 {price:4840,stock:'in_stock'});
assert.equal(exact.visible_offer.price_evidence.replace(/\s/g,' '),'4 840 ₽');
assert.equal(exact.visible_offer.availability_evidence,'В наличии остался в 1 магазине');
assert.equal(exact.visible_offer.regular_price_rub,null);
assert.equal(exact.visible_offer.method,'visible_main_product_price');
assert.equal(exact.extraction.raw_html_saved,false);
assert.equal(wineStyleCapture({stock:'Ожидаем поступление'}).visible_offer.availability,'out_of_stock');
assert.equal(wineStyleCapture({stock:'Нет в наличии'}).visible_offer.availability,'out_of_stock');
assert.equal(wineStyleCapture({stock:'Доступно под заказ'}).visible_offer.availability,'unknown');
assert.equal(wineStyleCapture({old:'6\u00a0100\u00a0₽'}).visible_offer.regular_price_rub,6100);
assert.equal(wineStyleCapture({conflicting:true}).visible_offer,null,
 'Two incompatible current prices must not produce an offer');
assert.equal(wineStyleCapture({withoutRoot:true}).visible_offer,null,
 'Recommended products cannot supply the main wine price');
assert.equal(wineStyleCapture({price:'от 4 840 ₽'}).visible_offer,null,
 'From-price is not an exact bottle price');
assert.equal(wineStyleCapture({url:'https://example.com/products/wine.html'}).visible_offer,null,
 'Non-WineStyle hosts cannot use site-specific selectors');
assert(!JSON.stringify(exact).includes('cookie'));
console.log('VISIBLE PRICE CAPTURE TESTS PASSED: primary panel, stock, old price, blocked ambiguity');
