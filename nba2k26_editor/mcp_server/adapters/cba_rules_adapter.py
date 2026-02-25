from __future__ import annotations

from nba2k_editor.gm_rl.cba.repository import load_ruleset_for_season

from ..api.v1.models import LeagueRuleSet


class CbaRulesAdapter:
    def load_league_rules(self, *, season: str) -> LeagueRuleSet:
        rules = load_ruleset_for_season(season)
        first_apron = float(rules.cap.first_apron_by_season.get(season, 0.0))
        second_apron = float(rules.cap.second_apron_by_season.get(season, 0.0))
        return LeagueRuleSet(
            season=season,
            salary_cap_percent_bri=float(rules.cap.salary_cap_percent_bri),
            first_apron=first_apron,
            second_apron=second_apron,
            hard_cap=second_apron,
            luxury_tax_line=first_apron,
            min_roster=int(rules.roster.regular_season_min_players),
            max_roster=int(rules.roster.regular_season_max_players),
        )
