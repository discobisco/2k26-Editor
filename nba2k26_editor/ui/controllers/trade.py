"""Trade controller helpers."""
from __future__ import annotations

def format_trade_summary(slot_number: int, transaction_count: int) -> str:
    return f"Trade staged (Slot {slot_number}): {transaction_count} moves (write hooks not yet implemented)."
