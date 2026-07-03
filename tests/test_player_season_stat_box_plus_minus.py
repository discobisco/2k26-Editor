from __future__ import annotations

import unittest

from nba2k_editor.core.conversions import convert_box_plus_minus_to_raw, convert_raw_to_box_plus_minus
from nba2k_editor.core.field_io import _display_to_raw_value, _raw_to_display_value


class PlayerSeasonStatBoxPlusMinusTests(unittest.TestCase):
    def test_box_plus_minus_decodes_live_negative_bias(self) -> None:
        field = {"normalized_name": "BOX+-", "display_name": "Total +/-"}
        payload = {"address": 45, "type": "int", "bit_offset": 6, "bit_length": 16}

        self.assertEqual(-124, convert_raw_to_box_plus_minus(32644))
        self.assertEqual(-52, convert_raw_to_box_plus_minus(32716))
        self.assertEqual(303, convert_raw_to_box_plus_minus(303))
        self.assertEqual(-124, _raw_to_display_value("Season IDs", field, payload, 32644))
        self.assertEqual(-52, _raw_to_display_value("Season IDs", field, payload, 32716))
        self.assertEqual(303, _raw_to_display_value("Season IDs", field, payload, 303))

    def test_box_plus_minus_encodes_negative_bias_for_writes(self) -> None:
        field = {"normalized_name": "BOX+-", "display_name": "Total +/-"}
        payload = {"address": 45, "type": "int", "bit_offset": 6, "bit_length": 16}

        self.assertEqual(32644, convert_box_plus_minus_to_raw(-124))
        self.assertEqual(32716, convert_box_plus_minus_to_raw(-52))
        self.assertEqual(303, convert_box_plus_minus_to_raw(303))
        self.assertEqual(32644, _display_to_raw_value("Season IDs", field, payload, -124))
        self.assertEqual(32716, _display_to_raw_value("Season IDs", field, payload, -52))
        self.assertEqual(303, _display_to_raw_value("Season IDs", field, payload, 303))


if __name__ == "__main__":
    unittest.main()
