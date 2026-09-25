"""In-memory graph backend (same interface as TigerGraphStore). Used when TigerGraph is not configured."""
import json, os

def _ntype(i):
    for p, t in (("CU_", "customer"), ("DV_", "device"), ("CD_", "card"), ("TX_", "tx"), ("AC_", "account")):
        if str(i).startswith(p): return t
    return "case"

class LocalStore:
    name = "local (in-memory)"
    def __init__(s, ds, path=None):
        s.ds, s.path, s.note = ds, path, ""; s.tx = {t["id"]: t for t in ds["txs"]}; s.cu = ds["customers"]; s.dev_c = {}
        for c, v in s.cu.items():
            for d in v["devices"]: s.dev_c.setdefault(d, set()).add(c)
        s.hist = {h["id"]: dict(h) for h in ds["hist"]}; s.cases = dict(s.hist); s.states = {}; s._load()
    def ping(s): return True
    def patterns(s): return s.ds["patterns"]
    def policies(s): return s.ds["policies"]
    def bench_list(s):
        return [dict(id=b["id"], tx_id=b["tx_id"], trigger=b["trigger"], cust=s.tx[b["tx_id"]]["cust"], bank_risk=s.tx[b["tx_id"]]["bank_risk"], status=s.states.get(b["id"], {}).get("status", "Open")) for b in s.ds["bench"]]
    def bench_case(s, cid): return next(x for x in s.bench_list() if x["id"] == cid)
    def tx_context(s, tid):
        t = s.tx[tid]; return dict(tx=dict(t), customer=s.customer(t["cust"]))
    def customer(s, cid): c = s.cu[cid]; return dict(id=cid, mean=c["mean"], std=c["std"], n_tx=c.get("n_tx", 0))
    def devices_of(s, c): return sorted(s.cu[c]["devices"])
    def customers_on(s, d): return sorted(s.dev_c.get(d, ()))
    def cards_of(s, c): return [s.cu[c]["card"]]
    def cases_of(s, custs, exclude=""):
        cs = set(custs); return [dict(k) for k in s.cases.values() if k.get("cust") in cs and k.get("closed") and k["id"] != exclude]
    def all_closed(s, exclude=""): return [dict(k) for k in s.cases.values() if k.get("closed") and k["id"] != exclude]
    def get_case(s, cid): return s.cases.get(cid)
    def write_case(s, rec): s.cases[rec["id"]] = {**s.cases.get(rec["id"], {}), **rec}; s._save(); return True
    def get_state(s, cid): return dict(s.states.get(cid, {}))
    def set_state(s, cid, st): s.states[cid] = st; s._save()
    def reset(s): s.cases = dict(s.hist); s.states = {}; s._save()
    def expand(s, nid):
        t = _ntype(nid); N, E, det = [], [], {}
        n = lambda i, ty, sus=False: N.append(dict(id=i, type=ty, label=i if ty != "card" else "Card", sus=sus))
        if t == "customer" and nid in s.cu:
            c = s.cu[nid]; det = dict(type="Customer", id=nid, card=c["card"], baseline=f"{c['mean']}±{c['std']}", devices=sorted(c["devices"]))
            n(c["card"], "card"); E.append((c["card"], nid, "owned by"))
            for d in sorted(c["devices"]): n(d, "device"); E.append((nid, d, "uses"))
            for k in s.cases_of([nid]): n(k["id"], "case", "Confirmed" in k.get("outcome", "")); E.append((nid, k["id"], k.get("outcome", "")))
        elif t == "device":
            cs = s.customers_on(nid); det = dict(type="Device", id=nid, customers=len(cs), linked=cs[:10])
            for x in cs[:8]: n(x, "customer", len(cs) >= 5); E.append((nid, x, "shared by"))
        elif t == "card":
            o = next((k for k, v in s.cu.items() if v["card"] == nid), None); det = dict(type="Card", id=nid, owner=o)
            if o: n(o, "customer"); E.append((nid, o, "owned by"))
        elif t == "tx" and nid in s.tx:
            x = s.tx[nid]; det = dict(type="Transaction", id=nid, amount=x["amt"], customer=x["cust"], device=x["dev"], bank_risk=x["bank_risk"])
            n(x["cust"], "customer"); n(x["dev"], "device"); E += [(nid, x["cust"], "by"), (nid, x["dev"], "used device")]
        elif nid in s.cases or nid in {b["id"] for b in s.ds["bench"]}:
            k = s.cases.get(nid) or {}; cu = k.get("cust") or s.bench_case(nid)["cust"]; det = dict(type="Case", id=nid, customer=cu, outcome=k.get("outcome") or k.get("status", "open"), pattern=k.get("pattern", ""))
            n(cu, "customer"); E.append((nid, cu, "about"))
        else: raise KeyError(nid)
        return dict(details=det, nodes=N, edges=[dict(s=a, t=b, l=l) for a, b, l in E])
    def _save(s):
        if not s.path: return
        try:
            with open(s.path, "w") as f: json.dump(dict(cases={k: v for k, v in s.cases.items() if k not in s.hist}, states=s.states), f)
        except OSError: pass
    def _load(s):
        try:
            d = json.load(open(s.path)); s.cases.update(d.get("cases", {})); s.states = d.get("states", {})
        except (OSError, ValueError, TypeError): pass
