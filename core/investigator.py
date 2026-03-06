import logging
from core.config import openai_client
from core.vector_store import search_evidence

logger = logging.getLogger("Sleuth.Investigator")


def investigate_variance(inv_id: str, entity: str, amt_a: float, amt_b: float) -> str:
    """
    Runs a full forensic investigation on a discrepancy:
    1. Semantically searches the Qdrant evidence locker.
    2. Builds a structured prompt for GPT-4o.
    3. Returns a formatted Markdown audit report.
    """
    variance = round(amt_a - amt_b, 2)
    variance_abs = abs(variance)

    # ── Evidence Retrieval ──────────────────────────────────────────────────
    relevant_evidence = search_evidence(inv_id, entity, variance)

    if not relevant_evidence:
        all_context = "No relevant evidence found in the vector database for this invoice or entity."
        source_citation = "N/A"
    else:
        all_context = "\n\n".join(relevant_evidence)
        # Extract a clean source label from the first hit's header line
        first_hit = relevant_evidence[0]
        try:
            source_citation = first_hit.split("---")[1].strip()
        except IndexError:
            source_citation = "Evidence Locker"

    # ── Forensic Prompt ─────────────────────────────────────────────────────
    prompt = f"""
You are 'Sleuth', an elite Senior Forensic Accountant AI working for an enterprise audit team.

━━━ CASE FILE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Invoice ID  : {inv_id}
Entity      : {entity}
System A    : ${amt_a:.2f}   (ZohoBooks — Vendor Ledger)
System B    : ${amt_b:.2f}   (ERP — Internal Record)
Variance    : ${variance:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILTERED EVIDENCE FROM LOCKER:
{all_context}

━━━ TASK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Investigate using ONLY the provided evidence. You MUST respond in the exact markdown template below. Do not add any conversational filler or preamble.

### 📌 Executive Summary
* **Verdict:** [Resolved - Evidence Found / Unresolved - Missing Evidence]
* **Root Cause:** [1-3 words: e.g., SLA Penalty, FX Variance, Freight Charge, Data Entry Typo, Duplicate Entry, Unknown]
* **AI Confidence:** [High / Medium / Low] — [1 concise sentence justifying the rating, e.g., "High — Exact dollar amount and entity matched in Slack log."]

### 🔎 Evidence Chain
> "[Insert the exact verbatim quote from the evidence that explains the variance. If none found, write: 'No corroborating evidence found in the locker.'"]
**Source:** `{source_citation}`

### 📝 Forensic Explanation
[2-4 sentence professional explanation of what caused the discrepancy based on the evidence. If unexplained, state it is flagged for manual review.]

### 🎯 Recommended Action
[Specific, actionable next step for the human accountant. e.g., "Approve the correcting journal entry below and re-run the ERP sync." or "Contact {entity} to obtain the missing credit note for ${variance_abs:.2f}."]

### 📓 Proposed Journal Entry
| Account Name | Debit | Credit |
| :--- | ---: | ---: |
| [Appropriate Expense / Adjustment Account] | ${variance_abs:.2f} | |
| [Accounts Payable / Accrued Liabilities] | | ${variance_abs:.2f} |
"""

    logger.info(f"Sending forensic prompt to GPT-4o for invoice {inv_id}...")

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a highly structured forensic accounting AI. "
                    "You output ONLY in the requested markdown format. "
                    "Never break from the template structure."
                )
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )

    return response.choices[0].message.content