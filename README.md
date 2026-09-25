# FraudX — Agentic Fraud Investigation

<p align="center">
  <strong>Investigate. Connect. Decide.</strong>
</p>

<p align="center">
  An AI-powered fraud investigation platform that combines graph intelligence, agentic investigation, evidence analysis, GraphRAG, case memory, and policy-aware next-best actions.
</p>

<p align="center">

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge\&logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-Web%20App-black?style=for-the-badge\&logo=flask)](https://flask.palletsprojects.com/)
[![TigerGraph](https://img.shields.io/badge/TigerGraph-Graph%20Intelligence-00A6A6?style=for-the-badge)](https://www.tigergraph.com/)
[![MCP](https://img.shields.io/badge/MCP-Agent%20Tools-purple?style=for-the-badge)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](#license)

</p>

<p align="center">
  <a href="https://github.com/rohanbhowm25308/FraudX">GitHub Repository</a> •
  <a href="https://fraudx-agentic-fraud-investigation.onrender.com">Live Demo</a>
</p>

---

## 🔎 What is FraudX?

FraudX is an **agentic fraud investigation system** designed to investigate suspicious financial activity the way a fraud analyst would.

Instead of simply asking whether a transaction is fraudulent, FraudX investigates the **relationships and evidence surrounding the transaction**.

The agent can:

* 🔍 Investigate suspicious transactions
* 🕸️ Explore customer, card, device, account, and transaction relationships
* 🔗 Discover hidden connections
* 🧠 Retrieve similar historical fraud cases
* 📚 Retrieve relevant fraud-policy evidence using GraphRAG
* 📊 Evaluate risk, confidence, and uncertainty
* 🧩 Identify potential fraud patterns
* 🔄 Request additional evidence when uncertainty remains
* ⚡ Recommend a policy-aware **Next Best Action**
* 👤 Route sensitive actions for analyst approval
* 📝 Maintain investigation timelines and case memory
* 📦 Export complete investigation records for benchmark evaluation

> **FraudX is built around investigation, not just classification.**

---

## 🚨 Why FraudX?

Traditional fraud detection often focuses on:

```text
Transaction → Fraud Score → Decision
```

FraudX extends this into an investigation workflow:

```text
Suspicious Signal
       ↓
Agent Investigation
       ↓
Graph Exploration
       ↓
Evidence Collection
       ↓
Pattern Detection
       ↓
Historical Case Retrieval
       ↓
Policy / GraphRAG Validation
       ↓
Risk + Confidence + Uncertainty
       ↓
Additional Evidence if Needed
       ↓
Next Best Action
       ↓
Human Approval When Required
       ↓
Case Memory + Investigation Record
```

This allows the system to explain **why** an action is recommended and what evidence supports it.

---

# 🧠 Core Features

### 🕸️ Graph-Based Investigation

Fraud rarely exists in isolation.

FraudX explores relationships between:

* Customers
* Cards
* Transactions
* Devices
* Accounts
* Fraud cases
* Evidence
* Actions

This makes it possible to uncover suspicious relationships that may not be visible from a single transaction.

---

### 🤖 Agentic Investigation Loop

FraudX does not simply execute a fixed sequence of checks.

The investigation agent maintains what it already knows and selects the next investigation step based on the expected value of additional evidence.

For example:

```text
Shared Device Found
        ↓
Increase priority of connected-customer investigation
        ↓
Historical fraud case discovered
        ↓
Increase priority of fraud-pattern analysis
        ↓
Evidence becomes sufficient
        ↓
Recommend Next Best Action
```

The agent also records its investigation trace so the reasoning path can be inspected through the interface.

---

### 📚 GraphRAG + Fraud Policy

FraudX retrieves relevant policy and fraud-typology information for the current investigation.

Instead of sending an entire policy document to an LLM, the system retrieves the **relevant policy passages** for the candidate action.

This helps connect:

```text
Evidence
   +
Fraud Pattern
   +
Policy
   ↓
Recommended Action
```

---

### 🧠 Case Memory

Previous investigations can become useful evidence for future investigations.

FraudX can retrieve similar historical cases based on signals such as:

* Customer relationship
* Device network
* Fraud pattern
* Connected entities
* Investigation evidence

This gives the agent access to historical investigation context instead of treating every case independently.

---

### ⚠️ Uncertainty-Aware Decisions

FraudX tracks:

* Risk
* Confidence
* Uncertainty
* Missing evidence
* Evidence sufficiency

When the evidence is insufficient, the system can request additional evidence instead of immediately making a final decision.

---

### 🎯 Next Best Action

FraudX can recommend actions such as:

* `ALLOW`
* `ALLOW + MONITOR`
* `REQUEST STEP-UP AUTH`
* `TEMPORARY CARD BLOCK`
* `ESCALATE TO ANALYST`

Actions are connected to policy and approval requirements.

Sensitive actions can require analyst approval before simulated execution.

---

### 🔐 Human-in-the-Loop

FraudX is designed so that the agent does not blindly execute high-impact actions.

The investigation can move through:

```text
Agent Recommendation
        ↓
Policy Check
        ↓
Approval Required?
      ↙       ↘
    YES        NO
     ↓          ↓
Analyst       Execute
Approval
     ↓
Decision
```

---

## 🏗️ Architecture

```text
                         ┌─────────────────────┐
                         │     FraudX UI       │
                         │  Investigation Hub  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   FraudX Agent      │
                         │  Agentic Controller  │
                         └──────────┬──────────┘
                                    │
                     ┌──────────────┼──────────────┐
                     │              │              │
                     ▼              ▼              ▼
              ┌────────────┐ ┌────────────┐ ┌─────────────┐
              │ Graph Tools│ │ GraphRAG   │ │ Case Memory │
              └─────┬──────┘ └─────┬──────┘ └──────┬──────┘
                    │              │               │
                    └──────────────┼───────────────┘
                                   ▼
                         ┌─────────────────────┐
                         │     TigerGraph      │
                         │  Fraud Relationship │
                         │        Graph        │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Evidence + Policy  │
                         │ + Historical Cases  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Next Best Action    │
                         │ + Approval Route    │
                         └─────────────────────┘
```

---

# 🧩 Technology Stack

| Technology                  | Purpose                                            |
| --------------------------- | -------------------------------------------------- |
| **Python**                  | Core backend and investigation logic               |
| **Flask**                   | Web application and API layer                      |
| **TigerGraph**              | Fraud relationship graph                           |
| **pyTigerGraph**            | TigerGraph integration                             |
| **GSQL**                    | Graph schema and graph queries                     |
| **GraphRAG**                | Policy-grounded investigation                      |
| **MCP**                     | Exposing investigation tools to compatible agents  |
| **Groq LLM**                | Optional agent planning and fraud-story generation |
| **HTML / CSS / JavaScript** | Investigation interface                            |
| **Render**                  | Deployment                                         |

---

# 📁 Project Structure

```text
FraudX/
│
├── agent.py                 # Agentic investigation engine
├── app.py                   # Flask application
├── data.py                  # Dataset + synthetic data handling
├── tools.py                 # Investigation tools
├── mcp_server.py            # MCP tool server
├── ingest.py                # TigerGraph data ingestion
├── export_cases.py          # Benchmark/submission export
├── upload.py                # Dataset upload utilities
│
├── graph/
│   ├── schema.gsql          # TigerGraph schema + queries
│   ├── tg.py                # TigerGraph backend
│   └── local.py             # Local graph fallback
│
├── static/
│   ├── app.js               # Frontend logic
│   ├── style.css            # UI styling
│   └── ...
│
├── templates/
│   └── index.html           # Main investigation interface
│
├── submission/
│   └── answers/             # Exported investigation cases
│
├── .env.example             # Environment configuration template
├── requirements.txt         # Python dependencies
├── Procfile                 # Deployment configuration
└── README.md
```

---

# ⚙️ How It Works

### 1. Detect

A suspicious transaction or investigation request enters FraudX.

### 2. Investigate

The agent gathers relevant context:

```text
Transaction
   ↓
Customer
   ↓
Card
   ↓
Device
   ↓
Connected Customers
   ↓
Historical Cases
```

### 3. Analyze

FraudX evaluates:

* Transaction behavior
* Customer baseline
* Device relationships
* Transaction velocity
* Authentication signals
* Historical cases
* Fraud patterns
* Policy evidence

### 4. Resolve Uncertainty

If evidence is insufficient, FraudX can request additional evidence such as step-up authentication and reassess the case.

### 5. Decide

The system produces:

```text
Risk
Confidence
Uncertainty
Fraud Pattern
Evidence
Missing Evidence
Next Best Action
Approval Requirement
```

### 6. Remember

The investigation outcome can be stored as case memory for future investigations.

---

# 🚀 Quick Start

Clone the repository:

```bash
git clone https://github.com/rohanbhowm25308/FraudX.git
cd FraudX
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
copy .env.example .env
```

Run FraudX:

```bash
python app.py
```

Open:

```text
http://localhost:5000
```

---

# 🕸️ TigerGraph Setup

FraudX can operate with a local in-memory graph or a configured TigerGraph backend.

Configure your `.env`:

```env
TG_HOST=YOUR_TIGERGRAPH_HOST
TG_GRAPH=FraudX
TG_USER=tigergraph
TG_PASSWORD=YOUR_PASSWORD
TG_SECRET=YOUR_SECRET
TG_TOKEN=YOUR_TOKEN
```

Then initialize/load the graph:

```bash
python ingest.py --synthetic
```

For the official HHGOA_IEEE dataset:

```bash
python ingest.py --data ./HHGOA_IEEE
```

> Read the dataset's own README before ingestion and verify the expected file/column names.

---

# 🤖 MCP Server

FraudX exposes its investigation tools through the **Model Context Protocol (MCP)**.

Start the MCP server with:

```bash
python mcp_server.py
```

This allows MCP-compatible agent frameworks to interact with FraudX investigation tools.

---

# 📊 Investigation Export

Export all benchmark cases:

```bash
python export_cases.py
```

The exported investigation records contain information such as:

* Investigation evidence
* Connected entities
* Fraud pattern
* Risk
* Confidence
* Uncertainty
* Missing evidence
* Next Best Action
* Policy
* Approval route
* Final decision
* SAR requirement
* Case-memory update
* Graph backend information

---

# 🧪 Demo Mode

FraudX can also run without external services.

If TigerGraph and Groq are not configured, the application can use:

```text
In-Memory Graph
      +
Synthetic Demo Data
      +
Fact-Based Investigation
```

This makes the project easy to test locally before connecting the production graph infrastructure.

---

# ⚠️ Simulation Notice

Some external actions are intentionally simulated in the current implementation.

These include:

* Cardholder verification
* Card blocking
* Account freezing
* SAR submission
* Analyst approval

The investigation workflow itself covers graph traversal, evidence analysis, fraud-pattern detection, policy retrieval, case memory, uncertainty handling, and next-best-action reasoning.

---

# 🎯 Project Goals

FraudX is designed around four core principles:

### 🔍 Investigate

Don't stop at a fraud score. Understand the surrounding evidence.

### 🕸️ Connect

Use graph relationships to uncover hidden fraud networks.

### 🧠 Reason

Combine evidence, historical cases, policy, and uncertainty.

###  Decide

Recommend a defensible next-best action with the appropriate approval path.

---

# 🌐 Live Demo

**Try FraudX:**
https://fraudx-agentic-fraud-investigation.onrender.com

**Source Code:**
https://github.com/rohanbhowm25308/FraudX

---

# 🏆 Built For

**TigerGraph Hacker House Goa 2026**

FraudX is designed around an agentic fraud-investigation workflow using graph intelligence, evidence-driven reasoning, case memory, policy grounding, and next-best-action recommendations.

---

Building projects around:

```text
Artificial Intelligence
Machine Learning
Data Science
Generative AI
Agentic AI
Graph Intelligence
Web Development
```

---

# ⭐ Support

If you find FraudX interesting, consider giving the repository a ⭐ on GitHub.

**Developed with Python, Graph Intelligence, AI Agents & TigerGraph.**

---

## 📄 License

This project is licensed under the MIT License.
