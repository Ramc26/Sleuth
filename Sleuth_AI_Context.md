# Sleuth — AI Context & Handover Document

This document is the full deep-state export of Sleuth. Feed it into any AI agent (Cursor, Windsurf, Claude, Gemini, etc.) so it immediately understands the full history, architecture, and current state of the codebase.

---

## 1. Project Background & Architecture

**Sleuth** is an AI-powered financial platform with three production modules:

### Tech Stack
| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| AI | OpenAI GPT-4o (structured output for extraction; RAG for forensic reports) |
| Vector DB | Qdrant (self-hosted via Docker) + fastembed |
| ERP | Zoho Books India DC — OAuth 2.0, Bills API, Contacts API, CoA API |
| PDF | PyMuPDF (fitz) |
| Data | Pandas |
| Frontend | HTML5, Vanilla CSS3 (design-token system), jQuery, Marked.js, Font Awesome 6 |

### Module Overview
1. **Invoice Capture (Tab 1):** Upload 1–N PDFs → parallel GPT-4o extraction → review fields → `POST /api/post_to_ledger` writes to `system_a_vendor_ledger.csv` AND creates a Bill in Zoho Books → PDF deleted.
2. **Audit Suite (Tab 2):** Upload two ledger CSVs → `POST /api/reconcile` merges on `[invoice_id, entity, date]` → click any discrepancy → `POST /api/investigate` runs a forensic RAG report querying Qdrant.
3. **Payroll Engine (Tab 3):** Upload a monthly Anchor-Attendance CSV → `POST /api/payroll/process` computes full payroll using formulas reverse-engineered from `SamplePaysheet.xlsx` → view KPIs / filter / export payroll CSV + leave-balance CSV.

---

## 2. Significant Technical Milestones

### A. Zoho Books OAuth & API Fix
- **Problem:** Bills created with ₹0.00 totals. Zoho silently drops `line_items` without a valid `account_id`.
- **Fix:** Added `ZohoBooks.accountants.READ` scope. Built `get_purchase_account_id()` in `core/zoho_client.py` — pulls full Chart of Accounts, filters locally for expense accounts, picks best match by keyword. Conditional `date` injection to avoid HTTP 400.

### B. Premium UI Redesign (V5)
- `:root` CSS token system: midnight-blue sidebar (`#090e17`), electric-blue accent (`#3b82f6`), Inter + JetBrains Mono.
- Glassmorphism, `fadeIn` / `slideUp` / `pulse` keyframe animations, responsive breakpoints at 1024px and 768px.
- Mobile sidebar drawer with overlay. Font Awesome 6 replacing all emojis.
- Parallel PDF batch upload: all files processed simultaneously via separate `$.ajax()` calls; per-file invoice card renders independently as each GPT-4o call completes.

### C. Health Check Optimization
- **Before:** `setInterval(checkHealth, 30_000)` — polling Qdrant every 30s regardless of active tab, flooding server logs.
- **After:** Single check on page load + re-check only when user opens the Audit Suite (Analysis) tab. Payroll and Invoice tabs never trigger a Qdrant health check.

---

## 3. Payroll Engine — Complete Technical Reference

### Files
| File | Purpose |
|---|---|
| `core/payroll_engine.py` | Core computation: parses attendance CSV, runs full payroll math, exports CSVs |
| `data/payroll_reference/formula_config.json` | All tunable formula parameters (salary slabs, EPF/ESI rates, PT slabs, gratuity config) |
| `data/payroll_reference/employee_db.json` | Per-employee persistent static deductions (TDS / Advance / Insurance) |
| `data/payroll_reference/Anchors_Feb26.csv` | Reference paysheet (SamplePaysheet.xlsx export) with embedded formula docs |
| `data/payroll_reference/Anchor_Attendance.csv` | Reference attendance CSV with formula docs |
| `data/payroll_reference/Jan26_LeaveBal.csv` | Reference Jan closing leave balances |

### Attendance CSV Column Map (0-indexed, data rows detected by `JAI-\d+` regex)
```
col  1: EMP ID        col  2: Names         col  3: Customer      col  9: DOJ
col 10: DOE           col 11–38: Day 1–28   col 39: Present count  col 40: W/O count
col 41: Leaves (L)    col 42: HFL count     col 43: Holidays       col 44: MG (Marriage)
col 45: ML            col 46: UL            col 51: Total Days (AZ) col 52: Total Actual
col 53: Payable Days (BB) — NOT read directly; see Payable Days note below
col 55: Opening CF    col 56: Opening CL    col 57: Opening SL     col 58: Opening EL
col 59: Opening MG    col 60: Opening ExtraEL
col 61: Util CF       col 62: Util CL       col 63: Util SL        col 64: Util EL
col 65: Util MG       col 66: Util LOP (BO) ← KEY for payable days
col 67: Closing CF    col 68: Closing CL    col 69: Closing SL     col 70: Closing EL
col 71: Closing MG    col 72: Closing ExtraEL
```

### Formula Chain (matches SamplePaysheet.xlsx exactly)

```
payable_days        = total_days − ul − util_lop          ← computed from cols 51, 46, 66
                      (NOT read from col 53 — some CSV exports round it to integers,
                       losing 0.5-day precision from HFL half-day leaves)

current_salary_raw  = std_salary / 28 * payable_days      ← raw float, NOT rounded

basic_raw           = current_salary_raw * basic_pct       ← 100% Anchor, 90% AMIA/Asset
hra_raw             = current_salary_raw * hra_pct         ← 0% Anchor, 10% AMIA/Asset

gross_salary        = ROUND(basic_raw + hra_raw + lta + sa)   ← FIRST & ONLY ROUND

gross_for_pf        = ROUND(basic_raw + lta + sa)             ← gross minus HRA
bonus               = std_salary − gross_salary               ← resigned employees, threshold gate
gratuity            = ROUND(std_salary * 15 / 26 * completed_years)   ← ≥5 yrs resigned only
final_gross         = gross_salary + bonus + gratuity
esi_base            = final_gross − gratuity                  ← gross + bonus

epf_wages           = ROUND(IF(gross_for_pf > 15000, 15000, gross_for_pf))
epf_employee        = ROUND(IF(gross_for_pf > 15000, 1800, gross_for_pf * 12%))
esi_employee        = ROUNDUP(IF(std_salary > 21000, 0, esi_base * 0.75%))
profession_tax      = IF(esi_base ≥ 20001, 200, IF(esi_base ≥ 15001, 150, 0))
lwf                 = config value (default 0)
pf_esi_lwf          = epf_employee + esi_employee + lwf

tds/advance/insurance ← loaded per EMP ID from employee_db.json

net_salary          = ROUND(final_gross − (tds + advance + insurance + profession_tax + pf_esi_lwf))
```

### Salary Slabs
| Slab | Std Salary | Basic % | HRA % | Detected by |
|---|---|---|---|---|
| `anchor` | ₹12,360 | 100% | 0% | Default |
| `amia` | ₹17,000 | 90% | 10% | "aima"/"amia" in customer |
| `asset` | ₹17,000 | 90% | 10% | "bht"/"asset" in customer |

### Employee Status Logic
| Status | Condition | Net Effect |
|---|---|---|
| Active | No DOE, ML < 28, UL < 28 | Normal proration |
| Resigned | DOE present | Prorated + bonus if `total_days ≥ 15` (makes up to full std_salary) |
| Maternity | ML ≥ 28 | Full payable days = 28, no deductions |
| Long Leave | UL ≥ 28 | payable_days = 0 → net = 0 |

### Employee Static Deductions (`employee_db.json`)
- Stores per-employee `tds`, `advance`, `insurance` that persist month-to-month.
- Pre-populated from reference paysheet (e.g. `JAI-805: insurance=₹5,763`).
- HR edits via **Payroll Engine → Deductions** button in the UI (saved to disk instantly).
- Engine merges these into `total_deductions` and `net_salary` on every payroll run.

### Key Bugs Fixed in This Session
| Bug | Root Cause | Fix |
|---|---|---|
| JAI-148, JAI-394 missing | Engine skipped first 3 rows (hardcoded), reference CSV has only 1 header row | Switched to EMP ID regex filter — no fixed row skip |
| HFL 0.5-day precision lost | Col 53 stored as integers in some CSV exports | Compute `payable_days = total_days − ul − util_lop` from raw cols |
| Pre-rounding of basic/hra | Each component rounded individually before summing | Raw floats until single `ROUND(sum)` at `gross_salary` level |

### Verified Results (Feb 2026, 80 employees)
- Final Gross: **₹10,83,893** ✓
- Net Salary:  **₹9,64,722** ✓
- EPF (12%):   **₹1,05,979** ✓
- Variance vs reference: **₹0.00**

---

## 4. API Endpoints (Full List)

### Invoice & Ledger
| Method | Route | Description |
|---|---|---|
| `POST` | `/api/upload_invoice` | Upload PDF → GPT-4o extract |
| `POST` | `/api/post_to_ledger` | Write CSV + Zoho Bill |
| `DELETE` | `/api/invoice_pdf` | Delete temp PDF |

### Audit Suite
| Method | Route | Description |
|---|---|---|
| `POST` | `/api/reconcile` | Merge two CSVs + compute variance |
| `POST` | `/api/investigate` | RAG forensic report for discrepancy |
| `POST` | `/api/index_db` | Sync evidence files → Qdrant |
| `GET` | `/api/health` | Qdrant health check |

### Zoho Books
| Method | Route | Description |
|---|---|---|
| `GET` | `/zoho/auth/start` | Start OAuth 2.0 flow |
| `GET` | `/zoho/oauth/callback` | OAuth callback |
| `GET` | `/api/zoho/status` | `{connected, org_id}` |
| `POST` | `/api/zoho/disconnect` | Clear refresh token |
| `GET` | `/api/zoho/debug` | Debug resolved `account_id` |

### Payroll Engine
| Method | Route | Description |
|---|---|---|
| `POST` | `/api/payroll/process` | Process attendance CSV → payroll |
| `GET` | `/api/payroll/config` | Get formula config JSON |
| `POST` | `/api/payroll/config` | Save updated formula config |
| `POST` | `/api/payroll/config/reset` | Reset to built-in defaults |
| `GET` | `/api/payroll/download/payroll` | Download payroll CSV |
| `GET` | `/api/payroll/download/leave_balance` | Download closing leave-balance CSV |
| `GET` | `/api/payroll/employee_deductions` | Get all per-employee static deductions |
| `POST` | `/api/payroll/employee_deductions` | Upsert employee deduction records |
| `DELETE` | `/api/payroll/employee_deductions/{emp_id}` | Remove an employee's deduction record |

---

## 5. Data File Map

| What | Path |
|---|---|
| Uploaded PDFs (temp) | `static/uploads/` — deleted after posting |
| Vendor ledger | `data/demo_data/ledgers/system_a_vendor_ledger.csv` |
| Evidence for RAG | `data/evidence/` |
| OAuth refresh token | `.env` → `ZOHO_REFRESH_TOKEN` (auto-written) |
| Formula config | `data/payroll_reference/formula_config.json` |
| Employee deductions DB | `data/payroll_reference/employee_db.json` |
| Reference paysheet | `data/payroll_reference/Anchors_Feb26.csv` |
| Reference attendance | `data/payroll_reference/Anchor_Attendance.csv` |
| Reference leave bals | `data/payroll_reference/Jan26_LeaveBal.csv` |

---

## 6. Handover Notes

The codebase is in a stable, fully-working state. All three tabs are functional and tested. The payroll engine produces zero variance against the Feb 2026 reference paysheet.

**If picking up new work:**
- Payroll formula parameters are fully editable via UI (`Formula Config` panel) — no code changes needed for rate adjustments.
- Employee deductions (TDS, Advance, Insurance) are managed via the `Deductions` panel — persistent, month-to-month.
- The `employee_db.json` currently has only `JAI-805` with `insurance=5763`. Add more entries via UI or the POST endpoint.
- Qdrant health check ONLY fires on page load and when the user opens the Audit Suite tab — log spam is eliminated.
