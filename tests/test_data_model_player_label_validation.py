from __future__ import annotations

import unittest

from nba2k_editor.models.data_model import EditorDataModel


class PlayerLabelValidationTests(unittest.TestCase):
    def test_player_label_accepts_question_mark_placeholder(self) -> None:
        model = object.__new__(EditorDataModel)

        self.assertTrue(model._valid_label_values("Players", 0x1000, ["??????"], ["??????"]))

    def test_player_label_accepts_names_with_letters(self) -> None:
        model = object.__new__(EditorDataModel)

        self.assertTrue(model._valid_label_values("Players", 0x1000, ["Allen", "Iverson"], ["Allen", "Iverson"]))

    def test_team_label_stays_existing_non_empty_behavior(self) -> None:
        model = object.__new__(EditorDataModel)

        self.assertTrue(model._valid_label_values("Teams", 0x1000, ["??????"], ["??????"]))


if __name__ == "__main__":
    unittest.main()
