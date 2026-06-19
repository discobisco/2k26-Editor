from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
BEFORE = OUT / "generator_formula_stats_fit_stdout.json"
AFTER = OUT / "generator_formula_stats_fit_stdout_after.json"
FIT = OUT / "generator_formula_stats_fit_1947.csv"
REPORT = OUT / "generator_formula_improvement_report_1947.md"

KEYS = [
    "Tendencies/SHOT vs irl_Field Goals Attempted",
    "Tendencies/SHOT vs irl_Points",
    "Tendencies/SHOT vs irl_Free Throws Attempted",
    "Attributes/OFFENSIVECONSISTENCY vs irl_Field Goals Attempted",
    "Attributes/OFFENSIVECONSISTENCY vs irl_Points",
]
PLAYERS = ["Pete Lalich", "Don Eliason", "Hank Biasatti", "Garland O'Shields", "Joe Fulks", "Stan Miasek", "Bob Feerick"]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    before = load_json(BEFORE)
    after = load_json(AFTER)
    rows = {r["player"]: r for r in csv.DictReader(FIT.open(encoding="utf-8"))}
    lines = [
        "# 1947 generator formula improvement from live-vs-history analytics",
        "",
        "Input comparisons:",
        f"- Before formula-fit metrics: `{BEFORE}`",
        f"- After formula-fit metrics: `{AFTER}`",
        f"- Per-player formula/stat fit rows: `{FIT}`",
        "",
        "## Correlation improvement",
        "",
        "| Metric | before r | after r | delta |",
        "|---|---:|---:|---:|",
    ]
    for key in KEYS:
        b = before["metrics"][key]["r"]
        a = after["metrics"][key]["r"]
        lines.append(f"| {key} | {b:.3f} | {a:.3f} | {a - b:+.3f} |")
    lines.extend([
        "",
        "## Player-level formula outputs after patch",
        "",
        "The live-vs-history comparison showed low-real-volume players were getting too much generated volume floor, while high-volume stars were already near the top of the generated volume scale. The patch removes neutral 0.45 blending for sparse-era volume formulas and uses low/floor neutrals for scoring, usage, draw-foul, and passing volume.",
        "",
        "| Player | SHOT | TOUCHES | Off Consistency | Draw Foul | Pass Accuracy | IRL FGA | live FGA | IRL PTS | live PTS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for player in PLAYERS:
        row = rows[player]
        lines.append(
            f"| {player} | {row['Tendencies/SHOT']} | {row['Tendencies/TOUCHES']} | {row['Attributes/OFFENSIVECONSISTENCY']} | "
            f"{row['Attributes/DRAWFOUL']} | {row['Attributes/PASSACCURACY']} | {row.get('irl_Field Goals Attempted', '')} | "
            f"{row.get('live_Field Goals Attempted', '')} | {row.get('irl_Points', '')} | {row.get('live_Points', '')} |"
        )
    lines.extend([
        "",
        "## Code change",
        "",
        "Changed sparse-era minimal-stat formulas in `nba2k_editor/Player Generator/player_rules.py`:",
        "- scoring neutral fallback: `0.45 -> 0.05`",
        "- usage / SHOT / TOUCHES neutral fallback: `0.45 -> 0.0`",
        "- draw-foul neutral fallback: `0.45 -> 0.05`",
        "- passing neutral fallback: `0.45 -> 0.05`",
        "",
        "This keeps real high-volume stars high while stopping one-game/zero-point players from inheriting a neutral volume tendency.",
    ])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
