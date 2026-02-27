import os
import pandas as pd
import random
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- 1. SETUP FOLDERS ---
BASE_DIR = "demo_data"
folders = ["ledgers", "evidence/emails", "evidence/messaging", "evidence/notices", "evidence/invoices"]
for folder in folders:
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

print("Folders initialized. Generating realistic corporate data...")

# --- 2. GENERATE BASE LEDGERS (50 Transactions) ---
entities = [
    "Apex Dynamics", "Zenith Logistics", "Novus Health", "BlueShift Tech", 
    "Meridian Financial", "Quantum Retail", "Starlight Media", "IronClad Security",
    "Nexus Cloud", "Veritas Legal"
]

data_a = {
    "invoice_id": [f"INV-{i}" for i in range(1001, 1051)],
    "entity": [random.choice(entities) for _ in range(50)],
    "date": [(datetime(2025, 1, 1) + timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d") for _ in range(50)],
    "amount": [round(random.uniform(1000, 25000), 2) for _ in range(50)]
}

df_a = pd.DataFrame(data_a)
df_b = df_a.copy()

# --- 3. INTRODUCE REALISTIC MISMATCHES ---
# Scenario 1: Unrecorded Freight Charge (Missing in System B)
df_b.loc[df_b['invoice_id'] == 'INV-1008', 'amount'] -= 450.00 

# Scenario 2: SLA Penalty Deduction applied by client (Missing in System A)
df_b.loc[df_b['invoice_id'] == 'INV-1015', 'amount'] -= 1200.00

# Scenario 3: State Tax Rate Change (System B used old rate)
base_amt = df_a.loc[df_a['invoice_id'] == 'INV-1022', 'amount'].values[0]
df_b.loc[df_b['invoice_id'] == 'INV-1022', 'amount'] = round(base_amt * 0.98, 2) # 2% difference

# Scenario 4: Transposition Error (Human typo in System B - NO EVIDENCE WILL EXIST)
val = df_a.loc[df_a['invoice_id'] == 'INV-1031', 'amount'].values[0]
df_b.loc[df_b['invoice_id'] == 'INV-1031', 'amount'] = val + 90.00 # e.g., typing 540 instead of 450

# Scenario 5: Volume Discount applied offline (Missing in System B)
df_b.loc[df_b['invoice_id'] == 'INV-1045', 'amount'] += 2500.00

df_a.to_csv(f"{BASE_DIR}/ledgers/system_a_vendor_ledger.csv", index=False)
df_b.to_csv(f"{BASE_DIR}/ledgers/system_b_erp_ledger.csv", index=False)

print("Ledgers generated: system_a_vendor_ledger.csv and system_b_erp_ledger.csv")

# --- 4. GENERATE EVIDENCE USING AI ---
def generate_document(doc_type, entity, invoice, scenario_prompt):
    prompt = f"""
    You are an employee at a corporate firm. Write a highly realistic, professional {doc_type} regarding invoice {invoice} for the company {entity}. 
    
    The context is: {scenario_prompt}
    
    Include realistic corporate headers, timestamps, email signatures, or chat handles. Do not use placeholders like [Your Name], invent realistic names (e.g., Sarah Jenkins, VP of Finance). Make it look exactly like a real exported text file from a corporate system.
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content

# Define our evidence tasks
clues = [
    ("emails", df_a.loc[7, 'entity'], "INV-1008", "An email thread discussing an unexpected $450 expedited freight charge added to the final bill because the warehouse needed it overnight.", f"RE_Shipping_Delay_INV-1008_{random.randint(100,999)}.txt"),
    ("messaging", df_a.loc[14, 'entity'], "INV-1015", "A Slack export between an account manager and a client where the client explicitly says they are deducting $1200 due to a 4-hour server outage (SLA penalty).", f"slack_export_finance_channel_Oct.txt"),
    ("notices", df_a.loc[21, 'entity'], "INV-1022", "An official memo from the state department of revenue about a 2% tax increase effective immediately, which affects this invoice.", f"State_Dept_Rev_Notice_Tax_Update.txt"),
    ("emails", df_a.loc[44, 'entity'], "INV-1045", "An email from the VP of Sales approving a $2500 volume discount for hitting a tier-3 purchasing threshold.", f"FWD_Approval_Tier3_Discount_INV-1045.txt")
]

# Generate Clues
for cat, entity, inv, reason, filename in clues:
    print(f"Generating evidence for {inv}...")
    content = generate_document(cat, entity, inv, reason)
    with open(f"{BASE_DIR}/evidence/{cat}/{filename}", "w") as f:
        f.write(content)

# Generate Realistic Noise (Red Herrings)
print("Generating background noise documents...")
noise_prompts = [
    ("emails", "An email thread arguing about who is paying for the company holiday party catering.", "Catering_Dispute_Holiday_Party.txt"),
    ("messaging", "A Slack chat about a new software update breaking the printer on the 4th floor.", "slack_it_support_printer.txt"),
    ("invoices", "A standard, perfectly matching invoice for a $50 monthly software subscription.", "INV-0999_Zoom_Subscription.txt"),
    ("notices", "A company-wide memo reminding people to submit their expense reports by Friday.", "Memo_Expense_Reports_Reminder.txt")
]

for cat, reason, filename in noise_prompts:
    content = generate_document(cat, "Internal", "N/A", reason)
    with open(f"{BASE_DIR}/evidence/{cat}/{filename}", "w") as f:
        f.write(content)

print("✅ Sleuth's Case Files Generated Successfully!")