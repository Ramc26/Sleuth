import os
import uuid
import shutil
import logging
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

import io

from core.investigator import investigate_variance
from core.vector_store import index_evidence_to_qdrant, get_qdrant_status
from core.invoice_processor import process_invoice_to_ledger
from core import zoho_client
from core.payroll_engine import (
    process_attendance_csv,
    generate_payroll_csv,
    generate_leave_balance_csv,
    _load_config,
    _default_config,
    save_config,
)

logger = logging.getLogger("Sleuth.API")

# ── Uploads dir ──────────────────────────────────────────────────
UPLOADS_DIR = "static/uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

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
        logger.warning("⚠️  Qdrant is NOT reachable. Docker may be down.")
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

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class InvestigateRequest(BaseModel):
    invoice_id: str
    entity: str
    amount_a: float
    amount_b: float


class PostToLedgerRequest(BaseModel):
    invoice_id:     str
    entity:         str
    amount:         float
    date:           str
    billing_period: Optional[str] = None
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
    return {
        "qdrant": status,
        "ok": status["reachable"] and status["collection_exists"],
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
        result = process_invoice_to_ledger(file.filename, saved_path, target_csv)
    except Exception as e:
        if os.path.exists(saved_path):
            os.remove(saved_path)
        raise HTTPException(status_code=500, detail=str(e))

    if result["status"] == "error":
        if os.path.exists(saved_path):
            os.remove(saved_path)
        raise HTTPException(status_code=422, detail=result["message"])

    result["pdf_url"] = f"/static/uploads/{safe_name}"
    return result


@app.post("/api/post_to_ledger")
async def post_to_ledger(req: PostToLedgerRequest):
    """
    Confirms an invoice: writes the 4 ledger fields to the local CSV
    AND (if Zoho Books is connected) creates a Bill in Zoho Books.
    """
    ledger_row = {
        "invoice_id": req.invoice_id,
        "entity":     req.entity,
        "amount":     req.amount,
        "date":       req.date,
    }
    # ── Write to local CSV ───────────────────────────────────────────
    try:
        df = pd.DataFrame([ledger_row])
        if not os.path.exists(req.target_csv):
            os.makedirs(os.path.dirname(req.target_csv), exist_ok=True)
            df.to_csv(req.target_csv, index=False)
        else:
            df.to_csv(req.target_csv, mode="a", header=False, index=False)
        logger.info(f"Ledger row saved to CSV: {req.invoice_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV write failed: {e}")

    # ── Optionally post to Zoho Books ────────────────────────────────
    zoho_result = None
    zoho_status = zoho_client.get_zoho_status()
    if zoho_status["connected"]:
        try:
            zoho_result = zoho_client.create_bill(req.model_dump())
            logger.info(f"Bill created in Zoho Books: {zoho_result.get('bill_id')}")
        except Exception as e:
            logger.warning(f"Zoho Books bill creation failed (CSV already saved): {e}")
            return {
                "status":      "partial",
                "csv_saved":   True,
                "zoho_posted": False,
                "zoho_error":  str(e),
            }

    return {
        "status":      "success",
        "csv_saved":   True,
        "zoho_posted": zoho_result is not None,
        "zoho_bill_id": zoho_result.get("bill_id") if zoho_result else None,
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
# Zoho Books OAuth
# ─────────────────────────────────────────────

@app.get("/zoho/auth/start")
async def zoho_auth_start():
    """Redirects the user to Zoho's consent page to begin OAuth."""
    client_id    = os.getenv("ZOHO_CLIENT_ID", "")
    redirect_uri = os.getenv("ZOHO_REDIRECT_URI", "http://localhost:8000/zoho/oauth/callback")
    auth_url = (
        f"https://accounts.zoho.in/oauth/v2/auth"
        f"?response_type=code"
        f"&client_id={client_id}"
        # 👇 Corrected scope here: added ZohoBooks.accountants.READ
        f"&scope=ZohoBooks.bills.CREATE,ZohoBooks.contacts.CREATE,ZohoBooks.contacts.READ,ZohoBooks.accountants.READ"
        f"&redirect_uri={redirect_uri}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(auth_url)


@app.get("/zoho/oauth/callback")
async def zoho_oauth_callback(code: str = None, error: str = None):
    """
    Handles the redirect from Zoho after user grants consent.
    Exchanges the auth code for tokens and saves the refresh token to .env.
    """
    if error or not code:
        return HTMLResponse(
            f"<h3>Zoho OAuth Error</h3><p>{error or 'No code returned.'}</p>"
            "<p><a href='/'>Return to Sleuth</a></p>",
            status_code=400,
        )
    try:
        zoho_client.exchange_code_for_tokens(code)
        return RedirectResponse("/?zoho_connected=1")
    except Exception as e:
        logger.error(f"Zoho token exchange failed: {e}")
        return HTMLResponse(
            f"<h3>Token Exchange Failed</h3><p>{e}</p>"
            "<p><a href='/'>Return to Sleuth</a></p>",
            status_code=500,
        )


@app.get("/api/zoho/status")
async def zoho_status():
    """Returns the current Zoho Books connection status."""
    return zoho_client.get_zoho_status()


@app.post("/api/zoho/disconnect")
async def zoho_disconnect():
    """Clears the stored refresh token, disconnecting Zoho Books."""
    zoho_client.disconnect_zoho()
    return {"status": "disconnected"}


@app.get("/api/zoho/debug")
async def zoho_debug():
    """
    Debug endpoint — tests token refresh and Chart of Accounts lookup.
    Returns the account_id that will be used for bill line items.
    """
    status = zoho_client.get_zoho_status()
    if not status["connected"]:
        return {"error": "Not connected", "status": status}
    try:
        token = zoho_client.get_access_token()
        account_id = zoho_client.get_purchase_account_id(token)
        return {
            "status":     "ok",
            "token":      token[:20] + "…",
            "account_id": account_id,
            "org_id":     status["org_id"],
        }
    except Exception as e:
        return {"error": str(e)}

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
                "🐳 Vector Store Offline — Qdrant is not reachable. "
                "Please start the Docker container: `docker run -p 6333:6333 qdrant/qdrant`. "
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
                    "🐳 Vector Store Offline — Lost connection to Qdrant mid-request. "
                    "Verify Docker is running and try again."
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
                "🐳 Qdrant is not reachable. Start Docker first: "
                "`docker run -p 6333:6333 qdrant/qdrant`"
            ),
        )
    try:
        index_evidence_to_qdrant()
        # Refresh global health state after successful index
        global _qdrant_health
        _qdrant_health = get_qdrant_status()
        return {"status": "success", "message": "Evidence locker synced successfully."}
    except Exception as e:
        logger.error(f"Indexing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))