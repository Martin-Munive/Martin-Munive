import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_profile_cards as profile_cards


def synthetic_contributions() -> dict:
    weeks = []
    day_number = 1
    for week_index in range(12):
        contribution_days = []
        for weekday in range(7):
            contribution_days.append(
                {
                    "date": f"2026-07-{day_number:02d}",
                    "weekday": weekday,
                    "contributionCount": (week_index * 2 + weekday) % 9,
                }
            )
            day_number = 1 if day_number == 28 else day_number + 1
        weeks.append({"contributionDays": contribution_days})
    return {"contributionCalendar": {"weeks": weeks}}


class EngineeringPulseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.svg = profile_cards.build_engineering_pulse(synthetic_contributions())
        self.root = ET.fromstring(self.svg)

    def test_is_valid_fixed_size_svg(self) -> None:
        self.assertEqual(self.root.attrib["width"], "820")
        self.assertEqual(self.root.attrib["height"], "370")
        self.assertEqual(self.root.attrib["viewBox"], "0 0 820 370")

    def test_replaces_contribution_grid_with_signal_and_cadence(self) -> None:
        self.assertIn("Engineering Pulse", self.svg)
        self.assertIn("WEEKLY SIGNAL / 12 CYCLES", self.svg)
        self.assertIn("CADENCE VECTOR", self.svg)
        self.assertNotIn("Daily heatmap", self.svg)
        self.assertNotIn('width="10" height="10"', self.svg)

    def test_text_anchors_remain_inside_canvas(self) -> None:
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        for text in self.root.findall(".//svg:text", namespace):
            x = float(text.attrib.get("x", "0"))
            y = float(text.attrib.get("y", "0"))
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x, 820)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(y, 370)


if __name__ == "__main__":
    unittest.main()
