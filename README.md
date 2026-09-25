# FraudX — Agentic Fraud Investigation

An AI agent that investigates a suspicious transaction the way a fraud analyst would: it walks a graph of
customers, cards, devices and transactions, retrieves prior cases and policy passages, weighs evidence,
asks for more evidence when uncertain, and recommends a **next best action** that is gated by policy and
(when required) analyst approval.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # already done for you; edit values as needed
python app.py                # http://localhost:5000
```

With no TigerGraph and no Groq key set, FraudX runs entirely on an in-memory graph with synthetic demo
data and a fact-based (non-LLM) story generator — no external services required to try it.

## Running against real TigerGraph + the HHGOA_IEEE dataset

```bash
# 1. Fill in TG_HOST / TG_USER / TG_PASSWORD (or TG_SECRET) in .env
# 2. Create the schema and load data (synthetic, to sanity-check the connection):
python ingest.py --synthetic
# 3. Or load the official dataset (point at the folder containing the CSVs + README):
python ingest.py --data ./HHGOA_IEEE
# 4. Run the app — it auto-detects TigerGraph via TG_HOST and uses it instead of the local graph:
python app.py
```

`data.py`'s `load_hhgoa()` looks for a transactions CSV, an identity CSV, a benchmark-cases CSV, a
historical/closed-cases CSV, and a fraud-policy text file, matching column names flexibly (e.g.
`TransactionID`/`transaction_id`, `risk_score`/`bank_risk_score`/`fraud_score`). **Read the dataset's own
README first** and adjust the column names in `load_hhgoa()` if they differ — the loader raises a clear
error naming the file it couldn't find rather than silently guessing.

If `TG_HOST` is set but unreachable or empty, the app logs why (shown as a warning badge in the UI) and
falls back to the local graph so the demo never breaks.

## Architecture

```
FraudX Agent (agent.py)
   |
   |-- tools.py  (get_transaction_context, find_shared_devices, find_connected_customers,
   |               find_prior_cases, find_fraud_patterns, search_policy [GraphRAG],
   |               find_similar_cases [case memory], create_case, update_case, ...)
   |
   |-- graph/tg.py (TigerGraph via pyTigerGraph + installed GSQL queries, graph/schema.gsql)
   |-- graph/local.py (in-memory graph, same interface, used when TigerGraph isn't configured)
   |
   |-- Groq LLM (optional): writes the "fraud story" narrative and, if AGENT_LLM_PLANNER=1,
                             can pick which tool to call next (validated against the real tool list)
```

- **Agent loop**: `agent.investigate()` does NOT run a fixed sequence. At each step it looks at what it
  already knows (`S`) and picks the next tool by expected information gain — e.g. finding a shared device
  raises the priority of "search prior cases of connected customers"; failed logins raise the priority of
  checking device novelty. It stops early once risk is decisive, or once all relevant checks are
  exhausted, and records *why* each step was chosen in the trace shown in the UI.
- **MCP**: `mcp_server.py` exposes the exact same tool functions over the Model Context Protocol
  (`pip install mcp`, then `python mcp_server.py`), so any MCP-compatible agent framework can drive
  FraudX's TigerGraph tools directly instead of importing `tools.py` in-process.
- **GraphRAG**: `search_policy()` retrieves the most relevant policy/typology passages (stored as `Policy`
  vertices, loaded from the dataset's fraud-policy document) for the *specific candidate action*, and only
  those passages — not the whole policy document — are passed to the LLM and shown to the user.
- **Case memory**: closed investigations are stored as `FraudCase` vertices in the graph (or, locally, in
  `memory.json`). `find_similar_cases()` retrieves cases connected to the same customer, the same device's
  network, or the same fraud pattern, and the UI shows them with the reason for the match.
- **Policy-gated NBA**: the recommended action always carries an `approval` object naming the specific
  policy retrieved via GraphRAG, whether approval is required, and the route. Card blocks and SAR filing
  require analyst approval in the UI before `decide()` marks the case closed and simulates execution.

## Submission export

```bash
python export_cases.py     # or click "Export 20 cases" in the UI, or GET /api/export
```

Writes `submission/all_cases.json` and one file per case in `submission/answers/`, each containing the
internal investigation record, graph evidence, connected entities, fraud pattern, risk/confidence,
uncertainty, missing evidence, **NBA before** and **NBA after** additional evidence, the policy and
approval route, the final decision, whether a SAR is required, the case-memory update, and whether the
case was actually written to the graph (`written_to_graph`, `graph_backend`).

## What's simulated

Per the challenge rules, these are intentionally mocked, and labelled "(simulated)" in the UI: cardholder
verification responses, card blocking, account freezing, SAR submission, and analyst approval. The
investigation itself (graph traversal, evidence, risk, patterns, policy retrieval, case memory) is real.

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask routes / UI backend |
| `agent.py` | The investigation agent (tool loop, risk/NBA logic, story, export) |
| `tools.py` | Tool layer used by the agent and exposed via MCP |
| `mcp_server.py` | Exposes `tools.py` over MCP |
| `data.py` | Synthetic demo data + `load_hhgoa()` for the real dataset |
| `graph/schema.gsql` | TigerGraph vertex/edge schema + installed GSQL queries |
| `graph/tg.py` | TigerGraph backend (pyTigerGraph) |
| `graph/local.py` | In-memory fallback backend, same interface |
| `ingest.py` | Loads data into TigerGraph |
| `export_cases.py` | CLI for the submission export |
| `templates/`, `static/` | Frontend (HTML/CSS/vanilla JS), white/blue UI, canvas network background |
