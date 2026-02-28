# 🕵️‍♂️ Sleuth: Enterprise AI Forensic Accounting

**Sleuth** is a smart Retrieval-Augmented Generation (RAG) app built for forensic accounting. Instead of waiting for audits after something breaks, Sleuth helps finance teams investigate issues in real time.

It looks through unstructured data like emails, Slack chats, and internal notices to uncover the *story* behind financial mismatches.

---

### 📖 The Problem It Solves

In most companies, reconciliation tools only tell you **there’s a mismatch** — for example, a $650 difference between a Vendor Ledger and your ERP system.

But they don’t tell you *why*.

Then a human has to manually search emails, Slack messages, and random files to figure out what happened. That can take hours.

**Sleuth does that digging automatically.**

It connects:

* **Numbers** → Structured CSV Ledgers
* **Context** → Emails, Slack logs, notices

Using semantic vector search, Sleuth finds explanations, identifies root causes, and even suggests ready-to-post Journal Entries.

---

### ✨ Key Features

* **Semantic Vector Search:**
  No fragile keyword matching. Sleuth uses dense embeddings (`FastEmbed` + `Qdrant`) so it understands that “six hundred and fifty” and “$650.00” mean the same thing — even if someone typed it differently.

* **Modern Web Dashboard:**
  Clean Bootstrap 5 UI with live financial metrics (Total Variance at Risk, Flagged Issues) and easy file uploads.

* **Decoupled API Architecture:**
  Built on `FastAPI` for speed. UI, AI logic, and data processing are cleanly separated.

* **Enterprise-Ready Reports:**
  Outputs clean markdown reports with:

  * AI Confidence Score
  * Root Cause Category
  * Proper T-Account Journal Entries

---

### 🛠 Tech Stack

* **Backend:** Python 3.x, FastAPI, Uvicorn
* **Frontend:** HTML5, CSS3, Bootstrap 5, jQuery
* **Vector Database:** Qdrant (Docker) + FastEmbed
* **LLM:** OpenAI (`gpt-4o`)
* **Data Processing:** Pandas
* **Environment Management:** uv

---

### 🚀 Quickstart Guide

Follow these steps to run Sleuth locally.

---

#### 1️⃣ Clone & Setup Environment

```bash
# Clone the repository
git clone https://github.com/YourUsername/Sleuth.git
cd Sleuth

# Install dependencies using uv
uv add fastapi uvicorn jinja2 python-multipart pandas openai qdrant-client[fastembed] python-dotenv
```

---

#### 2️⃣ Add Environment Variables

Create a `.env` file in the root folder:

```env
OPENAI_API_KEY=your_api_key_here
```

---

#### 3️⃣ Start Qdrant (Docker Required)

Sleuth uses Qdrant for semantic search. Make sure Docker is running:

```bash
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    qdrant/qdrant
```

The `-v` flag ensures vector data is stored locally in `qdrant_storage` even if the container restarts.

---

#### 4️⃣ Generate Demo Data

Create sample ledgers and communication data:

```bash
uv run utilities/demo_data.py
```

---

#### 5️⃣ Start the API Server

```bash
uv run uvicorn main:app --reload
```

---

#### 6️⃣ Start Investigating

Open your browser and go to:

**[http://localhost:8000](http://localhost:8000)**

1. Click **“Sync Evidence Locker”** to index documents into Qdrant.
2. Upload System A and System B ledgers from `data/demo_data_new/ledgers/`.
3. Click **Reconcile** and start the investigation.

---

**Developed by [Ram Bikkina](https://ramc26.github.io/RamTechSuite)**

---

If reconciliation tools show the numbers,
**Sleuth tells you the story behind them.** 🕵️‍♂️
