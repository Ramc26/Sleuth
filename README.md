# Sleuth — AI-Powered Financial Forensics

Sleuth is an AI-powered forensic accounting tool that automates the full financial lifecycle — from invoice capture straight into your ERP, all the way through reconciliation and AI-driven audit investigation.

Built with FastAPI, GPT-4o, Qdrant, and Zoho Books.

---

## What it does

Sleuth works in two focused workflows:

**Tab 1 — Invoice Capture (Data Entry)**
Upload vendor invoice PDFs → GPT-4o extracts the key fields → you review and confirm → data gets written to your local ledger CSV *and* posted directly to Zoho Books as a Bill.

**Tab 2 — Variance Analysis (Reconciliation & Audit)**
Upload two ledger CSVs (e.g. your vendor ledger vs your ERP export) → Sleuth computes row-by-row variance → you click any discrepancy → GPT-4o runs a forensic RAG investigation against your evidence base stored in Qdrant.

---

## Architecture

```
Browser UI (HTML + CSS + JS)
        │
        ▼
FastAPI (main.py)          ← Python HTTP layer
   ├── /api/upload_invoice   ← saves PDF, calls GPT-4o
   ├── /api/post_to_ledger   ← writes CSV + posts Zoho Bill
   ├── /api/reconcile        ← merges two CSVs, computes variance
   ├── /api/investigate      ← RAG forensic report via Qdrant
   ├── /api/index_db         ← indexes evidence files into Qdrant
   └── /zoho/auth/start      ← kicks off OAuth 2.0 flow
        │
        ├── GPT-4o (OpenAI)         ← invoice extraction + forensic report
        ├── Qdrant (Docker)         ← vector evidence store (cosine similarity)
        └── Zoho Books (India DC)   ← bills + vendor contacts via REST API
```

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| AI | OpenAI GPT-4o (JSON mode for extraction, free-form for investigation) |
| Vector DB | Qdrant (self-hosted via Docker) + fastembed |
| ERP | Zoho Books (India DC) — OAuth 2.0, Bills API, Contacts API, Chart of Accounts API |
| PDF parsing | PyMuPDF (fitz) |
| Data | Pandas |
| Frontend | HTML5, CSS3, Bootstrap 5, jQuery, Marked.js, Font Awesome 6 |

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/yourname/sleuth.git
cd sleuth
uv sync                       # or: pip install -r requirements.txt
```

### 2. Set up environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=sk-...

# Zoho Books (India DC)
ZOHO_CLIENT_ID=1000.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
ZOHO_CLIENT_SECRET=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
ZOHO_ORG_ID=XXXXXXXXXX
ZOHO_REDIRECT_URI=http://localhost:8000/zoho/oauth/callback
ZOHO_REFRESH_TOKEN=       # auto-written after first OAuth — do not edit manually
```

### 3. Start Qdrant (for the investigation feature)

```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 4. Start Sleuth

```bash
uv run uvicorn main:app --reload
```

Open **http://localhost:8000**

---

## Zoho Books Integration

### Setting up OAuth

Zoho Books is optional — if not connected, invoices are only saved to the local CSV.

To connect:

1. Create a **Self Client** in [Zoho API Console](https://api-console.zoho.in) → set redirect URI to `http://localhost:8000/zoho/oauth/callback`
2. Copy your Client ID, Client Secret, and Org ID into `.env`
3. Visit **http://localhost:8000/zoho/auth/start** in your browser
4. Complete the Zoho consent screen
5. You're redirected back to Sleuth — sidebar shows a green dot with your Org ID
6. `ZOHO_REFRESH_TOKEN` is automatically written to `.env` — no further re-auth needed

**Required OAuth scopes** (handled automatically by the app):
```
ZohoBooks.bills.CREATE
ZohoBooks.contacts.CREATE
ZohoBooks.contacts.READ
ZohoBooks.accountants.READ      ← needed to query Chart of Accounts for GL account_id
```

> The `ZohoBooks.accountants.READ` scope is critical — without it, Sleuth can't resolve the expense account ID for bill line items, and Zoho will silently create bills with ₹0.00 payable.

### What happens when you "Post to Ledger"

1. The 4 core fields (`invoice_id`, `entity`, `amount`, `date`) are written to `system_a_vendor_ledger.csv`
2. If Zoho is connected:
   - Looks up or creates the vendor contact by name
   - Resolves a purchase/expense GL account from your Chart of Accounts
   - Creates a Bill with a line item carrying `account_id`, `rate`, `quantity`
   - Sets `bill_number` = `reference_number` = the original invoice ID
3. The toast shows the Zoho `bill_id` on success, or `CSV only` if not connected
4. The uploaded PDF is deleted from `static/uploads/`

---

## API Reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Serves the UI |
| `GET` | `/api/health` | Qdrant health check |
| `POST` | `/api/upload_invoice` | Upload PDF → extract via GPT-4o |
| `POST` | `/api/post_to_ledger` | Confirm invoice → write CSV + Zoho Bill |
| `DELETE` | `/api/invoice_pdf` | Delete a temp PDF after posting |
| `POST` | `/api/reconcile` | Compare two CSVs, return variance |
| `POST` | `/api/investigate` | RAG forensic report for a discrepancy |
| `POST` | `/api/index_db` | Sync evidence files into Qdrant |
| `GET` | `/zoho/auth/start` | Start Zoho OAuth 2.0 flow |
| `GET` | `/zoho/oauth/callback` | OAuth callback — exchanges code for tokens |
| `GET` | `/api/zoho/status` | Returns `{connected, org_id}` |
| `POST` | `/api/zoho/disconnect` | Clears stored refresh token |
| `GET` | `/api/zoho/debug` | Debug: returns resolved `account_id` from Chart of Accounts |

---

## cURL Examples

### Upload an invoice PDF

```bash
curl -X POST http://localhost:8000/api/upload_invoice \
  -F "file=@invoice.pdf"
```

### Post to ledger (CSV + Zoho)

```bash
curl -X POST http://localhost:8000/api/post_to_ledger \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "INV-001",
    "entity": "Amazon Web Services",
    "amount": 4.11,
    "date": "2024-08-03",
    "billing_period": "Aug 2024"
  }'
```

### Reconcile two ledgers

```bash
curl -X POST http://localhost:8000/api/reconcile \
  -F "file_a=@system_a.csv" \
  -F "file_b=@system_b.csv"
```

### Investigate a discrepancy

```bash
curl -X POST http://localhost:8000/api/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "INV-001",
    "entity": "Amazon Web Services",
    "amount_a": 4.11,
    "amount_b": 5.00
  }'
```

### Check Zoho connection status

```bash
curl http://localhost:8000/api/zoho/status
# → {"connected": true, "org_id": "60066752082"}
```

### Debug Chart of Accounts lookup

```bash
curl http://localhost:8000/api/zoho/debug
# → {"status": "ok", "account_id": "460000XXXXXXX", "org_id": "60066752082", ...}
```

---

## Data Storage

| What | Where |
|---|---|
| Uploaded PDFs (temp) | `static/uploads/` — deleted after posting |
| Vendor ledger (SYS A) | `data/demo_data/ledgers/system_a_vendor_ledger.csv` |
| Evidence files (for RAG) | `data/evidence/` |
| OAuth refresh token | `.env` → `ZOHO_REFRESH_TOKEN` (auto-written) |

---

## Known Requirements

- **Docker must be running** for the Investigation feature. Sleuth shows a clear error in the UI if Qdrant is unreachable.
- **Zoho Org ID** must be filled in `.env` before connecting.
- Zoho auth codes expire in ~60 seconds — always complete the OAuth flow in one go (the app handles everything automatically).
