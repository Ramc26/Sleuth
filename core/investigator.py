import logging
from core.config import openai_client
from core.vector_store import search_evidence

logger = logging.getLogger("Sleuth.Investigator")

def investigate_variance(inv_id, entity, amt_a, amt_b):
    variance = round(amt_a - amt_b, 2)
    variance_abs = abs(variance)
    
    # Use the new Qdrant Vector Search instead of the old keyword filter
    relevant_evidence = search_evidence(inv_id, entity, variance)
    
    if not relevant_evidence:
        all_context = "No relevant evidence found in the vector database."
    else:
        all_context = "\n\n".join(relevant_evidence)

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
    Investigate the discrepancy using ONLY the provided evidence. Format exactly as below:

    ### 📌 Executive Summary
    * **Verdict:** [Resolved - Evidence Found / Unresolved - Missing Evidence]
    * **Root Cause:** [Categorize in 1-3 words e.g., SLA Penalty, Unknown]
    * **AI Confidence:** [High / Medium / Low] - [1 sentence why]

    ### 🔎 Evidence Chain
    > "[Insert exact quote from evidence. If none, write: 'No relevant text found.']"
    **Source:** `{relevant_evidence[0].split('---')[1].strip() if relevant_evidence else 'N/A'}`

    ### 📝 Forensic Explanation
    [Concise explanation of the discrepancy.]

    ### 🎯 Recommended Action
    [What should the human accountant do next?]

    ### 📓 Proposed Journal Entry
    | Account Name | Debit | Credit |
    | :--- | :--- | :--- |
    | [Appropriate Account] | ${variance_abs:.2f} | |
    | [Appropriate Account] | | ${variance_abs:.2f} |
    """
    
    logger.info("Sending prompt to OpenAI...")
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a structured forensic AI. Output only markdown."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0 
    )
    
    return response.choices[0].message.content