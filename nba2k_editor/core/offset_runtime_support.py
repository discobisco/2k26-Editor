from __future__ import annotations

import re
from typing import Any, Callable

VersionLabelDeriver = Callable[[str | None], str | None]
SchemaErrorFactory = type[Exception]
ToIntFn = Callable[[object], int]


def _derive_version_label(executable: str | None) -> str | None:
    """Return a version label like '2K26' based on the executable name."""
    if not executable:
        return None
    match = re.search(r"2k(\d{2})", executable.lower())
    if not match:
        return None
    return f"2K{match.group(1)}"



def _resolve_version_context(
    data: dict[str, Any] | None,
    target_executable: str | None,
    *,
    derive_version_label: VersionLabelDeriver = _derive_version_label,
) -> tuple[str | None, dict[str, Any], dict[str, Any]]:
    """Return (version_label, base_pointers, game_info) for the active target."""
    version_label = derive_version_label(target_executable)
    if not isinstance(data, dict):
        return version_label, {}, {}

    versions_raw = data.get("versions")
    versions_map = versions_raw if isinstance(versions_raw, dict) else {}
    version_info: dict[str, Any] = {}
    if version_label and versions_map:
        candidate = versions_map.get(version_label)
        if not isinstance(candidate, dict):
            candidate = versions_map.get(version_label.upper())
        if not isinstance(candidate, dict):
            candidate = versions_map.get(version_label.lower())
        if isinstance(candidate, dict):
            version_info = candidate

    version_base = version_info.get("base_pointers")
    base_pointers = version_base if isinstance(version_base, dict) else {}

    version_game = version_info.get("game_info")
    game_info = version_game if isinstance(version_game, dict) else {}
    stride_constants = version_info.get("stride_constants")
    if isinstance(stride_constants, dict):
        merged_game_info = dict(game_info)
        merged_game_info.update(stride_constants)
        game_info = merged_game_info

    return version_label, base_pointers, game_info



def _normalize_chain_steps(
    chain_data: object,
    *,
    to_int: ToIntFn,
    offset_schema_error: SchemaErrorFactory,
) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    if chain_data is None:
        return steps
    if not isinstance(chain_data, list):
        raise offset_schema_error("Pointer chain must be a list.")
    allowed_keys = {"offset", "post_add", "dereference"}
    for index, hop in enumerate(chain_data):
        if not isinstance(hop, dict):
            raise offset_schema_error(f"Pointer chain step at index {index} must be an object.")
        unknown = [key for key in hop.keys() if key not in allowed_keys]
        if unknown:
            raise offset_schema_error(
                f"Pointer chain step at index {index} contains unsupported keys: {', '.join(sorted(unknown))}."
            )
        steps.append(
            {
                "offset": to_int(hop.get("offset")),
                "post_add": to_int(hop.get("post_add")),
                "dereference": bool(hop.get("dereference")),
            }
        )
    return steps



def _parse_pointer_chain_config(
    base_cfg: dict | None,
    *,
    normalize_chain_steps: Callable[[object], list[dict[str, object]]],
    to_int: ToIntFn,
    offset_schema_error: SchemaErrorFactory,
) -> list[dict[str, object]]:
    chains: list[dict[str, object]] = []
    if not isinstance(base_cfg, dict):
        return chains
    allowed_keys = {"address", "chain", "absolute", "direct_table", "final_offset"}
    unknown = [key for key in base_cfg.keys() if key not in allowed_keys]
    if unknown:
        raise offset_schema_error(f"Base pointer config contains unsupported keys: {', '.join(sorted(unknown))}.")
    addr_raw = base_cfg.get("address")
    if addr_raw is None:
        return chains
    base_addr = to_int(addr_raw)
    final_offset = to_int(base_cfg.get("final_offset"))
    is_absolute = bool(base_cfg.get("absolute"))
    chain_data = base_cfg.get("chain")
    if chain_data is None:
        raise offset_schema_error("Base pointer config must include a 'chain' list (use [] for direct table pointers).")
    steps = normalize_chain_steps(chain_data)
    if "direct_table" in base_cfg:
        direct_table = bool(base_cfg.get("direct_table"))
    else:
        direct_table = False
    chains.append(
        {
            "rva": base_addr,
            "steps": steps,
            "final_offset": final_offset,
            "absolute": is_absolute,
            "direct_table": direct_table,
        }
    )
    return chains
