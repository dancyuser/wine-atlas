import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const css = fs.readFileSync(new URL('../styles.css', import.meta.url), 'utf8');
const match = html.match(/<script data-theme-bootstrap>([\s\S]*?)<\/script>/);
assert.ok(match, 'Theme bootstrap script must be present inline in head');
assert.ok(html.indexOf('data-theme-bootstrap') < html.indexOf('rel="stylesheet"'), 'Apply theme before CSS loads');
assert.match(html, /<select id="theme-select"[^>]*>/);
for (const option of ['dark','light','system']) assert.ok(html.includes('value="'+option+'"'), 'Missing theme option: '+option);

function scenario(value, initiallyDark=false, storageUnavailable=false) {
  const handlers = {};
  const mediaHandlers = {};
  const select = {value: 'dark', addEventListener(type,fn) { handlers['select:'+type] = fn; }};
  const root = {dataset:{},style:{}};
  const meta = { color:null, setAttribute(name,val) { assert.equal(name,'content'); this.color=val; } };
  const document = {
    documentElement:root,
    querySelector(s) { assert.equal(s,'meta[name="theme-color"]'); return meta; },
    getElementById(id) { assert.equal(id,'theme-select'); return select; },
    addEventListener(type,fn) { handlers[type]=fn; }
  };
  const media = {matches:initiallyDark,addEventListener(type,fn) { mediaHandlers[type]=fn; }};
  const stored = [];
  const localStorage = {
    getItem(key) { assert.equal(key,'wine-atlas-theme'); if(storageUnavailable)throw Error('blocked'); return value; },
    setItem(key,val) { if(storageUnavailable)throw Error('blocked'); stored.push([key,val]); }
  };
  vm.runInNewContext(match[1],{document,window:{matchMedia(){return media;}},localStorage});
  assert.equal(typeof handlers.DOMContentLoaded,'function');
  handlers.DOMContentLoaded();
  return {
    root,meta,select,stored,media,
    selectTheme(mode) { select.value=mode;handlers['select:change'](); },
    setSystemDark(dark) { media.matches=dark;mediaHandlers.change(); }
  };
}
const initial=scenario(null);
assert.equal(initial.root.dataset.theme,'dark','First visit must be dark');
assert.equal(initial.select.value,'dark');
assert.equal(initial.meta.color,'#101820');

const preselected=scenario('light');
assert.equal(preselected.root.dataset.theme,'light');
assert.equal(preselected.meta.color,'#f7f9fb');
preselected.selectTheme('dark');
assert.equal(preselected.root.dataset.theme,'dark');
assert.deepEqual(preselected.stored,[['wine-atlas-theme','dark']]);

const sys=scenario('system',false);
assert.equal(sys.root.dataset.theme,'light');
assert.equal(sys.select.value,'system');
sys.setSystemDark(true);
assert.equal(sys.root.dataset.theme,'dark');
sys.setSystemDark(false);
assert.equal(sys.root.dataset.theme,'light');
sys.selectTheme('dark');
sys.setSystemDark(false);
assert.equal(sys.root.dataset.theme,'dark','System changes cannot override explicit choice');
sys.selectTheme('system');
assert.equal(sys.root.dataset.theme,'light');

assert.equal(scenario('unrecognized').root.dataset.theme,'dark');
const denied=scenario('light',false,true);
assert.equal(denied.root.dataset.theme,'dark');
denied.selectTheme('light');
assert.equal(denied.root.dataset.theme,'light','Theme switch works without localStorage');

const palette=selector=>{
  const start=css.indexOf(selector+'{');
  assert.ok(start>=0,'Missing theme palette '+selector);
  const block=css.slice(start+selector.length+1,css.indexOf('}',start));
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map(([,key,value])=>[key,value]));
};
const dark=palette(':root'),light=palette(':root[data-theme="light"]');
const contrast=(a,b)=>{
  const lum=color=>{
    const ch=[1,3,5].map(x=>parseInt(color.slice(x,x+2),16)/255).map(v=>v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4));
    return .2126*ch[0]+.7152*ch[1]+.0722*ch[2];
  };
  const aL=lum(a),bL=lum(b);
  return (Math.max(aL,bL)+.05)/(Math.min(aL,bL)+.05);
};
for (const [name, colors] of [['dark',dark],['light',light]]) {
  for (const [foreground,background] of [['--ink','--bg'],['--ink','--white'],['--sub','--bg'],['--sub','--white'],['--ink','--rating-bg'],['--rating-label','--rating-bg'],['--accent','--white'],['--on-accent','--accent'],['--active-ink','--active']]) {
    assert.ok(colors[foreground] && colors[background],name+' missing color '+foreground+'/'+background);
    assert.ok(contrast(colors[foreground],colors[background]) >= 4.5,
      name+' '+foreground+' on '+background+' has insufficient contrast: '+contrast(colors[foreground],colors[background]).toFixed(2));
  }
}
for (const color of ['--bg','--white','--control-border','--rating-bg','--detail-line','--code-bg']) {
  assert.ok(css.includes('var('+color+')'),'CSS must use theme token '+color);
}
console.log('THEME TESTS PASSED: default, persistence, system changes, storage disabled, palette contrast');
