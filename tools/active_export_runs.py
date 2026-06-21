from __future__ import annotations

from pathlib import Path

RUNS_DIR_NAME = "current_active_stat_extractor_runs"
RUN_PREFIX = "run_"
RUN_DIGITS = 3


def runs_root(repo_root: Path) -> Path:
    return repo_root / "outputs" / RUNS_DIR_NAME


def parse_run_number(path: Path) -> int | None:
    name = path.name
    if not name.startswith(RUN_PREFIX):
        return None
    suffix = name[len(RUN_PREFIX) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


def format_run_dir(number: int) -> str:
    return f"{RUN_PREFIX}{number:0{RUN_DIGITS}d}"


def create_next_run_dir(repo_root: Path) -> Path:
    root = runs_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    used = [number for child in root.iterdir() if child.is_dir() and (number := parse_run_number(child)) is not None]
    number = (max(used) + 1) if used else 1
    while True:
        candidate = root / format_run_dir(number)
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            number += 1


def latest_run_dir(repo_root: Path) -> Path:
    root = runs_root(repo_root)
    if not root.is_dir():
        raise FileNotFoundError(f"no stat extractor run folder found under {root}")
    runs = [(number, child) for child in root.iterdir() if child.is_dir() and (number := parse_run_number(child)) is not None]
    if not runs:
        raise FileNotFoundError(f"no numbered stat extractor runs found under {root}")
    return max(runs, key=lambda item: item[0])[1]


def active_export_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "stats_csv": run_dir / "current_active_player_stats.csv",
        "stats_json": run_dir / "current_active_player_stats.json",
        "attributes_csv": run_dir / "current_active_player_attributes.csv",
        "attributes_json": run_dir / "current_active_player_attributes.json",
        "season_highs_csv": run_dir / "current_active_player_season_highs.csv",
        "season_highs_json": run_dir / "current_active_player_season_highs.json",
        "awards_csv": run_dir / "current_active_player_awards.csv",
        "awards_json": run_dir / "current_active_player_awards.json",
        "teams_csv": run_dir / "current_active_team_fields.csv",
        "teams_json": run_dir / "current_active_team_fields.json",
        "summary": run_dir / "current_active_player_stats_summary.md",
        "tendencies_csv": run_dir / "current_active_player_tendencies.csv",
        "tendencies_json": run_dir / "current_active_player_tendencies.json",
        "tendencies_summary": run_dir / "current_active_player_tendencies_summary.md",
    }
