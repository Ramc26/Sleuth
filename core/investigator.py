import logging
from typing import Optional

from core.config import openai_client
from core.investigation_jobs import InvestigationProgress
from core.vector_store import search_evidence_detailed

logger = logging.getLogger("Sleuth.Investigator")


def _truncate(text: str, max_len: int = 96) -> str:
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def investigate_variance(
    inv_id: str,
    entity: str,
    amt_a: float,
    amt_b: float,
    progress: Optional[InvestigationProgress] = None,
) -> str:
    """
    Runs a full forensic investigation on a discrepancy with optional live progress updates.
    """
    if progress:
        progress.activate("init", f"{inv_id} · {entity}")
        progress.complete("init")

    variance = round(amt_a - amt_b, 2)
    variance_abs = abs(variance)

    if progress:
        progress.activate(
            "parse",
            f"Vendor ${amt_a:,.2f} vs ERP ${amt_b:,.2f} · delta ${variance_abs:,.2f}",
        )
        progress.complete("parse")

    if progress:
        progress.activate("search", "Generating embedding · querying vector index")

    search_query, hits, relevant_evidence = search_evidence_detailed(inv_id, entity, variance)

    if progress:
        progress.complete("search", f'Query: "{_truncate(search_query)}"')

    if progress:
        progress.activate("rank")
    above_threshold = [h for h in hits if h["score"] > 0.50]
    if above_threshold:
        top = above_threshold[0]
        rank_meta = (
            f"{len(above_threshold)} hit(s) above threshold · "
            f"top: {top['filename']} ({top['score']:.0%} similarity)"
        )
    elif hits:
        top = hits[0]
        rank_meta = (
            f"{len(hits)} candidate(s) below threshold · "
            f"best: {top['filename']} ({top['score']:.0%})"
        )
    else:
        rank_meta = "No vectors returned from evidence locker"
    if progress:
        progress.complete("rank", rank_meta)

    if progress:
        progress.activate("crossref")
    if above_threshold:
        sources = ", ".join(h["filename"] for h in above_threshold[:3])
        cross_meta = f"Matched sources in index: {sources}"
    else:
        cross_meta = "No indexed communications matched invoice ID and entity at high confidence"
    if progress:
        progress.complete("crossref", cross_meta)

    if progress:
        progress.activate("chain")
    if not relevant_evidence:
        all_context = "No relevant evidence found in the vector database for this invoice or entity."
        source_citation = "N/A"
        chain_meta = "Evidence chain empty — analysis will flag manual review"
    else:
        all_context = "\n\n".join(relevant_evidence)
        first_hit = relevant_evidence[0]
        try:
            source_citation = first_hit.split("---")[1].strip()
        except IndexError:
            source_citation = "Evidence Locker"
        chain_meta = f"{len(relevant_evidence)} excerpt(s) linked · primary: {source_citation}"
    if progress:
        progress.complete("chain", chain_meta)

    prompt = f"""
You are 'Sleuth', an elite Senior Forensic Accountant AI working for an enterprise audit team.

━━━ CASE FILE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Invoice ID  : {inv_id}
Entity      : {entity}
System A    : ${amt_a:.2f}   (Vendor Ledger)
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

    if progress:
        progress.activate("analyze", "GPT-4o · structured forensic template · temperature 0")
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
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )

    report = response.choices[0].message.content

    if progress:
        progress.complete("analyze", "Root cause and confidence scored")
        progress.activate("remediation", "Proposed journal entry and control note")
        progress.complete("remediation", f"Adjustment magnitude ${variance_abs:,.2f}")
        progress.activate("report", "Rendering markdown for audit workspace")
        progress.complete("report", "Report ready for export")

    return report
