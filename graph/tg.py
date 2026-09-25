"""TigerGraph backend (pyTigerGraph + GSQL installed queries). Same interface as LocalStore."""
import os, json
from .local import _ntype

def _set(res, key):
    for r in res:
        if key in r: return [{**v["attributes"], "id": v["v_id"]} for v in r[key]]
    return []

class TigerGraphStore:
    name = "TigerGraph"
    def __init__(s):
        from pyTigerGraph import TigerGraphConnection as C
        host = os.environ["TG_HOST"]; s.g = os.getenv("TG_GRAPH", "FraudX"); s.note = ""
        s.c = C(host=host, graphname=s.g, username=os.getenv("TG_USER", "tigergraph"), password=os.getenv("TG_PASSWORD", ""), tgCloud="tgcloud" in host)
        if os.getenv("TG_TOKEN"): s.c.apiToken = os.environ["TG_TOKEN"]
        elif os.getenv("TG_SECRET"): s.c.getToken(os.environ["TG_SECRET"])
    def ping(s): s.c.echo(); return True
    def _q(s, name, params): return s.c.runInstalledQuery(name, params)
    def _v(s, vt, i):
        r = s.c.getVerticesById(vt, i); return r[0]["attributes"] if r else None
    # ---- setup / ingest ----
    def install(s):
        s.c.gsql(open(os.path.join(os.path.dirname(__file__), "schema.gsql")).read())
    def ingest(s, ds, batch=5000):
        up = lambda vt, rows: [s.c.upsertVertices(vt, rows[i:i + batch]) for i in range(0, len(rows), batch)]
        ue = lambda a, e, b, rows: [s.c.upsertEdges(a, e, b, rows[i:i + batch]) for i in range(0, len(rows), batch)]
        cu = ds["customers"]; txs = [t for t in ds["txs"]]
        up("Customer", [(c, dict(mean_amt=v["mean"], std_amt=v["std"], n_tx=v.get("n_tx", 0))) for c, v in cu.items()])
        up("Card", [(v["card"], {}) for v in cu.values()]); up("Account", [(v["acct"], {}) for v in cu.values()])
        up("Device", [(d, {}) for d in {d for v in cu.values() for d in v["devices"]} | {t["dev"] for t in txs if t.get("dev")}])
        up("Transaction", [(t["id"], dict(amt=t["amt"], ts=t["ts"], bank_risk=t["bank_risk"], fails=int(t["fails"]), vel=int(t["vel"]), new_dev=int(t["new_dev"]))) for t in txs])
        ue("Customer", "OWNS", "Card", [(c, v["card"]) for c, v in cu.items()]); ue("Customer", "HAS_ACCOUNT", "Account", [(c, v["acct"]) for c, v in cu.items()])
        ue("Customer", "USES_DEVICE", "Device", [(c, d) for c, v in cu.items() for d in v["devices"]])
        ue("Customer", "MADE", "Transaction", [(t["cust"], t["id"]) for t in txs]); ue("Transaction", "TX_CARD", "Card", [(t["id"], t["card"]) for t in txs])
        ue("Transaction", "TX_DEVICE", "Device", [(t["id"], t["dev"]) for t in txs if t.get("dev")])
        up("Pattern", [(p["id"], dict(name=p["name"], requires=p["requires"], anyof=p["anyof"], descr=p["desc"])) for p in ds["patterns"]])
        up("Policy", [(p["id"], dict(title=p["title"], body=p["text"], tags=p.get("tags", ""))) for p in ds["policies"]])
        rows = [(h["id"], dict(tx_id=h.get("tx_id", ""), cust_id=h["cust"], status="Closed", pattern=h.get("pattern", ""), outcome=h["outcome"], summary=h.get("summary", ""), is_benchmark=False, closed=True, state_json="{}", record_json="")) for h in ds["hist"]]
        txc = {t["id"]: t for t in txs}
        rows += [(b["id"], dict(tx_id=b["tx_id"], cust_id=txc[b["tx_id"]]["cust"], trigger_type=b["trigger"], status="Open", is_benchmark=True, closed=False, bank_risk=txc[b["tx_id"]]["bank_risk"], state_json="{}", record_json="")) for b in ds["bench"]]
        up("FraudCase", rows); ue("Customer", "HAS_CASE", "FraudCase", [(r[1]["cust_id"], r[0]) for r in rows])
        ue("FraudCase", "FOR_TX", "Transaction", [(r[0], r[1]["tx_id"]) for r in rows if r[1]["tx_id"]])
    # ---- reads ----
    def patterns(s): return [dict(id=v["v_id"], name=v["attributes"]["name"], requires=v["attributes"]["requires"], anyof=v["attributes"]["anyof"], desc=v["attributes"]["descr"]) for v in s.c.getVertices("Pattern")]
    def policies(s): return [dict(id=v["v_id"], title=v["attributes"]["title"], text=v["attributes"]["body"], tags=v["attributes"]["tags"]) for v in s.c.getVertices("Policy")]
    def _case(s, a): return dict(a, cust=a.get("cust_id"))
    def bench_list(s):
        out = []
        for v in s.c.getVertices("FraudCase", limit=5000):
            a = v["attributes"]
            if a.get("is_benchmark"): out.append(dict(id=v["v_id"], tx_id=a["tx_id"], trigger=a["trigger_type"], cust=a["cust_id"], bank_risk=a["bank_risk"], status=(json.loads(a.get("state_json") or "{}")).get("status", "Open")))
        return sorted(out, key=lambda x: x["id"])
    def bench_case(s, cid):
        a = s._v("FraudCase", cid)
        if not a or not a.get("is_benchmark"): raise KeyError(cid)
        return dict(id=cid, tx_id=a["tx_id"], trigger=a["trigger_type"], cust=a["cust_id"], bank_risk=a["bank_risk"])
    def tx_context(s, tid):
        r = s._q("tx_context", {"t": tid}); t = _set(r, "Start"); C = _set(r, "C"); D = _set(r, "D"); K = _set(r, "K")
        if not t or not C: raise KeyError(tid)
        t, c = t[0], C[0]
        return dict(tx=dict(id=tid, cust=c["id"], card=K[0]["id"] if K else None, dev=D[0]["id"] if D else None, amt=t["amt"], ts=t["ts"], bank_risk=t["bank_risk"], fails=t["fails"], vel=t["vel"], new_dev=t["new_dev"]), customer=dict(id=c["id"], mean=c["mean_amt"], std=c["std_amt"], n_tx=c["n_tx"]))
    def customer(s, cid): a = s._v("Customer", cid); return dict(id=cid, mean=a["mean_amt"], std=a["std_amt"], n_tx=a["n_tx"])
    def devices_of(s, c): return sorted(d["id"] for d in _set(s._q("devices_of_customer", {"c": c}), "D"))
    def customers_on(s, d): return sorted(x["id"] for x in _set(s._q("customers_on_device", {"d": d}), "O"))
    def cards_of(s, c): return [e["to_id"] for e in s.c.getEdges("Customer", c, "OWNS")]
    def cases_of(s, custs, exclude=""): return [s._case(k) for k in _set(s._q("closed_cases", {"cs": list(custs)}), "K") if k["id"] != exclude]
    def all_closed(s, exclude=""): return [s._case(dict(v["attributes"], id=v["v_id"])) for v in s.c.getVertices("FraudCase", limit=5000) if v["attributes"].get("closed") and v["v_id"] != exclude]
    def get_case(s, cid):
        a = s._v("FraudCase", cid)
        if not a: return None
        base = json.loads(a["record_json"]) if a.get("record_json") else {}
        return {**s._case(a), **base, "id": cid}
    def get_state(s, cid): a = s._v("FraudCase", cid); return json.loads(a.get("state_json") or "{}") if a else {}
    def set_state(s, cid, st): s.c.upsertVertex("FraudCase", cid, dict(state_json=json.dumps(st)))
    # ---- writes: case, evidence, action, pattern and policy links ----
    def write_case(s, r):
        cid = r["id"]; a = dict(record_json=json.dumps(r, default=str))
        for k, f in dict(tx_id="tx_id", cust="cust_id", trigger="trigger_type", status="status", risk="risk", confidence="confidence", pattern="pattern", outcome="outcome", summary="summary", is_benchmark="is_benchmark", closed="closed", bank_risk="bank_risk").items():
            if r.get(k) is not None: a[f] = r[k]
        s.c.upsertVertex("FraudCase", cid, a)
        if r.get("cust"): s.c.upsertEdge("Customer", r["cust"], "HAS_CASE", "FraudCase", cid)
        if r.get("tx_id"): s.c.upsertEdge("FraudCase", cid, "FOR_TX", "Transaction", r["tx_id"])
        for e in r.get("evidence", []):
            eid = f"EV_{cid}_{e['key']}"; s.c.upsertVertex("Evidence", eid, dict(kind=e["cat"], text=e["text"], weight=e["weight"])); s.c.upsertEdge("FraudCase", cid, "HAS_EVIDENCE", "Evidence", eid)
        if r.get("action"):
            aid = f"AC_{cid}"; s.c.upsertVertex("CaseAction", aid, dict(action=r["action"], approval=str(r.get("approval", ""))[:200], policy=",".join(r.get("policies", [])), executed=str(r.get("executed", ""))))
            s.c.upsertEdge("FraudCase", cid, "RESULTED_IN", "CaseAction", aid)
        for pid in r.get("pattern_ids", []): s.c.upsertEdge("FraudCase", cid, "MATCHES_PATTERN", "Pattern", pid)
        for pid in r.get("policies", []): s.c.upsertEdge("FraudCase", cid, "CITES_POLICY", "Policy", pid)
        return True
    def reset(s):
        for b in s.bench_list(): s.c.upsertVertex("FraudCase", b["id"], dict(closed=False, status="Open", outcome="", state_json="{}"))
    def expand(s, nid):
        vt = {"customer": "Customer", "device": "Device", "card": "Card", "tx": "Transaction", "account": "Account", "case": "FraudCase"}[_ntype(nid)]
        det = dict(type=vt, id=nid, **{k: v for k, v in (s._v(vt, nid) or {}).items() if k not in ("state_json", "record_json", "id")})
        N, E = [], []
        for e in s.c.getEdges(vt, nid)[:25]:
            o = e["to_id"]; ty = _ntype(o)
            if ty in ("account",): continue
            N.append(dict(id=o, type=ty, label=o if ty != "card" else "Card", sus=False)); E.append(dict(s=nid, t=o, l=e["e_type"]))
        return dict(details=det, nodes=N, edges=E)
