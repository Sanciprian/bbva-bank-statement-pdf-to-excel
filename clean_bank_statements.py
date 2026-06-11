from pathlib import Path

import re

import pandas as pd

from dateutil import parser

RAW_FILE = Path("output/bank_statements_raw.xlsx")

OUTPUT_FILE = Path("output/bank_statements_clean.xlsx")

raw = pd.read_excel(RAW_FILE, sheet_name="raw_extraction", dtype=str)

raw = raw.fillna("")

def looks_like_date(value):

    value = str(value).strip()

    if not value:

        return False

    try:

        parser.parse(value, fuzzy=False)

        return True

    except Exception:

        return False

def parse_money(value):

    if value is None:

        return None

    value = str(value).strip()

    if not value:

        return None

    value = value.replace("$", "").replace(",", "")

    value = value.replace("−", "-")

    negative = False

    if value.startswith("(") and value.endswith(")"):

        negative = True

        value = value[1:-1]

    try:

        amount = float(value)

        return -amount if negative else amount

    except Exception:

        return None

rows = []

for _, row in raw.iterrows():

    cells = [str(row[col]).strip() for col in raw.columns if str(col).isdigit()]

    cells = [c for c in cells if c]

    if len(cells) < 3:

        continue

    date_cell = None

    for c in cells[:3]:

        if looks_like_date(c):

            date_cell = c

            break

    if not date_cell:

        continue

    money_values = []

    text_values = []

    for c in cells:

        money = parse_money(c)

        if money is not None and re.search(r"\d", c):

            money_values.append(money)

        else:

            text_values.append(c)

    if len(money_values) < 1:

        continue

    description_parts = [x for x in text_values if x != date_cell]

    description = " ".join(description_parts)

    amount = None

    balance = None

    if len(money_values) == 1:

        amount = money_values[0]

    elif len(money_values) >= 2:

        amount = money_values[-2]

        balance = money_values[-1]

    rows.append({

        "date": date_cell,

        "description": description,

        "amount": amount,

        "balance": balance,

        "source_file": row.get("source_file", ""),

        "table_number": row.get("table_number", "")

    })

clean = pd.DataFrame(rows)

clean["date"] = pd.to_datetime(clean["date"], errors="coerce")

clean = clean.dropna(subset=["date"])

clean = clean.sort_values(["date", "source_file"])

clean["money_out"] = clean["amount"].apply(lambda x: abs(x) if pd.notna(x) and x < 0 else None)

clean["money_in"] = clean["amount"].apply(lambda x: x if pd.notna(x) and x > 0 else None)

clean = clean[[

    "date",

    "description",

    "money_out",

    "money_in",

    "amount",

    "balance",

    "source_file",

    "table_number"

]]

with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:

    clean.to_excel(writer, sheet_name="transactions", index=False)

print(f"Saved: {OUTPUT_FILE}")

print(f"Rows: {len(clean)}")
