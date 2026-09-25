import os, time
from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv
load_dotenv()
from graph import build_store
from tools import Tools, TOOL_NAMES
import agent as A

app = Flask(__name__)
ST = build_store(); T = Tools(ST)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submission")

def run(cid, **kw):
    r = A.investigate(ST, T, cid, verified=ST.get_state(cid).get("verified"), **kw); return r

@app.errorhandler(KeyError)
def _nf(e): return jsonify(error=f"not found: {e}"), 404

@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/status")
def status():
    ds = getattr(ST, "ds", None)
    return jsonify(backend=ST.name, note=ST.note, data=(ds or {}).get("source", "TigerGraph graph"), llm=bool(os.getenv("GROQ_API_KEY", "").strip()), planner="LLM-assisted" if os.getenv("AGENT_LLM_PLANNER") == "1" else "state-driven", tools=TOOL_NAMES, policies=len(ST.policies()), cases=len(ST.bench_list()))

@app.route("/api/cases")
def cases():
    return jsonify([dict(id=b["id"], tx=b["tx_id"], cust=b["cust"], status=b["status"], bank_risk=b["bank_risk"], risk="HIGH" if b["bank_risk"] >= .8 else "MEDIUM" if b["bank_risk"] >= .6 else "LOW") for b in ST.bench_list()])

@app.route("/api/case/<cid>")
def case(cid): return jsonify(run(cid))

@app.route("/api/case/<cid>/evidence", methods=["POST"])
def evidence(cid):
    v = (request.json or {}).get("result")
    if v not in ("fraud", "legit"): return jsonify(error="result must be fraud|legit"), 400
    before = run(cid, persist=False)["assessment"]; s = ST.get_state(cid); s.update(verified=v, status="Under Investigation"); ST.set_state(cid, s)
    out = run(cid); out["before"] = dict(nba=before["nba"], risk=before["risk"], confidence=before["confidence"], p=before["p"]); return jsonify(out)

@app.route("/api/case/<cid>/counterfactual")
def counterfactual(cid):
    rem = request.args.get("remove", ""); a, b = run(cid, persist=False)["assessment"], run(cid, removed=(rem,), persist=False)["assessment"]
    f = lambda x: dict(risk=x["risk"], nba=x["nba"], confidence=x["confidence"]); return jsonify(removed=rem, before=f(a), after=f(b))

@app.route("/api/case/<cid>/story")
def story(cid):
    t, src = A.story(run(cid, persist=False)); return jsonify(story=t, source=src)

@app.route("/api/case/<cid>/hidden")
def hidden(cid):
    r = run(cid, persist=False); return jsonify(A.hidden(ST, r["case"]["cust"], r["case"]["dev"]))

@app.route("/api/case/<cid>/decide", methods=["POST"])
def decide(cid):
    r = run(cid, persist=False); a = r["assessment"]; d = (request.json or {}).get("decision", "approve"); s = ST.get_state(cid)
    s.setdefault("approvals", []).append(dict(action=a["nba"], decision=d, by="analyst", at=time.strftime("%Y-%m-%d %H:%M")))
    if d == "approve":
        c = r["case"]; msg = {"TEMPORARY CARD BLOCK": f"Card {c['card']} temporarily blocked", "REQUEST STEP-UP AUTH": "Step-up authentication requested from cardholder", "ESCALATE TO ANALYST": "Escalated to fraud analyst queue", "FILE SAR": "SAR filed"}.get(a["nba"], "Transaction allowed" + (" and account monitored" if "MONITOR" in a["nba"] else ""))
        s.update(status="Closed", executed=msg + " (simulated)", outcome="Confirmed fraud" if a["p"] >= .7 else "Cleared")
    else: s["status"] = "Rejected — re-review"
    ST.set_state(cid, s); return jsonify(run(cid))

@app.route("/api/case/<cid>/sar", methods=["POST"])
def sar(cid):
    r = run(cid, persist=False)
    if not r["assessment"]["sar"]: return jsonify(error="SAR not required for this case under policy"), 400
    s = ST.get_state(cid); s["sar"] = dict(A.sar_doc(r), status="Filed (simulated)"); ST.set_state(cid, s); return jsonify(run(cid))

@app.route("/api/node/<nid>")
def node(nid): return jsonify(ST.expand(nid))

@app.route("/api/policies")
def policies(): return jsonify(ST.policies())

@app.route("/api/reset", methods=["POST"])
def reset(): ST.reset(); return jsonify(ok=True)

@app.route("/api/export")
def export():
    rows = A.run_export(ST, T, OUT); return jsonify(count=len(rows), written=sum(r["written_to_graph"] for r in rows), path="submission/answers/ (+ all_cases.json)", cases=rows)

if __name__ == "__main__": app.run(debug=True, port=int(os.getenv("PORT", 5000)))
