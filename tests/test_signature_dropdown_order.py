from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any

DROPDOWNS_PATH = Path(__file__).resolve().parents[1] / "nba2k_editor" / "core" / "Offsets" / "dropdowns.json"

LEGACY_2K26_SIGNATURE_SOURCES: dict[tuple[str, str], tuple[str, str]] = {
    ("Ball Handling", "BREAKDOWNCOMBOS"): ("Ball Handling", "BREAKDOWNCOMBOS"),
    ("Ball Handling", "DRIBBLESTYLE"): ("Ball Handling", "DRIBBLESTYLE"),
    ("Ball Handling", "MOVINGCROSSOVER"): ("Ball Handling", "MOVINGCROSSOVER"),
    ("Ball Handling", "MOVINGHESITATION"): ("Ball Handling", "MOVINGHESITATION"),
    ("Ball Handling", "MOVINGSPIN"): ("Ball Handling", "MOVINGSPIN"),
    ("Ball Handling", "MOVINGSTEPBACK"): ("Ball Handling", "MOVINGSTEPBACK"),
    ("Ball Handling", "TRIPLETHREATSTYLE"): ("Ball Handling", "TRIPLETHREATSTYLE"),
    ("Ball Handling", "ESCAPEMOVES"): ("Ball Handling", "SIZEUPESCAPEPACKAGES"),
    ("Ball Handling", "SIGNATURESIZEUP"): ("Ball Handling", "SIGNATURESIZEUPS"),
    ("Ball Handling", "MOVINGBEHINDTHEBACK"): ("Misc", "MOVINGBEHINDTHEBACK"),
    ("Jump Shooting", "DRIBBLEPULLUP"): ("Ball Handling", "DRIBBLEPULLUP"),
    ("Jump Shooting", "HOPJUMPER"): ("Misc", "HOPJUMPER"),
    ("Jump Shooting", "SPINJUMPER"): ("Ball Handling", "SPINJUMPER"),
    ("Jump Shooting", "RELEASETIMING"): ("Jump Shooting", "RELEASETIMING"),
    ("Layups And Dunks", "LAYUPPACKAGE"): ("Layups And Dunks", "LAYUPPACKAGE"),
    ("Misc", "NBAJUMPBALLRITUAL"): ("Jump Shooting", "JUMPBALLRITUAL"),
    ("Post Game", "POSTHOOK"): ("Post Game", "POSTHOOK"),
    ("Post Game", "HOPPOSTSHOT"): ("Post Game", "HOPPOSTSHOT"),
    ("Post Game", "POSTFADE"): ("Post Game", "POSTFADEAWAY"),
}

_ALIAS_KEYS = {
    "null": "none",
    "very_slow": "very slow",
    "very quick": "very quick",
    "big_player": "big",
    "small_player": "small",
    "basic_n 2": "basic 2",
    "basic_n#2": "basic 2",
    "normal_n 2": "normal 2",
    "normal_n#2": "normal 2",
    "pro_n 1": "pro",
    "pro_n#1": "pro",
    "pro_n 2": "pro 2",
    "pro_n#2": "pro 2",
    "pro_n 3": "pro 3",
    "pro_n#3": "pro 3",
    "normal_n wnba1": "normal wnba 1",
    "normal_n#wnba1": "normal wnba 1",
    "normal_n wnba2": "normal wnba 2",
    "normal_n#wnba2": "normal wnba 2",
    "normal_n wnba3": "normal wnba 3",
    "normal_n#wnba3": "normal wnba 3",
}


def _option_key(value: str) -> str:
    text = str(value).strip().lower().replace("_", " ")
    text = text.replace("n#", "n ")
    text = re.sub(r"[.']", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    text = re.sub(r"\s+", " ", text)
    return _ALIAS_KEYS.get(text, text)


def _entry(signature: dict[str, Any], group: str, normalized_name: str) -> dict[str, Any]:
    for entry in signature[group]:
        if entry.get("normalized_name") == normalized_name:
            return entry
    raise AssertionError(f"missing signature dropdown {group}/{normalized_name}")


def _latest_legacy_options(entry: dict[str, Any]) -> list[str]:
    versions = entry.get("versions", {})
    for preferred in ("2K24", "2K23", "2K22", "2K22,2K23,2K24"):
        payload = versions.get(preferred)
        if isinstance(payload, dict):
            options = payload.get("dropdown") or payload.get("values")
            if isinstance(options, list):
                return [str(option) for option in options]
    raise AssertionError(f"missing legacy dropdown options for {entry.get('normalized_name')}")


class SignatureDropdownOrderTests(unittest.TestCase):
    def test_2k26_signature_dropdowns_keep_shared_legacy_raw_id_order(self) -> None:
        data = json.loads(DROPDOWNS_PATH.read_text(encoding="utf-8"))
        signature = data["Players"]["Signature"]

        for target, source in LEGACY_2K26_SIGNATURE_SOURCES.items():
            with self.subTest(target=target, source=source):
                target_entry = _entry(signature, *target)
                source_entry = _entry(signature, *source)
                target_options = [str(option) for option in target_entry["versions"]["2K26"]["dropdown"]]
                target_keys = {_option_key(option) for option in target_options}
                shared_legacy_order = [
                    _option_key(option)
                    for option in _latest_legacy_options(source_entry)
                    if _option_key(option) in target_keys
                ]
                actual_shared_order = [
                    _option_key(option)
                    for option in target_options
                    if _option_key(option) in set(shared_legacy_order)
                ]

                self.assertGreater(len(shared_legacy_order), 1)
                self.assertEqual(actual_shared_order, shared_legacy_order)


if __name__ == "__main__":
    unittest.main()
