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


def _payload(layout: dict[str, object], section: str, group: str, name: str) -> dict[str, object]:
    entries = layout[section][group]  # type: ignore[index]
    field = next(entry for entry in entries if entry["normalized_name"] == name)
    return field["versions"]["2K26"]


def test_editor_layout_uses_learnfrom_offset_metadata_for_safe_dropdown_targets() -> None:
    layout = offsets.get_editor_layout_for_super("Players")

    pass_style = _payload(layout, "Signature", "Ball Handling", "PASSSTYLE")
    assert pass_style["address"] == 699
    assert pass_style["hex"] == "0x2bb"
    assert pass_style["type"] == "bitfield"
    assert pass_style["bit_offset"] == 2
    assert pass_style["bit_length"] == 6

    right_arm_frequency = _payload(layout, "Gear", "Upper Body Accessories", "RIGHTARMFREQUENCY")
    assert right_arm_frequency["address"] == 919
    assert right_arm_frequency["hex"] == "0x397"
    assert right_arm_frequency["type"] == "bitfield"
    assert right_arm_frequency["bit_offset"] == 0
    assert right_arm_frequency["bit_length"] == 3


def test_editor_layout_attaches_all_safe_learnfrom_dropdown_lists() -> None:
    players = offsets.get_editor_layout_for_super("Players")
    staff = offsets.get_editor_layout_for_super("Staff")

    expected_players = {
        ("Gear", "Upper Body Accessories", "RIGHTARMFREQUENCY", 5),
        ("Gear", "Shoes/Gear", "UNDERSHIRTAWAYCOLOR", 8),
        ("Signature", "Misc", "CHEWGUM", 2),
        ("Signature", "Misc", "DUNKEMOTION", 2),
        ("Signature", "Misc", "NBAJUMPBALLRITUAL", 30),
        ("Signature", "Ball Handling", "PASSSTYLE", 39),
        ("Signature", "Ball Handling", "TRIPLETHREATSTYLE", 14),
        ("Signature", "Ball Handling", "DRIBBLESTYLE", 44),
        ("Signature", "Ball Handling", "CROSSOVERCOMBOS", 25),
        ("Signature", "Ball Handling", "ESCAPEMOVES", 28),
        ("Signature", "Ball Handling", "MOVINGSPIN", 30),
        ("Signature", "Ball Handling", "MOVINGSTEPBACK", 25),
        ("Signature", "Ball Handling", "MOVINGBEHINDTHEBACK", 37),
        ("Signature", "Ball Handling", "MOVINGCROSSOVER", 52),
        ("Signature", "Ball Handling", "MOVINGHESITATION", 31),
        ("Signature", "Ball Handling", "BREAKDOWNCOMBOS", 71),
        ("Signature", "Post Game", "POSTFADE", 53),
        ("Signature", "Post Game", "POSTHOOK", 25),
        ("Signature", "Post Game", "HOPPOSTSHOT", 19),
        ("Signature", "Post Game", "POSTSPINSPOT", 2),
        ("Signature", "Post Game", "GOPOSTTOSHOT", 27),
        ("Signature", "Layups And Dunks", "LAYUPPACKAGE", 69),
        ("Signature", "Layups And Dunks", "GOTODUNKPACKAGE", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE2", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE3", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE4", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE5", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE6", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE7", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE8", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE9", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE10", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE11", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE12", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE13", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE14", 69),
        ("Signature", "Layups And Dunks", "DUNKPACKAGE15", 69),
    }

    layup_options = _payload(players, "Signature", "Layups And Dunks", "LAYUPPACKAGE")["dropdown"]

    for section, group, name, expected_count in expected_players:
        payload = _payload(players, section, group, name)
        options = payload.get("dropdown") or payload.get("values")
        assert isinstance(options, list), name
        assert len(options) == expected_count, name
        if name.startswith("DUNKPACKAGE") or name == "GOTODUNKPACKAGE":
            assert options == layup_options

    staff_position = _payload(staff, "Vitals", "Vitals", "POSITION")
    assert staff_position["values"][19] == "Foreign Scout"
    assert len(staff_position["values"]) == 26
