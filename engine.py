import os
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_all_evidence():
    evidence_data = []
    base_path = "demo_data/evidence"
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith(".txt"):
                with open(os.path.join(root, file), "r") as f:
                    evidence_data.append(f.read())
    return evidence_data

def investigate_variance(inv_id, amt_a, amt_b):
    variance = amt_a - amt_b
    evidence_list = get_all_evidence()
    all_context = "\n---\n".join(evidence_list)

    prompt = f"""
    You are 'Sleuth', a Senior Forensic Accountant.
    
    CASE DETAILS:
    Invoice ID: {inv_id}
    Subsidiary A says: ${amt_a}
    Subsidiary B says: ${amt_b}
    Discrepancy: ${variance}
    
    EVIDENCE LOGS:
    {all_context}
    
    TASK:
    1. Find the specific piece of evidence that explains this ${variance} difference.
    2. If found, explain the reason clearly.
    3. If not found, state that the evidence is missing.
    4. Provide a suggested 'Journal Entry' to fix it.
    
    Keep your response professional and investigative.
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "You are a detective accountant."},
                  {"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content