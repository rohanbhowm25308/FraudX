"""Dataset layer: synthetic demo data, and the HHGOA_IEEE loader (same in-memory shape for both)."""
import os, glob, re, random
R = random.Random(42)

def is_fraud(o):
    o = str(o).lower()
    return ("fraud" in o or "confirm" in o) and not any(k in o for k in ("clear", "not fraud", "false", "legit", "no fraud"))

PATTERNS = [
    dict(id="FP-1", name="Potential fraud ring", requires="device", anyof="prior|velocity", desc="Many customers share one device together with rapid activity or prior fraud."),
    dict(id="FP-2", name="Account takeover", requires="auth|newdev", anyof="", desc="Failed logins followed by a never-seen device."),
    dict(id="FP-3", name="Velocity burst", requires="velocity|amount", anyof="", desc="Rapid, unusually large transactions (card testing)."),
    dict(id="FP-4", name="Connected to confirmed fraud", requires="device|prior", anyof="", desc="Shared device links to entities in confirmed fraud cases."),
    dict(id="FP-5", name="Behavior deviation", requires="amount", anyof="", desc="Amount deviates strongly from the customer's baseline.")]
POLICIES = [
    dict(id="P-02", title="Low-risk handling", text="Transactions consistent with the customer's behaviour are allowed. Monitor the account when residual risk exists.", tags="allow monitor low risk"),
    dict(id="P-09", title="Step-up before blocking", text="When evidence is inconclusive, request step-up authentication or cardholder verification before any block.", tags="step-up verification inconclusive uncertain evidence insufficient"),
    dict(id="P-12", title="Suspicious activity reporting", text="A suspicious activity report (SAR) must be filed when coordinated activity is confirmed with high confidence. Reference: Bank Secrecy Act, 31 CFR 1020.320.", tags="sar suspicious activity report coordinated ring regulatory"),
    dict(id="P-17", title="Card block approval", text="A temporary card block requires fraud analyst approval before execution.", tags="block card approval analyst temporary"),
    dict(id="P-21", title="Escalation", text="Escalate to a fraud analyst when financial impact is high or evidence is material but inconclusive.", tags="escalate analyst high value financial impact")]

def synthetic():
    cu = {}
    for i in range(1, 41):
        c = f"CU_{i:03d}"; cu[c] = dict(id=c, mean=R.randint(40, 160), std=R.randint(15, 40), card=f"CD_{i:03d}", acct=f"AC_{i:03d}", devices={f"DV_{(i % 12) + 1:02d}"}, n_tx=12)
    ring = [f"CU_{i:03d}" for i in (5, 6, 7, 8, 9, 10)]
    for c in ring: cu[c]["devices"].add("DV_07")
    txs, n = [], 0
    for c, v in cu.items():
        dv = sorted(v["devices"])[0]
        for k in range(12):
            n += 1; txs.append(dict(id=f"TX_{n:05d}", cust=c, card=v["card"], dev=dv, amt=round(max(5, R.gauss(v["mean"], v["std"])), 2), ts=k * 10800, bank_risk=round(R.uniform(.02, .3), 2), fails=0, vel=1, new_dev=0))
    H = [("H-101", "CU_005", "Potential fraud ring", "Confirmed fraud"), ("H-102", "CU_006", "Potential fraud ring", "Confirmed fraud"), ("H-103", "CU_008", "Potential fraud ring", "Confirmed fraud"),
         ("H-104", "CU_015", "Account takeover", "Confirmed fraud"), ("H-105", "CU_022", "Account takeover", "Confirmed fraud"), ("H-106", "CU_030", "Behavior deviation", "Cleared"),
         ("H-107", "CU_033", "Behavior deviation", "Cleared"), ("H-108", "CU_018", "Velocity burst", "Confirmed fraud"), ("H-109", "CU_036", "Behavior deviation", "Cleared")]
    hist = [dict(id=i, cust=c, pattern=p, outcome=o, summary=f"{p}: {o}", is_benchmark=False, closed=True, status="Closed") for i, c, p, o in H]
    KINDS = ["ring", "ato", "benign", "velocity", "ambiguous"]; bench = []
    for i in range(1, 21):
        k = KINDS[(i - 1) % 5]; pool = {"ring": ring, "ato": [f"CU_{x:03d}" for x in range(11, 26)]}.get(k, [f"CU_{x:03d}" for x in range(26, 41)])
        c = cu[pool[(i * 3) % len(pool)]]; amt = {"ring": 5, "ato": 7, "benign": 1.1, "velocity": 2.5}.get(k, 0) * c["mean"] or c["mean"] + c["std"] * 3.2
        dev = "DV_07" if k == "ring" else (f"DV_{13 + i % 3}" if k == "ato" else sorted(c["devices"])[0])
        c["devices"].add(dev); tid = f"TX_{9000 + i}"
        txs.append(dict(id=tid, cust=c["id"], card=c["card"], dev=dev, amt=round(amt, 2), ts=40 * 3600 + i, fails={"ato": 4, "ambiguous": 1}.get(k, 0), vel={"velocity": 6, "ring": 4}.get(k, 1), new_dev=int(k == "ato"),
                        bank_risk=round(min(.98, {"ring": .88, "ato": .91, "benign": .83, "velocity": .79, "ambiguous": .62}[k] + R.uniform(-.05, .05)), 2)))
        bench.append(dict(id=f"HHG-{i:03d}", tx_id=tid, trigger=["Risk score", "Customer report", "Analyst request"][i % 3]))
    return dict(source="synthetic demo data", customers=cu, txs=txs, hist=hist, bench=bench, patterns=PATTERNS, policies=POLICIES)

def load_hhgoa(d, full=False):
    """Loads the HHGOA_IEEE folder. Column names are matched flexibly; see README if your files differ."""
    import pandas as pd, numpy as np
    files = [f for f in glob.glob(os.path.join(d, "**", "*"), recursive=True) if os.path.isfile(f)]
    def find(*keys, ext=(".csv",), no=()):
        for f in sorted(files):
            n = os.path.basename(f).lower()
            if n.endswith(ext) and all(k in n for k in keys) and not any(x in n for x in no): return f
    def col(df, *names):
        low = {c.lower(): c for c in df.columns}
        for n in names:
            if n.lower() in low: return low[n.lower()]
    tf, idf = find("transaction", no=("case", "bench")), find("identity")
    bf, hf = find("benchmark"), find("hist") or find("closed") or find("case", no=("bench",))
    if not (tf and bf): raise FileNotFoundError(f"Need a transactions CSV and a benchmark-cases CSV in {d}. Found: {[os.path.basename(f) for f in files][:25]}")
    tx = pd.read_csv(tf); T = lambda *n: col(tx, *n)
    tid, dt, amt = T("TransactionID", "transaction_id"), T("TransactionDT", "timestamp"), T("TransactionAmt", "amount")
    cu = T("customer_id", "CustomerID", "cust_id")
    if not cu: tx["_cu"] = tx[T("card1")].astype(str) + "_" + tx[T("addr1")].fillna(0).astype(str); cu = "_cu"
    rk = T("risk_score", "bank_risk_score", "fraud_score", "riskscore", "bank_risk")
    if not rk: raise KeyError("No bank risk score column found (looked for risk_score / bank_risk_score / fraud_score).")
    df = pd.DataFrame(dict(id="TX_" + tx[tid].astype(str), cust="CU_" + tx[cu].astype(str), amt=tx[amt].astype(float), ts=tx[dt].astype(float), bank_risk=tx[rk].astype(float), card="CD_" + tx[T("card1", "card_id")].astype(str)))
    df["fails"] = tx[T("failed_auth", "failed_logins", "auth_failures")].fillna(0).astype(int) if T("failed_auth", "failed_logins", "auth_failures") else 0
    df["dev"] = None
    if idf:
        idn = pd.read_csv(idf); dc = col(idn, "device_id", "DeviceID", "DeviceInfo"); ic = col(idn, "TransactionID", "transaction_id")
        if dc and ic: m = dict(zip("TX_" + idn[ic].astype(str), "DV_" + idn[dc].astype(str).str.replace(r"\W+", "_", regex=True))); df["dev"] = df["id"].map(m)
    df = df.sort_values(["cust", "ts"]).reset_index(drop=True)
    ts = df.ts.values; vel = np.zeros(len(df), dtype=int)
    for idx in df.groupby("cust").indices.values(): t = ts[idx]; vel[idx] = np.arange(len(idx)) - np.searchsorted(t, t - 3600, side="left")
    df["vel"] = vel; df["new_dev"] = (df.dev.notna() & ~df.duplicated(["cust", "dev"])).astype(int)
    def cases(path):
        c = pd.read_csv(path); return c, col(c, "case_id", "CaseID", "id"), col(c, "transaction_id", "TransactionID", "tx_id"), col(c, "outcome", "resolution", "decision", "label", "status"), col(c, "trigger", "trigger_type", "source")
    bc, bid, btx, _, btr = cases(bf); bench = [dict(id=str(r[bid]), tx_id="TX_" + str(r[btx]), trigger=str(r[btr]) if btr else "Risk score") for _, r in bc.iterrows()]
    btx_ids = {b["tx_id"] for b in bench}; base = df[~df.id.isin(btx_ids)]
    g = base.groupby("cust").amt.agg(["mean", "std", "count"]).fillna(0)
    rel = set(df[df.id.isin(btx_ids)].cust)
    if not full:
        devs = set(df[df.cust.isin(rel)].dev.dropna()); rel |= set(df[df.dev.isin(devs)].cust); df = df[df.cust.isin(rel)]
    custs = {}
    for c, grp in df.groupby("cust"):
        r = g.loc[c] if c in g.index else None
        custs[c] = dict(id=c, mean=round(float(r["mean"]), 2) if r is not None else 0, std=round(float(r["std"]), 2) if r is not None else 0, n_tx=int(r["count"]) if r is not None else 0,
                        card=grp.card.iloc[0], acct="AC_" + c[3:], devices=set(grp.dev.dropna()))
    hist = []
    if hf:
        hc, hid, htx, hout, _ = cases(hf); txc = dict(zip(df.id, df.cust)) if not full else dict(zip(df.id, df.cust))
        for _, r in hc.iterrows():
            t = "TX_" + str(r[htx]); o = "Confirmed fraud" if is_fraud(r[hout]) else "Cleared"
            if t in txc: hist.append(dict(id=str(r[hid]), cust=txc[t], tx_id=t, pattern="", outcome=o, summary=f"Historical case ({r[hout]})", is_benchmark=False, closed=True, status="Closed"))
    pol, pat = list(POLICIES), list(PATTERNS)
    for f in files:
        n = os.path.basename(f).lower()
        if n.endswith((".md", ".txt")) and "polic" in n:
            txt = open(f, encoding="utf8", errors="ignore").read()
            parts = re.split(r"\n\s*(?=P-?\d+\b)", txt) if re.search(r"^\s*P-?\d+\b", txt, re.M) else re.split(r"\n\s*\n", txt)
            chunks = [x.strip() for x in parts if len(x.strip()) > 30]
            pol = [dict(id=(re.match(r"P-?\d+", ch) or re.search(r"\bP-?\d+\b", ch) or [f"DP-{i+1}"])[0], title=ch.split("\n")[0][:60], text=re.sub(r"\s+", " ", ch), tags="") for i, ch in enumerate(chunks)] or pol
    return dict(source="HHGOA_IEEE dataset", customers=custs, txs=df.to_dict("records"), hist=hist, bench=bench, patterns=pat, policies=pol)
