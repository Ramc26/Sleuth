# 📘 Sleuth: Technical & Functional Deep-Dive

This document explains how Sleuth works internally

Sleuth started as a basic inference script. Now it has evolved into a clean, modular **Retrieval-Augmented Generation (RAG)** system built to scale for enterprise use.

---

## 📂 Modular Architecture & File Breakdown

Sleuth is structured clearly so each part has one responsibility.

---

### 1. `core/` (The Brain)

This folder contains the main intelligence.

* **`config.py`:**  
  Stores environment variables and initializes core clients (`OpenAI` for reasoning and `QdrantClient` for vector storage).

* **`vector_store.py` (RAG Engine):**  
  Handles semantic search. It converts unstructured evidence into vector embeddings using `FastEmbed`, stores them in **Qdrant**, and performs similarity search to retrieve relevant documents.

* **`investigator.py` (LLM Agent):**  
  Builds a strict markdown prompt. It combines structured ledger data with retrieved evidence and forces the LLM to return:
  - Executive Summary  
  - Root Cause  
  - Journal Entry table  

---

### 2. `main.py` (UI & Control Layer)

Built using Streamlit. This file handles user interaction and app flow.

* **Database Management:**  
  A button allows users to index new evidence into the Qdrant vector database.

* **Dynamic Sourcing:**  
  Users can choose demo data or upload custom `.csv` files.

* **Investigation Board:**  
  - *Single Mode:* Investigate one discrepancy interactively.  
  - *Batch Mode:* Runs investigations on all flagged rows and generates `sleuth_audit_report.csv`.

---

### 3. `utilities/demo_data.py` (Scenario Generator)

Creates realistic corporate data for testing.

* **Data Asymmetry:**  
  Generates mismatched Vendor (System A) and ERP (System B) ledgers with shuffled and missing rows.

* **Scenario Injection:**  
  Adds anomalies like FX variances, SLA penalties, missing invoice IDs, and human typos.

---

# 🧠 How RAG & Vector Search Works in Sleuth

Traditional keyword matching (like checking if `"INV-101"` exists in text) is fragile.  
It fails with typos, nicknames, or indirect descriptions.

Sleuth uses **Semantic Vector Search** instead.

---

## 1. Vector Creation (Ingestion Phase)

When the user clicks “Index Evidence to Qdrant”:

- Each document is converted into a dense vector using `FastEmbed`.
- A vector represents the *meaning* of the text.
- Vectors + metadata (like filename) are stored in Qdrant.

So we store meaning, not exact words.

---

## 2. Semantic Search (Retrieval Phase)

When investigating a discrepancy:

- Sleuth creates a search query using known details (invoice ID, entity, amount).
- That query is converted into a vector.
- Qdrant calculates cosine similarity between the query vector and stored document vectors.
- Documents with similarity score > 0.50 are returned.
- Top 3 most relevant documents are passed to the LLM.

---

## 💡 Example: Why This Matters

Suppose there’s a **$650 discrepancy** for **Zenith Logistics**.

A Slack message says:

> “We docked six hundred and fifty dollars from the Zenith bill due to pallet damage.”

**Keyword Search:**  
Fails if searching for `"650"` or `"Zenith Logistics"`.

**Vector Search:**  
Understands:
- "six hundred and fifty" = 650  
- "Zenith" relates to "Zenith Logistics"  
- The context explains a deduction  

It retrieves the correct message.

---

# ⚙️ End-to-End Logic Flow

1. **Structured Ingestion:**  
   `main.py` loads Ledger A and Ledger B using Pandas.

2. **Detection:**  
   Variance is calculated (`System A - System B`).  
   Rows where `Variance != 0` are flagged.

3. **Unstructured Ingestion:**  
   Evidence documents are embedded and stored in Qdrant.

4. **Trigger:**  
   User clicks “Investigate” on a flagged row.

5. **Retrieval (RAG):**  
   `vector_store.py` fetches top 3 semantically similar documents.

6. **Reasoning (LLM):**  
   `investigator.py` sends structured data + filtered evidence to GPT-4o using a strict template (`temperature = 0.0`).

7. **Resolution:**  
   Streamlit renders:
   - Executive Summary  
   - Root Cause  
   - Source citations  
   - Journal Entry  
   Batch mode generates a downloadable report.

---
---

### 🚀 Future Roadmap: Phase 2 (Hardening & Scale)

To transition from MVP to a production-ready enterprise tool, the following features are scheduled for development:

#### 1. Multi-Modal Evidence Processing (OCR)
* **The Goal:** Handle scanned receipts, handwritten notes, and mobile photos.
* **Tech:** Integration of `EasyOCR` or `AWS Textract` to process image-based evidence that lacks a digital text layer.

#### 2. Archive & Attachment Extraction
* **The Goal:** Automatically unpack `.zip` archives and `.msg` email attachments.
* **Tech:** Recursive pre-processing layer to "flatten" nested data structures before indexing into Qdrant.

#### 3. Temporal Search Weighting (Recency Bias)
* **The Goal:** Prevent "Semantic Drift" where old documents with similar amounts trick the AI.
* **Tech:** Implementing a decay function in Qdrant to prioritize evidence where the document metadata date matches the ledger transaction date.

#### 4. ERP Integration (The "Close-the-Loop" Phase)
* **The Goal:** Direct API hooks into SAP, NetSuite, or QuickBooks.
* **Tech:** OAuth2 authentication to post approved Journal Entries directly to the General Ledger after human verification.
Sleuth combines structured data, semantic retrieval, and controlled LLM reasoning  
to deliver reliable, enterprise-ready audit investigations.