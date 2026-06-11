from pathlib import Path
import pandas as pd
import camelot

INPUT_DIR = Path("input")
OUTPUT_FILE = Path("output/bank_statements_raw.xlsx")

all_tables = []

for pdf_path in INPUT_DIR.glob("*.pdf"):
    print(f"Processing {pdf_path.name}")

    try:
        tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="stream")
    except Exception as e:
        print(f"Failed on {pdf_path.name}: {e}")
        continue

    for i, table in enumerate(tables):
        df = table.df
        df["source_file"] = pdf_path.name
        df["table_number"] = i + 1
        all_tables.append(df)

if not all_tables:
    raise RuntimeError("No tables found. Try the OCR/Docling path below.")

combined = pd.concat(all_tables, ignore_index=True)

with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
    combined.to_excel(writer, sheet_name="raw_extraction", index=False)

print(f"Saved: {OUTPUT_FILE}")