from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_ROOT = PROJECT_ROOT / "nba2k_editor" / "Player Generator"
sys.path.insert(0, str(GENERATOR_ROOT))

import player_rules  # noqa: E402

FORBIDDEN_PREFIXES = ("identity.", "season_info.")
FORBIDDEN_FIXED_KEY_MARKERS = ("default_90_pending_injury_database",)


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _derive_function_evidence() -> dict[str, tuple[str, tuple[str, ...]]]:
    evidence: dict[str, tuple[str, tuple[str, ...]]] = {}
    for path in GENERATOR_ROOT.glob("player_rules*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("derive_")):
            call = None
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {
                    "_attribute",
                    "_attribute_curve",
                    "_tendency",
                    "_tendency_curve",
                    "_fixed",
                }:
                    call = node
            if call is None:
                continue
            helper = call.func.id
            keys: tuple[str, ...] = ()
            if helper == "_fixed":
                keys = tuple(str(key) for key in (_literal(call.args[2]) or ())) if len(call.args) >= 3 else ()
            elif len(call.args) >= 4:
                parts = _literal(call.args[3])
                if isinstance(parts, tuple):
                    keys = tuple(str(part[0]).removeprefix("!") for part in parts if isinstance(part, tuple) and part)
            evidence[function.name] = (helper, keys)
    return evidence


class PlayerGeneratorStatDrivenRuleTests(unittest.TestCase):
    def test_post_scoring_attributes_and_tendencies_are_offense_owned(self) -> None:
        self.assertEqual("offense", player_rules.rule_spec_for("Attributes/POSTFADEAWAY").module)
        mental_source = (GENERATOR_ROOT / "player_rules_mental.py").read_text(encoding="utf-8")
        self.assertNotIn("postfade", mental_source.lower())
        post_tendency_offenders = [
            f"{field_key}: {spec.module}"
            for field_key, spec in player_rules.PLAYER_RULE_SCHEME.items()
            if field_key.startswith("Tendencies/POST") and spec.module != "offense"
        ]
        self.assertEqual([], post_tendency_offenders)

    def test_shooting_attributes_use_direct_master_sql_split_columns(self) -> None:
        by_function = _derive_function_evidence()

        three_keys = by_function["derive_attribute_field_3point"][1]
        self.assertIn("shooting.fg_percent_from_x3p_range", three_keys)
        self.assertIn("shooting.percent_fga_from_x3p_range", three_keys)
        self.assertIn("shooting.corner_3_point_percent", three_keys)
        self.assertNotIn("advanced.ts_percent", three_keys)

        close_keys = by_function["derive_attribute_closeshot"][1]
        self.assertIn("shooting.fg_percent_from_x0_3_range", close_keys)
        self.assertIn("shooting.fg_percent_from_x3_10_range", close_keys)
        self.assertNotIn("per_game.fg_percent", close_keys)

        mid_keys = by_function["derive_attribute_midrange"][1]
        self.assertIn("shooting.fg_percent_from_x16_3p_range", mid_keys)
        self.assertIn("shooting.percent_fga_from_x16_3p_range", mid_keys)
        self.assertNotIn("shooting.percent_fga_from_x10_16_range", mid_keys)

    def test_defense_and_foul_rules_use_correct_directional_sql_evidence(self) -> None:
        by_function = _derive_function_evidence()

        defense_source = (GENERATOR_ROOT / "player_rules_defense.py").read_text(encoding="utf-8")
        self.assertIn("('!team_summary.d_rtg', 0.25)", defense_source)
        self.assertIn("('!team_summary.d_rtg', 0.15)", defense_source)
        self.assertNotIn("('team_summary.d_rtg'", defense_source)

        foul_keys = by_function["derive_tendency_foul"][1]
        self.assertIn("play_by_play.shooting_foul_committed", foul_keys)
        self.assertIn("play_by_play.offensive_foul_committed", foul_keys)
        self.assertNotIn("advanced.f_tr", foul_keys)

    def test_non_vitals_player_rules_do_not_use_identity_or_season_fallbacks(self) -> None:
        by_function = _derive_function_evidence()
        offenders: list[str] = []
        for field_key, spec in sorted(player_rules.PLAYER_RULE_SCHEME.items()):
            if field_key.startswith("Vitals/") or field_key.endswith("DURABILITY"):
                continue
            helper, keys = by_function.get(spec.function, ("", ()))
            bad_keys = [key for key in keys if key.startswith(FORBIDDEN_PREFIXES)]
            bad_keys.extend(key for key in keys if any(marker in key for marker in FORBIDDEN_FIXED_KEY_MARKERS))
            if helper == "_fixed":
                bad_keys.append("_fixed")
            if bad_keys:
                offenders.append(f"{field_key}: {spec.function}: {', '.join(dict.fromkeys(bad_keys))}")
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
