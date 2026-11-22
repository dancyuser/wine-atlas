"""Local browser integration checks, with all external network requests blocked."""
import argparse
import functools
import http.server
import json
import os
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--screenshots',type=Path,default=ROOT/'reports/screenshots')
    args=ap.parse_args();args.screenshots.mkdir(parents=True,exist_ok=True)
    temp_dir=ROOT/'tests/.tmp';temp_dir.mkdir(exist_ok=True)
    os.environ['TEMP']=str(temp_dir);os.environ['TMP']=str(temp_dir)
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    checks=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=False)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith('http://127.0.0.1:') else r.abort())
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            expect(page.locator('.wine-card')).to_have_count(163)
            checks.append('163 real catalog cards rendered')
            page.locator('#search').fill('Alma Valley')
            expect(page.locator('.card-description').first).to_contain_text('Sabonis')
            page.locator('#search').fill('Peter Zemmer')
            expect(page.locator('.wine-card')).to_have_count(1)
            expected=page.evaluate("state.records.find(r=>r.title.includes('Peter Zemmer')).description")
            expect(page.locator('.card-description')).to_have_text(expected)
            fallback_title=page.evaluate("state.records.find(r=>r.description.includes('Сочетания указаны как ориентиры для категории')).title")
            page.locator('#search').fill(fallback_title)
            expect(page.locator('.card-description').first).to_contain_text('пока не подтверждено')
            page.locator('#search').fill('Peter Zemmer')
            checks.append('individual existing descriptions and honest unknown-description fallback')
            page.locator('.save-btn').click();page.reload()
            page.locator('[data-scope="saved"]').click()
            expect(page.locator('.wine-card')).to_have_count(1)
            expect(page.locator('.save-btn')).to_have_attribute('aria-pressed','true')
            checks.append('favorite persisted across reload and saved scope')
            page.locator('[data-scope="all"]').click();page.locator('#reset').click()
            for selector,value in [('#country','Италия'),('#grape','Шардоне'),('#type','Белое'),('#pairing','Рыба')]:
                page.locator(selector).select_option(value)
                count=page.locator('.wine-card').count()
                assert 0<count<163,(selector,count)
                page.locator('#reset').click()
            checks.append('country, grape, type, food pairing filters')
            for sort in ('alpha','price-asc','price-desc','year-desc','recommended'):
                page.locator('#sort').select_option(sort)
                expect(page.locator('.wine-card')).to_have_count(163)
            checks.append('all sorting options')
            page.locator('#search').fill('no-such-wine-xyz')
            expect(page.locator('#empty')).to_be_visible()
            page.locator('#empty-reset').click()
            expect(page.locator('.wine-card')).to_have_count(163)
            checks.append('empty-state reset')
            # Render synthetic confirmed data in memory only: never write it to wines.json.
            fixture=page.evaluate('''() => {
              const r=structuredClone(state.records[0]);const s=r.stores[0];
              s.price_rub=2500;s.regular_price_rub=3000;s.price_checked_at='2026-11-22';
              s.enrichment_status={status:'verified'};s.product_details={source_url:s.url,
                checked_at:'2026-11-22',full_name:'<script>bad</script>',producer:'Fixture Winery',
                description:'Unique synthetic taste description',alcohol_percent:13.5,volume_l:.75,
                image_url:'https://example.com/image.jpg',image_usage_allowed:false};
              const holder=document.createElement('div');holder.innerHTML=card(r,0);
              return {old:holder.querySelector('del')?.textContent,
                text:holder.textContent,image:!!holder.querySelector('img'),script:!!holder.querySelector('script')};
            }''')
            assert '3' in fixture['old'] and '22.11.2026' in fixture['text']
            assert 'Unique synthetic' in fixture['text'] and '13.5%' in fixture['text']
            assert not fixture['image'] and not fixture['script']
            checks.append('synthetic confirmed price, discount, facts, date, image rights and HTML escaping')
            page.screenshot(path=str(args.screenshots/'wine-atlas-desktop.png'),full_page=False)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'horizontal overflow'
            expect(page.locator('.wine-card').first).to_be_visible()
            page.locator('.save-btn').first.click()
            checks.append('390 px mobile layout without horizontal overflow; favorite button usable')
            assert page.locator('.searchbox').bounding_box()['height']>=46
            page.locator('.wine-card').first.scroll_into_view_if_needed()
            page.screenshot(path=str(args.screenshots/'wine-atlas-mobile.png'),full_page=False)
            assert not errors,errors
            checks.append('no browser JavaScript errors')
            browser.close()
    finally:server.shutdown();server.server_close()
    report={'passed':len(checks),'checks':checks,'external_network':'blocked','fixtures':'synthetic in-memory UI checks; screenshots use real catalog'}
    (ROOT/'reports/browser-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
