"""FraudX tool layer. These are the tools the agent may call; mcp_server.py exposes the same functions over the Model Context Protocol."""
import re
from data import is_fraud

TOOL_NAMES = ["get_transaction_context", "get_customer_history", "find_shared_devices", "find_connected_customers", "find_prior_cases",
              "find_fraud_patterns", "get_case_evidence", "search_policy", "find_similar_cases", "create_case", "update_case"]

class Tools:
    def __init__(s, store): s.st = store
    def call(s, name, args):
        if name not in TOOL_NAMES: raise ValueError(f"unknown tool {name}")
        return getattr(s, name)(**args)
    def get_transaction_context(s, tx_id: str) -> dict:
        """Transaction, its card/device and the customer's spending baseline (GSQL: tx_context)."""
        return s.st.tx_context(tx_id)
    def get_customer_history(s, customer_id: str) -> dict:
        """Customer baseline, known devices and cards."""
        return dict(customer=s.st.customer(customer_id), devices=s.st.devices_of(customer_id), cards=s.st.cards_of(customer_id))
    def find_shared_devices(s, customer_id: str, device_id: str = "") -> list:
        """For the customer's devices (plus device_id) count how many OTHER customers use each."""
        ds = sorted(set(s.st.devices_of(customer_id)) | ({device_id} if device_id else set()))
        return [dict(device=d, other_customers=len([c for c in s.st.customers_on(d) if c != customer_id])) for d in ds]
    def find_connected_customers(s, device_id: str) -> list:
        """Customers connected through a device (GSQL: customers_on_device)."""
        return s.st.customers_on(device_id)
    def find_prior_cases(s, customer_ids: list, exclude: str = "") -> list:
        """Closed investigations of these customers (GSQL: closed_cases)."""
        return s.st.cases_of(customer_ids, exclude)
    def find_fraud_patterns(s, evidence_keys: list) -> list:
        """Match evidence against the known fraud patterns stored in the graph."""
        ks, out = set(evidence_keys), []
        for p in s.st.patterns():
            req = set(filter(None, p["requires"].split("|"))); anyof = set(filter(None, p["anyof"].split("|")))
            ok = req <= ks
            if ok and (not anyof or anyof & ks): out.append(dict(id=p["id"], name=p["name"], desc=p["desc"], matched=sorted((req | anyof) & ks)))
        return sorted(out, key=lambda x: -len(x["matched"]))
    def get_case_evidence(s, case_id: str) -> list:
        """Evidence stored on a case in the graph."""
        c = s.st.get_case(case_id); return (c or {}).get("evidence", [])
    def search_policy(s, query: str, k: int = 3) -> list:
        """GraphRAG retrieval over policy / typology / regulatory passages stored in the graph."""
        q = set(re.findall(r"\w+", query.lower())); out = []
        for p in s.st.policies():
            w = re.findall(r"\w+", (p["title"] + " " + p["text"] + " " + p.get("tags", "")).lower()); sc = sum(1 for x in w if x in q) / (len(w) ** .5 + 1)
            out.append(dict(id=p["id"], title=p["title"], text=p["text"][:400], score=round(sc, 3)))
        return sorted(out, key=lambda x: -x["score"])[:k]
    def find_similar_cases(s, case_id: str, customer_id: str, device_id: str, pattern: str = "") -> list:
        """Case memory: closed cases involving the same customer, the same device's customers, or the same fraud pattern."""
        near = {c: "same device network" for c in s.st.customers_on(device_id)} if device_id else {}
        near[customer_id] = "same customer"; out = {}
        for k in s.st.cases_of(list(near), case_id): out[k["id"]] = dict(id=k["id"], cust=k.get("cust"), outcome=k.get("outcome", ""), pattern=k.get("pattern", ""), via=near.get(k.get("cust"), "linked"), sim=.6)
        if pattern:
            for k in s.st.all_closed(case_id):
                if k.get("pattern") == pattern:
                    e = out.setdefault(k["id"], dict(id=k["id"], cust=k.get("cust"), outcome=k.get("outcome", ""), pattern=pattern, via="same pattern", sim=0)); e["sim"] = round(e["sim"] + .4, 2)
        return sorted(out.values(), key=lambda x: -x["sim"])[:5]
    def create_case(s, record: dict) -> dict:
        """Create a case vertex (plus links) in the graph."""
        return dict(ok=s.st.write_case(record))
    def update_case(s, case_id: str, patch: dict) -> dict:
        """Update a case: add evidence, findings, action, approval, outcome."""
        return dict(ok=s.st.write_case({**patch, "id": case_id}))

def make_mcp(tools):
    from mcp.server.fastmcp import FastMCP
    m = FastMCP("fraudx-tigergraph")
    for n in TOOL_NAMES: m.tool(name=n)(getattr(tools, n))
    return m
