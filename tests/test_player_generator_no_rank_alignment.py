from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
REPO_DIR = GENERATOR_DIR.parents[1]
for path in (REPO_DIR, GENERATOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import player_generator  # type: ignore[import-not-found]


def test_pre_per_batch_uses_requested_team_without_rank_postprocessing(monkeypatch) -> None:
    calls: list[str | None] = []
    marker = SimpleNamespace(player_id="A", team="AAA")

    class Context:
        season = 1947

        def player_keys(self, *, team_filter: str | None = None):
            calls.append(team_filter)
            return (("A", "AAA"),)

    monkeypatch.setattr(
        player_generator,
        "generate_player_proposal_from_index",
        lambda context, *, player_id, team: marker,
    )

    batch = player_generator.generate_player_proposals_from_index(Context(), team_filter="AAA")

    assert calls == ["AAA"]
    assert batch.proposals == (marker,)
