from __future__ import annotations

from .transactions import TransactionRecommendation, recommend_team_transactions
from .world import TeamContext


def rotation_recommendations(context: TeamContext) -> tuple[TransactionRecommendation, ...]:
    return tuple(item for item in recommend_team_transactions(context) if item.kind == "rotation")
