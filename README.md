# 🕵️‍♂️ Sleuth: AI-Powered Forensic Accounting Platform

**Sleuth** is a production-grade financial forensics tool that takes you from a raw vendor PDF invoice all the way to a published AI audit report — in a single, guided workflow.

Built on **FastAPI + custom Web UI**, it replaces the original Streamlit prototype with a premium two-tab application.

---

## 📖 The Problem It Solves

Most reconciliation tools only tell you **there's a mismatch** — e.g., a $650 difference between your Vendor Ledger and your ERP.

They don't tell you *why*.

**Sleuth does that digging automatically.** It connects:

- **PDF Invoices** → AI-extracted ledger entries (GPT-4o JSON mode)
- **Numbers** → Structured CSV ledgers (ZohoBooks vs. ERP)
- **Context** → Emails, Slack logs, internal notices (Qdrant RAG)

Using semantic vector search, Sleuth surfaces the root cause, evidence trail, and ready-to-post journal entries in a clean Markdown audit report.

---

## ✨ Features

### Tab 1 — Data Entry (Invoice Ingestion)
- **Multi-PDF Upload Queue** — Drop one or many PDFs at once; a queue progress bar tracks each file
- **AI Extraction** — GPT-4o extracts Invoice ID, Entity, Amount, and Date in JSON mode
- **Side-by-Side PDF Viewer** — The source document is embedded alongside the extracted data so you can visually cross-verify
- **Editable Fields** — Click any extracted field to correct it before saving
- **🔄 Re-extract** — Re-run AI extraction on the same PDF if the result looks wrong
- **Confirm & Save** — Appends the confirmed record to the System A (ZohoBooks) CSV ledger
- **Session History** — Last 5 confirmed invoices shown in the sidebar

### Tab 2 — Audit Suite (Reconciliation & Investigation)
- **KPI Cards** — Total Transactions · Flagged Issues · Variance at Risk
- **SYS A vs SYS B Reconciliation** — Upload both CSVs; all rows returned with 🔴 Discrepancy / 🟢 Matched status badges
- **Forensic Investigation** — Click any flagged row to run a RAG-powered investigation using Qdrant + GPT-4o
- **Markdown Audit Report** — Evidence chain, root cause analysis, journal entry table, AI confidence score — rendered live in the panel

### Infrastructure & Observability
- **Startup Health Check** — On boot, Sleuth checks if Qdrant is reachable and if the evidence collection exists, logging warnings to the console
- **Dashboard Warning Banner** — If Docker/Qdrant is offline, a persistent amber banner appears with a precise error and **Retry** button; auto-dismisses when healthy; polls every 30 s
- **Clear Investigation Errors** — 503 responses for "Vector Store Offline" and "Evidence Locker Empty" surface actionable messages inside the Forensic Report panel instead of a generic error
- **Qdrant Guard on Index** — `/api/index_db` also checks Qdrant before attempting to index

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.x, FastAPI, Uvicorn |
| **LLM** | OpenAI GPT-4o (JSON mode for extraction, RAG for investigation) |
| **Vector DB** | Qdrant (Docker) + FastEmbed |
| **PDF Processing** | PyMuPDF (`fitz`) |
| **Data Processing** | Pandas (`pd.to_numeric` for safe float coercion) |
| **Frontend** | HTML5, CSS3 (Inter Font), Bootstrap 5, jQuery, Marked.js |
| **Environment** | `uv`, `python-dotenv` |

---

## 🚀 Quickstart

### 1️⃣ Clone & Install

```bash
git clone https://github.com/Ramc26/Sleuth.git
cd Sleuth

# Install dependencies
uv add fastapi uvicorn jinja2 python-multipart pandas openai \
       qdrant-client[fastembed] pymupdf python-dotenv
```

### 2️⃣ Add Environment Variables

Create a `.env` file in the root:

```env
OPENAI_API_KEY=your_api_key_here
```

### 3️⃣ Start Qdrant (Docker Required)

The forensic investigation engine requires a running Qdrant instance:

```bash
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    qdrant/qdrant
```

> **Note:** The `-v` flag persists your vector data locally so it survives container restarts.

> **Note:** If Docker is not running, the app will start normally but will display a warning banner on the dashboard and return clear error messages when you attempt to run an investigation.

### 4️⃣ Generate Demo Data

```bash
uv run utilities/demo_data.py
```

### 5️⃣ Start the Server

```bash
uv run uvicorn main:app --reload
```

On startup, Sleuth logs the Qdrant health status:
```
✅ Qdrant healthy — evidence collection found.
# or
⚠️  Qdrant is NOT reachable. Docker may be down.
```

### 6️⃣ Open the App

**[http://localhost:8000](http://localhost:8000)**

---

## 🗂 Workflow

```
Tab 1: Data Entry
  ┌───────────────────────────────────────────────────────────┐
  │  Drop PDF(s) → AI Extracts → Review + Edit → Save Ledger │
  └───────────────────────────────────────────────────────────┘

Tab 2: Audit Suite
  ┌─────────────────────────────────────────────────────────────────┐
  │  Upload SYS A + SYS B → Reconcile → Click Discrepancy          │
  │  → AI searches Qdrant (emails, Slacks) → Forensic Report       │
  └─────────────────────────────────────────────────────────────────┘
```

**First time?**
1. Click **⚡ Sync Evidence Locker** (sidebar) to index evidence files into Qdrant.
2. Go to **Tab 1** and upload a vendor PDF invoice.
3. Go to **Tab 2**, upload both CSV ledgers from `data/demo_data/ledgers/`, and click **Reconcile**.
4. Click **Investigate** on any 🔴 Discrepancy row to generate the forensic report.

---

## 📁 Project Structure

```
Sleuth/
├── main.py                   # FastAPI app (routes, lifespan health check)
├── core/
│   ├── config.py             # Qdrant client + collection config
│   ├── invoice_processor.py  # PDF → JSON extraction (PyMuPDF + GPT-4o)
│   ├── investigator.py       # RAG forensic investigation (GPT-4o)
│   └── vector_store.py       # Qdrant indexing, search, & health check
├── templates/
│   └── index.html            # Two-tab UI with warning banner
├── static/
│   ├── css/style.css         # Premium FinTech styling (v2.1)
│   ├── js/app.js             # State management, queue, health polling
│   └── uploads/              # Uploaded PDFs (gitignored, served for viewer)
├── data/demo_data/
│   ├── ledgers/              # Sample CSVs (System A + System B)
│   └── evidence/             # Emails, Slack logs, notices for RAG
└── utilities/
    └── demo_data.py          # Demo data generator
```

---

## ⚠️ Common Issues

| Issue | Fix |
|---|---|
| `"Vector Store Offline"` banner on dashboard | Start the Qdrant Docker container (Step 3 above) |
| `"Evidence Locker Empty"` banner | Click **⚡ Sync Evidence Locker** in the sidebar |
| `❌ unsupported operand type(s) for -` on reconcile | Fixed in v2.1 — `pd.to_numeric()` coercion handles mixed-type CSVs |
| PDF viewer blank in browser | Some browsers block embedded PDFs — use the **"Open in new tab →"** fallback link |

---

**Developed by [Ram Bikkina](https://ramc26.github.io/RamTechSuite)**

---

*If reconciliation tools show the numbers, **Sleuth tells you the story behind them.** 🕵️‍♂️*
