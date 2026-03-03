import os
import pandas as pd
import random
import uuid
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- 1. SETUP FOLDERS ---
BASE_DIR = "data/demo_data"
BANKING_DIR = os.path.join(BASE_DIR, "evidence/banking_docs")
os.makedirs(BANKING_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "ledgers"), exist_ok=True)

batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
print(f"Initializing Banking Audit Data (Batch: {batch_id})...")

# --- 2. GENERATE CORE BANKING SYSTEM (CBS) EXTRACT ---
# Real Kerala locations and realistic loan types
locations = ["Kochi", "Thiruvananthapuram", "Kozhikode", "Thrissur", "Kottayam", "Palakkad"]
loan_types = ["Agricultural Loan", "Commercial Property Loan", "Gold Loan", "SME Business Loan"]

data_cbs = []
for i in range(20):
    loc = random.choice(locations)
    loan_id = f"SIB-LN-{1000 + i}"
    data_cbs.append({
        "loan_account_id": loan_id,
        "customer_name": f"Customer_{i}", # Placeholder for logic, AI will replace in docs
        "loan_type": random.choice(loan_types),
        "disbursed_amount": round(random.uniform(500000, 7500000), 2),
        "interest_rate": random.choice([8.5, 9.25, 10.5, 12.0]),
        "collateral_status": "Clean",
        "location": loc
    })

df_cbs = pd.DataFrame(data_cbs)

# --- 3. INJECT CRITICAL COMPLIANCE GAPS ---

# Case 1: The Litigation Trap (Kochi Commercial Property)
# CSV says "Clean", but Deed will mention a court stay order.
df_cbs.loc[2, 'customer_name'] = "Thomas Kurian"
df_cbs.loc[2, 'location'] = "Kochi"
df_cbs.loc[2, 'collateral_status'] = "Clean" # The "Lie" in the system

# Case 2: The Interest Rate Mismatch
# CSV says 10.5, but Signed Deed will say 9.5
df_cbs.loc[5, 'customer_name'] = "Meenakshi Menon"
df_cbs.loc[5, 'interest_rate'] = 10.5 

# Case 3: Under-reported Land Area
# CSV says 15 Ares, Deed says 12 Ares
df_cbs.loc[8, 'customer_name'] = "Rajesh Pillai"
df_cbs.loc[8, 'location'] = "Palakkad"

# Save the CBS Extract
cbs_path = f"{BASE_DIR}/ledgers/sib_cbs_extract_{batch_id}.csv"
df_cbs.to_csv(cbs_path, index=False)
print(f"CBS Extract saved: {cbs_path}")

# --- 4. GENERATE REALISTIC INDIAN LEGAL DOCUMENTS ---
def generate_bank_doc(doc_type, customer, loan_id, scenario_context):
    prompt = f"""
    You are a legal expert in Kerala, India. Write a highly realistic, formal {doc_type} for South Indian Bank.
    
    Context: {scenario_context}
    Customer: {customer}
    Loan ID: {loan_id}
    
    STRICT RULES:
    1. DO NOT use placeholders like [Name], [Amount], or [Address]. 
    2. Use real Kerala locations (e.g., Kakkanad, MG Road Kochi, Aluva).
    3. Include realistic survey numbers (e.g., Survey No. 42/1A), document numbers, and Registrar Office details.
    4. Mention specific Indian legal terms like 'Encumbrance Certificate', 'Pattayam', or 'Non-Litigation Certificate'.
    5. Ensure the document looks like a formal scan or official memo.
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content

# Generate the specific evidence files
scenarios = [
    ("Legal_Opinion_Report", "Thomas Kurian", "SIB-LN-1002", "A legal opinion for a commercial plot in Edappally, Kochi. It MUST mention that while the bank system marks it clean, there is an active dispute (OS No. 422/2023) in the Munsiff Court regarding boundary walls."),
    ("Loan_Agreement_Deed", "Meenakshi Menon", "SIB-LN-1005", "A formal loan agreement signed in Thrissur. The interest rate explicitly stated in this deed is 9.5% per annum, despite what the computer system might say."),
    ("Property_Valuation_Report", "Rajesh Pillai", "SIB-LN-1008", "A valuation report for agricultural land in Palakkad. The actual measured area is 12 Ares, but note that the applicant originally claimed 15 Ares.")
]

for doc_type, name, lid, context in scenarios:
    print(f"Generating Bank Evidence for {lid}...")
    content = generate_bank_doc(doc_type, name, lid, context)
    filename = f"{lid}_{doc_type}.txt"
    with open(os.path.join(BANKING_DIR, filename), "w") as f:
        f.write(content)

print("✅ Banking Audit Dataset Generated Successfully!")