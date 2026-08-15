"""Turn classified rows into normalized Transaction objects (doc sections
14, 18-20). Continuation rows are merged into the transaction they follow;
signed amounts and dates are derived generically from whichever columns the
detected layout actually has -- no bank-specific branching.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from bank_parser.detection.columns import ColumnLayout
from bank_parser.models.document import DocumentWord
from bank_parser.models.transaction import ClassifiedRow, DetectedRow, RowType, Transaction
from bank_parser.parsing.dates import looks_like_date, parse_date
from bank_parser.parsing.money import looks_like_money, parse_money
from bank_parser.profiles.base import BankProfile

_SIGN_TOKENS = {"+", "-"}


def merge_continuations(classified: list[ClassifiedRow]) -> list[list[ClassifiedRow]]:
    """Group each TRANSACTION row with the CONTINUATION rows that follow it
    (doc section 14). Any other row type (header, repeated header, footer,
    unknown) breaks the chain and is simply not part of any group."""
    groups: list[list[ClassifiedRow]] = []
    for row in classified:
        if row.row_type == RowType.TRANSACTION:
            groups.append([row])
        elif row.row_type == RowType.CONTINUATION and groups:
            groups[-1].append(row)
    return groups


def _row_text(words: list[DocumentWord]) -> str:
    return " ".join(w.text for w in sorted(words, key=lambda w: w.x0))


def _is_expected_for_column(column: str, text: str) -> bool:
    if column == "date":
        return looks_like_date(text)
    if column in ("debit", "credit", "amount", "balance"):
        return looks_like_money(text) or text.strip() in _SIGN_TOKENS
    return True


def _description_words(primary: DetectedRow) -> list[DocumentWord]:
    """The description column's own words, plus any word that leaked into a
    neighboring column but doesn't actually look like that column's content
    (e.g. the start of a long description spilling a pixel into the date
    column) -- generic boundary-precision correction, not a special case."""
    words: list[DocumentWord] = []
    for column, cell_words in primary.cells.items():
        if column == "description":
            words.extend(cell_words)
        else:
            words.extend(w for w in cell_words if not _is_expected_for_column(column, w.text))
    return sorted(words, key=lambda w: w.x0)


def _extract_dates(cell_words: list[DocumentWord], period: tuple[date, date] | None) -> list:
    date_tokens = sorted((w for w in cell_words if looks_like_date(w.text)), key=lambda w: w.x0)
    return [parse_date(w.text, period) for w in date_tokens]


def _leftmost_money(cell_words: list[DocumentWord]):
    money_words = sorted((w for w in cell_words if looks_like_money(w.text)), key=lambda w: w.x0)
    if not money_words:
        return None
    return parse_money(money_words[0].text)


def _signed_amount(
    row: DetectedRow, layout: ColumnLayout
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Returns (debit, credit, amount). Driven entirely by which semantic
    columns the detected layout actually has -- a separate debit/credit
    layout never falls through to the signed-amount path and vice versa."""
    if "debit" in layout.names or "credit" in layout.names:
        debit_money = _leftmost_money(row.cells.get("debit", []))
        credit_money = _leftmost_money(row.cells.get("credit", []))
        debit = debit_money.value if debit_money else None
        credit = credit_money.value if credit_money else None
        if debit is not None:
            amount = -debit
        elif credit is not None:
            amount = credit
        else:
            amount = None
        return debit, credit, amount

    amount_words = row.cells.get("amount", [])
    money = _leftmost_money(amount_words)
    if money is None:
        return None, None, None
    sign_tokens = {w.text.strip() for w in amount_words}
    amount = -money.value if "-" in sign_tokens else money.value
    return None, None, amount


def normalize_transaction(
    group: list[ClassifiedRow],
    layout: ColumnLayout,
    period: tuple[date, date] | None,
    profile: BankProfile,
) -> Transaction | None:
    primary = group[0].row

    dates = _extract_dates(primary.cells.get("date", []), period)
    if not dates:
        return None

    # Some layouts print two dates per row (e.g. "fecha de cargo" then
    # "fecha de operacion"); when that happens the leftmost is treated as
    # the transaction date and the rightmost as the posting date. With a
    # single date it fills both.
    transaction_date = dates[0].value
    posting_date = dates[1].value if len(dates) > 1 else dates[0].value
    raw_date_text = " / ".join(d.raw_text for d in dates)

    debit, credit, amount = _signed_amount(primary, layout)
    balance_money = _leftmost_money(primary.cells.get("balance", []))
    balance = balance_money.value if balance_money else None

    xs = [w.x0 for w in primary.raw_words] + [w.x1 for w in primary.raw_words]
    bbox = (min(xs), primary.y0, max(xs), primary.y1) if xs else None

    txn = Transaction(
        transaction_date=transaction_date,
        posting_date=posting_date,
        description=_row_text(_description_words(primary)),
        debit=debit,
        credit=credit,
        amount=amount,
        balance=balance,
        reference=None,
        source_page=primary.page,
        source_bbox=bbox,
        confidence=group[0].confidence,
        raw_date_text=raw_date_text,
    )

    for continuation in group[1:]:
        txn.add_detail(_row_text(continuation.row.raw_words))

    return txn


def normalize_transactions(
    rows: list[ClassifiedRow],
    layout: ColumnLayout,
    period: tuple[date, date] | None,
    profile: BankProfile,
) -> list[Transaction]:
    transactions = []
    for group in merge_continuations(rows):
        txn = normalize_transaction(group, layout, period, profile)
        if txn is not None:
            transactions.append(txn)
    return transactions
