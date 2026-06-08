from __future__ import annotations

from typing import Any

from nba2k_editor.models.data_model import RecordListItem
from nba2k_editor.ui.dpg_editor import DpgEditorApp


class FakeDpg:
    mvTable_SizingStretchProp = 0

    def __init__(self) -> None:
        self.listbox_callback = None
        self.calls: list[tuple[str, object]] = []
        self.buttons: list[str] = []
        self.button_callbacks: dict[str, Any] = {}
        self.table_columns: list[str] = []
        self.texts: list[str] = []
        self.values: dict[str, str] = {}
        self.items: set[str] = set()
        self.configs: dict[str, dict[str, object]] = {}
        self.combos: list[tuple[list[str], str | None]] = []
        self.combo_callbacks: dict[str, Any] = {}

    def window(self, **kwargs: object) -> "FakeDpg":
        self.calls.append(("window", kwargs.get("label")))
        return self

    def child_window(self, **_kwargs: object) -> "FakeDpg":
        return self

    def group(self, **kwargs: object) -> "FakeDpg":
        tag = kwargs.get("tag")
        if isinstance(tag, str):
            self.items.add(tag)
            self.configs[tag] = dict(kwargs)
        return self

    def add_group(self, **kwargs: object) -> str:
        tag = kwargs.get("tag")
        if isinstance(tag, str):
            self.items.add(tag)
            self.configs[tag] = dict(kwargs)
        return "group"

    def tab_bar(self, **_kwargs: object) -> "FakeDpg":
        self.calls.append(("tab_bar", None))
        return self

    def tab(self, **kwargs: object) -> "FakeDpg":
        self.calls.append(("tab", kwargs.get("label")))
        return self

    def collapsing_header(self, **kwargs: object) -> "FakeDpg":
        self.calls.append(("collapsing_header", kwargs.get("label")))
        return self

    def table(self, **_kwargs: object) -> "FakeDpg":
        return self

    def table_row(self, **_kwargs: object) -> "FakeDpg":
        return self

    def __enter__(self) -> "FakeDpg":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def add_button(self, **kwargs: object) -> str:
        label = kwargs.get("label")
        if isinstance(label, str):
            self.buttons.append(label)
            callback = kwargs.get("callback")
            if callback is not None:
                self.button_callbacks[label] = callback
        return "button"

    def add_spacer(self, **_kwargs: object) -> str:
        return "spacer"

    def add_text(self, *args: object, **kwargs: object) -> str:
        if args:
            self.texts.append(str(args[0]))
        tag = kwargs.get("tag")
        if isinstance(tag, str):
            self.items.add(tag)
        return "text"

    def add_listbox(self, *_args: object, **kwargs: object) -> str:
        self.listbox_callback = kwargs["callback"]
        tag = kwargs.get("tag")
        if isinstance(tag, str):
            self.items.add(tag)
        return "listbox"

    def add_table_column(self, **kwargs: object) -> str:
        label = kwargs.get("label")
        if isinstance(label, str):
            self.table_columns.append(label)
        return "column"

    def add_input_text(self, **kwargs: object) -> str:
        tag = kwargs.get("tag")
        if isinstance(tag, str):
            self.items.add(tag)
        return "input"

    def add_combo(self, items: list[str], **kwargs: object) -> str:
        tag = kwargs.get("tag")
        self.combos.append((items, tag if isinstance(tag, str) else None))
        if isinstance(tag, str):
            self.items.add(tag)
            callback = kwargs.get("callback")
            if callback is not None:
                self.combo_callbacks[tag] = callback
        return "combo"

    def does_item_exist(self, _tag: str) -> bool:
        return _tag in self.items

    def configure_item(self, tag: str, **kwargs: object) -> None:
        self.configs.setdefault(tag, {}).update(kwargs)

    def focus_item(self, _tag: str) -> None:
        return None

    def delete_item(self, tag: str, **kwargs: object) -> None:
        self.calls.append(("delete_item", tag))
        if not bool(kwargs.get("children_only")):
            self.items.discard(tag)

    def set_value(self, tag: str, value: object) -> None:
        self.values[tag] = str(value)

    def get_value(self, _tag: str) -> str:
        return ""


class FakeModel:
    def __init__(self) -> None:
        self.selections: list[tuple[str | None, str | None]] = []
        self.target_executable = "NBA2K26.exe"
        self.summary_calls: list[dict[str, object]] = []
        self.player_labels = ["[0] Tyrese Maxey", "[1] Jayson Tatum"]
        self.team_labels = ["[2] Philadelphia 76ers", "[3] Boston Celtics"]
        self.filtered_player_labels = {"[2] Philadelphia 76ers": ["[0] Tyrese Maxey"], "[3] Boston Celtics": ["[1] Jayson Tatum"]}
        self.selected_items: dict[str, RecordListItem | None] = {"Players": None, "Teams": None}

    def runtime_status_text(self) -> str:
        return "not attached"

    def select_item_by_label(self, domain: str | None, selected_label: str | None) -> RecordListItem | None:
        self.selections.append((domain, selected_label))
        if domain == "Players" and selected_label in self.player_labels:
            self.selected_items["Players"] = RecordListItem("Players", self.player_labels.index(str(selected_label)), 0x7000, str(selected_label).split("] ", 1)[-1])
        elif domain == "Teams" and selected_label in self.team_labels:
            self.selected_items["Teams"] = RecordListItem("Teams", self.team_labels.index(str(selected_label)), 0x9000, str(selected_label).split("] ", 1)[-1])
        elif domain in self.selected_items:
            self.selected_items[domain] = None
        return self.selected_items.get(str(domain))

    def selected_detail_title(self, domain: str, display_label: str) -> str:
        return f"Select a {display_label}"

    def selected_record_address_text(self, domain: str) -> str:
        return "--"

    def domain_item_labels(self, domain: str) -> list[str]:
        if domain == "Players":
            return list(self.player_labels)
        if domain == "Teams":
            return list(self.team_labels)
        return []

    def domain_item_count(self, domain: str) -> int:
        return len(self.domain_item_labels(domain))

    def selected_item(self, domain: str) -> RecordListItem | None:
        return self.selected_items.get(domain)

    def domain_status(self, _domain: str) -> str:
        return "loaded"

    def player_team_filter_options(self) -> tuple[str, ...]:
        return ("All Players", *self.team_labels)

    def player_item_labels_for_team_filter(self, selected_team_label: str | None) -> list[str]:
        selected = str(selected_team_label or "")
        if not selected or selected == "All Players":
            return list(self.player_labels)
        return list(self.filtered_player_labels.get(selected, []))

    def player_item_count_for_team_filter(self, selected_team_label: str | None) -> int:
        return len(self.player_item_labels_for_team_filter(selected_team_label))

    def team_summary_labels(self) -> tuple[str, ...]:
        return ("Team Name",)

    def selected_player_detail_values(self) -> dict[str, str]:
        return {"OVR": "--"}

    def selected_team_summary_values(self) -> dict[str, str]:
        return {"Team Name": "--"}

    def record_summary_labels(self, domain: str) -> tuple[str, ...]:
        if domain == "NBA History":
            return ("Season", "Team Logo", "Team City", "Team Name", "First Name", "Last Name", "Data")
        if domain == "NBA Records":
            return ("Rank", "First Name", "Last Name", "Signature ID", "Team Logo", "Year", "Month", "Day", "Data")
        return ()

    def selected_record_summary_values(self, domain: str) -> dict[str, str]:
        return {label: "--" for label in self.record_summary_labels(domain)}

    def record_summary_rows(
        self,
        domain: str,
        *,
        limit: int | None,
        history_type: int | None = None,
        record_row_start: int | None = None,
        record_row_count: int | None = None,
        record_row_stride: int | None = None,
    ) -> list[dict[str, str]]:
        self.summary_calls.append(
            {
                "domain": domain,
                "limit": limit,
                "history_type": history_type,
                "record_row_start": record_row_start,
                "record_row_count": record_row_count,
                "record_row_stride": record_row_stride,
            }
        )
        if domain == "NBA History":
            row_count = 25 if limit is None else min(limit, 25)
        else:
            requested_limit = 0 if limit is None else limit
            row_count = min(requested_limit, record_row_count if record_row_count is not None else requested_limit)
        return [{label: "--" for label in self.record_summary_labels(domain)} for _ in range(row_count)]

    def player_detail_labels(self) -> tuple[str, ...]:
        return ("OVR",)

    def grouped_fields(self, domain: str) -> dict[str, dict[str, list[Any]]]:
        return {
            "Vitals": {"ID": [FakeEntry(domain, "Vitals", "ID", 1, "First Name", {"versions": {"2K26": {"type": "wstring"}}})]},
            "Gear": {"Shoes": [FakeEntry(domain, "Gear", "Shoes", 2, "Shoe Brand")]},
        }

    def read_entry_value(self, entry: Any, *, index: int) -> dict[str, object]:
        return {"display_value": f"value-{entry.ordinal}", "address": 0x1000 + entry.ordinal}


class FakeEntry:
    def __init__(self, domain: str, section: str, group: str, ordinal: int, display_name: str, field: dict[str, Any] | None = None) -> None:
        self.domain = domain
        self.section = section
        self.group = group
        self.ordinal = ordinal
        self.display_name = display_name
        self.field = field or {"versions": {"2K26": {"type": "bitfield", "dropdown": ["Nike", "Jordan"]}}}


def test_generic_domain_listbox_callback_keeps_captured_domain_when_extra_callback_arg_is_none() -> None:
    dpg = FakeDpg()
    model = FakeModel()
    app = DpgEditorApp(model)  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "Staff")
    assert dpg.listbox_callback is not None

    dpg.listbox_callback("sender", "Coach Name", None, None)

    assert model.selections == [("Staff", "Coach Name")]


def test_generic_domain_list_pane_omits_empty_placeholder_text() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "Staff")

    assert "No staff records available." not in dpg.texts


def test_history_screen_uses_reference_sidebar_tabs_and_preview_table() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "NBA History")

    assert "Season Awards" in dpg.texts
    for label in ("Season Awards", "Past Champions", "League Leaders", "Hall of Famers"):
        assert label in dpg.buttons
    for label in ("Most Valuable Player", "Rookie of the Year", "Sixth Man of the Year", "Coach of the Year"):
        assert label in dpg.buttons
    for label in ("NBA Championship", "FMVP", "Points/Game", "All Hall of Famers"):
        assert label in dpg.buttons
    for label in ("Rank", "Season", "Team Logo", "Team City", "Team Name", "First Name", "Last Name"):
        assert label in dpg.table_columns
    dpg.button_callbacks["Past Champions"]()
    for label in ("Winner Team City", "Winner Team Name", "Result", "Loser Team City", "Loser Team Name"):
        assert label in dpg.table_columns
    dpg.button_callbacks["League Leaders"]()
    assert "Data" in dpg.table_columns
    assert "Record address" not in dpg.texts


def test_history_buttons_change_preview_filter_type() -> None:
    dpg = FakeDpg()
    model = FakeModel()
    app = DpgEditorApp(model)  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "NBA History")
    dpg.button_callbacks["Rookie of the Year"]()
    dpg.button_callbacks["Past Champions"]()

    assert model.summary_calls[-2]["history_type"] == 9
    assert model.summary_calls[-1]["history_type"] == 1


def test_history_preview_requests_and_renders_all_rows_without_cap() -> None:
    dpg = FakeDpg()
    model = FakeModel()
    app = DpgEditorApp(model)  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "NBA History")

    assert model.summary_calls[-1]["limit"] is None
    assert "NBA_History__Season_Awards__preview__24__Rank" in dpg.items


def test_records_screen_uses_reference_sidebar_tabs_and_record_cards() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "NBA Records")

    assert "Single Game (Regular)" in dpg.texts
    for label in ("Single Game (Regular)", "Single Game (Playoffs)", "Season", "Career"):
        assert label in dpg.buttons
    for label in ("Points", "FG Made", "3PT Made", "FT Made", "Rebounds", "Assists", "Blocks", "Steals", "Minutes", "Turnovers", "PPG", "Triple Doubles"):
        assert label in dpg.buttons
    assert "Record #1" in dpg.texts
    for label in ("First Name:", "Last Name:", "Signature ID:", "Team Logo:", "Year:", "Data:"):
        assert label in dpg.texts
    assert "Record address" not in dpg.texts


def test_record_buttons_change_preview_record_row_group() -> None:
    dpg = FakeDpg()
    model = FakeModel()
    app = DpgEditorApp(model)  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "NBA Records")

    dpg.button_callbacks["FG Made"]()
    dpg.button_callbacks["Season"]()
    dpg.button_callbacks["Career"]()

    assert model.summary_calls[-3]["record_row_start"] == 5
    assert model.summary_calls[-3]["record_row_count"] == 5
    assert model.summary_calls[-2]["record_row_start"] == 110
    assert model.summary_calls[-2]["record_row_count"] == 10
    assert model.summary_calls[-1]["record_row_start"] == 450
    assert model.summary_calls[-1]["record_row_count"] == 100


def test_record_preview_hides_cards_after_active_group_count() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "NBA Records")

    dpg.button_callbacks["Season"]()
    assert dpg.configs["NBA_Records__preview__9__card"]["show"] is True
    assert dpg.configs["NBA_Records__preview__10__card"]["show"] is False

    dpg.button_callbacks["Single Game (Regular)"]()
    assert dpg.configs["NBA_Records__preview__4__card"]["show"] is True
    assert dpg.configs["NBA_Records__preview__5__card"]["show"] is False

    dpg.button_callbacks["Career"]()
    assert dpg.configs["NBA_Records__preview__cards"]["show"] is False
    assert dpg.configs["NBA_Records__preview__career_table"]["show"] is True


def test_record_career_uses_table_instead_of_cards() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]

    app._build_domain_screen(dpg, "NBA Records")

    dpg.button_callbacks["Career"]()

    assert dpg.configs["NBA_Records__preview__cards"]["show"] is False
    assert dpg.configs["NBA_Records__preview__career_table"]["show"] is True
    for label in ("Rank", "First Name", "Last Name", "Signature ID", "Team Logo", "Year", "Data"):
        assert label in dpg.table_columns


def test_teams_list_pane_omits_empty_placeholder_text() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]

    app._build_teams_screen(dpg)

    assert "No teams available." not in dpg.texts


def test_players_list_pane_omits_status_text() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]

    app._build_players_screen(dpg)

    assert "not attached" not in dpg.texts


def test_players_team_filter_uses_loaded_teams_and_filters_player_list() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]

    app._build_players_screen(dpg)
    app._sync_domain_list(dpg, "Teams")

    assert dpg.configs["Players__team_filter"]["items"] == [
        "All Players",
        "[2] Philadelphia 76ers",
        "[3] Boston Celtics",
    ]

    dpg.combo_callbacks["Players__team_filter"]("sender", "[2] Philadelphia 76ers", None, None)

    assert dpg.configs["Players__list"]["items"] == ["[0] Tyrese Maxey"]
    assert dpg.values["Players__team_filter"] == "[2] Philadelphia 76ers"
    assert dpg.values["Players__count"] == "Players: 1 / 2"


def test_item_editor_uses_top_level_tabs_instead_of_section_dropdowns() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]
    item = RecordListItem(domain="Players", index=2, address=0x123456, label="Example Player")

    app._open_editor_window(dpg, item)

    assert ("tab_bar", None) in dpg.calls
    assert ("tab", "Vitals") in dpg.calls
    assert ("tab", "Gear") in dpg.calls
    assert ("collapsing_header", "Vitals") not in dpg.calls
    assert ("collapsing_header", "Gear") not in dpg.calls
    assert ("collapsing_header", "ID") in dpg.calls
    assert ("collapsing_header", "Shoes") in dpg.calls


def test_item_editor_omits_top_debug_address_text() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]
    item = RecordListItem(domain="Players", index=2, address=0x123456, label="Example Player")

    app._open_editor_window(dpg, item)

    assert "Players [2] Example Player" not in dpg.texts
    assert "record address: 0x123456" not in dpg.texts


def test_item_editor_uses_combo_for_dropdown_backed_fields() -> None:
    dpg = FakeDpg()
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]
    item = RecordListItem(domain="Players", index=2, address=0x123456, label="Example Player")

    app._open_editor_window(dpg, item)

    assert (["Nike", "Jordan"], "editor__Players__2__2__new") in dpg.combos
