#!/usr/bin/env python3
"""Import human-reviewable WineStyle price observations without network access.

Default mode is read-only. --apply writes only verified, recent, exact-URL matches.
No price is inferred from a discount percentage or unrelated retailer record.
"""
import argparse
import copy
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / 'data' / 'wines.json'
MAX_PRICE_RUB = 1_000_000
PRICE_RE = re.compile(r'^\s*([0-9 \u00a0\u202f]+)(?:[.,]00)?\s*(?:₽|руб\.?|RUB)\s*$', re.I)


class ObservationError(ValueError):
    """The entire import must be rejected, without partial writes."""


def url_key(url):
    if not isinstance(url, str) or url != url.strip():
        raise ObservationError('URL must be a nonempty HTTPS string without surrounding spaces')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or
            parsed.password or parsed.port or parsed.query or parsed.fragment):
        raise ObservationError(f'URL must be a canonical HTTPS product URL: {url!r}')
    return parsed.hostname.lower() + parsed.path.rstrip('/')


def winestyle_url(url):
    host = urlsplit(url).hostname or ''
    return host == 'winestyle.ru' or host.endswith('.winestyle.ru')


def date_value(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ObservationError(f'{field} must be a YYYY-MM-DD date')
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ObservationError(f'{field} is not a calendar date: {value}') from exc


def integer_price(value, field):
    if type(value) is not int or not 100 <= value <= MAX_PRICE_RUB:
        raise ObservationError(f'{field} must be an integer price from 100 to {MAX_PRICE_RUB} RUB')
    return value


def price_from_text(value, field):
    if not isinstance(value, str):
        raise ObservationError(f'{field} must contain the price as shown by the source')
    match = PRICE_RE.fullmatch(value)
    if not match:
        raise ObservationError(f'{field} must contain one unambiguous RUB amount (e.g. "3 490 ₽")')
    return int(re.sub(r'\D', '', match.group(1)))


def load_observations(path):
    contents = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.jsonl':
        rows = [json.loads(line) for line in contents.splitlines() if line.strip()]
    else:
        obj = json.loads(contents)
        rows = obj.get('observations') if isinstance(obj, dict) else obj
    if not isinstance(rows, list) or not rows:
        raise ObservationError('Expected a nonempty JSON array, {"observations": [...]}, or JSONL rows')
    return rows


def apply_observations(catalog, observations, today=None, max_age_days=7):
    """Validate every row before applying any change; return (new_catalog, updated, skipped)."""
    today = today or dt.date.today()
    if max_age_days < 0:
        raise ObservationError('max_age_days cannot be negative')
    new_catalog = copy.deepcopy(catalog)
    index = {}
    for record in new_catalog['records']:
        for store in record['stores']:
            key = url_key(store['url'])
            if winestyle_url(store['url']):
                if key in index:
                    raise ObservationError(f'Duplicate WineStyle URL in catalog: {store["url"]}')
                index[key] = store
    seen = set()
    changes = []
    skipped = 0
    for number, row in enumerate(observations, 1):
        if not isinstance(row, dict):
            raise ObservationError(f'Row {number}: expected an object')
        try:
            url = row['url']
            key = url_key(url)
            if key in seen:
                raise ObservationError('duplicate observation URL')
            seen.add(key)
            if not winestyle_url(url):
                raise ObservationError('only WineStyle product URLs are accepted')
            store = index.get(key)
            if store is None:
                raise ObservationError('URL is not in the active wishlist')
            if url_key(row.get('source_url')) != key:
                raise ObservationError('source_url must identify the same exact product page')
            if row.get('currency') != 'RUB':
                raise ObservationError('currency must be RUB')
            checked = date_value(row.get('checked_at'), 'checked_at')
            age = (today - checked).days
            if age < 0 or age > max_age_days:
                raise ObservationError(f'price observation is future-dated or older than {max_age_days} days')
            price = integer_price(row.get('price_rub'), 'price_rub')
            if price_from_text(row.get('price_text'), 'price_text') != price:
                raise ObservationError('price_text does not match price_rub')
            regular = row.get('regular_price_rub')
            if regular is not None:
                regular = integer_price(regular, 'regular_price_rub')
                if regular <= price:
                    raise ObservationError('regular_price_rub must exceed price_rub')
                if price_from_text(row.get('regular_price_text'), 'regular_price_text') != regular:
                    raise ObservationError('regular_price_text does not match regular_price_rub')
            elif row.get('regular_price_text') not in (None, ''):
                raise ObservationError('regular_price_text supplied without regular_price_rub')
            old_date = store.get('price_checked_at')
            if old_date:
                previous = date_value(old_date, 'stored price_checked_at')
                if previous >= checked:
                    if (previous == checked and store.get('price_rub') == price and
                            store.get('regular_price_rub') == regular):
                        skipped += 1
                        continue
                    raise ObservationError('stored price has the same or a newer date; inspect manually')
            changes.append((store, price, regular, checked.isoformat()))
        except (ObservationError, KeyError, TypeError, ValueError) as exc:
            raise ObservationError(f'Row {number}: {exc}') from exc
    for store, price, regular, checked_at in changes:
        store.update(price_rub=price, regular_price_rub=regular, price_checked_at=checked_at)
    if changes:
        new_catalog['updated_at'] = today.isoformat()
    return new_catalog, len(changes), skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations', type=Path, help='JSON or JSONL export from the data collection agent')
    parser.add_argument('--apply', action='store_true', help='write data/wines.json (without this: dry run)')
    parser.add_argument('--max-age-days', type=int, default=7, help='maximum observation age (default 7)')
    args = parser.parse_args(argv)
    try:
        catalog = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
        rows = load_observations(args.observations)
        updated, count, skipped = apply_observations(catalog, rows, max_age_days=args.max_age_days)
        print(f'OBSERVATIONS={len(rows)} UPDATED={count} UNCHANGED={skipped} MODE={"apply" if args.apply else "dry-run"}')
        if args.apply and count:
            tmp = CATALOG_PATH.with_suffix('.tmp')
            try:
                tmp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                tmp.replace(CATALOG_PATH)
            finally:
                tmp.unlink(missing_ok=True)
    except (OSError, ValueError, KeyError) as exc:
        print(f'IMPORT REJECTED: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
