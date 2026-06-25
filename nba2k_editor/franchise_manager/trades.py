from __future__ import annotations

from .models import TeamDirection
from .transactions import TransactionRecommendation, recommend_team_transactions
from .world import TeamContext


def trade_recommendations(context: TeamContext, direction: TeamDirection | None = None) -> tuple[TransactionRecommendation, ...]:
    return tuple(item for item in recommend_team_transactions(context, direction) if item.kind == "trade")
