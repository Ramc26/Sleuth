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

    # ── Prompt: extract rich fields from the invoice ────────────────
    prompt = f"""
    You are an automated Accounts Payable data extraction system.
    Extract ALL available details from the raw invoice text below.

    You MUST respond in strict JSON format with exactly these keys.
    If a value is not present in the invoice, use null.

    {{
        "invoice_id":      "string  — invoice or bill number",
        "entity":          "string  — vendor / company name who issued the invoice",
        "amount":          "float   — TOTAL amount due (numbers only, no currency symbols)",
        "date":            "YYYY-MM-DD — invoice issue date",
        "billing_period":  "string  — the service/billing period this invoice covers (e.g. 'July 1 – July 31, 2014')",
        "account_number":  "string  — customer or account number on the invoice",
        "bill_to":         "string  — name and address of the customer being billed",
        "currency":        "string  — currency code (e.g. USD, INR, GBP)",
        "subtotal":        "float   — charges before tax/credits",
        "tax":             "float   — total tax amount (VAT, GST, etc.)",
        "credits":         "float   — any credits applied",
        "service_breakdown": {{
            "<service name>": "float amount"
        }}
    }}

    RAW INVOICE TEXT:
    {raw_text}
    """

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a data extraction API. Output only valid JSON."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.0
        )

        invoice_data = json.loads(response.choices[0].message.content)
        logger.info(f"Successfully extracted data: {invoice_data}")

        # Format raw_text as clean line list
        raw_lines = [line for line in raw_text.split("\n") if line.strip()]

        return {
            "status":   "success",
            "data":     invoice_data,
            "raw_text": raw_lines,
        }

    except Exception as e:
        logger.error(f"Extraction or CSV writing failed: {e}")
        return {"status": "error", "message": str(e)}