#!/usr/bin/env python3
"""Extract verified price/photo observations from a full Wine Atlas HTML ZIP.

No requests to stores. Never accept redirects, recommendation cards, or
a mismatched product; never silently overwrite the source wishlist.
"""
import argparse
from datetime import date
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile

PHOTO_RE = re.compile(r'https://s2\.wine\.style/images_gen/(\d+)/(\d+)/0_0_695x600\.webp(?:\?.*)?')


def extract(archive: Path, observed_date: str):
    date.fromisoformat(observed_date)
    with ZipFile(archive) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read('manifest.json'))
        capture = json.loads(z.read('capture.json'))
        targets = {x['id']: x for x in capture['targets']}
        pages = {x['id']: x for x in manifest['captures']}
        assert len(targets) == len(capture['targets']), 'Duplicate target IDs'
        assert len(pages) == len(manifest['captures']), 'Duplicate manifest IDs'
        observations, rejected = {}, []
        for c in capture['captures']:
            id_ = c['id']
            t, page = targets.get(id_), pages.get(id_)
            if not t or not page:
                raise ValueError('Missing target or HTML metadata: ' + id_)
            if c.get('status') != 'captured':
                rejected.append({'id': id_, 'url': t['url'], 'reason': c.get('status')})
                continue
            if c.get('url') != t['url'] or c.get('final_url') != t['url']:
                rejected.append({'id': id_, 'url': t['url'], 'reason': 'redirected_product'})
                continue
            identity = c.get('identity') or {}
            if identity.get('target_id') != id_ or identity.get('canonical_url') != t['url']:
                rejected.append({'id': id_, 'url': t['url'], 'reason': 'identity_not_verified'})
                continue
            html_path = page.get('html_path')
            if html_path not in names:
                raise ValueError('Missing HTML: ' + id_)
            sha = hashlib.sha256(z.read(html_path)).hexdigest()
            if sha != c.get('html_sha256') or sha != page.get('html_sha256'):
                raise ValueError('HTML SHA-256 mismatch: ' + id_)
            price, photo = c.get('price'), c.get('image')
            if not isinstance(price, dict) or price.get('method') != 'direct_product_offer':
                rejected.append({'id': id_, 'url': t['url'], 'reason': 'unverified_price'})
                continue
            money = price.get('value_rub')
            if type(money) is not int or not 100 <= money <= 1_000_000:
                rejected.append({'id': id_, 'url': t['url'], 'reason': 'invalid_price'})
                continue
            if not isinstance(photo, dict) or photo.get('method') != 'primary_product_gallery' or photo.get('source_url') != t['url']:
                rejected.append({'id': id_, 'url': t['url'], 'reason': 'unverified_photo'})
                continue
            m = PHOTO_RE.fullmatch(photo.get('url') or '')
            if not m or m[1] != m[2][:3]:
                rejected.append({'id': id_, 'url': t['url'], 'reason': 'unrecognized_gallery_photo'})
                continue
            observations[id_] = [money, m[2]]
        return ({
            'version': 1, 'as_of': observed_date, 'source_archive': archive.name,
            'source_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'method': 'Exact product path, year, Offer.price, gallery photo, HTML SHA256',
            'image_pattern': 'https://s2.wine.style/images_gen/{image_id_first_3}/{image_id}/0_0_695x600.webp',
            'records': observations
        }, rejected)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--date', required=True, help='YYYY-MM-DD')
    p.add_argument('--output', type=Path, help='Write JSON (without this: read-only report)')
    args = p.parse_args()
    result, rejected = extract(args.archive, args.date)
    print(json.dumps({'verified': len(result['records']), 'rejected': rejected}, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
