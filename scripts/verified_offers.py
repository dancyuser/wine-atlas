#!/usr/bin/env python3
"""Conservative exact-bottle verification for public retailer JSON-LD offers.

Never use a redirected variant, an unreviewed merchant, a different vintage or
bottle volume as evidence of a current wine offer.
"""
import html
import json
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit


class ProductSchemaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.blocks = []
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.capture = True
            self.buffer = []

    def handle_data(self, data):
        if self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.capture:
            self.blocks.append("".join(self.buffer))
            self.capture = False
            self.buffer = []


def canonical_url(value):
    try:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            return None
        return (url.hostname.lower(), unquote(url.path).rstrip("/") or "/", url.query)
    except (TypeError, ValueError):
        return None


def product_nodes(text):
    parser = ProductSchemaParser()
    parser.feed(text)
    for block in parser.blocks:
        try:
            data = json.loads(html.unescape(block))
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
            kinds = node.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if isinstance(kinds, list) and any(str(t).split("/")[-1].lower() == "product" for t in kinds):
                yield node


def words(s):
    normalized = unicodedata.normalize("NFKD", str(s or "").casefold())
    normalized = "".join(x for x in normalized if not unicodedata.combining(x))
    normalized = normalized.replace("ё", "е").replace("’", "'")
    stop = {"wine", "вино", "port", "porto", "портвейн", "late", "bottled",
            "vintage", "reserve", "reserva", "the", "of", "and", "de", "la", "do"}
    tokens = {x for x in re.findall(r"[a-zа-я]{3,}", normalized) if x not in stop}
    if re.search(r"\blate\s+bottled\s+vintage\b", normalized):
        tokens.add("lbv")
    return tokens


def identity_years(text):
    # Reject contradictory vintages rather than looking for one favorable mention.
    return {int(m) for m in re.findall(r"(?<!\d)(?:19\d{2}|20\d{2})(?!\d)", text)}


def identity_volumes(text):
    text = text.casefold().replace(",", ".")
    found = set()
    liters = r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:л|l|литр(?:а|ов)?|lit(?:re|er)s?)(?![\w])"
    milliliters = r"(?<!\d)(\d+)\s*(?:мл|ml|миллилитр(?:а|ов)?)(?![\w])"
    for volume in re.findall(liters, text):
        found.add(round(float(volume) * 1000))
    for volume in re.findall(milliliters, text):
        found.add(int(volume))
    return found


def exact_vintage(text, year):
    return year is not None and identity_years(text) == {int(year)}


def exact_volume(text, volume_l):
    return (isinstance(volume_l, (int, float)) and volume_l > 0
            and identity_volumes(text) == {round(volume_l * 1000)})


def numeric_price(value):
    try:
        v = float(str(value).strip().replace(" ", "").replace(",", "."))
        return round(v) if 100 <= v <= 1_000_000 else None
    except (ValueError, TypeError):
        return None


def availability(value):
    name = str(value or "").split("/")[-1].split("#")[-1].lower()
    if name == "instock":
        return "in_stock"
    if name in {"outofstock", "discontinued", "soldout"}:
        return "out_of_stock"
    return "unknown"


def verified_offer(text, record, original_url, final_url):
    """Return (offer, reason), never a plausible but unverified product match."""
    review = record.get("publication_review") or {}
    if review.get("status") != "verified":
        return None, "no_manual_identity_review"
    canonical = canonical_url(original_url)
    if not canonical or canonical != canonical_url(final_url):
        return None, "redirected_to_different_product"
    if canonical != canonical_url(review.get("final_url")):
        return None, "reviewed_url_changed"
    year, volume = record.get("year"), record.get("volume_l")
    if year is None or volume is None:
        return None, "missing_identity_fields"
    title_words = words(record.get("title"))
    if not title_words:
        return None, "missing_product_title"
    candidates = []
    for product in product_nodes(text):
        name = str(product.get("name") or "")
        if product.get("url") and canonical_url(product["url"]) != canonical:
            continue
        overlap = len(title_words & words(name))
        if overlap < min(2, len(title_words)):
            continue
        evidence = " ".join(str(product.get(k) or "") for k in ("name", "description", "size"))
        if not exact_vintage(evidence, year) or not exact_volume(evidence, volume):
            continue
        offers = product.get("offers") or []
        offers = offers if isinstance(offers, list) else [offers]
        for offer in offers:
            if not isinstance(offer, dict) or offer.get("priceCurrency") not in {"RUB", "RUR"}:
                continue
            kinds = offer.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if kinds and not any(str(t).rsplit("/", 1)[-1].lower() == "offer" for t in kinds):
                continue
            if offer.get("url") and canonical_url(offer["url"]) != canonical:
                continue
            value = offer.get("price")
            if value is None and isinstance(offer.get("priceSpecification"), dict):
                value = offer["priceSpecification"].get("price")
            price = numeric_price(value)
            if price is None:
                continue
            old_price = None
            for key in ("oldPrice", "previousPrice", "originalPrice"):
                value = numeric_price(offer.get(key))
                if value is not None and value > price:
                    old_price = value
                    break
            candidates.append({
                "price_rub": price,
                "regular_price_rub": old_price,
                "availability": availability(offer.get("availability")),
                "product_name": name,
                "source_url": final_url,
                "verification_method": "exact_jsonld_product",
            })
    if not candidates:
        return None, "no_exact_identified_offer"
    unique = {(x["price_rub"], x["regular_price_rub"], x["availability"]) for x in candidates}
    if len(unique) != 1:
        return None, "ambiguous_product_offers"
    return candidates[0], "verified"
