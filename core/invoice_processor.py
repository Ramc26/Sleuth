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


def process_invoice_to_zoho_bill(pdf_filename, pdf_path, target_csv):
    """Extracts data using LLM formatted specifically for Zoho Books Bill creation."""
    logger.info(f"Processing invoice for Zoho Books: {pdf_filename}")

    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text:
        return {"status": "error", "message": "Could not read PDF text."}

    # ── Prompt: Updated for Zoho Books Fields ────────────────
    prompt = f"""
    You are an expert financial data extraction system for Zoho Books.
    Extract details from the raw invoice text to fill a "Bill" form.
    
    RULES:
    1. Respond in strict JSON.
    2. Use null if a field is not found.
    3. 'line_items' must be a list of objects.
    4. Dates must be in YYYY-MM-DD format.

    Required JSON Structure:
    {{
        "vendor_name": "string - The person/entity who issued the bill",
        "bill_number": "string - The invoice or bill ID",
        "order_number": "string - Purchase Order (PO) number if present",
        "bill_date": "YYYY-MM-DD",
        "due_date": "YYYY-MM-DD",
        "payment_terms": "string - e.g., 'Due on Receipt', 'Net 30', 'Net 15'",
        "subject": "string - Brief summary of the bill (max 250 chars)",
        "currency": "string - ISO code (USD, INR, etc.)",
        "line_items": [
            {{
                "item_details": "string - Description of service or product",
                "quantity": "float - Default to 1.00 if not specified",
                "rate": "float - Unit price",
                "account": "string - Suggested chart of accounts (e.g., 'Travel Expense', 'Office Supplies')",
                "amount": "float - Total for this line"
            }}
        ],
        "sub_total": "float",
        "discount": {{
            "value": "float",
            "is_percentage": "boolean"
        }},
        "tax_type": "string - Either 'TDS' or 'TCS' if applicable",
        "tax_amount": "float",
        "adjustment": "float - Any shipping or rounding adjustments",
        "total": "float - Final amount after all taxes/discounts",
        "notes": "string - Internal notes"
    }}

    RAW INVOICE TEXT:
    {raw_text}
    """

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o", # Or your preferred model
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a precise data extraction API for accounting software. Output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )

        invoice_data = json.loads(response.choices[0].message.content)
        
        # Logic for Zoho: If payment_terms is null, default to 'Due on Receipt'
        if not invoice_data.get("payment_terms"):
            invoice_data["payment_terms"] = "Due on Receipt"

        return {
            "status": "success",
            "data": invoice_data
        }

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return {"status": "error", "message": str(e)}