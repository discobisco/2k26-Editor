from __future__ import annotations

import re


_TEAM_ABBREVS = [
    "ATL",
    "BOS",
    "BKN",
    "CHA",
    "CHI",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GSW",
    "HOU",
    "IND",
    "LAC",
    "LAL",
    "MEM",
    "MIA",
    "MIL",
    "MIN",
    "NOP",
    "NYK",
    "OKC",
    "ORL",
    "PHI",
    "PHX",
    "POR",
    "SAC",
    "SAS",
    "TOR",
    "UTA",
    "WAS",
]


class TeamIdResolver:
    @staticmethod
    def _season_start_year(season: str) -> str:
        season = str(season or "").strip()
        if not season:
            return "2025"
        if "-" in season:
            return season.split("-", 1)[0]
        if len(season) == 4 and season.isdigit():
            return season
        return "2025"

    def normalize(self, team_id: str | int, *, season: str) -> str:
        year = self._season_start_year(season)
        if isinstance(team_id, int):
            idx = max(0, min(len(_TEAM_ABBREVS) - 1, team_id))
            return f"{_TEAM_ABBREVS[idx]}_{year}"

        raw = str(team_id).strip().upper()
        if raw.isdigit():
            return self.normalize(int(raw), season=season)

        if re.fullmatch(r"[A-Z]{2,4}_\d{4}", raw):
            return raw
        if raw in _TEAM_ABBREVS:
            return f"{raw}_{year}"

        cleaned = re.sub(r"[^A-Z0-9]+", "_", raw).strip("_")
        if not cleaned:
            cleaned = "TEAM"
        if re.search(r"_\d{4}$", cleaned):
            return cleaned
        return f"{cleaned}_{year}"
