from __future__ import annotations

from nba2k_editor.core import offsets


def test_editor_layout_for_super_attaches_exact_grouped_dropdowns_json_options() -> None:
    layout = offsets.get_editor_layout_for_super("Players")
    payload = next(
        field["versions"]["2K26"]
        for field in layout["Contract"]["Contract Status"]
        if field["normalized_name"] == "FREEAGENCYTYPE"
    )

    assert payload["dropdown"] == ["Unrestricted", "Restricted", "Rookie Restricted"]


def test_editor_layout_dropdowns_json_does_not_attach_across_groups() -> None:
    layout = offsets.get_editor_layout_for_super("Players")
    season_fields = [
        field
        for groups in layout.values()
        if isinstance(groups, dict)
        for entries in groups.values()
        if isinstance(entries, list)
        for field in entries
        if field["normalized_name"] == "SEASON"
    ]

    assert season_fields
    assert all("dropdown" not in payload for field in season_fields for payload in field["versions"].values())
