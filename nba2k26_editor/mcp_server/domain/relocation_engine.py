from __future__ import annotations


class RelocationEngine:
    def evaluate(
        self,
        *,
        city: str,
        new_name: str,
        market_size: float,
        arena_quality: float,
    ) -> dict[str, float | str]:
        revenue_index = (market_size * 0.65) + (arena_quality * 0.35)
        return {
            "city": city,
            "new_name": new_name,
            "revenue_index": round(revenue_index, 4),
            "projected_revenue_delta_pct": round((revenue_index - 0.5) * 100.0, 2),
        }
