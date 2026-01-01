import os
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Setup Folders
BASE_DIR = "demo_data"
folders = ["ledgers", "evidence/emails", "evidence/messaging", "evidence/notices", "evidence/invoices"]
for folder in folders:
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

# 1. Generate Ledgers
data_a = {
    "invoice_id": [f"INV-{i}" for i in range(101, 116)],
    "entity": ["GlobalCorp", "TechVentures", "BioHealth", "RetailGiant", "AlphaSystems", "CloudNine", "DataFlow", "EcoSmart", "FinTech", "GreenLeaf", "HyperLoop", "IonDrive", "JetSet", "Krypto", "Luna"],
    "amount": [5000, 12000, 8500, 22000, 5000, 15000, 7200, 9000, 3000, 11000, 6000, 4500, 8800, 13000, 2500],
    "date": ["2025-12-01"] * 15
}

df_a = pd.DataFrame(data_a)
df_b = df_a.copy()

# Introduce Mismatches for Sleuth to find
df_b.at[1, "amount"] = 11500 # INV-102: Wire fee
df_b.at[4, "amount"] = 4500  # INV-105: Holiday discount
df_b.at[9, "amount"] = 10000 # INV-110: Damaged goods return
df_b.at[13, "amount"] = 12800 # INV-114: Tax adjustment

df_a.to_csv(f"{BASE_DIR}/ledgers/ledger_sub_a.csv", index=False)
df_b.to_csv(f"{BASE_DIR}/ledgers/ledger_sub_b.csv", index=False)

# 2. Generate Evidence using AI
def generate_clue(category, invoice_id, reason):
    prompt = f"Create a realistic short {category} about invoice {invoice_id} explaining why there is a discrepancy because of {reason}. Keep it brief."
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# Create 4 specific clues for our mismatches
clues = [
    ("emails", "INV-102", "a $500 international wire transfer fee"),
    ("messaging", "INV-105", "a 10% holiday discount for early ordering"),
    ("notices", "INV-110", "a $1000 return for damaged units"),
    ("invoices", "INV-114", "a $200 local tax adjustment")
]

for i, (cat, inv, reason) in enumerate(clues):
    content = generate_clue(cat, inv, reason)
    with open(f"{BASE_DIR}/evidence/{cat}/clue_{i}.txt", "w") as f:
        f.write(content)

# Fill rest with noise (Red Herrings)
for i in range(5, 10):
    with open(f"{BASE_DIR}/evidence/emails/noise_{i}.txt", "w") as f:
        f.write("Just a routine check-in on project status. No financial changes.")

print("Sleuth's Case Files Generated Successfully!")