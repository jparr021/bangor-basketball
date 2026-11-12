"""Checks on the built site (site/). Build it first: .venv/bin/python scripts/build_site.py

Broken links are checked separately, by scripts/check_links.py.
"""
import csv
import glob
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def read(path):
    with open(os.path.join(SITE, path)) as f:
        return f.read()


def page(path):
    """A page's file, with or without .html (clean-URL builds keep the .html files too)."""
    return path if os.path.exists(os.path.join(SITE, path)) else path[:-5] + "/index.html"


@unittest.skipUnless(os.path.exists(os.path.join(SITE, "index.html")), "build the site first")
class BuiltSite(unittest.TestCase):
    def test_every_game_has_a_page(self):
        with open(os.path.join(ROOT, "data", "games.csv")) as f:
            ids = [g["game_id"] for g in csv.DictReader(f)]
        missing = [i for i in ids if not os.path.exists(os.path.join(SITE, "games", f"{i}.html"))]
        self.assertEqual(missing, [])

    def test_every_season_on_file_has_a_page(self):
        with open(os.path.join(ROOT, "data", "games.csv")) as f:
            seasons = {g["season"] for g in csv.DictReader(f)}
        missing = [s for s in sorted(seasons) if not os.path.exists(os.path.join(SITE, "seasons", f"{s}.html"))]
        self.assertEqual(missing, [])

    def test_structured_data_parses(self):
        n = 0
        for path in glob.glob(os.path.join(SITE, "**", "*.html"), recursive=True):
            with open(path) as f:
                for block in LD.findall(f.read()):
                    with self.subTest(os.path.relpath(path, SITE)):
                        d = json.loads(block)
                        self.assertEqual(d["@context"], "https://schema.org")
                    n += 1
        self.assertGreater(n, 1000)

    def test_game_pages_describe_the_game(self):
        d = json.loads(LD.search(read("games/2025-26-01.html")).group(1))
        ev = next(x for x in d["@graph"] if x["@type"] == "SportsEvent")
        self.assertEqual(ev["startDate"][:10], "2025-12-02")
        self.assertIn("Arcadia", ev["name"])

    def test_unlisted_pages_stay_out_of_the_sitemap(self):
        sm = read("sitemap.xml")
        for p in ("/admin", "/sheet-check", "/404"):
            self.assertNotIn(f"vercel.app{p}<", sm)
        self.assertIn("Disallow: /admin", read("robots.txt"))
        for p in ("admin/index.html", "sheet-check.html"):
            self.assertIn('content="noindex', read(p))

    def test_current_season_before_its_first_game(self):
        with open(os.path.join(ROOT, "overrides", "current_season.json")) as f:
            cur = json.load(f)["season"]
        with open(os.path.join(ROOT, "data", "games.csv")) as f:
            played = [g for g in csv.DictReader(f) if g["season"] == cur and g["result"]]
        if played:
            self.skipTest("the current season has started")
        html = read(f"seasons/{cur}.html")
        self.assertNotIn('class="big-rec">0–0<', html)
        self.assertIn("Starts ", html)

    def test_photos_are_published_with_a_version(self):
        with open(os.path.join(ROOT, "overrides", "photos.csv")) as f:
            photos = [r for r in csv.DictReader(f) if not r["image"].startswith("http")]
        for r in photos:
            if r["kind"] != "team":
                continue
            with self.subTest(r["image"]):
                html = read(f"seasons/{r['season']}.html")
                self.assertRegex(html, r'src="[^"]*static/photos/[^"?]+\.jpg\?v=[0-9a-f]{8}"')

    def test_every_public_page_has_its_own_share_card(self):
        """A link to any page people share shows that page's own preview image, not the plain logo card,
        and the image it names was drawn."""
        og = re.compile(r'<meta property="og:image" content="[^"]*?/(static/[^"?]+)')
        unlisted = {"404.html", "sheet-check.html", os.path.join("admin", "index.html")}
        for path in glob.glob(os.path.join(SITE, "**", "*.html"), recursive=True):
            rel = os.path.relpath(path, SITE)
            if rel in unlisted:
                continue
            with self.subTest(rel):
                m = og.search(read(rel))
                self.assertTrue(m, "no og:image")
                self.assertNotEqual(m.group(1), "static/img/share.png", "uses the plain logo card")
                self.assertTrue(os.path.exists(os.path.join(SITE, m.group(1))), f"{m.group(1)} wasn't drawn")

    def test_pages_say_what_an_admin_can_edit(self):
        """Season, player and game pages carry data-edit for the admin edit buttons (static/admin-edit.js), and no
        page loads the editing code itself: site.js does that only on a signed-in admin's device."""
        de = re.compile(r"<body [^>]*data-edit='([^']*)'")
        for path, kind, key in (("seasons/2018-19.html", "season", "season"), ("seasons/1955-56.html", "season", "season"),
                                ("games/2018-19-03.html", "game", "date"), ("players/grant-manke.html", "player", "name")):
            with self.subTest(path):
                m = de.search(read(page(path)))
                self.assertTrue(m, "no data-edit")
                d = json.loads(m.group(1))
                self.assertEqual(d["kind"], kind)
                self.assertTrue(d[key])
        self.assertEqual(json.loads(de.search(read("seasons/1955-56.html")).group(1))["stats"], False)
        self.assertNotIn("data-edit", read("records/index.html"))
        for path in glob.glob(os.path.join(SITE, "**", "*.html"), recursive=True):
            self.assertNotRegex(read(os.path.relpath(path, SITE)), r'src="[^"]*admin-edit\.js', path)
        self.assertTrue(os.path.exists(os.path.join(SITE, "static", "admin-edit.js")))

    def test_admin_page_has_its_data(self):
        html = read("admin/index.html")
        m = re.search(r"var DATA = (\{.*?\});\n", html)
        self.assertTrue(m, "admin data missing")
        data = json.loads(m.group(1))
        for k in ("players", "games", "outlets", "all_seasons", "game_seasons", "current"):
            self.assertIn(k, data)
        self.assertGreater(len(data["players"]), 100)


if __name__ == "__main__":
    unittest.main()
