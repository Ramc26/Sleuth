# Sleuth — AI-Powered Financial Forensics

Sleuth is a three-module financial operations platform: autonomous invoice capture into your ERP, AI-powered ledger reconciliation & audit investigation, and a fully-automated payroll engine.

Built with FastAPI, GPT-4o, Qdrant, and Zoho Books.

---

## What it does

**Tab 1 — Invoice Capture**
Upload vendor invoice PDFs → GPT-4o extracts fields in parallel → review and confirm → data written to local ledger CSV and posted directly to Zoho Books as a Bill → PDF deleted automatically.

**Tab 2 — Variance Analysis (Audit Suite)**
Upload two ledger CSVs → row-by-row variance computed → click any discrepancy → GPT-4o runs a forensic RAG investigation against your evidence base in Qdrant.

**Tab 3 — Payroll Engine**
Upload the monthly Anchor Attendance CSV → full payroll calculated using Excel-matched formulas → view KPIs → export payroll CSV and next month's leave-balance CSV. Per-employee deductions (TDS, Advance, Insurance) are stored and auto-applied every month.

---

## Architecture

```
Browser UI (HTML + CSS + jQuery)
        │
        ▼
FastAPI (main.py)
   ├── Invoice Capture
   │     ├── POST /api/upload_invoice          ← save PDF, call GPT-4o
   │     ├── POST /api/post_to_ledger          ← write CSV + Zoho Bill
   │     └── DELETE /api/invoice_pdf           ← cleanup after posting
   │
   ├── Audit Suite
   │     ├── POST /api/reconcile               ← merge two CSVs, compute variance
   │     ├── POST /api/investigate             ← RAG forensic report via Qdrant
   │     ├── POST /api/index_db               ← index evidence files into Qdrant
   │     └── GET  /api/health                  ← Qdrant reachability check
   │
   ├── Payroll Engine
   │     ├── POST /api/payroll/process         ← parse attendance CSV → compute payroll
   │     ├── GET|POST /api/payroll/config      ← read/write formula_config.json
   │     ├── POST /api/payroll/config/reset    ← revert to built-in defaults
   │     ├── GET  /api/payroll/download/payroll
   │     ├── GET  /api/payroll/download/leave_balance
   │     ├── GET|POST /api/payroll/employee_deductions   ← TDS/Advance/Insurance DB
   │     └── DELETE /api/payroll/employee_deductions/{emp_id}
   │
   └── Zoho Books
         ├── GET  /zoho/auth/start             ← start OAuth 2.0
         ├── GET  /zoho/oauth/callback         ← exchange code for tokens
         ├── GET  /api/zoho/status
         ├── POST /api/zoho/disconnect
         └── GET  /api/zoho/debug
         │
         ├── OpenAI GPT-4o       ← invoice extraction + forensic reports
         ├── Qdrant (Docker)     ← cosine-similarity vector evidence store
         └── Zoho Books India DC ← Bills + Contacts via REST API
```

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| AI | OpenAI GPT-4o (JSON mode for extraction, prose for forensic reports) |
| Vector DB | Qdrant (self-hosted via Docker) + fastembed |
| ERP | Zoho Books India DC — OAuth 2.0, Bills API, Contacts API, Chart of Accounts |
| PDF | PyMuPDF (fitz) |
| Data | Pandas |
| Frontend | HTML5, Vanilla CSS3 (design-token system), jQuery, Marked.js, Font Awesome 6 |

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/yourname/sleuth.git
cd sleuth
uv sync                        # or: pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=sk-...

# Zoho Books (India DC) — optional; Sleuth works without it (CSV-only mode)
ZOHO_CLIENT_ID=1000.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
ZOHO_CLIENT_SECRET=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
ZOHO_ORG_ID=XXXXXXXXXX
ZOHO_REDIRECT_URI=http://localhost:8000/zoho/oauth/callback
ZOHO_REFRESH_TOKEN=       # auto-written after first OAuth
```

### 3. Start Qdrant (only needed for the Audit Suite investigation feature)

```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 4. Start Sleuth

```bash
uv run uvicorn main:app --reload
```

Open **http://localhost:8000**

---

## Payroll Engine — How It Works

### Input files
| File | What it contains |
|---|---|
| Monthly Attendance CSV | Per-employee day-by-day tags (P, W/O, L, HFL, UL, ML, MG…) + computed attendance totals and leave balance columns |
| `formula_config.json` | Editable salary slabs, EPF/ESI rates, profession tax slabs, gratuity params, LWF |
| `employee_db.json` | Per-employee persistent deductions — TDS, Advance recovery, Insurance premium |

### Payroll calculation flow

```
1. Parse attendance CSV (regex filter for JAI-XXXX rows — no fixed row-skip)

2. payable_days = total_days − UL − util_lop
   (computed from raw cols; never from pre-computed col 53 which may be integer-rounded)

3. current_salary_raw = std_salary / 28 × payable_days    ← raw float

4. basic_raw = current_salary_raw × basic_pct             ← 100% Anchor / 90% AMIA
   hra_raw   = current_salary_raw × hra_pct               ← 0% Anchor / 10% AMIA

5. gross_salary = ROUND(basic_raw + hra_raw + lta + sa)   ← FIRST & ONLY ROUND here

6. gross_for_pf = ROUND(basic_raw + lta + sa)             ← excludes HRA

7. bonus     = std_salary − gross_salary   [resigned employees; total_days ≥ 15 threshold]
   gratuity  = ROUND(std_salary × 15/26 × completed_years)  [resigned, ≥ 5 years]

8. final_gross = gross_salary + bonus + gratuity
   esi_base   = final_gross − gratuity

9. epf_employee   = ROUND(IF(gross_for_pf > 15000, 1800, gross_for_pf × 12%))
   esi_employee   = ROUNDUP(IF(std_salary > 21000, 0, esi_base × 0.75%))
   profession_tax = IF(esi_base ≥ 20001, 200, IF(esi_base ≥ 15001, 150, 0))

10. Load tds, advance, insurance from employee_db.json (keyed by EMP ID)

11. net_salary = ROUND(final_gross − (tds + advance + insurance + profession_tax
                                     + epf_employee + esi_employee + lwf))
```

### Salary slabs

| Slab | Std Salary | Basic % | HRA % | Detection keyword |
|---|---|---|---|---|
| Anchor | ₹12,360 | 100% | 0% | Default |
| AMIA | ₹17,000 | 90% | 10% | "amia" / "aima" |
| Asset | ₹17,000 | 90% | 10% | "bht" / "asset" |

### Employee Deductions Manager

Per-employee TDS, Advance recovery, and Insurance deductions are stored permanently in `data/payroll_reference/employee_db.json`. They auto-apply to every payroll run until manually removed.

**UI:** Payroll Engine tab → **Deductions** button → editable table → Save All Changes.

**Useful for:** Multi-month advance recovery, insurance premiums, TDS on high earners. New HR staff see the deductions immediately — no institutional-knowledge required.

---

## API Reference

### Invoice Capture

```bash
# Upload a PDF invoice
curl -X POST http://localhost:8000/api/upload_invoice \
  -F "file=@invoice.pdf"

# Confirm and post to ledger + Zoho Books
curl -X POST http://localhost:8000/api/post_to_ledger \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "INV-2024-001",
    "entity": "Amazon Web Services",
    "amount": 4582.50,
    "date": "2024-08-03",
    "billing_period": "Aug 2024"
  }'

# Delete a temporary PDF (called automatically by the UI)
curl -X DELETE "http://localhost:8000/api/invoice_pdf?pdf_url=/static/uploads/invoice.pdf"
```

### Audit Suite

```bash
# Reconcile two ledgers
curl -X POST http://localhost:8000/api/reconcile \
  -F "file_a=@system_a.csv" \
  -F "file_b=@erp_export.csv"

# Investigate a flagged discrepancy
curl -X POST http://localhost:8000/api/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "INV-2024-001",
    "entity": "Amazon Web Services",
    "amount_a": 4582.50,
    "amount_b": 5000.00
  }'

# Sync evidence files into Qdrant (run once, or after adding new evidence docs)
curl -X POST http://localhost:8000/api/index_db

# Qdrant health check
curl http://localhost:8000/api/health
# → {"ok": true, "qdrant": {"reachable": true}}
```

### Payroll Engine

```bash
# Process an attendance CSV → full payroll
curl -X POST http://localhost:8000/api/payroll/process \
  -F "attendance_file=@Anchor-Attendance.csv"
# → { "employees": [...], "summary": {...}, "config": {...} }

# Download payroll CSV (after processing)
curl http://localhost:8000/api/payroll/download/payroll -o payroll_output.csv

# Download leave-balance CSV for next month
curl http://localhost:8000/api/payroll/download/leave_balance -o closing_leave_bal.csv

# Get current formula configuration
curl http://localhost:8000/api/payroll/config

# Update formula parameters (e.g. change EPF ceiling)
curl -X POST http://localhost:8000/api/payroll/config \
  -H "Content-Type: application/json" \
  -d '{"epf": {"ceiling": 15000, "employee_rate": 0.12, "pension_rate": 0.0833}}'

# Reset formula config to built-in defaults
curl -X POST http://localhost:8000/api/payroll/config/reset

# View all per-employee static deductions
curl http://localhost:8000/api/payroll/employee_deductions
# → { "JAI-805": { "tds": 0, "advance": 0, "insurance": 5763 } }

# Add or update an employee's deductions
curl -X POST http://localhost:8000/api/payroll/employee_deductions \
  -H "Content-Type: application/json" \
  -d '{
    "JAI-805": { "tds": 0, "advance": 0, "insurance": 5763 },
    "JAI-042": { "tds": 2000, "advance": 5000, "insurance": 0 }
  }'

# Clear a specific employee's deduction record
curl -X DELETE http://localhost:8000/api/payroll/employee_deductions/JAI-805
```

### Zoho Books

```bash
# Start OAuth (open in browser — redirects to Zoho consent screen)
open http://localhost:8000/zoho/auth/start

# Check connection status
curl http://localhost:8000/api/zoho/status
# → {"connected": true, "org_id": "60066752082"}

# Disconnect
curl -X POST http://localhost:8000/api/zoho/disconnect

# Debug: see resolved GL account_id from Chart of Accounts
curl http://localhost:8000/api/zoho/debug
```

---

## Zoho Books Setup

1. Create a **Self Client** at [Zoho API Console India DC](https://api-console.zoho.in) → Redirect URI: `http://localhost:8000/zoho/oauth/callback`
2. Add Client ID, Client Secret, and Org ID to `.env`
3. Visit `http://localhost:8000/zoho/auth/start` → complete consent screen
4. Sidebar shows green dot with Org ID. `ZOHO_REFRESH_TOKEN` auto-written to `.env`.

**Required OAuth scopes** (set automatically):
```
ZohoBooks.bills.CREATE
ZohoBooks.contacts.CREATE
ZohoBooks.contacts.READ
ZohoBooks.accountants.READ    ← critical: needed to resolve GL account_id for bill line items
```

> Without `ZohoBooks.accountants.READ`, Zoho silently creates bills with ₹0.00 payable. This is a documented India DC API behavior.

---

## Data Storage

| What | Where |
|---|---|
| Uploaded PDFs (temp) | `static/uploads/` — deleted after posting |
| Vendor ledger | `data/demo_data/ledgers/system_a_vendor_ledger.csv` |
| Evidence files (for RAG) | `data/evidence/` |
| Qdrant vector store | `qdrant_storage/` (git-ignored) |
| OAuth refresh token | `.env` → `ZOHO_REFRESH_TOKEN` |
| Payroll formula config | `data/payroll_reference/formula_config.json` |
| Employee deductions DB | `data/payroll_reference/employee_db.json` |
| Reference paysheet | `data/payroll_reference/Anchors_Feb26.csv` |
| Reference attendance | `data/payroll_reference/Anchor_Attendance.csv` |

---

## Requirements & Notes

- **Qdrant via Docker** is only needed for the Audit Suite investigation feature. Invoice Capture and Payroll Engine work without it. The UI shows a clear warning if Qdrant is unreachable.
- **Zoho Org ID** must be in `.env` before starting OAuth.
- Zoho auth codes expire in ~60 seconds — complete the OAuth flow in one go.
- Payroll attendance CSV must use the Anchor CSV format (`JAI-XXXX` employee IDs). The engine auto-detects data rows by regex — any number of header rows are tolerated.
- All payroll formula parameters are editable in the UI **Formula Config** panel — no code changes needed for rate adjustments.
