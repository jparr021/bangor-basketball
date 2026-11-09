"""The hand-kept files in overrides/ stay in the shape the build and the admin page expect.

A failure names the file and the line, so a typo made by hand (or a bad save) is easy to find.
"""
import csv
import datetime as dt
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OV = os.path.join(ROOT, "overrides")
SEASON = re.compile(r"^\d{4}-\d{2}$")
URL = re.compile(r"^https?://\S+$")
YOUTUBE = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|embed/|live/|shorts/))[A-Za-z0-9_-]{11}")


def rows(name):
    with open(os.path.join(OV, name), newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def is_date(s):
    try:
        dt.date.fromisoformat(s)
        return True
    except ValueError:
        return False


class Columns(unittest.TestCase):
    """The columns the admin page (api/admin.js) reads and writes."""
    EXPECTED = {
        "photos.csv": ["kind", "season", "player", "image", "caption", "credit"],
        "news_stories.csv": ["published", "outlet", "kind", "title", "url", "access", "game_date", "opponent", "player", "matched_by"],
        "game_film.csv": ["date", "opponent", "youtube_url", "title", "matched_by"],
        "hudl_video.csv": ["date", "opponent", "kind", "access", "url", "title"],
        "rosters.csv": ["season", "number", "name", "position", "height", "grade", "source"],
        "season_history.csv": ["season", "w", "l", "t", "coach", "notes"],
        "grad_years.csv": ["name", "grad_year", "note"],
    }

    def test_columns(self):
        for name, cols in self.EXPECTED.items():
            with self.subTest(name):
                self.assertEqual(rows(name)[0], cols)


class Lines(unittest.TestCase):
    def test_season_history(self):
        seen = set()
        for i, r in enumerate(rows("season_history.csv")[1], 2):
            with self.subTest(line=i):
                self.assertRegex(r["season"], SEASON)
                self.assertNotIn(r["season"], seen, "season listed twice")
                seen.add(r["season"])
                for k in ("w", "l", "t"):
                    self.assertRegex(r[k] or "", r"^\d*$", k)

    def test_rosters(self):
        for i, r in enumerate(rows("rosters.csv")[1], 2):
            with self.subTest(line=i, name=r["name"]):
                self.assertRegex(r["season"], SEASON)
                self.assertTrue(r["name"].strip())
                self.assertIn(r["grade"], ("", "7", "8", "9", "10", "11", "12"))

    def test_identify(self):
        for i, r in enumerate(rows("identify.csv")[1], 2):
            with self.subTest(line=i, name=r["name"]):
                self.assertRegex(r["season"], SEASON)
                self.assertTrue(r["name"].strip() and r["question"].strip())

    def test_same_names(self):
        roster = rows("rosters.csv")[1]
        on_rosters = ({(r["season"], r["name"].strip()) for r in roster}  # "D. Hussa #21" names one numbered line
                      | {(r["season"], f"{r['name'].strip()} #{r['number'].strip()}") for r in roster if r["number"].strip()})
        for i, r in enumerate(rows("same_names.csv")[1], 2):
            with self.subTest(line=i, name=r["name"]):
                self.assertIn((r["season"], r["name"].strip()), on_rosters, "no roster line with this season and name")
                self.assertRegex(r["page"], r"^[a-z0-9]+(-[a-z0-9]+)*$", "page should look like john-bosshard-1939")

    def test_grad_years(self):
        seen = set()
        for i, r in enumerate(rows("grad_years.csv")[1], 2):
            with self.subTest(line=i, name=r["name"]):
                self.assertTrue(r["name"].strip())
                self.assertRegex(r["grad_year"], r"^(19|20)\d\d$")
                self.assertNotIn(r["name"], seen, "player listed twice")
                seen.add(r["name"])

    def test_news_stories(self):
        for i, r in enumerate(rows("news_stories.csv")[1], 2):
            with self.subTest(line=i, title=r["title"][:40]):
                self.assertIn(r["kind"], ("article", "video", "photos"))
                self.assertRegex(r["url"], URL)
                self.assertTrue(is_date(r["published"]))
                if r["game_date"]:
                    self.assertTrue(is_date(r["game_date"]))
                self.assertIn(r["access"], ("free", "subscriber", ""))

    def test_game_film(self):
        for i, r in enumerate(rows("game_film.csv")[1], 2):
            with self.subTest(line=i):
                self.assertTrue(is_date(r["date"]))
                self.assertRegex(r["youtube_url"], YOUTUBE)

    def test_hudl_video(self):
        for i, r in enumerate(rows("hudl_video.csv")[1], 2):
            with self.subTest(line=i):
                self.assertTrue(is_date(r["date"]))
                self.assertIn(r["kind"], ("full", "recap"))
                self.assertIn("hudl.com", r["url"])

    def test_photos_have_their_files(self):
        for i, r in enumerate(rows("photos.csv")[1], 2):
            with self.subTest(line=i, image=r["image"]):
                self.assertIn(r["kind"], ("team", "player"))
                if r["kind"] == "team":
                    self.assertRegex(r["season"], SEASON)
                else:
                    self.assertTrue(r["player"].strip())
                if not URL.match(r["image"]):
                    self.assertTrue(os.path.exists(os.path.join(OV, "photos", r["image"])), "listed but the file is missing")

    def test_admin_log(self):
        path = os.path.join(OV, "admin_log.jsonl")
        if not os.path.exists(path):
            self.skipTest("no admin changes yet")
        with open(path) as f:
            for i, line in enumerate(f, 1):
                if line.strip():
                    with self.subTest(line=i):
                        e = json.loads(line)
                        self.assertIn("id", e)
                        self.assertIn("label", e)

    def test_settings_files(self):
        for name in ("site.json", "current_season.json"):
            with self.subTest(name):
                with open(os.path.join(OV, name)) as f:
                    json.load(f)
        with open(os.path.join(OV, "current_season.json")) as f:
            self.assertRegex(json.load(f)["season"], SEASON)


if __name__ == "__main__":
    unittest.main()
