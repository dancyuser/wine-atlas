"""Conservative extraction of retailer-reported wine ratings from matched Product markup.

Never treat retailer summaries as direct Vivino/critic verification. No HTTP access.
A score is recorded only with a named source, explicit scale and page provenance.
"""
import math
import re

SCALES = {5, 10, 20, 100}
CRITICS = ('Wine Enthusiast', 'Jancis Robinson', 'Wine Spectator',
           'Robert Parker', 'Decanter', 'James Suckling', 'Falstaff',
           'Vinous', 'Tim Atkin', 'Wine Advocate')
CRITIC_PATTERN = re.compile(
    r'(?<![a-zA-Z])(' + '|'.join(re.escape(s) for s in CRITICS) +
    r')\s*(?:[:–—-]\s*)?(\d{1,3}(?:[.,]\d)?)\s*(?:/|из)\s*(5|10|20|100)\b',
    re.I,
)
CUSTOMER_PATTERN = re.compile(
    r'(?:оценк[аи]\s+(?:покупател\w*|пользовател\w*)|отзывы\s+покупателей|customer\s+rating)'
    r'\s*[:–—-]?\s*(\d(?:[.,]\d+)?)\s*(?:/|из)\s*(5|10)\b'
    r'(?:\s*[·,;\-]\s*(\d+)\s*(?:оцен\w*|отзыв\w*|ratings?))?', re.I,
)


def named(value):
    if isinstance(value, dict):
        return named(value.get('name'))
    if isinstance(value, str):
        return ' '.join(value.split()) or None
    return None


def scalar(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(',', '.')
        if not re.fullmatch(r'\d{1,3}(?:\.\d+)?', value):
            return None
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError, OverflowError):
        return None


def score_row(source, value, scale, source_url, checked_at, count=None, evidence=None):
    if source not in (*CRITICS, 'WineStyle users'):
        return None
    n, top = scalar(value), scalar(scale)
    if n is None or top not in SCALES or not 0 < n <= top:
        return None
    if count is not None:
        if isinstance(count, bool) or not str(count).isdigit():
            return None
        count = int(count)
        if not 1 <= count <= 100_000_000:
            return None
    return {'source': source, 'score': int(n) if n.is_integer() else n,
            'scale': int(top), 'ratings_count': count,
            'scope': 'unspecified', 'reported_by': 'WineStyle',
            'source_url': source_url, 'observed_on': checked_at,
            'evidence': evidence}


def collect_structured(product, url, date):
    result = []
    agg = product.get('aggregateRating')
    if isinstance(agg, dict):
        row = score_row('WineStyle users', agg.get('ratingValue'),
                        agg.get('bestRating', 5), url, date,
                        agg.get('ratingCount', agg.get('reviewCount')),
                        'Product.aggregateRating')
        if row:
            result.append(row)
    reviews = product.get('review') or []
    for review in reviews if isinstance(reviews, list) else [reviews]:
        if not isinstance(review, dict):
            continue
        source = named(review.get('author')) or named(review.get('publisher'))
        if source not in CRITICS:
            continue
        rating = review.get('reviewRating') or {}
        if not isinstance(rating, dict):
            continue
        row = score_row(source, rating.get('ratingValue'), rating.get('bestRating'),
                        url, date, evidence='Product.review.reviewRating')
        if row:
            result.append(row)
    return result


def collect_dom(soup, url, date):
    # Limit extraction to one product's main content. Do not scan unrelated tiles.
    main = soup.select_one('main') or soup.select_one('[itemscope][itemtype$="/Product"]')
    if main is None:
        return []
    result = []
    for region in main.select('section, [class*="rating"], [class*="critic"], [class*="expert"], [id*="rating"]'):
        marker = ' '.join(str(x) for x in (region.get('id', ''), ' '.join(region.get('class', [])))).lower()
        heading = ' '.join(t.get_text(' ', strip=True) for t in region.select('h2,h3,h4')[:2]).lower()
        if not re.search(r'rating|critic|expert|рейтинг|оценк|критик|эксперт', marker + ' ' + heading):
            continue
        if re.search(r'related|similar|recommend|suggest|похож|рекоменду', marker):
            continue
        lines = [x.get_text(' ', strip=True) for x in region.select('li, tr, p')]
        if not lines and len(region.get_text(' ', strip=True)) < 1000:
            lines = [region.get_text(' ', strip=True)]
        for line in lines:
            if len(line) > 500:
                continue
            for m in CRITIC_PATTERN.finditer(line):
                source = next((name for name in CRITICS if name.casefold() == m.group(1).casefold()), None)
                if source:
                    row = score_row(source, m.group(2), m.group(3), url, date,
                                    evidence='labelled DOM rating section')
                    if row:
                        result.append(row)
            for m in CUSTOMER_PATTERN.finditer(line):
                row = score_row('WineStyle users', m.group(1), m.group(2),
                                url, date, m.group(3), evidence='labelled DOM rating section')
                if row:
                    result.append(row)
    return result


def extract_ratings(soup, product, source_url, checked_at):
    """Return only non-conflicting supported scores for the matched product."""
    rows = collect_structured(product, source_url, checked_at) + collect_dom(soup, source_url, checked_at)
    by_source = {}
    conflicted = set()
    for row in rows:
        source = row['source']
        current = by_source.get(source)
        if current and (current['score'], current['scale']) != (row['score'], row['scale']):
            conflicted.add(source)
            continue
        if current is None or (row['ratings_count'] is not None and current['ratings_count'] is None):
            by_source[source] = row
    return [row for source, row in by_source.items() if source not in conflicted]
