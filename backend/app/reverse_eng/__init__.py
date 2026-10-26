"""Reverse Engineering (SQLGlot DDL Parser) and Complete Compare Engine."""
from .ddl_parser import parse_ddl_to_metamodel
from .complete_compare import run_complete_compare, CompareDiffResult

__all__ = [
    "parse_ddl_to_metamodel",
    "run_complete_compare",
    "CompareDiffResult",
]
