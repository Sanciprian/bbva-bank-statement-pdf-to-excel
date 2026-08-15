"""Local, geometry-first, bank-agnostic PDF bank-statement parser."""

from bank_parser.models.statement import BankStatement
from bank_parser.parsing.statement_parser import StatementParser

__version__ = "0.1.0"

__all__ = ["BankStatement", "StatementParser", "__version__"]
