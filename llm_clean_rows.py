from pathlib import Path
import json
import requests
import pandas as pd

INPUT_FILE = Path("output/bank_statements_clean.xlsx")
OUTPUT_FILE = Path("output/bank_statements_llm_clean.xlsx")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

df = pd.read_excel(INPUT_FILE, dtype=str).fillna("")

def clean_with_llm(row):
    prompt = f"""
You are cleaning bank statement transaction data.

Return ONLY valid JSON with these keys:
date, description, money_out, money_in, amount, balance, category_guess

Rules:
- Do not invent transactions.
- Preserve the date and amounts unless clearly malformed.
- money_out should be positive for spending.
- money_in should be positive for deposits.
- category_guess should be one of:
  groceries, restaurants, income, transfer, rent, utilities, fees, shopping, travel, healthcare, unknown.

Input row:
{row.to_dict()}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0
            }
        },
        timeout=120
    )

    response.raise_for_status()
    text = response.json()["response"].strip()

    try:
        return json.loads(text)
    except Exception:
        return {
            "date": row.get("date", ""),
            "description": row.get("description", ""),
            "money_out": row.get("money_out", ""),
            "money_in": row.get("money_in", ""),
            "amount": row.get("amount", ""),
            "balance": row.get("balance", ""),
            "category_guess": "unknown"
        }

cleaned_rows = []

for i, row in df.iterrows():
    print(f"Cleaning row {i + 1}/{len(df)}")
    cleaned_rows.append(clean_with_llm(row))

out = pd.DataFrame(cleaned_rows)

with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
    out.to_excel(writer, sheet_name="transactions", index=False)

print(f"Saved: {OUTPUT_FILE}")