"""Small pieces of the converter (scripts/convert.py) that tidy what the season sheets export."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from convert import clean_location  # noqa: E402


class CleanLocation(unittest.TestCase):
    def test_scheduling_export_gym_names(self):
        cases = {
            "Bangor High School High School Main Gym": "Bangor High School Main Gym",
            "Seneca High School Seneca High School Gym": "Seneca High School Gym",
            "Wonewoc-Center High School Highschool Gym": "Wonewoc-Center High School Gym",
            "Gale-Ettrick-Trempealeau High School North Gym - Rm 605": "Gale-Ettrick-Trempealeau High School North Gym",
            "De Soto High School (New) Gym": "De Soto High School Gym",
        }
        for raw, want in cases.items():
            self.assertEqual(clean_location(raw), want, raw)

    def test_leaves_clean_names_alone(self):
        for name in ("Bangor High School", "Royall High School New Gym", "Tiger Fieldhouse Main Court",
                     "Cashton Elementary School", "La Crosse Center", ""):
            self.assertEqual(clean_location(name), name)


if __name__ == "__main__":
    unittest.main()
