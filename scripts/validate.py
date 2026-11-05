"""Check the converted data against the season totals recorded on each sheet.
Writes data/validation_report.md.  Run after convert.py.
"""
import csv, os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")


def load(name):
    with open(os.path.join(D, name)) as f:
        return list(csv.DictReader(f))


def n(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


games = load("games.csv")
pg = load("player_games.csv")
src = load("source_season_totals.csv")

# stat in player_games -> column name on the sheets' season tab
MAP = {"pts": "PTS", "fgm": "FGM", "fga": "FGA", "tpm": "3PM", "tpa": "3PA", "ftm": "FTM", "fta": "FTA",
       "reb": "REB", "oreb": "OFF", "dreb": "DEF", "ast": "AST", "to": "TO", "stl": "STL", "blk": "BLK",
       "pf": "PF"}

lines = ["# Validation report", ""]

# ---- season summary
lines += ["## Seasons", "",
          "| Season | Games | W-L | Box scores (full / points-only / none) | Box scores missing points |",
          "|---|---|---|---|---|"]
by_season = defaultdict(list)
for g in games:
    by_season[g["season"]].append(g)
for s in sorted(by_season):
    gs = by_season[s]
    w = sum(g["result"] == "W" for g in gs); l = sum(g["result"] == "L" for g in gs)
    full = sum(g["box_score"] == "full" for g in gs); pts = sum(g["box_score"] == "points" for g in gs)
    none = sum(g["box_score"] == "none" for g in gs)
    inc = sum(g["box_complete"] == "N" for g in gs)
    nr = sum(g["result"] == "" for g in gs)
    extra = f" ({nr} no result)" if nr else ""
    lines.append(f"| {s} | {len(gs)} | {w}-{l}{extra} | {full} / {pts} / {none} | {inc} |")

# ---- per-player season totals vs sheet season tabs
sums = defaultdict(lambda: defaultdict(float))
tracked = defaultdict(lambda: defaultdict(int))
gp = defaultdict(int)
added = {g["game_id"] for g in games if g.get("box_source") in ("printout", "newspaper")}
# Printouts replace some of a season's game tabs, so the sheet's season tab can't be checked against them
printout_seasons = {g["season"] for g in games if g.get("box_source") == "printout"}
for r in pg:
    if r["game_id"] in added:  # box scores typed in from other sources aren't on the sheet's season tab
        continue
    key = (r["season"], r["name"].strip().lower())
    gp[key] += 1
    for k in MAP:
        if r.get(k, "") != "":
            sums[key][k] += float(r[k]); tracked[key][k] += 1

lines += ["", "## Player season totals vs. the sheets' season tabs", "",
          "A check compares one player's season total for one stat. A match means the sum of the "
          "converted box-score rows equals the total on the sheet's own Player Stats tab (or the "
          "Totals tab for 2025-26).", "",
          "| Season | Checks | Match | Mismatch | Player on season tab but no box-score rows |",
          "|---|---|---|---|---|"]
detail = []
season_stats = defaultdict(lambda: [0, 0, 0])
for r in src:
    s, name = r["season"], r["name"].strip()
    key = (s, name.lower())
    if not name or s in printout_seasons:
        continue
    if key not in gp:
        season_stats[s][2] += 1
        detail.append(f"- {s} **{name}**: on the season tab, no box-score rows")
        continue
    for k, col in MAP.items():
        sv = n(r.get(col))
        if sv is None:
            continue
        if tracked[key][k] == 0:
            continue  # not in the game box scores (e.g. OFF/DEF only kept as season totals)
        mine = sums[key][k]
        if abs(mine - sv) < 0.01:
            season_stats[s][0] += 1
        else:
            season_stats[s][1] += 1
            detail.append(f"- {s} **{name}** {col}: sheet {sv:g}, converted {mine:g}")
    gpv = n(r.get("GP"))
    if gpv is not None and gpv != gp[key]:
        detail.append(f"- {s} **{name}** GP: sheet {gpv:g}, converted {gp[key]}")
for s in sorted(season_stats):
    a, b, c = season_stats[s]
    lines.append(f"| {s} | {a + b} | {a} | {b} | {c} |")

lines += ["", "### Mismatch detail", ""] + (detail or ["None."])

lines += ["", "## Games whose box score doesn't account for every point", ""]
for g in games:
    if g["box_complete"] == "N":
        lines.append(f"- {g['date']} vs {g['opponent']}: box score adds to {g['box_points']}, "
                     f"final {g['bangor_score']}")

with open(os.path.join(D, "validation_report.md"), "w") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines[:40]))
print(f"... {len(detail)} detail lines")
