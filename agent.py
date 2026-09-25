"""FraudX investigation agent: state-driven tool loop over the graph tools, GraphRAG policy retrieval, policy-gated next best action."""
import os, json, time, requests
from datetime import datetime, timedelta
from data import is_fraud

NEEDS_APPROVAL = {"TEMPORARY CARD BLOCK", "FILE SAR"}
ACT_Q = {"TEMPORARY CARD BLOCK": "temporary card block requires fraud analyst approval", "REQUEST STEP-UP AUTH": "inconclusive evidence step-up authentication verification before block",
         "ALLOW": "low risk allow monitor", "ALLOW + MONITOR": "low risk allow monitor", "ESCALATE TO ANALYST": "escalate analyst high financial impact"}
SIM = "(simulated)"

def _summ(n, r):
    if n == "get_transaction_context": t = r["tx"]; return f"{t['id']}: ${t['amt']}, device {t['dev']}, bank risk {t['bank_risk']}"
    if n == "get_customer_history": return f"baseline ${r['customer']['mean']}±{r['customer']['std']}, {len(r['devices'])} known device(s)"
    if n == "find_shared_devices": return "; ".join(f"{d['device']}: {d['other_customers']} other customers" for d in r)
    if n == "find_connected_customers": return f"{len(r)} customers: {', '.join(r[:5])}"
    if n == "find_prior_cases": return f"{len(r)} closed cases ({sum(1 for c in r if is_fraud(c.get('outcome')))} confirmed fraud)"
    if n == "find_fraud_patterns": return ", ".join(p["name"] for p in r) or "no known pattern"
    if n == "search_policy": return ", ".join(f"{p['id']} ({p['score']})" for p in r)
    if n == "find_similar_cases": return f"{len(r)} similar closed cases"
    return "ok"

def assess(ev, tx, verified, ring):
    keys = {e["key"] for e in ev}; p = sum(e["weight"] for e in ev)
    if verified == "fraud": p = max(p, .6) + .35
    elif verified == "legit": p *= .2
    p = round(max(0, min(p, .99)), 2); unc = (.35 < p < .8) and not verified
    conf = round(max(.5, min(.97, .5 + abs(p - .5) * .95 - (.12 if unc else 0))), 2)
    risk = "HIGH" if p >= .7 else "MEDIUM" if p >= .35 else "LOW"
    ftype = "Coordinated / fraud ring" if ring else "Account takeover" if ({"auth", "newdev"} & keys) and p > .4 else "Card fraud" if p > .5 else "Likely legitimate"
    if p >= .8 or verified == "fraud": pick = "TEMPORARY CARD BLOCK"
    elif unc: pick = "REQUEST STEP-UP AUTH"
    elif p < .35: pick = "ALLOW" if p < .2 else "ALLOW + MONITOR"
    else: pick = "ESCALATE TO ANALYST"
    sar = p >= .85 and ring
    raw = [("ALLOW", 1 - p, "Behaviour consistent with the customer's baseline.", False), ("ALLOW + MONITOR", .6 - abs(p - .3), "Some legitimate behaviour; low residual risk.", False),
           ("REQUEST STEP-UP AUTH", (.95 - abs(p - .58)) if unc else .2, "Evidence incomplete; verification would resolve the uncertainty.", False),
           ("TEMPORARY CARD BLOCK", p * (1 if (p >= .8 or verified) else .7), "High-risk connected entities or verified fraud.", True),
           ("ESCALATE TO ANALYST", .45 + p * .35 + (.1 if tx["amt"] > 800 else 0), "Material risk or high financial impact needs analyst review.", False),
           ("FILE SAR", .9 if sar else .1, "Coordinated activity with high confidence triggers reporting.", True)]
    opts = sorted([dict(action=a, score=round(max(0, min(1, s)), 2), reason=r, approval=ap, chosen=(a == pick)) for a, s, r, ap in raw], key=lambda o: -o["score"])
    return dict(p=p, risk=risk, confidence=conf, uncertainty="High" if unc else "Low" if conf > .8 else "Medium", ftype=ftype, nba=pick, sar=sar, options=opts, ring=ring,
                missing=[] if (verified or not unc) else ["Cardholder verification", "Device ownership confirmation"], sufficient=not unc)

def _llm_pick(out, S, ev):
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key: return None
    try:
        msg = f"Known: {[e['text'] for e in ev]}; done: {[k for k in S if k in ('hist','shared','conn','prior')]}. Choose the most informative next tool from: {[o[0] for o in out]}. Reply JSON {{\"tool\":name}}."
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=6,
                          json=dict(model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), temperature=0, max_tokens=40, response_format={"type": "json_object"}, messages=[{"role": "user", "content": msg}]))
        t = json.loads(r.json()["choices"][0]["message"]["content"])["tool"]
        return next((o for o in out if o[0] == t), None)
    except Exception: return None

def investigate(st, T, cid, verified=None, removed=(), persist=True, llm=None):
    llm = os.getenv("AGENT_LLM_PLANNER") == "1" if llm is None else llm
    c = st.bench_case(cid); state = st.get_state(cid); rem = set(removed); ev, trace, S = [], [], {}
    def add(key, cat, w, text):
        if key not in rem: ev.append(dict(key=key, cat=cat, weight=round(w, 2), text=text))
    gp = lambda: min(.99, sum(e["weight"] for e in ev if e["key"] != "verify"))
    ring = lambda: {"device"} <= {e["key"] for e in ev} and bool({"prior", "velocity"} & {e["key"] for e in ev})
    if persist and not st.get_case(cid):
        T.create_case(dict(id=cid, tx_id=c["tx_id"], cust=c["cust"], trigger=c["trigger"], status="Under Investigation", is_benchmark=True, closed=False, bank_risk=c["bank_risk"]))
    if verified:
        trace.append(dict(tool="cardholder_verification", args={"result": verified}, why="Controlled evidence request answered " + SIM, result=("Cardholder DENIED the transaction" if verified == "fraud" else "Cardholder CONFIRMED the transaction"), ms=0, p=0))
    def cands():
        if "ctx" not in S: return [("get_transaction_context", {"tx_id": c["tx_id"]}, "Start by examining the flagged transaction", 1.0)]
        cu, dv, out = S["cust"], S["dev"], []
        if gp() < .8:
            if "hist" not in S: out.append(("get_customer_history", {"customer_id": cu}, "Need the customer's baseline to judge amount and behaviour", .7))
            if "shared" not in S and dv: out.append(("find_shared_devices", {"customer_id": cu, "device_id": dv}, "Check whether this device is shared with other customers", .6 + (.3 if S["tx"]["bank_risk"] > .85 else 0) + (.2 if S["tx"]["new_dev"] else 0)))
            if S.get("shared_n", 0) >= 3 and "conn" not in S: out.append(("find_connected_customers", {"device_id": dv}, "The device links several customers - identify them", .95))
            if "prior" not in S and ("hist" in S or "shared" in S): out.append(("find_prior_cases", {"customer_ids": [cu] + S.get("conn", [])[:25], "exclude": cid}, "Have these customers appeared in prior investigations?", .9 if "conn" in S else .35))
        if out: return out
        if "pat" not in S: return [("find_fraud_patterns", {"evidence_keys": [e["key"] for e in ev]}, "Match the evidence against known fraud patterns", 1)]
        if "pol" not in S:
            S["a0"] = assess(ev, S["tx"], verified, ring()); q = ACT_Q[S["a0"]["nba"]] + (" suspicious activity report coordinated" if S["a0"]["sar"] else "")
            return [("search_policy", {"query": q, "k": 3}, f"GraphRAG: retrieve policy for the candidate action ({S['a0']['nba']})", 1)]
        if "mem" not in S:
            pn = S["pat"][0]["name"] if S["pat"] else ""
            return [("find_similar_cases", {"case_id": cid, "customer_id": cu, "device_id": dv or "", "pattern": pn}, "Case memory: retrieve similar closed investigations", 1)]
        return []
    stopped = False
    for _ in range(12):
        out = cands()
        if not out: break
        pick = (_llm_pick(out, S, ev) if llm and len(out) > 1 else None) or max(out, key=lambda o: o[3])
        name, args, why, _s = pick; t0 = time.time(); res = T.call(name, args); ms = int((time.time() - t0) * 1000)
        if name == "get_transaction_context":
            tx = res["tx"]; S.update(ctx=res, tx=tx, cust=tx["cust"], dev=tx["dev"], cu=res["customer"])
            if tx["vel"] >= 4: add("velocity", "Transaction behavior", .15, f"{tx['vel']} transactions in the last hour (baseline ≈1).")
            if tx["fails"] >= 2: add("auth", "Customer history", .15, f"{tx['fails']} failed authentication attempts before the transaction.")
            if tx["new_dev"]: add("newdev", "Device analysis", .10, f"Device {tx['dev']} had never been used by this customer before.")
        elif name == "get_customer_history":
            S["hist"] = res; cu = res["customer"]; z = (S["tx"]["amt"] - cu["mean"]) / max(cu["std"], .1 * cu["mean"], 1)
            if z > 2 and cu["n_tx"] >= 5: add("amount", "Transaction behavior", min(z / 4, 1) * .25, f"Amount {S['tx']['amt']} is {z:.1f}σ above the customer's normal ({cu['mean']}±{cu['std']}).")
        elif name == "find_shared_devices":
            S["shared"] = res; e = next((d for d in res if d["device"] == S["dev"]), None); S["shared_n"] = e["other_customers"] if e else 0
            if S["shared_n"] >= 4: add("device", "Device analysis", .30 * min(S["shared_n"] / 5, 1), f"Device {S['dev']} is linked to {S['shared_n']} other customers.")
        elif name == "find_connected_customers": S["conn"] = [x for x in res if x != S["cust"]]
        elif name == "find_prior_cases":
            S["prior"] = res; pf = [k for k in res if is_fraud(k.get("outcome"))]
            if pf: add("prior", "Historical cases", .25 * min(len(pf) / 2, 1), f"{len(pf)} confirmed fraud case(s) among this customer and connected customers ({', '.join(k['id'] for k in pf[:4])}).")
        elif name == "find_fraud_patterns": S["pat"] = res
        elif name == "search_policy": S["pol"] = res
        elif name == "find_similar_cases": S["mem"] = res
        if verified and "tx" in S and not any(e["key"] == "verify" for e in ev):
            add("verify", "Cardholder verification", .35 if verified == "fraud" else -.5, "Cardholder DENIED the transaction." if verified == "fraud" else "Cardholder CONFIRMED the transaction.")
        trace.append(dict(tool=name, args=args if name != "find_prior_cases" else dict(args, customer_ids=f"{len(args['customer_ids'])} customers"), why=why, result=_summ(name, res), ms=ms, p=round(gp(), 2)))
    stopped = gp() >= .8 and not all(k in S for k in ("hist", "shared", "prior"))
    tx = S["tx"]; a = assess(ev, tx, verified, ring()); pol = S.get("pol", []); pat = S.get("pat", []); mem = S.get("mem", [])
    top = pol[0] if pol else dict(id="P-?", title="", text="")
    sarp = next((p for p in pol if "sar" in (p["title"] + p["text"]).lower() or "suspicious" in (p["title"] + p["text"]).lower()), top)
    need = a["nba"] in NEEDS_APPROVAL or a["sar"]
    a["approval"] = dict(required=need, policy=f"{(sarp if a['sar'] and a['nba'] not in NEEDS_APPROVAL else top)['id']}: " + ((sarp if a['sar'] and a['nba'] not in NEEDS_APPROVAL else top)["text"][:150]) if pol else "No policy retrieved",
                         policy_id=(sarp if a["sar"] and a["nba"] not in NEEDS_APPROVAL else top)["id"], route="Fraud analyst → Team lead" if a["sar"] else "Fraud analyst" if need else "None (auto-execute)")
    a.update(evidence=ev, patterns=pat, policies=pol, similar=mem, trace=trace, additional_actions=["FILE SAR"] if a["sar"] and a["nba"] != "FILE SAR" else [], sufficient_reason=None)
    a["stop_reason"] = ("Stopped early: evidence already decisive. " if stopped else "All relevant checks completed. ") + ("Enough evidence for a defensible action." if a["sufficient"] else "Still insufficient - requesting controlled evidence.")
    top4 = [e["text"] for e in sorted(ev, key=lambda e: -abs(e["weight"]))[:4]]
    a["why_points"] = top4 + ([f"{len(mem)} similar closed case(s) retrieved from case memory"] if mem else []) + [f"Policy {a['approval']['policy_id']} applies: {top['title']}" if top["title"] else "No matching policy passage"]
    a["why"] = f"{a['nba'].title()}: " + ("evidence is not yet sufficient to block; verification resolves the uncertainty." if a["nba"] == "REQUEST STEP-UP AUTH" else "risk exceeds the blocking threshold and policy-relevant evidence exists." if a["nba"] == "TEMPORARY CARD BLOCK" else "risk is low and consistent with the customer's behaviour." if a["nba"].startswith("ALLOW") else "risk is material but not conclusive; analyst judgement is needed.")
    conn = S.get("conn", []); rel = [tx["cust"], tx["dev"]] + conn[:6]
    keys = {e["key"] for e in ev}
    if state.get("status") in (None, "Open"): state["status"] = "Under Investigation"
    if verified: state["verified"] = verified
    written = dict(backend=st.name, ok=False, error=None)
    if persist:
        st.set_state(cid, state)
        rec = dict(id=cid, tx_id=c["tx_id"], cust=c["cust"], trigger=c["trigger"], status=state["status"], risk=a["risk"], confidence=a["confidence"], pattern=pat[0]["name"] if pat else a["ftype"], pattern_ids=[p["id"] for p in pat],
                   evidence=ev, findings=a["ftype"], action=a["nba"], approval=a["approval"]["policy"], policies=[p["id"] for p in pol[:2]], related=rel, executed=state.get("executed", ""), summary=a["why"],
                   is_benchmark=True, closed=state["status"] == "Closed", outcome=state.get("outcome", ""), bank_risk=c["bank_risk"])
        try: written["ok"] = bool(T.update_case(cid, rec)["ok"])
        except Exception as e: written["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    return dict(case=dict(id=cid, tx=c["tx_id"], cust=c["cust"], amt=tx["amt"], dev=tx["dev"], card=tx["card"], trigger=c["trigger"], bank_risk=c["bank_risk"], status=state["status"], verified=state.get("verified")),
                assessment=a, graph=_graph(S, a), timeline=_timeline(c, S, a), counterfactual_keys=[e["key"] for e in ev if e["key"] != "verify"], state=state, written=written, keys=sorted(keys))

def _graph(S, a):
    tx = S["tx"]; N, E = {}, []
    def add(i, t, l=None, sus=False): N.setdefault(i, dict(id=i, type=t, label=l or i, sus=sus))
    add(tx["id"], "tx", sus=True); add(tx["card"], "card", "Card"); add(tx["cust"], "customer"); add(tx["dev"], "device", sus=a["ring"])
    E += [(tx["id"], tx["card"], "made with"), (tx["card"], tx["cust"], "owned by"), (tx["id"], tx["dev"], "used device")]
    prior = S.get("prior", []); pc = {k["cust"] for k in prior}; conn = sorted(S.get("conn", []), key=lambda o: o not in pc)[:7]
    for o in conn: add(o, "customer", sus=True); E.append((tx["dev"], o, "shared by"))
    for k in prior[:14]:
        if k["cust"] in N: add(k["id"], "case", sus=is_fraud(k.get("outcome"))); E.append((k["cust"], k["id"], k.get("outcome", "")))
    first = next((o for o in conn if o in pc), None)
    path = [tx["id"], tx["dev"]] + ([first] + [k["id"] for k in prior if k["cust"] == first] if first else [])
    return dict(nodes=list(N.values()), edges=[dict(s=s, t=t, l=l) for s, t, l in E], path=path)

def _timeline(c, S, a):
    tx = S["tx"]; k = int(''.join(ch for ch in c["id"] if ch.isdigit()) or 1); t0 = datetime(2026, 6, 1, 9, 0) + timedelta(days=k * 2, minutes=k * 7); ev = []
    add = lambda m, text, node=None: ev.append(dict(m=m, ts=(t0 + timedelta(minutes=m)).strftime("%Y-%m-%d %H:%M"), text=text, node=node))
    if tx["fails"]: add(-8, f"{tx['fails']} failed authentication attempts", tx["cust"])
    add(-6, f"Login from device {tx['dev']}", tx["dev"])
    if tx["vel"] >= 4: add(-3, f"{tx['vel']} rapid transactions on this card", tx["card"])
    add(0, f"Transaction {tx['id']} for ${tx['amt']}", tx["id"])
    for i, o in enumerate(S.get("conn", [])[:4]): add(2 + i * 3, f"Connected customer {o} active on device {tx['dev']}", o)
    pk = next((k for k in S.get("prior", [])), None)
    if pk: add(20, f"Previous case {pk['id']} ({pk.get('outcome','')}) connected", pk["id"])
    return sorted(ev, key=lambda e: e["m"])

def hidden(st, cust, dev):
    N, E, paths, seen = {}, set(), [], {cust}
    nd = lambda i, t: N.setdefault(i, dict(id=i, type=t, label=i, sus=True))
    for d in sorted(set(st.devices_of(cust)) | {dev}):
        nd(d, "device"); E.add((cust, d, "uses"))
        for o in st.customers_on(d):
            if o in seen: continue
            seen.add(o); nd(o, "customer"); E.add((d, o, "shared by")); hs = st.cases_of([o])
            for h in hs: nd(h["id"], "case"); E.add((o, h["id"], h.get("outcome", "")))
            paths.append(dict(path=[cust, d, o] + [h["id"] for h in hs], hops=2 + bool(hs)))
            for d2 in sorted(set(st.devices_of(o)) - {d}):
                nd(d2, "device"); E.add((o, d2, "uses"))
                for o2 in st.customers_on(d2):
                    if o2 not in seen and len(seen) < 30: seen.add(o2); nd(o2, "customer"); E.add((d2, o2, "shared by")); paths.append(dict(path=[cust, d, o, d2, o2], hops=4))
    N.pop(cust, None)
    return dict(connections=paths, nodes=list(N.values()), edges=[dict(s=a, t=b, l=l) for a, b, l in E], ring=len(paths) >= 3,
                summary=dict(customers=len(seen), devices=sum(1 for n in N.values() if n["type"] == "device"), historical_cases=sum(1 for n in N.values() if n["type"] == "case")))

def story(r):
    a, c = r["assessment"], r["case"]; facts = " ".join(a["why_points"][:5])
    pol = a["policies"][0] if a["policies"] else None
    fb = (f"Investigation summary: transaction {c['tx']} (${c['amt']}) for customer {c['cust']} is {a['risk']} risk ({int(a['confidence']*100)}% confidence, {a['ftype']}). Evidence: {facts}. "
          f"Recommended action: {a['nba']}. {('Policy ' + a['approval']['policy_id'] + ' - ' + a['approval']['policy']) if pol else ''} Approval route: {a['approval']['route']}.")
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key: return fb, "template"
    ctx = dict(evidence=[e["text"] for e in a["evidence"]], similar_cases=a["similar"][:3], policy=[dict(id=p["id"], text=p["text"]) for p in a["policies"][:2]], action=a["nba"], approval=a["approval"]["route"], risk=a["risk"])
    try:
        rr = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=12,
                           json=dict(model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), temperature=.2, max_tokens=380, messages=[
                               {"role": "system", "content": "You are a bank fraud analyst. Write: Investigation Summary, Key Finding, Decision, Why (cite policy IDs). Use ONLY the JSON facts; never invent numbers."}, {"role": "user", "content": json.dumps(ctx)}]))
        return rr.json()["choices"][0]["message"]["content"], "groq"
    except Exception: return fb, "template"

def sar_doc(r):
    a, c = r["assessment"], r["case"]
    return dict(sar_id=f"SAR-{c['id']}", status="Draft generated " + SIM, subject=c["cust"], narrative=f"Suspicious activity related to transaction {c['tx']} (${c['amt']}). " + " ".join(a["why_points"][:4]), reference="Bank Secrecy Act, 31 CFR 1020.320")

def run_export(st, T, out_dir):
    st.reset(); rows = []; os.makedirs(os.path.join(out_dir, "answers"), exist_ok=True)
    for b in st.bench_list():
        cid = b["id"]; bef = investigate(st, T, cid, persist=False); ba = bef["assessment"]; asked = bool(ba["missing"]); resp = ("fraud" if ba["p"] >= .5 else "legit") if asked else None
        aft = investigate(st, T, cid, verified=resp, persist=False) if asked else bef; fa = aft["assessment"]
        st.set_state(cid, dict(status="Under Investigation", verified=resp))
        final = "Awaiting analyst approval" if fa["approval"]["required"] else "Closed (auto-executed " + SIM + ")"; closed = not fa["approval"]["required"]
        outcome = ("Confirmed fraud" if fa["p"] >= .7 else "Cleared") if closed else ""
        rec = dict(id=cid, tx_id=b["tx_id"], cust=b["cust"], trigger=b["trigger"], status=final, risk=fa["risk"], confidence=fa["confidence"], pattern=fa["patterns"][0]["name"] if fa["patterns"] else fa["ftype"], pattern_ids=[p["id"] for p in fa["patterns"]],
                   evidence=fa["evidence"], findings=fa["ftype"], action=fa["nba"], approval=fa["approval"]["policy"], policies=[p["id"] for p in fa["policies"][:2]], related=aft["graph"]["path"], summary=fa["why"], is_benchmark=True, closed=closed, outcome=outcome, bank_risk=b["bank_risk"])
        ok = bool(T.update_case(cid, rec)["ok"]) and st.get_case(cid) is not None
        row = dict(case_id=cid, transaction=b["tx_id"], customer=b["cust"], trigger=b["trigger"], bank_risk_score=b["bank_risk"], investigation_steps=[dict(tool=t["tool"], why=t["why"], result=t["result"]) for t in fa["trace"]],
                   graph_evidence=fa["evidence"], connected_entities=aft["graph"]["path"], fraud_pattern=[p["name"] for p in fa["patterns"]] or [fa["ftype"]], risk_assessment=fa["risk"], confidence=fa["confidence"], uncertainty_before=ba["uncertainty"], missing_evidence=ba["missing"],
                   additional_evidence_requested=("Cardholder verification (step-up) - simulated response: " + resp) if asked else "None needed", nba_before=dict(action=ba["nba"], risk=ba["risk"], confidence=ba["confidence"], approval=ba["approval"]),
                   additional_evidence=resp, nba_after=dict(action=fa["nba"], risk=fa["risk"], confidence=fa["confidence"], approval=fa["approval"]), policy=fa["approval"]["policy"], approval_route=fa["approval"]["route"],
                   final_decision=final, sar_required=fa["sar"], sar=sar_doc(aft) if fa["sar"] else None, case_memory_update=f"Case stored in graph as {final}" + (f"; outcome '{outcome}' available to future investigations" if closed else "; memory update pending analyst approval"),
                   similar_cases_used=[k["id"] for k in fa["similar"]], written_to_graph=ok, graph_backend=st.name)
        rows.append(row); json.dump(row, open(os.path.join(out_dir, "answers", f"{cid}.json"), "w"), indent=1, default=str)
    json.dump(rows, open(os.path.join(out_dir, "all_cases.json"), "w"), indent=1, default=str)
    return rows
