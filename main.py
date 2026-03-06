import os
import uuid
import shutil
import logging
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.investigator import investigate_variance
from core.vector_store import index_evidence_to_qdrant, get_qdrant_status
from core.invoice_processor import process_invoice_to_ledger

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