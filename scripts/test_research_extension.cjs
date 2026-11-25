'use strict';
const assert=require('node:assert/strict');
const {captureWineResearch}=require('../research-extension/collector.js');
const {SOURCES}=require('../research-extension/sources.js');
assert(SOURCES.some(([name])=>name==='Luding'));
assert(SOURCES.some(([name])=>name==='Wine Enthusiast'));
assert.equal(new Set(SOURCES.map(x=>x[0])).size,SOURCES.length);
global.location={href:'https://spb.luding.ru/collection/item/a/?token=secret',hostname:'spb.luding.ru'};
global.document={body:{innerText:'Санкт-Петербург\nВ наличии у поставщика\n2 000 ₽'},querySelector:s=>s==='h1'?{innerText:'Test 2022'}:null,querySelectorAll:()=>[]};
let row=captureWineResearch();
assert.equal(row.url,'https://spb.luding.ru/collection/item/a/');
assert.equal(row.status,'needs_review');
assert(row.excerpts.some(s=>s.includes('поставщика')));
document.body.innerText='Please verify you are human';
row=captureWineResearch();assert.equal(row.status,'blocked');assert.equal(row.excerpts.length,0);
document.body.innerText='Пожалуйста, подождите, пока ваш запрос будет проверен…';
assert.equal(captureWineResearch().status,'blocked');

const link=(href,innerText)=>({href,innerText,querySelector:()=>null});
global.location={href:'https://spb.winestyle.ru/wine/',hostname:'spb.winestyle.ru'};
global.document={body:{innerText:'Каталог'},querySelector:()=>({innerText:'Вино'}),querySelectorAll:()=>[
  link('https://spb.winestyle.ru/wine/rioja/','Риоха'),
  link('https://spb.winestyle.ru/products/Wine-2022.html','Вино 2022')
]};
assert.deepEqual(captureWineResearch().links.map(l=>l.url),['https://spb.winestyle.ru/products/Wine-2022.html']);
global.location={href:'https://www.decanter.com/wine-reviews/search/page/1/',hostname:'www.decanter.com'};
global.document.querySelectorAll=()=>[
  link('https://www.decanter.com/wine/wine-regions/','Wine Regions'),
  link('https://www.decanter.com/wine-reviews/search/page/2/','2'),
  link('https://www.decanter.com/wine-reviews/spain/rioja/review-92636/','Review')
];
assert.deepEqual(captureWineResearch().links.map(l=>l.kind),['next','detail']);
global.location={href:'https://top100.winespectator.com/archives/',hostname:'top100.winespectator.com'};
global.document.querySelectorAll=()=>[
  link('https://top100.winespectator.com/2025/restaurant-awards/example/','Restaurant'),
  link('https://top100.winespectator.com/2025/wine/example/','Wine')
];
assert.deepEqual(captureWineResearch().links.map(l=>l.label),['Wine']);
global.location={href:'https://simplewine.ru/catalog/vino/filter/rating_num-from-90-to-95/',hostname:'simplewine.ru'};
global.document.querySelectorAll=()=>[
  link('https://simplewine.ru/catalog/vino/filter/rating_num-from-90-to-95/page2/','2'),
  link('https://simplewine.ru/catalog/vino/filter/main-to-5000/page2/','Another filter')
];
assert.deepEqual(captureWineResearch().links.map(l=>l.kind),['next']);
global.location={href:'https://simplewine.ru/catalog/product/example/',hostname:'simplewine.ru'};
global.document={querySelector:s=>s==='h1'?{innerText:'Вино Example 2024'}:null,querySelectorAll:()=>[],
 body:{innerText:'Санкт-Петербург\nВино Example 2024\n'+Array.from({length:86},(_,i)=>'Line '+i).join('\n')+
  '\nРейтинги экспертов\nWS 90.0\nJS 92.0\nОсобенности\nRP 99.0'}};
assert.equal(captureWineResearch().blocks.critic_hints,'WS 90.0\nJS 92.0');

global.location={href:'https://www.botti.no/smaksnotater-example/',hostname:'www.botti.no'};
global.document={querySelector:()=>null,querySelectorAll:()=>[],
 body:{innerText:'Varenr: 5\nVin: Domaine Example 2023\nPris: 225,– kr\nPoeng: 89'}};
row=captureWineResearch();
assert.equal(row.status,'needs_review');
assert.match(row.blocks.review,/Poeng: 89/);

const astUrl = 'https://ast.wine/catalog/product/example_25031/';
global.location={href:astUrl,hostname:'ast.wine'};
const item = {
  getClientRects:()=>[{}],
  querySelector:s=>({innerText:s.includes('address')?'ул. Жуковского, 22':'Мало'})
};
global.document={
  title:'Вино Domaine Example 0.75 л',
  body:{innerText:'Санкт-Петербург\nВино Domaine Example\nВинтажи и объемы\n2015, 0.75 л\n2016, 0.75 л'},
  querySelector:s=>s==='h1'?{innerText:'Вино Domaine Example'}:
    s==='a.vintage_item.current'?{href:astUrl,innerText:'\n2016, 0.75 л\n1 800 ₽'}:null,
  querySelectorAll:s=>s==='.product-price__wrap'?[{innerText:'1 800 ₽'}]:
    s==='.stock-list-short__item'?[item]:[]
};
row=captureWineResearch();
assert.equal(row.blocks.city,'Санкт-Петербург');
assert.equal(row.blocks.selected_variant,'2016, 0.75 л');
assert.equal(row.blocks.offer_price,'1 800 ₽');
assert.equal(row.blocks.local_shops,'ул. Жуковского, 22 | Мало');
document.body.innerText='Москва\n'+document.body.innerText;
assert.equal(captureWineResearch().blocks.city,undefined);
console.log('research browser capture tests passed');
