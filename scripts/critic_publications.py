"""Extract named vintage entries from the publishers' public article formats."""
import re


MONEY = r'\d+(?:[.,]\d{1,2})?'
VINTAGE = r'(?:19|20)\d{2}'
ATKIN_DATE = re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}')


def publication_kind(host, path):
    if host == 'jamessuckling.com' and path.startswith('/wine-tasting-reports/'):
        return 'suckling'
    if host == 'content.robertparker.com' and path.rstrip('/') == '/best-wines-2019-mark-squires':
        return 'parker'
    if host == 'timatkin.com' and path.startswith('/score-ranges/'):
        return 'atkin'
    if host == 'decanter.com' and path.rstrip('/').endswith('/top-20-value-golds-best-wines-under-15-from-dwwa-2024-531852'):
        return 'dwwa'
    if host == 'wineandspiritsmagazine.com' and path.rstrip('/') == '/the-short-list/great-rioja-for-under-25':
        return 'wine_spirits'
    if host == 'jancisrobinson.com' and path.rstrip('/') == '/articles/grattamacco-2022-bolgheri-rosso':
        return 'jancis'
    if host == 'botti.no' and path.startswith('/smaksnotater-'):
        return 'botti'
    if host == 'iwsc.net' and path.rstrip('/') == '/news/wine/results-revealed-iwsc-judging-in-conegliano-valdobbiadene':
        return 'iwsc'
    return None


def entry(source, title, score, currency=None, amount=None, price_kind='exact', scale=100, span=''):
    years = set(re.findall(rf'\b{VINTAGE}\b', title))
    if len(years) != 1 or not 0 < float(score) <= scale:
        return None
    year = int(years.pop())
    title = ' '.join(re.sub(rf'\b{year}\b', '', title).replace(' • ', ' ').split()).strip(' ,–-')
    if not title:
        return None
    return {'title': title, 'year': year, 'source': source, 'score': float(score), 'scale': scale,
            'currency': currency if amount else None, 'amount': amount, 'price_kind': price_kind,
            'window_text': span}


def tuck_price(lines, index):
    for line in lines[index + 1:index + 3]:
        if match := re.fullmatch(rf'[^$:]+:\s*\$\s*({MONEY})', line):
            return match[1]
    return None


def publication_entries(kind, title, text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows = []
    if kind == 'suckling':
        for index, line in enumerate(lines):
            if match := re.fullmatch(r'(.+?)\s+[–—-]\s*JS\s*(\d{2,3})', line):
                rows.append(entry('James Suckling', match[1], match[2], 'USD', tuck_price(lines, index)))
    elif kind == 'parker':
        for line in lines:
            if match := re.fullmatch(rf'({VINTAGE} .+)\s+\(([^()]*)\)', line):
                marks = re.search(r'(?:^|,\s*)(\d{2,3}) points?(?:,|$)', match[2], re.I)
                price = re.search(rf'\$\s*({MONEY})', match[2])
                if marks and price:
                    rows.append(entry('Robert Parker Wine Advocate', match[1], marks[1], 'USD', price[1]))
    elif kind == 'atkin':
        # The date and score can render on adjacent lines.
        for i in range(len(lines) - 1, 0, -1):
            if re.fullmatch(r'\d{2,3}', lines[i]) and ATKIN_DATE.search(lines[i - 1]):
                lines[i - 1:i + 1] = [lines[i - 1] + ' ' + lines[i]]
        starts = [i for i, line in enumerate(lines[1:], 1)
                  if re.match(rf'^{VINTAGE}\s+\S', line) and ATKIN_DATE.search(lines[i - 1])]
        for pos, i in enumerate(starts):
            mark = re.search(r'\s(\d{2,3})$', lines[i - 1])
            end = starts[pos + 1] - 1 if pos + 1 < len(starts) else len(lines)
            body = '\n'.join(lines[i + 1:end])
            price = re.match(rf'^\(\s*£({MONEY})(?:\s*[-–]\s*£({MONEY}))?\s*,', body)
            if mark:
                amount = (price[2] or price[1]) if price else None
                price_kind = 'upper_bound' if price and price[2] else 'exact'
                rows.append(entry('Tim Atkin', lines[i], mark[1], 'GBP', amount, price_kind, span=body))
    elif kind == 'dwwa':
        for i, line in enumerate(lines):
            mark = re.fullmatch(r'(\d{2,3}) points,\s*Value Gold', line, re.I)
            if mark:
                for heading in reversed(lines[max(0, i - 5):i]):
                    if len(heading) < 190 and heading.count(',') >= 2 and re.search(rf'\b{VINTAGE}$', heading):
                        rows.append(entry('Decanter World Wine Awards', heading, mark[1], 'GBP', 15, 'upper_bound'))
                        break
    elif kind == 'wine_spirits':
        for i, line in enumerate(lines[2:], 2):
            mark = re.fullmatch(rf'(\d{{2,3}})\s*\|\s*\$({MONEY})', line)
            if mark:
                heading = lines[i - 1]
                if re.match(rf'^{VINTAGE}\b', heading) and len(lines[i - 2]) < 90:
                    heading = lines[i - 2] + ' ' + heading
                rows.append(entry('Wine & Spirits', heading.replace('(Best Buy)', ''), mark[1], 'USD', mark[2]))
    elif kind == 'jancis':
        marks = {m[1] for m in re.finditer(r'\b(\d{2}(?:\.\d+)?)\s*/\s*20\b', text)}
        price = re.search(rf'\bFrom\s+€\s*({MONEY})', text)
        if len(marks) == 1:
            rows.append(entry('Jancis Robinson', title, marks.pop(), 'EUR', price[1] if price else None, 'starting_price',
                              scale=20, span=text))
    elif kind == 'botti':
        for block in re.split(r'(?mi)^Varenr\s*:', text)[1:]:
            wine = re.search(r'(?mi)^Vin\s*:\s*([^\n]+)', block)
            mark = re.search(r'(?mi)^Poeng\s*:\s*(\d{2,3})(?:\s|$)', block)
            price = re.search(r'(?mi)^Pris\s*:\s*(\d[\d \u00a0]*)(?:,(\d{2}|[–-]))?\s*kr\b', block)
            if wine and mark:
                amount = None
                if price:
                    major = re.sub(r'\s+', '', price[1])
                    minor = price[2] if (price[2] or '').isdigit() else '00'
                    amount = float(f'{major}.{minor}')
                rows.append(entry('BOTTI', wine[1], mark[1], 'NOK', amount))
    elif kind == 'iwsc':
        # Use the printed score beside the vintage, not the medal category.
        for match in re.finditer(
                rf'\)\s+(?:and\s+)?([A-Z][^().\n]{{2,100}}?\b{VINTAGE})\s+\((\d{{2,3}})\s+points\)', text):
            rows.append(entry('IWSC', match[1], match[2]))
    return [row for row in rows if row is not None]
