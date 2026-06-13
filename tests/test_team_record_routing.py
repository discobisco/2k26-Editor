from __future__ import annotations

from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.models.team_record_routing import team_record_rows


class FakeTeamRecordModel:
    target_executable = "NBA2K26.exe"

    def __init__(self) -> None:
        self.calls: list[dict[str, int | str | None]] = []

    def _layout_entries(self, domain: str):
        assert domain == "Teams"
        return (
            FieldEntry(
                domain="Teams",
                section="Stats",
                group="Records",
                ordinal=0,
                field={
                    "display_name": "CURRENT_YEAR_STATS",
                    "selected_record_source": {
                        "role": "team_record_start",
                        "target_domain": "NBA Records",
                        "versions": ["2K26"],
                        "strategy": "team_records_start_plus_team_index_block",
                        "start_index": 3100,
                        "row_count": 510,
                    },
                },
            ),
        )

    def record_summary_rows(
        self,
        domain: str,
        *,
        limit: int | None,
        record_row_start: int,
        record_row_count: int,
    ):
        self.calls.append(
            {
                "domain": domain,
                "limit": limit,
                "record_row_start": record_row_start,
                "record_row_count": record_row_count,
            }
        )
        return [{"Rank": "1"}]


def test_team_records_start_at_authored_team_block_start_for_first_team() -> None:
    model = FakeTeamRecordModel()
    item = RecordListItem(domain="Teams", index=0, address=0x3CAD85690, label="Philadelphia 76ers")

    assert team_record_rows(model, item, "Single Game (Regular)", "Points") == [{"Rank": "1"}]

    assert model.calls == [
        {
            "domain": "NBA Records",
            "limit": 5,
            "record_row_start": 3100,
            "record_row_count": 5,
        }
    ]


def test_team_records_use_team_index_block_plus_category_row_math() -> None:
    model = FakeTeamRecordModel()
    item = RecordListItem(domain="Teams", index=2, address=0x3CAD882E0, label="Washington Bullets")

    team_record_rows(model, item, "Career", "Points")

    assert model.calls == [
        {
            "domain": "NBA Records",
            "limit": 10,
            "record_row_start": 3100 + 2 * 510 + 300,
            "record_row_count": 10,
        }
    ]
