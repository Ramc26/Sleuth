import os
import uuid
import shutil
import logging
import pandas as pd
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

import io

from core.investigator import investigate_variance
from core.vector_store import index_evidence_to_qdrant, get_qdrant_status
from core.invoice_processor import process_invoice_to_zoho_bill
from core.payroll_engine import (
    process_attendance_csv,
    generate_payroll_csv,
    generate_leave_balance_csv,
    _load_config,
    _default_config,
    save_config,
    load_employee_db,
    upsert_employee_db,
    save_employee_db,
)

logger = logging.getLogger("Sleuth.API")

# ── Uploads dir ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOADS_DIR = os.getenv(
    "UPLOADS_DIR",
    "/tmp/sleuth_uploads" if os.getenv("VERCEL") else str(STATIC_DIR / "uploads"),
)
os.makedirs(UPLOADS_DIR, exist_ok=True)
UPLOADS_PUBLIC_PREFIX = "/static/uploads" if Path(UPLOADS_DIR).is_relative_to(STATIC_DIR) else ""

# ── Global Qdrant health state (set on startup) ──────────────────
_qdrant_health: dict = {"reachable": False, "collection_exists": False, "error": None}


# ── Startup / Shutdown Lifespan ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run pre-flight checks before accepting requests."""
    global _qdrant_health
    logger.info("🚀 Sleuth starting up — checking Qdrant health…")
    _qdrant_health = get_qdrant_status()

    if not _qdrant_health["reachable"]:
        logger.warning("⚠️  Qdrant is NOT reachable. Check QDRANT_URL and QDRANT_API_KEY.")
    elif not _qdrant_health["collection_exists"]:
        logger.warning("⚠️  Qdrant is up but evidence collection is missing. Run /api/index_db.")
    else:
        logger.info("✅ Qdrant healthy — evidence collection found.")

    yield
    logger.info("Sleuth shutting down.")


# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────
app = FastAPI(title="Sleuth API", version="2.2.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class InvestigateRequest(BaseModel):
    invoice_id: str
    entity: str
    amount_a: float
    amount_b: float


class PostToLedgerRequest(BaseModel):
    # ── Core fields (from new extractor) ─────────────────────────────────
    vendor_name:    str
    bill_number:    Optional[str] = None
    order_number:   Optional[str] = None
    bill_date:      Optional[str] = None
    due_date:       Optional[str] = None
    payment_terms:  Optional[str] = "Due on Receipt"
    subject:        Optional[str] = None
    currency:       Optional[str] = "INR"
    # Line items (list of dicts: item_details, quantity, rate, account, amount)
    line_items:     Optional[list] = None
    # Totals
    sub_total:      Optional[float] = None
    total:          Optional[float] = None
    # Discount — {value, is_percentage}
    discount:       Optional[dict] = None
    # TDS / TCS selection and amount
    tax_type:       Optional[str] = None          # "TDS" | "TCS" | None
    tax_amount:     Optional[float] = None
    # Shipping / rounding adjustment
    adjustment:     Optional[float] = None
    # Notes
    notes:          Optional[str] = None
    # PDF path for attaching to Zoho bill (set by server, not sent from UI)
    pdf_path:       Optional[str] = None
    pdf_filename:   Optional[str] = None
    # Legacy CSV target
    target_csv:     str = "data/demo_data/ledgers/system_a_vendor_ledger.csv"


# ─────────────────────────────────────────────
# UI Route
# ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    """
    Returns the current Qdrant health status.
    Used by the frontend on page load to decide whether to show the warning banner.
    Re-checks live so the banner disappears once Docker is started.
    """
    status = get_qdrant_status()
    # Update the cached global too (useful in dev with --reload)
    global _qdrant_health
    _qdrant_health = status
    has_evidence = status["reachable"] and status["collection_exists"] and status.get("points_count", 0) > 0
    return {
        "qdrant": status,
        "ok": has_evidence,
    }


# ─────────────────────────────────────────────
# Tab 1 — Data Entry
# ─────────────────────────────────────────────
@app.post("/api/upload_invoice")
async def upload_invoice(
    file: UploadFile = File(...),
    target_csv: str = "data/demo_data/ledgers/system_a_vendor_ledger.csv"
):
    """
    Receives a PDF invoice, saves it to static/uploads for the viewer,
    extracts data via GPT-4o JSON mode, and appends the record to System A CSV.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    safe_name = f"{uuid.uuid4().hex}_{file.filename.replace(' ', '_')}"
    saved_path = os.path.join(UPLOADS_DIR, safe_name)

    try:
        with open(saved_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
        result = process_invoice_to_zoho_bill(file.filename, saved_path, target_csv)
    except Exception as e:
        if os.path.exists(saved_path):
            os.remove(saved_path)
        raise HTTPException(status_code=500, detail=str(e))

    if result["status"] == "error":
        if os.path.exists(saved_path):
            os.remove(saved_path)
        raise HTTPException(status_code=422, detail=result["message"])

    result["pdf_url"]        = f"{UPLOADS_PUBLIC_PREFIX}/{safe_name}" if UPLOADS_PUBLIC_PREFIX else ""
    result["pdf_saved_path"] = saved_path   # server-side path for Zoho attachment
    return result


@app.post("/api/post_to_ledger")
async def post_to_ledger(req: PostToLedgerRequest):
    """
    Confirms a bill by writing to the local CSV ledger.
    Zoho integration is intentionally disabled for the public demo.
    """
    # ── Build a minimal ledger row for CSV ───────────────────────────────
    ledger_row = {
        "vendor_name": req.vendor_name,
        "bill_number": req.bill_number or "",
        "bill_date":   req.bill_date or "",
        "total":       req.total or 0,
        "currency":    req.currency or "INR",
        "tax_type":    req.tax_type or "",
        "payment_terms": req.payment_terms or "",
    }
    try:
        df = pd.DataFrame([ledger_row])
        if not os.path.exists(req.target_csv):
            os.makedirs(os.path.dirname(req.target_csv), exist_ok=True)
            df.to_csv(req.target_csv, index=False)
        else:
            df.to_csv(req.target_csv, mode="a", header=False, index=False)
        logger.info(f"Ledger row saved to CSV: {req.bill_number}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV write failed: {e}")

    return {
        "status":       "success",
        "csv_saved":    True,
        "zoho_posted":  False,
        "pdf_attached": False,
        "zoho_bill_id": None,
    }


@app.delete("/api/invoice_pdf")
async def delete_invoice_pdf(pdf_url: str):
    """
    Deletes an uploaded PDF from static/uploads after the user confirms (posts) the invoice.
    Only allows deletion of files inside UPLOADS_DIR to prevent directory traversal.
    """
    filename = os.path.basename(pdf_url)               # strip any path traversal
    file_path = os.path.join(UPLOADS_DIR, filename)

    if os.path.abspath(file_path).startswith(os.path.abspath(UPLOADS_DIR)):
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted uploaded PDF: {filename}")
            return {"status": "success", "message": f"{filename} removed."}
        return {"status": "not_found"}

    raise HTTPException(status_code=400, detail="Invalid path.")


# ─────────────────────────────────────────────
# Tab 2 — Audit Suite
# ─────────────────────────────────────────────
@app.post("/api/reconcile")
async def get_discrepancies(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...)
):
    """
    Merges two ledger CSVs, computes variance (rounded to 2dp),
    returns ALL rows tagged 'Matched' or 'Discrepancy'.
    """
    try:
        df_a = pd.read_csv(file_a.file)
        df_b = pd.read_csv(file_b.file)

        for df in (df_a, df_b):
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

        comp_df = pd.merge(
            df_a, df_b,
            on=["invoice_id", "entity", "date"],
            suffixes=("_SubA", "_SubB")
        )
        comp_df["amount_SubA"] = pd.to_numeric(comp_df["amount_SubA"], errors="coerce").fillna(0.0)
        comp_df["amount_SubB"] = pd.to_numeric(comp_df["amount_SubB"], errors="coerce").fillna(0.0)

        comp_df["Variance"] = (comp_df["amount_SubA"] - comp_df["amount_SubB"]).round(2)
        comp_df["status"] = comp_df["Variance"].apply(
            lambda v: "Discrepancy" if v != 0 else "Matched"
        )

        flagged = comp_df[comp_df["status"] == "Discrepancy"]
        summary = {
            "total_rows": len(comp_df),
            "flagged": len(flagged),
            "risk": round(abs(flagged["Variance"]).sum(), 2),
        }

        return {"status": "success", "summary": summary, "data": comp_df.to_dict(orient="records")}

    except KeyError as e:
        logger.error(f"Missing column: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid CSV format. Missing column: {e}. Required: invoice_id, entity, date, amount."
        )
    except Exception as e:
        logger.error(f"Reconciliation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/investigate")
async def run_investigation(req: InvestigateRequest):
    """
    Runs the RAG-powered forensic investigation.
    Returns a production-grade error if Qdrant is unreachable.
    """
    # ── Pre-flight: Qdrant reachability check ────────────────────
    health = get_qdrant_status()
    if not health["reachable"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "Vector Store Offline — Qdrant is not reachable. "
                "Check QDRANT_URL and QDRANT_API_KEY. "
                "Investigation cannot proceed without the evidence locker."
            ),
        )
    if not health["collection_exists"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "📭 Evidence Locker Empty — The Qdrant vector collection does not exist yet. "
                "Click the '⚡ Sync Evidence Locker' button in the sidebar to index your evidence files first."
            ),
        )

    # ── Run investigation ────────────────────────────────────────
    try:
        report = investigate_variance(req.invoice_id, req.entity, req.amount_a, req.amount_b)
        return {"status": "success", "report": report}
    except Exception as e:
        err_msg = str(e)
        # Detect common connection errors and surface a friendly message
        if any(kw in err_msg.lower() for kw in ("connection", "refused", "connect", "timeout", "unreachable")):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Vector Store Offline — Lost connection to Qdrant mid-request. "
                    "Verify Qdrant Cloud settings and try again."
                ),
            )
        logger.error(f"Investigation error: {e}")
        raise HTTPException(status_code=500, detail=f"Investigation failed: {err_msg}")


# ─────────────────────────────────────────────
# Tab 3 — Payroll Engine
# ─────────────────────────────────────────────

# In-memory store for the last processed payroll (used by download endpoints)
_last_payroll: dict = {}


@app.get("/api/payroll/config")
async def get_payroll_config():
    """Return the current formula configuration."""
    return _load_config()


@app.post("/api/payroll/config")
async def update_payroll_config(payload: dict):
    """Save updated formula configuration."""
    try:
        # Basic validation — ensure key sections are present
        required = ["month_days", "salary_slabs", "epf", "esi", "profession_tax_slabs"]
        for key in required:
            if key not in payload:
                raise HTTPException(status_code=400, detail=f"Missing required config key: {key}")
        save_config(payload)
        return {"status": "saved", "message": "Formula configuration saved successfully."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")


@app.post("/api/payroll/config/reset")
async def reset_payroll_config():
    """Reset formula configuration to built-in defaults."""
    defaults = _default_config()
    save_config(defaults)
    return {"status": "reset", "config": defaults}


@app.get("/api/payroll/employee_deductions")
async def get_employee_deductions():
    """
    Return all per-employee static deductions (TDS / Advance / Insurance).
    These persist month-to-month until HR manually clears them.
    """
    return load_employee_db()


@app.post("/api/payroll/employee_deductions")
async def update_employee_deductions(payload: dict):
    """
    Upsert per-employee static deductions.
    Body: { "JAI-805": { "tds": 0, "advance": 0, "insurance": 5763 }, ... }
    Only the fields provided are updated; others remain unchanged.
    """
    try:
        # Validate field names
        allowed = {"tds", "advance", "insurance"}
        for emp_id, fields in payload.items():
            if not isinstance(fields, dict):
                raise HTTPException(status_code=400, detail=f"Invalid payload for {emp_id}")
            invalid = set(fields.keys()) - allowed
            if invalid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown field(s) for {emp_id}: {invalid}. Allowed: {allowed}"
                )
        updated_db = upsert_employee_db(payload)
        return {"status": "saved", "db": updated_db}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update deductions: {e}")


@app.delete("/api/payroll/employee_deductions/{emp_id}")
async def clear_employee_deductions(emp_id: str):
    """
    Remove a specific employee's deductions record (effectively sets all to 0).
    """
    try:
        db = load_employee_db()
        if emp_id in db:
            del db[emp_id]
            save_employee_db(db)
            return {"status": "cleared", "emp_id": emp_id}
        return {"status": "not_found", "emp_id": emp_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear deductions: {e}")


@app.post("/api/payroll/process")
async def process_payroll(attendance_file: UploadFile = File(...)):
    """
    Accepts the Anchor-Attendance CSV, runs the payroll engine using
    the current formula_config.json, returns full breakdown and summary.
    """
    if not attendance_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")
    try:
        contents = await attendance_file.read()
        buf = io.BytesIO(contents)
        cfg = _load_config()
        result = process_attendance_csv(buf, cfg=cfg)
        global _last_payroll
        _last_payroll = result
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Payroll processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Payroll processing failed: {e}")


@app.get("/api/payroll/download/payroll")
async def download_payroll_csv():
    """Download the full payroll output as a CSV."""
    if not _last_payroll:
        raise HTTPException(status_code=404, detail="No payroll data. Run /api/payroll/process first.")
    csv_data = generate_payroll_csv(_last_payroll["employees"])
    return StreamingResponse(
        io.StringIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payroll_output.csv"},
    )


@app.get("/api/payroll/download/leave_balance")
async def download_leave_balance_csv():
    """Download the closing leave balance CSV (input for next month)."""
    if not _last_payroll:
        raise HTTPException(status_code=404, detail="No payroll data. Run /api/payroll/process first.")
    csv_data = generate_leave_balance_csv(_last_payroll["employees"])
    return StreamingResponse(
        io.StringIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=closing_leave_balance.csv"},
    )


@app.post("/api/index_db")
async def index_database():
    """Syncs local evidence files into the Qdrant vector store."""
    # Check Qdrant is up before attempting to index
    health = get_qdrant_status()
    if not health["reachable"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "Qdrant is not reachable. Check QDRANT_URL and QDRANT_API_KEY."
            ),
        )
    try:
        indexed_count = index_evidence_to_qdrant()
        # Refresh global health state after successful index
        global _qdrant_health
        _qdrant_health = get_qdrant_status()
        return {
            "status": "success",
            "indexed_count": indexed_count,
            "message": f"Evidence locker synced successfully ({indexed_count} files).",
        }
    except Exception as e:
        logger.error(f"Indexing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))