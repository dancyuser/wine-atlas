#!/usr/bin/env python3
"""Validate independent ratings overlay. No external dependencies."""
import json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
catalog=json.loads((ROOT/"data/wines.json").read_text(encoding="utf-8"))
obj=json.loads((ROOT/"data/ratings.json").read_text(encoding="utf-8"))
simple=json.loads((ROOT/"data/simplewine-catalog.json").read_text(encoding="utf-8"))
items={r["id"]:r for r in catalog["records"]+simple["records"]}
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
assert scored>=0,(scored,count)
assert vivino>=5,(vivino,count)
print("RATINGS VALIDATED",count,"entries",scored,"rated wines",vivino,"Vivino matches")

# The entire catalog has an explicit Vivino result or a documented unresolved status.
rated_ids={key for key,rr in obj["records"].items() if any(s["source"]=="Vivino" for s in rr)}
unrated=obj.get("unrated",{})
assert isinstance(unrated,dict)
assert rated_ids.isdisjoint(unrated),rated_ids.intersection(unrated)
assert rated_ids|set(unrated)==set(items),set(items)-(rated_ids|set(unrated))
for key,u in unrated.items():
    assert u["status"] in ("insufficient_ratings","unverified_score","ambiguous_product","no_verified_match")
    assert isinstance(u.get("reason"),str) and len(u["reason"])>=20
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}",u["checked_on"])
    assert u.get("source_url") is None or u["source_url"].startswith("https://www.vivino.com/")
assert len(rated_ids)+len(unrated)==len(items), 'All active entries must have scored or unresolved Vivino status'
print("VIVINO AUDIT",len(rated_ids),"scored",len(unrated),"unresolved",len(items),"covered")
