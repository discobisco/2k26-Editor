from __future__ import annotations

from typing import Any

from nba2k_editor.core.field_io import _read_pointer_value


def record_address(*, base: int, index: int, stride: int) -> int:
    """Return the absolute record address for a zero-based record number."""
    if index < 0:
        raise ValueError("index must be zero or greater")
    if stride <= 0:
        raise ValueError("stride must be greater than zero")
    return int(base) + int(index) * int(stride)


def resolve_base_pointer_entry(
    memory: Any,
    base_entry: dict[str, Any],
    *,
    label: str,
    apply_final_offset_without_module_base: bool = True,
    follow_chain: bool = True,
) -> int:
    if "address" not in base_entry:
        raise KeyError(f"base entry for {label} is missing address")
    authored_address = int(base_entry["address"])
    module_base = memory.base_addr
    final_offset = int(base_entry.get("finalOffset") or 0)
    if not module_base:
        return authored_address + (final_offset if apply_final_offset_without_module_base else 0)
    pointer_address = authored_address if bool(base_entry.get("absolute")) else int(module_base) + authored_address
    if bool(base_entry.get("direct_table")):
        return pointer_address + final_offset
    resolved = _read_pointer_value(memory, pointer_address)
    chain = base_entry.get("chain") or base_entry.get("steps") or []
    if follow_chain and isinstance(chain, list):
        for step in chain:
            if not isinstance(step, dict):
                raise TypeError(f"base chain step for {label} must be an object")
            resolved += int(step.get("offset") or 0)
            if bool(step.get("dereference")):
                resolved = _read_pointer_value(memory, resolved)
    return resolved + final_offset
