import os
import json
import logging
import fitz  # PyMuPDF
import pandas as pd
from core.config import openai_client

logger = logging.getLogger("Sleuth.InvoiceProcessor")

def extract_text_from_pdf(pdf_path):
    """Reads a PDF and extracts all raw text."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        logger.error(f"Failed to read PDF {pdf_path}: {e}")
        return None

def process_invoice_to_ledger(pdf_filename, pdf_path, target_csv):
    """Extracts data using LLM and appends it to the target CSV ledger."""
    logger.info(f"Processing new invoice: {pdf_filename}")
    
    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text:
        return {"status": "error", "message": "Could not read PDF text."}

    # Force the LLM to return strict JSON matching our ledger format
    prompt = f"""
    You are an automated Accounts Payable data entry system.
    Extract the following details from the raw invoice text below.
    
    You MUST respond in strict JSON format with exactly these keys:
    {{
        "invoice_id": "string (The invoice number)",
        "entity": "string (The vendor/company name who sent the bill)",
        "amount": "float (The TOTAL amount due, numbers only)",
        "date": "YYYY-MM-DD (The date of the invoice)"
    }}
    
    RAW INVOICE TEXT:
    {raw_text}
    """

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" }, # Crucial for API reliability
            messages=[
                {"role": "system", "content": "You are a data extraction API. Output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        
        # Parse the JSON response
        invoice_data = json.loads(response.choices[0].message.content)
        logger.info(f"Successfully extracted data: {invoice_data}")
        
        # Simulate pushing to ZohoBooks (Appending to our CSV)
        df = pd.DataFrame([invoice_data])
        
        # If the CSV doesn't exist, create it with headers. Otherwise, append.
        if not os.path.exists(target_csv):
            df.to_csv(target_csv, index=False)
        else:
            df.to_csv(target_csv, mode='a', header=False, index=False)
            
        return {"status": "success", "data": invoice_data}

    except Exception as e:
        logger.error(f"Extraction or CSV writing failed: {e}")
        return {"status": "error", "message": str(e)}