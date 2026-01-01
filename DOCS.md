# 📘 Sleuth: Technical & Functional Deep-Dive

### 📂 Detailed File Breakdown

* **`main.py` / `app.py`**: The command center. It handles the UI state, triggers the background investigation, and displays results.
* **`engine.py`**: Contains the `investigate_variance` function. It performs the "RAG-lite" process of reading all text files and passing them to the LLM with a specific forensic prompt.
* **`demo_data.py`**: The scenario generator. It builds a controlled environment with 15 transactions, 4 deliberate errors, and 4 specific text clues hidden in sub-folders.
* **`pyproject.toml`**: Managed by `uv`, ensuring high-speed dependency resolution.

---

### 🖥 The User Interface (UI) Experience

#### **1. The Dashboard (Initial View)**

When the user opens Sleuth, they see two distinct sections:

* **The Comparison Table:** A merged view of Ledger A and Ledger B. Rows with mismatches are highlighted in **Soft Red** to draw the eye.
* **The Variance Column:** A calculated field showing exactly how many dollars are missing or extra.

#### **2. Interaction & Investigation**

* **The Selection Box:** The user selects a specific "Red" Invoice ID from a dropdown menu.
* **The "Investigate" Button:** Clicking this triggers the `sleuth_engine`.
* **The Progress State:** A "Sleuth is digging..." spinner appears, indicating the agent is reading the Evidence Locker.

#### **3. The Sleuth Verdict**

An **Information Card** appears in the UI containing:

* **The Evidence Found:** A quote from the specific email or log that explains the gap.
* **The Reasoning:** Why the agent thinks this matches the variance.
* **The Fix:** A proposed Journal Entry (e.g., "Adjust Sub-A Ledger by -$500").

---

### ⚙️ How the Functions Work (The Logic Flow)

#### **Step 1: Data Alignment (`Pandas Merge`)**

Sleuth loads two CSVs and uses `pd.merge(on='invoice_id')`. It then calculates:



If , the record is sent to the "Investigation Board."

#### **Step 2: Evidence Aggregation (`os.walk`)**

The `get_all_evidence()` function recursively walks through all sub-directories in `/evidence`. It reads every `.txt` file and joins them into one large string of "Context."

#### **Step 3: The Agentic Reasoning (LLM)**

The LLM is given a "System Prompt" that defines its personality as a **Forensic Accountant**. It receives:

1. The specific math problem (e.g., "Find where $500 went").
2. The massive pile of unstructured text.
3. The instruction to **ignore noise** and only cite relevant proof.

#### **Step 4: Output Rendering**

The text returned by the LLM is rendered in Streamlit using `st.info()`. This ensures the report is formatted clearly with markdown (bold text, bullet points).

---

### 🔄 The "Sentinel" Flow

1. **Ingestion:** New ledger and email files are dropped into the `demo_data` folder.
2. **Detection:** Sleuth immediately identifies which transactions no longer match.
3. **Diagnosis:** The user clicks "Investigate" to let the agent connect the dots.
4. **Resolution:** The agent provides the text needed to update the books.

### 🎯 Strategic Value

By using this flow, a company reduces the **"Time to Resolution"** for accounting errors from weeks to seconds. It replaces manual "document hunting" with AI-driven "story-finding."

---

**Would you like me to help you add a "Download Investigation Report" button so the user can save Sleuth's findings as a PDF?**