"""A season's game scores (overrides/season_results.csv) agree with everything else known about that season.

For a season whose results are all in (as many games as its record in season_history.csv):
  - the wins and losses add up to that record;
and when every game also has both scores:
  - Bangor's points add up to the stat sheet's team points (the Team row in season_totals.csv),
  - the number of games matches the stat sheet's games,
  - points per game and points allowed per game match the record book (historical_records.csv), to the rounding.

A yearbook score list with a typo, opponents shifted by a row, or a game left off shows up here. A difference that
is known and can't be settled from the sources goes in KNOWN, with why, so the test stays green; once it's fixed,
the test says to take it out.
"""
import csv
import os
import unittest
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OV = os.path.join(ROOT, "overrides")

KNOWN = {
    ("1976-77", "record"): "The scores as printed give 8 wins; the book and the site say 7-13. Which score is a misprint isn't known.",
    ("1992-93", "points"): "The game scores add to 1,153; the stat sheet's players add to 1,139 (the record book's 54.2 a game).",
    ("1992-93", "ppg"): "Same 14 points as above: the record book's 54.2 a game comes from the stat sheet.",
    ("1993-94", "points"): "The game scores add to 1,314; the stat sheet's players add to 1,308.",
    ("1993-94", "ppg"): "The record book gives 57.4 a game; the game scores give 57.1 and the stat sheet 56.9.",
    ("1994-95", "ppg"): "The record book gives 50.4 a game; the game scores and the stat sheet both give 55.2.",
    ("1994-95", "opp_ppg"): "The record book gives 58.5 allowed a game; the game scores give 59.0.",
}


def load(name):
    with open(os.path.join(OV, name), newline="") as f:
        return list(csv.DictReader(f))


def result(g):
    if g["result"].strip():
        return g["result"].strip().upper()
    if g["bangor_score"] and g["opp_score"]:
        b, o = int(g["bangor_score"]), int(g["opp_score"])
        return "W" if b > o else "L" if b < o else "T"
    return ""


def mismatches():
    """(season, check) -> what doesn't agree, for every season the checks can cover."""
    games = defaultdict(list)
    for g in load("season_results.csv"):
        games[g["season"]].append(g)
    history = {h["season"]: h for h in load("season_history.csv")}
    team = {r["season"]: r for r in load("season_totals.csv") if r["name"].strip().lower() == "team"}
    book = {(r["season"], r["stat"]): float(r["value"]) for r in load("historical_records.csv")
            if r["scope"] == "team" and r["period"] == "season" and r["stat"] in ("ppg", "opp_ppg") and r["value"]}
    out = {}
    for s, gs in games.items():
        h = history.get(s)
        if not h or h["w"] == "":
            continue
        w, l, t = int(h["w"]), int(h["l"]), int(h["t"] or 0)
        n = len(gs)
        if n != w + l + t:
            continue  # not every result is in
        rw, rl = sum(result(g) == "W" for g in gs), sum(result(g) == "L" for g in gs)
        if (rw, rl) != (w, l):
            out[(s, "record")] = f"the results give {rw}-{rl}, the season's record is {w}-{l}"
        if not all(g["bangor_score"] and g["opp_score"] for g in gs):
            continue
        pts, opp = sum(int(g["bangor_score"]) for g in gs), sum(int(g["opp_score"]) for g in gs)
        sheet = team.get(s)
        if sheet and sheet.get("PTS"):
            if pts != int(sheet["PTS"]):
                out[(s, "points")] = f"the scores add to {pts}, the stat sheet says {sheet['PTS']}"
            if sheet.get("GP") and n != int(sheet["GP"]):
                out[(s, "games")] = f"{n} games in the results, {sheet['GP']} on the stat sheet"
        for stat, total in (("ppg", pts), ("opp_ppg", opp)):
            if (s, stat) in book and abs(total / n - book[(s, stat)]) > 0.051:
                out[(s, stat)] = f"the scores give {total / n:.2f} a game, the record book says {book[(s, stat)]}"
    return out


class SeasonScores(unittest.TestCase):
    def test_scores_agree(self):
        found = mismatches()
        for key, what in sorted(found.items()):
            if key not in KNOWN:
                with self.subTest(season=key[0], check=key[1]):
                    self.fail(f"{key[0]} {key[1]}: {what}")

    def test_known_still_differ(self):
        found = mismatches()
        for key in KNOWN:
            with self.subTest(season=key[0], check=key[1]):
                self.assertIn(key, found, "this now agrees: take it out of KNOWN")


if __name__ == "__main__":
    unittest.main()
