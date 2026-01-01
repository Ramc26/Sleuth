# 🕵️‍♂️ Sleuth: Don't Just Audit. Investigate.

**Sleuth** is an AI-powered "Detective Accountant" designed to move corporate finance from reactive auditing to real-time investigation. Instead of just flagging a discrepancy, Sleuth digs through unstructured data—emails, Slack logs, and PDFs—to find the "story" behind the numbers.

### 📖 Description

In traditional finance, reconciliation software identifies a variance (e.g., a $10k gap), but a human must spend weeks investigating why it exists. **Sleuth** automates the investigation. It connects the "Numbers" (General Ledger) with the "Context" (Communications) to provide instant explanations and corrective actions.

### 🏗 Basic Architecture

Sleuth operates on a **Triple-Layer Truth** model:

1. **The Comparison Layer:** Matches structured data from different ledgers to identify mismatches (Variances).
2. **The Evidence Layer:** Ingests unstructured files (PDFs, .txt, .msg) from the "Evidence Locker."
3. **The Reasoning Layer (Agentic):** An LLM acts as the lead investigator, reading the context to reconcile the variance and propose a fix.

### 🛠 Tech Stack

* **Language:** Python 3.x
* **Environment Manager:** [uv](https://github.com/astral-sh/uv)
* **Frontend:** Streamlit
* **Intelligence:** OpenRouter / OpenAI (GPT-4o / Gemini 1.5 Pro)
* **Data Handling:** Pandas

### 👨‍💻 Developer

* **Name:** RamBikkina
* **Portfolio:** [RamTechSuite](https://ramc26.github.io/RamTechSuite)
* **Focus:** Building AI agents and Automation solutions.

---
