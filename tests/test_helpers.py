"""Small helpers the whole build leans on: names, numbers, dates, links and structured data.

Run all the Python tests:  .venv/bin/python -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from sitegen import common  # noqa: E402

ROOT = common.ROOT


class Names(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(common.slug("Canon O'Heron"), "canon-oheron")
        self.assertEqual(common.slug("L.H. Griffin"), "lh-griffin")
        self.assertEqual(common.slug("  Alma Center Lincoln "), "alma-center-lincoln")
        self.assertEqual(common.slug("Melrose-Mindoro"), "melrose-mindoro")

    def test_canon_uses_aliases(self):
        for wrong, right in common.PLAYER_ALIASES.items():
            self.assertEqual(common.canon(f" {wrong} "), right)
        self.assertEqual(common.canon("Hayden Massman"), "Hayden Massman")

    def test_admin_page_names_photos_like_the_build(self):
        """The admin page names a headshot file after the player (api/admin.js) and finds the published copy
        (admin.html); the build publishes it under its own slug. All three must agree."""
        names = ["Canon O'Heron", "L.H. Griffin", "Hayden Massman", "Jean-Luc St. Pierre", "team-2025-26-20261106041527"]
        js = ("const {slug}=require(process.argv[1]);"
              "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(slug)))")
        out = subprocess.run(["node", "-e", js, os.path.join(ROOT, "api", "admin.js"), json.dumps(names)],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [common.slug(n) for n in names])


class Numbers(unittest.TestCase):
    def test_fmt_int(self):
        self.assertEqual(common.fmt_int(1733), "1,733")
        self.assertEqual(common.fmt_int("12"), "12")
        self.assertEqual(common.fmt_int(12.5), "12.5")
        self.assertEqual(common.fmt_int(None), "")
        self.assertEqual(common.fmt_int(""), "")

    def test_averages_and_percentages(self):
        self.assertEqual(common.fmt_avg(558, 26), "21.5")
        self.assertEqual(common.fmt_avg(10, 0), "")
        self.assertEqual(common.fmt_avg(None, 3), "")
        self.assertEqual(common.fmt_pct(1, 3), "33.3%")
        self.assertEqual(common.fmt_pct(1, 0), "")

    def test_num(self):
        self.assertEqual(common.num("7"), 7.0)
        self.assertIsNone(common.num(""))
        self.assertIsNone(common.num(None))


class Dates(unittest.TestCase):
    def test_fmt_date(self):
        self.assertEqual(common.fmt_date("2026-11-30"), "Nov 30, 2026")
        self.assertEqual(common.fmt_date("2026-11-30", "long"), "Monday, November 30, 2026")
        self.assertEqual(common.fmt_date(""), "")

    def test_season_end_year(self):
        self.assertEqual(common.season_end_year("2026-27"), 2027)
        self.assertEqual(common.season_end_year("1999-00"), 2000)


class Links(unittest.TestCase):
    def test_clean_path(self):
        self.assertEqual(common.clean_path("index.html"), "/")
        self.assertEqual(common.clean_path("seasons/index.html"), "/seasons")
        self.assertEqual(common.clean_path("players/hayden-massman.html"), "/players/hayden-massman")


class StructuredData(unittest.TestCase):
    """These load the whole data set (a few seconds)."""

    @classmethod
    def setUpClass(cls):
        from sitegen import jsonld
        cls.j = jsonld

    def test_start_time_in_wisconsin_time(self):
        self.assertEqual(self.j.ld_start("2026-11-30", "7:00 PM"), "2026-11-30T19:00:00-06:00")
        self.assertEqual(self.j.ld_start("2027-03-12", "12:30 pm"), "2027-03-12T12:30:00-06:00")  # standard time
        self.assertEqual(self.j.ld_start("2027-03-19", "12:30 pm"), "2027-03-19T12:30:00-05:00")  # daylight time from Mar 14
        self.assertEqual(self.j.ld_start("2026-12-03", ""), "2026-12-03")
        self.assertEqual(self.j.ld_start("2026-12-03", "TBA"), "2026-12-03")

    def test_json_can_sit_in_a_script_tag(self):
        out = str(self.j.ld_json([{"@type": "Thing", "name": "</script><b>"}]))
        self.assertNotIn("</script>", out)
        self.assertEqual(json.loads(out)["name"], "</script><b>")

    def test_one_item_or_a_graph(self):
        self.assertEqual(self.j.ld_json([]), "")
        one = json.loads(str(self.j.ld_json([{"@type": "Thing"}])))
        self.assertEqual(one["@type"], "Thing")
        two = json.loads(str(self.j.ld_json([{"@type": "A"}, None, {"@type": "B"}])))
        self.assertEqual([x["@type"] for x in two["@graph"]], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
