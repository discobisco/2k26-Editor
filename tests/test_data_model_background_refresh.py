from __future__ import annotations

from nba2k_editor.models.data_model import EDITOR_DOMAINS, EditorDataModel
from nba2k_editor.models.schema import RecordListItem
from nba2k_editor.models.view_data import DomainRefreshView


class RefreshModel(EditorDataModel):
    def __init__(self) -> None:
        self.loaded_items = {domain: {} for domain in EDITOR_DOMAINS}
        self.selected_items = {domain: None for domain in EDITOR_DOMAINS}
        self.domain_statuses = {domain: "not loaded" for domain in EDITOR_DOMAINS}
        self._data_version = 0
        self._player_team_pointer_cache: dict[int, int] = {}
        self._player_filter_items_by_key = {}
        self._player_search_keys = {}
        self._player_filter_index_ready = False
        self.attach_calls = 0
        self.staff = RecordListItem("Staff", 3, 0x3300, "Coach Example")

    def attach(self) -> bool:  # type: ignore[override]
        self.attach_calls += 1
        return True

    def scan_records(self, domain: str, *, limit: int | None = None):  # type: ignore[override]
        assert domain == "Staff"
        return [self.staff]

    def runtime_status_text(self) -> str:  # type: ignore[override]
        return "attached"


def test_refresh_domains_returns_immutable_views_and_progress_without_model_thread_state() -> None:
    model = RefreshModel()
    progress: list[tuple[int, int, str]] = []

    result = model.refresh_domains(("Staff",), progress_callback=lambda current, total, message: progress.append((current, total, message)))

    assert result == (DomainRefreshView("Staff", (model.staff,), "loaded 1 staff records", 1),)
    assert progress == [(1, 1, "Loaded Staff")]
    assert model.attach_calls == 1
    assert not hasattr(model, "refresh_thread")
    assert not hasattr(model, "refresh_events")
