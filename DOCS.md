# 📘 Sleuth: Technical & Functional Deep-Dive

This document outlines the internal architecture, data flow, and logic mechanisms that power the Sleuth application.

---

### 📂 Detailed File Breakdown

#### 1. `demo_data.py` (The Scenario Generator)
This script does not just create random numbers; it builds a highly realistic, chaotic corporate data environment to stress-test the AI.
* **Data Asymmetry:** It generates Vendor ledgers (System A) and ERP ledgers (System B) with shuffled rows and missing entries to mimic real-world system drops.
* **Scenario Injection:** It deliberately injects specific accounting anomalies:
  * *FX Variances* (Exchange rate shifts resulting in floating-point differences).
  * *SLA Penalties* (Deductions communicated via Slack).
  * *Indirect Clues* (Evidence that mentions the company and the dollar amount, but omits the Invoice ID).
  * *Human Typos* (Transposition errors with zero supporting evidence).

#### 2. `engine.py` (The Investigative Core)
This handles the "RAG-lite" (Retrieval-Augmented Generation) pipeline. It acts as the bridge between the local file system and the LLM.
* **The Smart Filter:** Before calling the LLM, a strict Python gatekeeper filters the evidence locker. It searches for:
  1. Direct `Invoice ID` matches.
  2. A combination of the `Entity Name` (or short-name) AND the exact `Variance Amount`.
  * *Note on Floating-Point Math:* The engine actively rounds ledger variances to 2 decimal places to ensure string-matching succeeds even when Pandas generates numbers like `$649.9999999999964`.
* **Prompt Engineering:** The LLM is constrained by a strict markdown template, forcing it to output specific sections (Executive Summary, Evidence Chain, Recommended Action, and a Markdown Table for Journal Entries) rather than conversational text.

#### 3. `main.py` (The Command Center & UI)
Built with Streamlit, this file manages state, user interaction, and layout.
* **Dynamic Sourcing:** A sidebar allows users to either select pre-generated demo data or upload their own custom `.csv` files via drag-and-drop.
* **Data Alignment (`Pandas Merge`):** Uses `pd.merge(on=["invoice_id", "entity", "date"])` to align disparate ledgers and calculate the `Variance` column.
* **Investigation Board:** * *Single Mode:* Users can investigate a specific discrepancy via a dropdown.
  * *Batch Mode:* Iterates through all flagged rows, runs the `investigate_variance` pipeline for each, and compiles a downloadable `sleuth_audit_report.csv`.

---

### ⚙️ The Logic Flow (Step-by-Step)



1. **Ingestion:** `main.py` loads Ledger A and Ledger B.
2. **Detection:** Pandas calculates the variance. If `Variance != 0`, the row is flagged.
3. **Trigger:** User clicks "Investigate" (or "Run Full Audit").
4. **Retrieval (Local):** `engine.py` scans the `/evidence` directory and reads all `.txt` files into memory.
5. **Filtering (Local):** The Smart Filter discards 90% of the files (the "noise"), keeping only documents mathematically or contextually linked to the specific variance.
6. **Reasoning (Cloud):** The tightly filtered context is sent to GPT-4o with the strict forensic prompt.
7. **Resolution:** The UI renders the LLM's Markdown response, highlighting the root cause and providing the exact Journal Entry needed to fix the ERP.