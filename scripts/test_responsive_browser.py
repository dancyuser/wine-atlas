#!/usr/bin/env python3
"""Use an installed headless Chromium to check actual responsive layout geometry.

Self-contained: uses production styles with a static 3-card fixture. No network
requests and no third-party Python modules; page images are data URLs.
"""
import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSER = (shutil.which('google-chrome-stable') or shutil.which('google-chrome')
           or shutil.which('chromium') or shutil.which('chromium-browser'))
assert BROWSER, 'Headless Chromium/Chrome is required for layout regression checks.'
CSS = '\n'.join((ROOT / name).read_text(encoding='utf-8')
                for name in ('styles.css', 'editorial.css', 'responsive.css'))

CARD = """<article class="wine-card">
  <div class="card-head"><span class="type-tag">Красное</span>
    <button class="save-btn" type="button">♡</button></div>
  <div class="card-intro">
    <div class="bottle-media"><button class="bottle-view" type="button">
      <img class="bottle-photo" alt="Бутылка" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='695' height='600'%3E%3Crect x='300' y='50' width='95' height='500' fill='black'/%3E%3C/svg%3E"></button>
    <span class="photo-credit">Фото: источник</span></div>
    <div class="card-intro-copy"><h3 class="card-title">Capo di Stato Colli Trevigiani IGT</h3>
    <p class="card-meta">Италия · Каберне Совиньон · 2013</p>
    <p class="card-description">Достаточно длинное описание вина, которое должно переноситься по строкам
    и оставаться читабельным на любой ширине без переполнения соседнего столбца.</p></div>
  </div>
  <div class="rating-box">
    <div class="rating-cell"><span class="rating-label">Сводный рейтинг</span>
      <div class="rating-value">93 / 100</div><span class="rating-sub">2 источника</span></div>
    <div class="rating-cell"><span class="rating-label">Vivino</span>
      <div class="rating-value">4,3 / 5</div><span class="rating-sub">Все урожаи</span></div>
  </div>
  <details class="rating-details characteristics" open><summary>Вкус и характеристики</summary>
    <ul><li><span>Описание</span><strong>Красное сухое с насыщенным букетом и длительным послевкусием,
    отлично сочетающееся с несколькими видами блюд.</strong></li></ul></details>
  <p class="card-pairings">Подходит к: Красное мясо, Мясо, Сыры</p>
  <div class="card-bottom"><div class="price-block"><div class="price-main">4 990 ₽</div>
    <div class="price-note">Архивная цена</div></div>
    <a class="store-link" href="#">Карточка вина</a></div>
</article>"""

SCRIPT = """<script>
const nodes=[...document.querySelectorAll('.wine-card')];
const container=document.querySelector('.container');
const bottle=document.querySelector('.bottle-media');
const grid=document.querySelector('.wine-grid');
const summary=document.querySelector('.rating-details summary');
const result={
  width:innerWidth,viewport:document.documentElement.clientWidth,
  pageWidth:document.documentElement.scrollWidth,
  containerWidth:Math.round(container.getBoundingClientRect().width),
  gridColumns:getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length,
  cards:nodes.length,photoWidth:Math.round(bottle.getBoundingClientRect().width),
  photoHeight:Math.round(bottle.getBoundingClientRect().height),
  bodyFont:parseFloat(getComputedStyle(document.body).fontSize),
  titleFont:parseFloat(getComputedStyle(document.querySelector('.card-title')).fontSize),
  metaFont:parseFloat(getComputedStyle(document.querySelector('.card-meta')).fontSize),
  detailsFont:parseFloat(getComputedStyle(summary).fontSize),
  readingMode:document.documentElement.dataset.readingSize
};
const pre=document.createElement('pre');
pre.id='layout-metrics';pre.textContent=JSON.stringify(result);
document.body.appendChild(pre);
</script>"""

def render(tmp: Path, width: int, mode: str) -> dict:
    page=tmp / f'layout-{width}-{mode}.html'
    markup=f"""<!DOCTYPE html><html lang="ru" data-reading-size="{mode}"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>{CSS}</style></head><body>
    <header class="site-header"><div class="container header-inner">
      <a class="logo">Мой список вин</a>
      <div class="header-controls"><label class="theme-control"><span>Тема</span>
      <select><option>Тёмная</option></select></label>
      <label class="text-scale-control"><span>Текст</span>
      <select><option>Очень крупный</option></select></label></div></div></header>
    <main class="container"><section class="intro">
      <p class="intro-kicker">PRIVATE CELLAR</p><h1>Моя винная коллекция</h1>
      <p>Оценки критиков, гастрономия, фото и цены.</p></section>
      <section class="catalog"><div class="search-row">
      <label class="search-field">Поиск<input placeholder="Название"></label>
      <label class="sort-field">Сортировка<select><option>Рейтинг</option></select></label>
      </div><div class="filters"><label>Страна<select><option>Все</option></select></label>
      <label>Тип<select><option>Все</option></select></label>
      <label>Сорт<select><option>Все</option></select></label>
      <label>Еда<select><option>Все</option></select></label></div>
      <div class="wine-grid">{CARD*3}</div></section>
    </main>{SCRIPT}</body></html>"""
    # Headless Chrome clamps top-level windows to a minimum width (~500px).
    # Testing "320px" via --window-size alone silently runs at 500px.
    # A fixed-width srcdoc iframe has a genuine CSS layout viewport at 320px.
    frame_source=html.escape(markup,quote=True)
    outer=f"""<!doctype html><html><head><meta charset="utf-8"></head>
    <body style="margin:0"><iframe id="fixture" srcdoc="{frame_source}"
      style="border:0;display:block;width:{width}px;height:1000px"></iframe>
    <script>
    const frame=document.getElementById('fixture');
    frame.addEventListener('load',()=>{{
      const metric=frame.contentDocument.getElementById('layout-metrics');
      const pre=document.createElement('pre');
      pre.id='layout-metrics';
      pre.textContent=metric?metric.textContent:'{{}}';
      document.body.appendChild(pre);
    }});
    </script></body></html>"""
    page.write_text(outer,encoding='utf-8')
    command=[BROWSER, '--headless=new', '--no-sandbox', '--disable-gpu',
             '--disable-dev-shm-usage', '--hide-scrollbars',
             '--force-device-scale-factor=1', f'--window-size={width},1000',
             '--dump-dom', '--virtual-time-budget=1500',
             f'--user-data-dir={tmp / ("profile-" + str(width) + "-" + mode)}',
             page.as_uri()]
    run=subprocess.run(command,capture_output=True,text=True,timeout=45,check=False)
    match=re.search(r'<pre id="layout-metrics">([^<]+)</pre>',run.stdout)
    assert match, f'Chromium did not return metrics for {width}px: {run.stderr[-900:]}'
    return json.loads(html.unescape(match.group(1)))

with tempfile.TemporaryDirectory(prefix='wine-layout-') as folder:
    root=Path(folder)
    for width,expected in ((320,1),(390,1),(768,1),(1024,1),(1366,2),(1920,3),(2560,3),(3840,3)):
        values=render(root,width,'normal')
        assert values['width']==width,('Test viewport must equal requested CSS width',width,values)
        assert values['pageWidth']<=values['viewport']+1,values
        assert values['containerWidth']<=2241,values
        assert values['gridColumns']==expected,values
        assert values['cards']==3,values
        assert values['photoHeight']>=245,values
        assert values['photoWidth']>=150 if width>=600 else values['photoWidth']>=120,values
        assert values['bodyFont']>=16 and values['metaFont']>=14,values
        print('LAYOUT',width,'columns',values['gridColumns'],'photo',
              values['photoWidth'],values['photoHeight'],'body',values['bodyFont'])
    normal=render(root,1440,'normal')
    large=render(root,1440,'large')
    xlarge=render(root,1440,'xlarge')
    assert large['bodyFont']>=normal['bodyFont']+1.9,(normal,large)
    assert xlarge['metaFont']>=normal['metaFont']+3.9,(normal,xlarge)
print('BROWSER RESPONSIVE CHECKS PASSED')
