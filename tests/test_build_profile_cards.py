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


class LanguageConstellationTests(unittest.TestCase):
    def test_repository_policy_excludes_generated_flutter_wrappers(self) -> None:
        repositories = [
            {
                "name": "Control-insulinas",
                "fork": False,
                "archived": False,
                "languages_url": "https://example.test/control/languages",
            },
            {
                "name": "analysis",
                "fork": False,
                "archived": False,
                "languages_url": "https://example.test/analysis/languages",
            },
        ]
        payloads = {
            "https://example.test/control/languages": {
                "C++": 220_870,
                "C": 200_249,
                "CMake": 122_402,
                "Dart": 63_283,
            },
            "https://example.test/analysis/languages": {"Python": 9_000, "C++": 1_000},
        }
        original_request = profile_cards.request_json
        try:
            profile_cards.request_json = lambda url: payloads[url]
            signals = profile_cards.fetch_language_signals(repositories)
        finally:
            profile_cards.request_json = original_request

        self.assertEqual(signals["Dart"]["repositories"], 1)
        self.assertEqual(signals["C++"]["repositories"], 1)
        self.assertEqual(signals["C++"]["bytes"], 1_000)

    def test_each_repository_contributes_equal_total_weight(self) -> None:
        repositories = [
            {
                "name": "large",
                "fork": False,
                "archived": False,
                "languages_url": "https://example.test/large/languages",
            },
            {
                "name": "small",
                "fork": False,
                "archived": False,
                "languages_url": "https://example.test/small/languages",
            },
        ]
        payloads = {
            "https://example.test/large/languages": {"JavaScript": 1_000_000},
            "https://example.test/small/languages": {"Python": 100},
        }
        original_request = profile_cards.request_json
        try:
            profile_cards.request_json = lambda url: payloads[url]
            signals = profile_cards.fetch_language_signals(repositories)
        finally:
            profile_cards.request_json = original_request

        self.assertEqual(signals["JavaScript"]["score"], 1.0)
        self.assertEqual(signals["Python"]["score"], 1.0)

    def test_constellation_is_valid_fixed_size_svg(self) -> None:
        signals = {
            "Python": {"score": 2.0, "repositories": 3, "bytes": 10_000},
            "TypeScript": {"score": 1.0, "repositories": 1, "bytes": 5_000},
        }
        svg = profile_cards.build_language_constellation(signals)
        root = ET.fromstring(svg)

        self.assertEqual(root.attrib["width"], "820")
        self.assertEqual(root.attrib["height"], "390")
        self.assertIn("Language Constellation", svg)
        self.assertNotIn("Top Languages", svg)
        self.assertNotIn(">C++<", svg)


class ProfileSurfaceTests(unittest.TestCase):
    def test_static_svgs_share_fixed_accessible_canvases(self) -> None:
        root = SCRIPTS_DIR.parent
        expected = {
            root / "assets" / "profile-header.svg": ("1200", "340"),
            root / "assets" / "clinical-systems-map.svg": ("820", "420"),
        }
        for path, dimensions in expected.items():
            svg = ET.parse(path).getroot()
            self.assertEqual(svg.attrib["width"], dimensions[0])
            self.assertEqual(svg.attrib["height"], dimensions[1])
            self.assertEqual(svg.attrib.get("role"), "img")

    def test_readme_uses_local_map_and_only_public_representative_links(self) -> None:
        readme = (SCRIPTS_DIR.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("assets/clinical-systems-map.svg", readme)
        self.assertNotIn("```mermaid", readme)
        self.assertNotIn("Martin-Munive/AIEPI)", readme)
        self.assertNotIn("Martin-Munive/MATER_LOTTO", readme)
        self.assertNotIn("Martin-Munive/INVIMA-HematoOncologia", readme)
        self.assertIn("Martin-Munive/Estadistica-con-Python", readme)


if __name__ == "__main__":
    unittest.main()
