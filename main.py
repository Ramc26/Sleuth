import os
import pandas as pd
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import logging

from core.investigator import investigate_variance
from core.vector_store import index_evidence_to_qdrant

logger = logging.getLogger("Sleuth.API")

app = FastAPI(title="Sleuth API")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class InvestigateRequest(BaseModel):
    invoice_id: str
    entity: str
    amount_a: float
    amount_b: float

@app.get("/", response_class=HTMLResponse)
async def serve_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/reconcile")
async def get_discrepancies(file_a: UploadFile = File(...), file_b: UploadFile = File(...)):
    """Receives two uploaded CSVs, compares them, and returns metrics & mismatches."""
    try:
        df_a = pd.read_csv(file_a.file)
        df_b = pd.read_csv(file_b.file)
        
        comp_df = pd.merge(df_a, df_b, on=["invoice_id", "entity", "date"], suffixes=('_SubA', '_SubB'))
        comp_df['Variance'] = comp_df['amount_SubA'] - comp_df['amount_SubB']
        
        mismatches = comp_df[comp_df['Variance'] != 0].copy()
        mismatches['Variance'] = mismatches['Variance'].round(2)
        
        # Calculate summary metrics for the UI
        summary = {
            "total_rows": len(comp_df),
            "flagged": len(mismatches),
            "risk": abs(mismatches['Variance']).sum()
        }
        
        return {"status": "success", "summary": summary, "data": mismatches.to_dict(orient="records")}
    except Exception as e:
        logger.error(f"Reconciliation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid CSV format. Please ensure 'invoice_id', 'entity', and 'date' columns exist.")

@app.post("/api/investigate")
async def run_investigation(req: InvestigateRequest):
    try:
        report = investigate_variance(req.invoice_id, req.entity, req.amount_a, req.amount_b)
        return {"status": "success", "report": report}
    except Exception as e:
        logger.error(f"Investigation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/index_db")
async def index_database():
    try:
        index_evidence_to_qdrant()
        return {"status": "success", "message": "Evidence indexed successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))