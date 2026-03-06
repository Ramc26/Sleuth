"""
core/zoho_client.py — Zoho Books OAuth 2.0 + Bills API  (India DC)
"""

import os
import time
import logging
import requests
from dotenv import set_key

logger = logging.getLogger("Sleuth.ZohoClient")

# ── Constants ──────────────────────────────────────────────────────────
ZOHO_ACCOUNTS_URL = "https://accounts.zoho.in"
ZOHO_BOOKS_URL    = "https://www.zohoapis.in/books/v3"
ENV_FILE          = ".env"

# ── In-memory token + account cache ───────────────────────────────────
_token_cache = {"access_token": None, "expires_at": 0}
_account_id_cache: str | None = None


# ── Status ─────────────────────────────────────────────────────────────
def get_zoho_status() -> dict:
    refresh_token = os.getenv("ZOHO_REFRESH_TOKEN", "").strip()
    org_id        = os.getenv("ZOHO_ORG_ID", "").strip()
    return {
        "connected": bool(refresh_token),
        "org_id":    org_id or None,
    }


# ── Token Exchange (code → tokens) ─────────────────────────────────────
def exchange_code_for_tokens(code: str) -> dict:
    resp = requests.post(
        f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
        data={
            "grant_type":    "authorization_code",
            "client_id":     os.getenv("ZOHO_CLIENT_ID"),
            "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
            "redirect_uri":  os.getenv("ZOHO_REDIRECT_URI", "http://localhost:8000/zoho/oauth/callback"),
            "code":          code,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"Token exchange response: {data}")

    if "error" in data:
        raise ValueError(f"Zoho token exchange failed: {data['error']}")

    refresh_token = data.get("refresh_token", "")
    access_token  = data.get("access_token", "")
    expires_in    = int(data.get("expires_in", 3600))

    if refresh_token:
        set_key(ENV_FILE, "ZOHO_REFRESH_TOKEN", refresh_token)
        os.environ["ZOHO_REFRESH_TOKEN"] = refresh_token
        logger.info("✅ Zoho refresh token saved to .env")
    else:
        logger.warning("⚠️  No refresh_token in response — did you request access_type=offline?")

    _token_cache["access_token"] = access_token
    _token_cache["expires_at"]   = time.time() + expires_in - 60
    return data


# ── Access Token (auto-refresh) ─────────────────────────────────────────
def get_access_token() -> str:
    refresh_token = os.getenv("ZOHO_REFRESH_TOKEN", "").strip()
    if not refresh_token:
        raise RuntimeError("Zoho Books is not connected. Visit /zoho/auth/start to complete OAuth.")

    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    logger.info("Refreshing Zoho access token…")
    resp = requests.post(
        f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
        data={
            "grant_type":    "refresh_token",
            "client_id":     os.getenv("ZOHO_CLIENT_ID"),
            "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"Token refresh response: {data}")

    if "error" in data:
        raise RuntimeError(f"Zoho token refresh failed: {data['error']}")

    access_token = data["access_token"]
    expires_in   = int(data.get("expires_in", 3600))
    _token_cache["access_token"] = access_token
    _token_cache["expires_at"]   = time.time() + expires_in - 60
    return access_token


# ── Common headers ──────────────────────────────────────────────────────
def _headers(access_token: str, json_body: bool = False) -> dict:
    org_id = os.getenv("ZOHO_ORG_ID", "").strip()
    h = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "X-com-zoho-books-organizationid": org_id,
    }
    if json_body:
        h["Content-Type"] = "application/json"
    return h


# ── Vendor Lookup / Create ──────────────────────────────────────────────
def get_or_create_vendor(entity_name: str, access_token: str) -> str:
    org_id = os.getenv("ZOHO_ORG_ID", "").strip()

    resp = requests.get(
        f"{ZOHO_BOOKS_URL}/contacts",
        headers=_headers(access_token),
        params={"organization_id": org_id, "contact_type": "vendor", "search_text": entity_name},
        timeout=15,
    )
    resp.raise_for_status()
    contacts = resp.json().get("contacts", [])

    for c in contacts:
        if c.get("contact_name", "").strip().lower() == entity_name.strip().lower():
            logger.info(f"Found vendor: {c['contact_id']} — {entity_name}")
            return str(c["contact_id"])

    logger.info(f"Creating new Zoho vendor: {entity_name}")
    create_resp = requests.post(
        f"{ZOHO_BOOKS_URL}/contacts",
        headers=_headers(access_token, json_body=True),
        params={"organization_id": org_id},
        json={"contact_name": entity_name, "contact_type": "vendor"},
        timeout=15,
    )
    create_resp.raise_for_status()
    result = create_resp.json()
    if result.get("code") != 0:
        raise RuntimeError(f"Could not create vendor: {result.get('message')}")
    return str(result["contact"]["contact_id"])


# ── Default Purchase Account ────────────────────────────────────────────
def get_purchase_account_id(access_token: str) -> str | None:
    global _account_id_cache
    if _account_id_cache:
        return _account_id_cache

    org_id = os.getenv("ZOHO_ORG_ID", "").strip()
    try:
        resp = requests.get(
            f"{ZOHO_BOOKS_URL}/chartofaccounts",
            headers=_headers(access_token),
            params={"organization_id": org_id},
            timeout=15,
        )
        resp.raise_for_status()
        accounts = resp.json().get("chartofaccounts", [])

        priority_keywords = ["cost of goods sold", "purchase", "direct cost", "other expense", "expense"]
        expense_types = {"expense", "cost_of_goods_sold", "other_expense"}
        expense_accounts = [a for a in accounts if a.get("account_type", "").lower() in expense_types]

        for keyword in priority_keywords:
            for acct in expense_accounts:
                if keyword in acct.get("account_name", "").lower():
                    _account_id_cache = str(acct["account_id"])
                    return _account_id_cache

        if expense_accounts:
            _account_id_cache = str(expense_accounts[0]["account_id"])
            return _account_id_cache

        if accounts:
            _account_id_cache = str(accounts[0]["account_id"])
            return _account_id_cache

    except Exception as e:
        logger.error(f"❌ Chart of accounts lookup failed: {e}")
    return None


# ── Create Bill ─────────────────────────────────────────────────────────
def create_bill(invoice_data: dict) -> dict:
    access_token = get_access_token()
    org_id       = os.getenv("ZOHO_ORG_ID", "").strip()

    if not org_id:
        raise ValueError("ZOHO_ORG_ID is not set in .env.")

    entity_name = (invoice_data.get("entity") or "Unknown Vendor").strip()
    vendor_id   = get_or_create_vendor(entity_name, access_token)

    amount       = float(invoice_data.get("amount") or 0)
    description  = invoice_data.get("billing_period") or f"Invoice from {entity_name}"
    account_id   = get_purchase_account_id(access_token)

    line_item: dict = {
        "description": description,
        "rate":        amount,
        "quantity":    1,
    }
    if account_id:
        line_item["account_id"] = account_id

    # Base payload without the date
    bill_payload = {
        "vendor_id":        vendor_id,
        "bill_number":      invoice_data.get("invoice_id") or "BILL",
        "reference_number": invoice_data.get("invoice_id") or "",
        "notes":            f"Auto-posted by Sleuth | {entity_name} | {description}",
        "line_items":       [line_item],
    }
    
    # Safely inject date only if it exists and is not empty
    invoice_date = invoice_data.get("date")
    if invoice_date and invoice_date.strip():
        bill_payload["date"] = invoice_date.strip()

    logger.info(f"Creating Zoho Bill payload: {bill_payload}")

    resp = requests.post(
        f"{ZOHO_BOOKS_URL}/bills",
        headers=_headers(access_token, json_body=True),
        params={"organization_id": org_id},
        json=bill_payload,
        timeout=20,
    )

    if not resp.ok:
        logger.error(f"Zoho validation error: {resp.text}")

    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0:
        raise RuntimeError(f"Zoho Books API error {result.get('code')}: {result.get('message', 'Unknown error')}")

    bill = result.get("bill", {})
    logger.info(f"✅ Bill created in Zoho Books: {bill.get('bill_id')} — {bill.get('bill_number')}")
    return bill


# ── Disconnect ──────────────────────────────────────────────────────────
def disconnect_zoho() -> None:
    set_key(ENV_FILE, "ZOHO_REFRESH_TOKEN", "")
    os.environ["ZOHO_REFRESH_TOKEN"] = ""
    _token_cache["access_token"] = None
    _token_cache["expires_at"]   = 0
    global _account_id_cache
    _account_id_cache = None
    logger.info("Zoho Books disconnected.")