from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .schema import CbaRuleSet


def _cba_dir() -> Path:
    return Path(__file__).resolve().parent


def default_ruleset_path(season: str = "2025-26") -> Path:
    if season == "2025-26":
        return _cba_dir() / "rules_2025_26.json"
    return _cba_dir() / "rules_all_years.json"


@lru_cache(maxsize=8)
def load_ruleset(path: Optional[str] = None) -> CbaRuleSet:
    source = Path(path) if path else default_ruleset_path()
    data = json.loads(source.read_text(encoding="utf-8"))
    if "rulesets" in data:
        rulesets = data["rulesets"]
        if "2025-26" in rulesets:
            return CbaRuleSet.from_dict(rulesets["2025-26"])
        first_key = next(iter(rulesets))
        return CbaRuleSet.from_dict(rulesets[first_key])
    return CbaRuleSet.from_dict(data)


@lru_cache(maxsize=8)
def load_ruleset_for_season(season: str, path: Optional[str] = None) -> CbaRuleSet:
    if path:
        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8"))
        if "rulesets" in data:
            if season in data["rulesets"]:
                return CbaRuleSet.from_dict(data["rulesets"][season])
            if "2025-26" in data["rulesets"]:
                return CbaRuleSet.from_dict(data["rulesets"]["2025-26"])
            first_key = next(iter(data["rulesets"]))
            return CbaRuleSet.from_dict(data["rulesets"][first_key])
        return CbaRuleSet.from_dict(data)
    if season == "2025-26":
        return load_ruleset(str(default_ruleset_path("2025-26")))
    return load_ruleset(str(default_ruleset_path(season)))

