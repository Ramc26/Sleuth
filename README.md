# 🕵️‍♂️ Sleuth: AI-Powered Forensic Accounting

**Sleuth** is a "RAG-lite" forensic accounting tool designed to move corporate finance from reactive auditing to real-time investigation. Instead of just flagging a discrepancy between ledgers, Sleuth dynamically searches through unstructured data—emails, Slack logs, and official notices—to find the "story" behind the numbers.

### 📖 The Problem It Solves
In traditional finance, reconciliation software identifies a variance (e.g., a $650 gap between a Vendor Ledger and an ERP Ledger). A human accountant must then spend hours hunting through inboxes and chat channels to find out *why* that gap exists. 

**Sleuth automates the investigation.** It connects the "Numbers" (Structured Ledgers) with the "Context" (Unstructured Communications) to provide instant explanations, root cause categorization, and ready-to-post Journal Entries.

### ✨ Key Features
* **Smart Context Filtering:** A custom Python-based filter that matches documents using Invoice IDs, Entity short-names, and float-rounded dollar amounts, preventing LLM hallucination and context-window overflow.
* **Executive Dashboard:** Real-time metrics showing total transactions, flagged discrepancies, and total variance at risk.
* **Batch Auditing:** Investigate the entire ledger at once with a single click and export the findings to a CSV report.
* **Flexible Data Ingestion:** Use the built-in realistic data generator, or drag-and-drop your own CSV ledgers directly via the UI sidebar.
* **Enterprise Formatting:** Outputs strict, scannable markdown reports including Confidence Scores, Root Causes, and formatted T-Account Journal Entries.

### 🛠 Tech Stack
* **Language:** Python 3.x
* **Environment Manager:** [uv](https://github.com/astral-sh/uv) (for high-speed dependency resolution)
* **Frontend:** Streamlit
* **Intelligence:** OpenAI (GPT-4o)
* **Data Handling:** Pandas

### 🚀 How to Run
1. Clone the repository and navigate to the directory.
2. Initialize the environment: `uv init` and install dependencies (`streamlit`, `pandas`, `openai`, `python-dotenv`).
3. Set your `OPENAI_API_KEY` in a `.env` file.
4. Generate the realistic test data: `uv run demo_data.py`
5. Launch the app: `uv run streamlit run main.py`

---
**Developer:** RamBikkina | **Portfolio:** [RamTechSuite](https://ramc26.github.io/RamTechSuite)