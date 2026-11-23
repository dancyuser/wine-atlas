#!/usr/bin/env python3
"""Report all visible catalog gaps after merging verified page snapshots.

Usage: python scripts/report_catalog_gaps.py [--output /tmp/wine-gaps.json]
Unknown identity and missing observations remain gaps: never infer availability
or copy prices/photos from redirected products.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def report():
    c = json.loads((ROOT / 'data/wines.json').read_text(encoding='utf-8'))
    independent = json.loads((ROOT / 'data/ratings.json').read_text(encoding='utf-8'))
    snapshot = json.loads((ROOT / 'data/verified-snapshot-2026-11-23.json').read_text(encoding='utf-8'))
    verified = snapshot['records']
    researched = json.loads((ROOT / 'data/researched-photos-2026-11-23.json').read_text(encoding='utf-8'))['records']
    def displayed(r):
        if (r.get('availability', {}).get('status') == 'out_of_stock'
                or r.get('publication_review', {}).get('status') == 'excluded'):
            return False
        live = r['stores'][0].get('live_offer') or {}
        return not (live.get('verification_method') in ('exact_jsonld_product','exact_main_product_visible_price')
                    and live.get('availability') == 'out_of_stock'
                    and live.get('observed_on', '') >=
                        r.get('availability', {}).get('observed_on', '0000-00-00'))
    visible = [r for r in c['records'] if displayed(r)]
    missing = []
    totals = {'visible': len(visible), 'snapshot_price_and_photo': 0,
              'missing_price': 0, 'missing_photo': 0,
              'missing_vivino': 0, 'missing_critic': 0}
    for r in visible:
        s = r['stores'][0]
        x = verified.get(r['id'])
        if x:
            totals['snapshot_price_and_photo'] += 1
        has_price = bool(x or (s.get('live_offer') or {}).get('price_rub') is not None
                         or s.get('price_rub') is not None or s.get('reference_price_rub') is not None)
        has_photo = bool(x or researched.get(r['id'], {}).get('url') or r.get('photo', {}).get('url'))
        has_vivino = any(y.get('source') == 'Vivino'
                         for y in independent['records'].get(r['id'], []))
        product_critic = (s.get('enrichment_status', {}).get('status') == 'verified'
                          and s.get('product_details', {}).get('source_url') == s['url']
                          and any(y.get('scale') in (20, 100) and y.get('source') != 'Vivino'
                                  for y in s.get('product_details', {}).get('ratings', [])))
        independent_critic = any(
            y.get('scale') in (20, 100) and y.get('source') != 'Vivino'
            and 'winestyle.ru' not in (y.get('source_url') or '')
            for y in independent['records'].get(r['id'], []))
        has_critic = product_critic or independent_critic
        gaps = [name for name, exists in [('price', has_price),
                  ('photo', has_photo), ('vivino', has_vivino), ('critic', has_critic)]
                if not exists]
        for key in gaps:
            totals['missing_' + key] += 1
        if gaps:
            missing.append({'id': r['id'], 'title': r['title'], 'vintage': r.get('year'),
                            'source_url': s['url'], 'gaps': gaps,
                            'identity_verified_in_archive': r['id'] in verified})
    detail_fields=('color','aging_potential','wine_style','body','pairing_notes',
                   'alcohol_percent','aroma','taste')
    detail_totals={k:0 for k in ('year','volume_l','grapes',*detail_fields)}
    detail_gaps=[]
    for r in visible:
        st=r['stores'][0]
        archived = (st.get('product_details') or {}) if (
            st.get('enrichment_status',{}).get('status')=='verified'
            and (st.get('product_details') or {}).get('source_url')==st['url']) else {}
        manual = st.get('research_details') or {}
        if manual.get('source_url') != st['url'].split('#')[0]:
            manual = {}
        # Either verified layer can fill a blank/null field without allowing
        # an empty archival value to shadow a valid manual observation.
        absent=[]
        for field in ('year','volume_l','grapes'):
            if not r.get(field):
                absent.append(field)
        for field in detail_fields:
            if not (archived.get(field) or manual.get(field)):
                absent.append(field)
        for field in absent:
            detail_totals[field]+=1
        if absent:
            detail_gaps.append({'id':r['id'],'title':r['title'],
                                'vintage':r.get('year'),'missing_fields':absent})
    totals['missing_explicit_regular_price']=sum(
        (r['stores'][0].get('regular_price_rub') is None and
         not (r['stores'][0].get('live_offer') or {}).get('regular_price_rub'))
        for r in visible)
    totals['with_verified_newer_live_offer']=sum(
        bool(r['stores'][0].get('live_offer')) for r in visible)
    totals['vivino_all_vintages_only']=sum(
        not any(y.get('source')=='Vivino' and y.get('scope')=='vintage'
                for y in independent['records'].get(r['id'],[]))
        for r in visible)
    return {'as_of':snapshot['as_of'],'totals':totals,'gaps':missing,
            'metadata_missing_counts':detail_totals,'metadata_gaps':detail_gaps}



def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    o = report()
    output = json.dumps(o, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
