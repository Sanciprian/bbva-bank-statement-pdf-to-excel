from pathlib import Path
import pandas as pd

INPUT_FILE = Path("output/bank_statements_llm_clean.xlsx")
OUTPUT_FILE = Path("output/bank_statements_final.xlsx")

df = pd.read_excel(INPUT_FILE)

for col in ["money_out", "money_in", "amount", "balance"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

summary = pd.DataFrame([
    {"metric": "Total money out", "value": df["money_out"].sum(skipna=True)},
    {"metric": "Total money in", "value": df["money_in"].sum(skipna=True)},
    {"metric": "Net amount", "value": df["amount"].sum(skipna=True)},
    {"metric": "Transaction count", "value": len(df)}
])

with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
    df.to_excel(writer, sheet_name="transactions", index=False)
    summary.to_excel(writer, sheet_name="summary", index=False)

print(f"Saved: {OUTPUT_FILE}")