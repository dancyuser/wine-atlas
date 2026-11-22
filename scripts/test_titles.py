#!/usr/bin/env python3
"""Regressions for vendor slugs and normalized catalog titles."""
import json
import runpy
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
func=runpy.run_path(str(ROOT/"scripts"/"build_catalog.py"),run_name="wine_titles_contract")["wine_title"]
cases=[
 ("https://ast.wine/catalog/product/dow_s_late_bottled_vintage_port_5608309002876_43233/","Dow",True),
 ("https://vinissimo.biz/catalog/wine/kendall_jackson_vintners_reserve_chardonnay-1831018/","Kendall",True),
 ("https://spb.winestyle.ru/products/Vigna-Senza-Nome-Moscato-d-Asti-DOCG-2023-375.html","Vigna",True),
 ("https://spb.winestyle.ru/products/Bodegas-Ramon-Bilbao-Crianza-Rioja-DOC-2013-1500.html","Bodegas",True),
 ("https://spb.winestyle.ru/products/Lucien-Albrecht-Brut-Cremant-d-Alsace-AOC.html","Lucien",False)
]
for url,start,has_numbers in cases:
 name=func(url)
 assert name.startswith(start),(url,name)
 assert not re.search(r'(?<!\d)\d{5,}(?!\d)',name),(url,name)
 assert not re.search(r'(?:^|\s)(?:075|375|750|1500)$',name),(url,name)
 assert not re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)',name),(url,name)

obj=json.loads((ROOT/"data/wines.json").read_text(encoding="utf-8"))
overrides=json.loads((ROOT/"data/overrides.json").read_text(encoding="utf-8"))
by_id={w["id"]:w for w in obj["records"]}
for id_,title in {
 "c9f63273980c":"Dow’s Late Bottled Vintage Port (LBV)",
 "8433dbc66ae6":"Kendall-Jackson Vintner’s Reserve Chardonnay",
 "28bf2f843af7":"Braida Vigna Senza Nome Moscato d’Asti DOCG",
 "e8609b5a3c65":"Dulong Crémant de Bordeaux Brut AOP",
 "7c836f833ee2":"Lucien Albrecht Crémant d’Alsace Brut AOC",
}.items():
 assert by_id[id_]["title"]==title,(id_,by_id.get(id_,{}).get("title"))
 assert overrides[id_]["title"]==title,(id_,overrides[id_])
assert len(obj["records"])==124
print("TITLE REGRESSIONS PASSED",len(cases),"source slugs",len(overrides),"overrides")
