# Sleuth — AI Context & Handover Document

This document serves as a deep-state export of the Sleuth application. It is designed to be fed into a new AI agent (Cursor, Windsurf, Claude, etc.) so that it immediately understands the full project history, recent technical decisions, the exact state of the UI redesign, and the newly mapped payroll logic.

---

## 1. Project Background & Architecture

**Sleuth** is an AI-powered financial platform currently handling Invoice Ingestion and Ledger Reconciliation via RAG.

### Tech Stack
*   **Backend:** Python 3.12, FastAPI, Uvicorn, Pandas.
*   **AI Engine:** OpenAI GPT-4o (Structured Output for extraction; standard prompts for RAG investigations).
*   **Vector Database:** Qdrant (running locally via Docker) + FastEmbed for embedding generation.
*   **Integrations:** Zoho Books India DC (OAuth 2.0, Bills API, Contacts API, Chart of Accounts API).
*   **Frontend:** Vanilla JS/jQuery, CSS3 Custom Properties (Premium FinTech UI), HTML5, Font Awesome 6.

### Core Workflows
1.  **Data Entry (Tab 1):** Users upload 1-to-N PDF invoices (`/api/upload_invoice`). In parallel, GPT-4o extracts the Counterparty, Amount, Date, and Line Items. Upon review, hitting "Post to Ledger" (`/api/post_to_ledger`) appends the data to a local `system_a_vendor_ledger.csv` AND creates a Bill in Zoho Books. The source PDF is then deleted (`/api/invoice_pdf`).
2.  **Audit Suite (Tab 2):** Users upload two CSV ledgers (`/api/reconcile`). The backend merges them on `[invoice_id, entity, date]` and calculates variance. Clicking a discrepancy triggers a forensic RAG investigation (`/api/investigate`), querying Qdrant against indexed evidence rules/contracts (`/api/index_db`).

---

## 2. Recent Technical Milestones & Code Fixes

### A. The Zoho Books OAuth & API Rewrite
We successfully integrated Zoho Books, converting it from a theoretical feature into a working pipeline.
*   **The Problem:** Bills were being created in Zoho with `₹0.00` total amounts, despite the JSON payload containing the correct rates and quantities.
*   **The Diagnosis:** According to the OpenAPI spec for India DC, Zoho silently drops `line_items` if they don't contain a valid `account_id` (GL Account). 
*   **The Fix in `/core/zoho_client.py`:**
    1.  We fixed the OAuth flow scope. Added `ZohoBooks.accountants.READ` to `/zoho/auth/start` so Sleuth could read the Chart of Accounts.
    2.  Built `get_purchase_account_id(access_token)`: The India DC API does not support `filter_by=AccountType.Expense`. Instead, we pull the *entire* chart, filter locally for `account_type` in `["expense", "cost_of_goods_sold", "other_expense"]`, and pick the best match by prioritizing keywords like "cost of goods", "purchase", and "direct cost".
    3.  In `create_bill()`, we now resolve the `vendor_id`, resolve the `account_id`, and construct the line items perfectly.
    4.  **Date Bug Fixed:** Zoho returns HTTP 400 if you pass an empty `date: ""`. The payload now conditionally injects the date only if truthy.

### B. The Premium UI Redesign (V5 in progress)
The user requested a massive aesthetic overhaul: *"Behave like a 20+ years seasoned UI/UX frontend developer. Make it premium, enterprise-ready, with glassmorphism, responsive views, and animations."*

*   **`index.html`:** Emojis stripped out completely, replaced with Font Awesome 6 (`<i class="fa-solid fa-*">`). Added a new `<header class="mobile-header">` and `<div class="sidebar-overlay">` for responsive mobile drawer toggling. Tab panels were given `animate-fade-in` wrappers.
*   **`style.css`:** Implemented a new `:root` token system. 
    *   Colors: Midnight blue sidebar (`#090e17`), electric blue accents (`#3b82f6`), and subtle slate backgrounds (`#f3f5f9`).
    *   Shadows: Layered depth (`--shadow-glass`, `--shadow-md`).
    *   Typography: Inter for UI, JetBrains Mono for financial figures.
    *   Animations: `@keyframes fadeIn`, `slideUp`, `pulse` added. 
    *   Media Queries: Added breakpoints at `1024px` (stacking panels) and `768px` (hiding sidebar, enabling mobile header).
*   **`app.js` (Current Focus):** Rewrote `switchTab()` to force HTML reflows so CSS animations trigger properly on tab changes. Added `toggleSidebar()` logic. **Currently migrating the PDF batch uploader to process in parallel (`Promise.all()`) and inject individual loading state cards into the UI.**

---

## 3. Reverse-Engineered Payroll Logic (New Discovery)

The user provided three CSVs (`Jan'26- LeaveBal`, `Anchor-Attendance`, `Anchors_Feb'26`) to deduce precisely how "Anchors" (employees) are paid.

**Here is the explicit mathematical model we extracted for February 2026:**

#### Step 1: Leave Balances & Accrual
*   **Monthly Accrual:** Employees gain +0.5 Casual Leave (CL), +0.5 Sick Leave (SL), and +1.0 Earned Leave (EL) each month.
*   **Feb Opening Balance:** `[Closing Leave Balance - Jan]` + `[Monthly Accrual]`
*   **Feb Utilization:** Counted from the Attendance CSV (tags like `L`, `HFL`).
*   **Feb Closing Balance:** `[Opening]` - `[Utilized]`. *(Extra EL balances are tracked in a standalone column).*

#### Step 2: "Payable Days" Calculation
*   Anchors are measured against a standard **28-day** month (Feb).
*   **Base formula:** `Present + Paid Week-Offs (W/O) + Paid Leaves (L) + Holidays (H) + Half-Days (HFL = 0.5)`
*   **Deductions:** Unpaid Leaves (UL) or Loss Of Pay (LOP) are subtracted from 28.
*   **Resignations:** If an employee resigns mid-month, the denominator remains 28, but their payable days only count up to their Date of Exit (DOE).

#### Step 3: Base Pay & Arrears/Bonuses
*   **Standard Month Salary:** Typically fixed at `₹12,360/month` for standard Anchors.
*   **Current Month Salary (Prorated Basic):** 
    `Standard Salary \u00d7 (Payable Days \u00f7 28)`
*   **One-Time Bonus / Notice Adjustment:** 
    For certain separated employees, the company makes them whole. For instance, if an anchor resigns on Feb 19, their prorated pay is ₹8,387. A bonus of ₹3,973 is added to reach exactly ₹12,360.
*   **Gratuity Calculation:** Evaluated for tenure \u2265 5 years.
    `Statutory Formula: (Last Drawn Basic \u00f7 26) \u00d7 15 \u00d7 Completed Years`

#### Step 4: Statutory Deductions & Final Net
*   **EPF (Employee Provident Fund - 12%):** 
    Calculated **exclusively** on the prorated `Current Month Salary`. Bonuses and Gratuity are absolutely excluded from this math.
*   **ESI (Employee State Insurance - 0.75%):** 
    Calculated on the *Gross combination* of (`Current Month Salary` + `One-Time Bonus`). Gratuity is exempt from ESI.
*   *(Employer Contributions exist in the sheet but are standard statutory matches: 8.33% Pension, 3.67% EPF, 3.25% ESI).*
*   **Final Net Salary:** `[Current Salary + Bonus + Gratuity] - [EPF + ESI + LWF + TDS]`

---

## 4. Immediate Next Steps / Agent Handover

To the next AI agent picking up this context, here is exactly where the work paused:

1.  **Frontend Batch Parallelism:** The UI redesign looks great in CSS, but `app.js` needs the `startBatch()` function updated. The user requested that multiple PDF uploads be iterated via `Promise.all()`, injecting a UI card for *each* file into the `#queueListBody` independently as their specific GPT-4o extractions complete.
2.  **Payroll Module (Optional but planned):** Using the exact logic mapped out in Section 3, the next logical backend step is to create an `/api/process_payroll` endpoint that ingests raw attendance and spits out the final `Anchors_Feb'26.csv` output ledger perfectly matched to the math models above.
3.  **Cleanup Verification:** Test that calling `/api/post_to_ledger` successfully deletes the PDF out of `static/uploads/` via the new cleanup routine.

**Godspeed.** 
