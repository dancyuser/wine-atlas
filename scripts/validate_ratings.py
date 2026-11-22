#!/usr/bin/env python3
"""Validate independent ratings overlay. No external dependencies."""
import json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
catalog=json.loads((ROOT/"data/wines.json").read_text(encoding="utf-8"))
obj=json.loads((ROOT/"data/ratings.json").read_text(encoding="utf-8"))
items={r["id"]:r for r in catalog["records"]}
assert obj["version"]==1
count=0;vivino=0;scored=0
for key,rr in obj["records"].items():
    assert key in items,key
    assert isinstance(rr,list)
    seen=set()
    for s in rr:
        assert s["source"] and isinstance(s["source"],str)
        assert s["scale"] in (5,100)
        v=s["score"]
        assert isinstance(v,(float,int)) and not isinstance(v,bool)
        assert (1<=v<=5 if s["scale"]==5 else 0<=v<=100),(key,s)
        assert s["scope"] in ("vintage","all_vintages")
        if s["scope"]=="vintage":assert s["vintage"]==items[key]["year"],(key,s)
        else:assert s["vintage"] is None
        assert s["source_url"].startswith("https://")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}",s["observed_on"])
        uniq=(s["source"].casefold(),s["scope"],s["vintage"])
        assert uniq not in seen,(key,uniq)
        seen.add(uniq)
        if s["source"]=="Vivino":
            vivino+=1
            assert s["scale"]==5
        count+=1
    if any(s["scope"]=="vintage" for s in rr):scored+=1
assert scored>=51,(scored,count)
assert vivino>=5,(vivino,count)
print("RATINGS VALIDATED",count,"entries",scored,"rated wines",vivino,"Vivino matches")
