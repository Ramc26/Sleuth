import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger("Sleuth.Engine")
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_all_evidence():
    logger.info("Scanning /evidence directory for text files...")
    evidence_data = []
    base_path = "demo_data/evidence"
    
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith(".txt"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    evidence_data.append({"file": filepath, "content": f.read()})
    return evidence_data

def investigate_variance(inv_id, entity, amt_a, amt_b):
    variance = round(amt_a - amt_b, 2)
    variance_abs = abs(variance)
    
    var_exact = f"{variance_abs:.2f}"
    var_whole = str(int(variance_abs))
    
    all_evidence = get_all_evidence()
    relevant_evidence = []
    
    entity_short = entity.split()[0].lower()
    
    for ev in all_evidence:
        content = ev['content'].lower()
        filename = ev['file'].lower()
        
        id_match = inv_id.lower() in content or inv_id.lower() in filename
        entity_match = entity.lower() in content or entity_short in content or entity.lower() in filename
        money_match = var_exact in content or var_whole in content
        
        if id_match or (entity_match and money_match):
            relevant_evidence.append(f"--- SOURCE FILE: {ev['file']} ---\n{ev['content']}")
    
    if not relevant_evidence:
        all_context = "No relevant evidence found in the system mentioning this Invoice ID, Entity, or specific dollar amount."
    else:
        all_context = "\n\n".join(relevant_evidence)

    # --- THE NEW ENTERPRISE REPORT FORMAT ---
    prompt = f"""
    You are 'Sleuth', an elite Senior Forensic Accountant AI.
    
    CASE DETAILS:
    Invoice ID: {inv_id}
    Entity: {entity}
    Subsidiary A says: ${amt_a:.2f}
    Subsidiary B says: ${amt_b:.2f}
    Discrepancy: ${variance:.2f}
    
    FILTERED EVIDENCE LOGS:
    {all_context}
    
    TASK:
    Investigate the discrepancy using ONLY the provided evidence. You MUST format your response exactly matching the markdown template below. Do not add conversational filler.

    ### 📌 Executive Summary
    * **Verdict:** [Resolved - Evidence Found / Unresolved - Missing Evidence]
    * **Root Cause:** [Categorize it in 1-3 words: e.g., SLA Penalty, FX Variance, Freight Charge, Data Entry Typo, Unknown]
    * **AI Confidence:** [High / Medium / Low] - [1 sentence explaining why. e.g., "High - Exact dollar amount and entity matched in Slack log."]

    ### 🔎 Evidence Chain
    > "[Insert the exact quote from the evidence that explains the variance. If none, write: 'No relevant text found.']"
    **Source:** `{ev['file'] if relevant_evidence else 'N/A'}`

    ### 📝 Forensic Explanation
    [Provide a concise, professional explanation of what caused the discrepancy based on the evidence, or state that it is unexplained and likely a typo/omission.]

    ### 🎯 Recommended Action
    [What should the human accountant do next? e.g., "Approve the journal entry below to align the ERP," or "Contact the vendor to request the missing freight receipt."]

    ### 📓 Proposed Journal Entry
    | Account Name | Debit | Credit |
    | :--- | :--- | :--- |
    | [Appropriate Expense/Revenue/Adjustment Account] | ${variance_abs:.2f} | |
    | [Accounts Payable / Accounts Receivable] | | ${variance_abs:.2f} |
    """
    
    logger.info("Sending strict prompt to OpenAI...")
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a highly structured forensic accounting AI. You only output in the requested markdown format."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0 # Dropped to 0 for maximum formatting consistency
    )
    
    return response.choices[0].message.content