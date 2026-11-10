"""Compute season totals, career totals and the record book from data/*.csv.

Writes:
  data/player_seasons.csv  one row per player per season (season tab totals where the sheet has them,
                           otherwise summed from box scores)
  data/player_careers.csv  one row per player
  data/records.json        record lists (game / season / career, individual and team)
Run after convert.py.
"""
import csv, json, os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")

# Same person, different spelling in the sheets -> canonical name.
PLAYER_ALIASES = {
    "Konnor Kaiser": "Connor Kaiser",   # 2008-09 sheet; record book says Connor's 08-09 stats were missing
}

STATS = ["pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "to", "pf", "chg"]
SRC_COL = {"pts": "PTS", "fgm": "FGM", "fga": "FGA", "tpm": "3PM", "tpa": "3PA", "ftm": "FTM", "fta": "FTA",
           "oreb": "OFF", "dreb": "DEF", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK", "to": "TO",
           "pf": "PF"}
TOP = 10


def load(name):
    with open(os.path.join(D, name)) as f:
        return list(csv.DictReader(f))


def canon(name):
    name = name.strip()
    return PLAYER_ALIASES.get(name, name)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def i(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


games = {g["game_id"]: g for g in load("games.csv")}
pg = load("player_games.csv")
src = load("source_season_totals.csv")
# Season totals typed in from printed stat sheets for seasons without a spreadsheet season tab
# (overrides/season_totals.csv, same column names as the sheets' season tabs)
_ovst = os.path.join(ROOT, "overrides", "season_totals.csv")
# A row named "Team" is the sheet's printed team totals line (it includes players the sheet lumps together
# as "Other"); it is used for the team season records instead of adding up the players.
TEAM_TOTALS = {}
if os.path.exists(_ovst):
    with open(_ovst) as f:
        for r in csv.DictReader(f):
            if r["name"].strip().lower() == "team":
                TEAM_TOTALS[r["season"]] = r
            else:
                src.append(r)
# Bangor's team totals for games with no player box score (overrides/team_game_stats.csv)
TEAM_GAME = {}
_ovtg = os.path.join(ROOT, "overrides", "team_game_stats.csv")
if os.path.exists(_ovtg):
    with open(_ovtg) as f:
        for r in csv.DictReader(f):
            if r["team"].strip().lower() == "bangor":
                TEAM_GAME[r["date"]] = {k: num(r.get(k)) for k in STATS}
_ovsr = os.path.join(ROOT, "overrides", "season_results.csv")
RESULTS = defaultdict(list)
if os.path.exists(_ovsr):
    with open(_ovsr) as f:
        for r in csv.DictReader(f):
            RESULTS[r["season"]].append(r)

# ------------------------------------------------------------- player seasons
box = defaultdict(lambda: {"gp": 0, **{k: None for k in STATS}})
printout_seasons = set()  # (season, player) with a printout game
real_box = set()
for r in pg:
    key = (r["season"], canon(r["name"]))
    b = box[key]
    b["gp"] += 1
    b["number"] = r["number"]; b["class"] = r.get("class", "")
    # A full box score typed in from a printout (overrides/boxscores.csv) fills a game the season's sheet
    # has no stats for. It adds only points to the season, which the sheet's other games track: one game's
    # rebounds or shooting would read as a whole season's.
    if games.get(r["game_id"], {}).get("box_source") != "newspaper":
        real_box.add(key)  # a game with a real box score, not just a clipping's leading scorers
    printout = games.get(r["game_id"], {}).get("box_source") == "printout"
    if printout:
        printout_seasons.add(key)
    for k in STATS:
        v = num(r.get(k))
        if v is not None and not (printout and k != "pts"):
            b[k] = (b[k] or 0) + v

seasons = {}
for key, b in box.items():
    seasons[key] = {"season": key[0], "name": key[1], "number": b.get("number", ""), "gp": b["gp"],
                    **{k: b[k] for k in STATS}, "source": "box scores"}
for r in src:
    key = (r["season"], canon(r["name"]))
    s = seasons.setdefault(key, {"season": key[0], "name": key[1], "number": r["number"], "gp": None,
                                 **{k: None for k in STATS}})
    if r.get("number") and not s.get("number"):
        s["number"] = r["number"]
    used = False
    for k, col in SRC_COL.items():
        v = num(r.get(col))
        # a sheet's zero usually means a blank cell, but a zero made with shots attempted (0 of 7) is real
        tried = (num(r.get({"FGM": "FGA", "3PM": "3PA", "FTM": "FTA"}.get(col, ""))) or 0) > 0
        if v is None or (v == 0 and s.get(k) in (None, 0) and col not in ("PTS",) and not tried):
            continue
        if k == "pts" and key in printout_seasons:
            # The 2012-13 season tab is the sum of the game tabs, plus the Jan 8 game for only some players.
            # With the printouts, the box scores cover every game, so they give points and games played.
            continue
        if s.get(k) != v:
            used = True
        s[k] = v
    gp = num(r.get("GP"))
    if key in printout_seasons:
        gp = None
    if not gp and key not in real_box:
        s["gp"] = None  # the sheet gives no games played, and clippings cover only some games
    if gp:
        s["gp"] = gp if (s["gp"] is None or gp > s["gp"]) else s["gp"]
    if used:
        s["source"] = "season tab"

season_rows = sorted(seasons.values(), key=lambda s: (s["season"], -(s["pts"] or 0)))
# The stat sheets cover every season without a gap only from COVERED_FROM on. A career with a season
# before that (2002-03, typed in from a printed sheet) may include seasons with no stats at all, so it is
# marked partial: shown on the player's page, but kept out of the career records and leaderboards.
_with_stats = sorted({s["season"] for s in season_rows})
COVERED_FROM = _with_stats[-1] if _with_stats else ""
for s_ in reversed(_with_stats[:-1]):
    if int(s_[:4]) + 1 != int(COVERED_FROM[:4]):
        break
    COVERED_FROM = s_

# ------------------------------------------------------------- careers
careers = defaultdict(lambda: {"seasons": [], "gp": 0, **{k: None for k in STATS}})
for s in season_rows:
    c = careers[s["name"]]
    c["seasons"].append(s["season"])
    c["gp"] += s["gp"] or 0
    for k in STATS:
        if s[k] is not None:
            c[k] = (c[k] or 0) + s[k]
        else:
            c.setdefault("untracked", set()).add(k)
# Official totals from the record book where the stats sheets are known to be incomplete
# (overrides/career_totals.csv, maintained by hand).
overrides = defaultdict(dict)
ov_path = os.path.join(ROOT, "overrides", "career_totals.csv")
if os.path.exists(ov_path):
    with open(ov_path) as f:
        for r in csv.DictReader(f):
            overrides[r["name"].strip()][r["stat"].strip()] = r

career_rows = []
for name, c in careers.items():
    ss = sorted(c["seasons"])
    row = {"name": name, "first_season": ss[0], "last_season": ss[-1], "n_seasons": len(ss),
           "seasons": "|".join(ss), "gp": c["gp"] or "", **{k: c[k] for k in STATS}, "override_note": "",
           "_untracked": c.get("untracked", set())}
    notes = []
    for stat, ov in overrides.get(name, {}).items():
        row[stat] = float(ov["value"])
        if ov.get("games"):
            row["gp"] = float(ov["games"])
        notes.append(f"{stat}: {ov['source']} ({ov['note']})")
    row["override_note"] = "; ".join(notes)
    row["partial"] = "Y" if ss[0] < COVERED_FROM else ""
    career_rows.append(row)
career_rows.sort(key=lambda c: -(c["pts"] or 0))
career_full = [c for c in career_rows if not c["partial"]]


def write(path, rows):
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else i(v)) for k, v in r.items()})


write(os.path.join(D, "player_seasons.csv"), season_rows)
write(os.path.join(D, "player_careers.csv"), career_rows)


# ------------------------------------------------------------- record lists
# Each list keeps the top 25 (plus ties) so the site can merge in older record-book entries
# and still show a full top 10.
def top(rows, value, label, n=25, reverse=True):
    vals = [(value(r), r) for r in rows]
    vals = [(v, r) for v, r in vals if v is not None]
    vals.sort(key=lambda x: x[0], reverse=reverse)
    out = []
    for v, r in vals:
        if len(out) >= n and v != out[-1]["value"]:
            break
        # 6 places, so a percentage shown to one decimal isn't rounded twice (57-130 is 43.8%, not 43.9%)
        out.append({"value": round(v, 6) if isinstance(v, float) and not v.is_integer() else i(v), **label(r)})
    return out


def pct(m, a, minimum):
    def f(r):
        if r.get(a) is None or r.get(m) is None or r.get(a) < minimum:
            return None
        if a in r.get("_untracked", ()):  # career with seasons where this wasn't recorded
            return None
        return r[m] / r[a]
    return f


def detail(m, a):
    return lambda r: f"{i(r[m])}-{i(r[a])}"


def slug(name):
    import re
    s = name.lower().replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# Minimums for percentage records (same as the existing record book where it states one)
MIN = {"season_fg": 25, "season_tp": 75, "season_ft": 25, "career_fg": 100, "career_tp": 75, "career_ft": 100,
       "season_ppg_gp": 10}

game_label = lambda r: {"name": canon(r["name"]), "player": slug(canon(r["name"])), "date": r["date"],
                        "opponent": r["opponent"], "season": r["season"], "game_id": r["game_id"]}
season_label = lambda s: {"name": s["name"], "player": slug(s["name"]), "season": s["season"],
                          "gp": i(s["gp"]) if s["gp"] else None}
career_label = lambda c: {"name": c["name"], "player": slug(c["name"]),
                          "season": c["first_season"] if c["first_season"] == c["last_season"]
                          else f"{c['first_season']} to {c['last_season']}", "gp": i(c["gp"]) if c["gp"] else None}


def with_detail(label, fn):
    return lambda r: {**label(r), "detail": fn(r)}


pgn = [{**r, **{k: num(r[k]) for k in STATS}} for r in pg]
R = {"individual": {"game": {}, "season": {}, "career": {}}, "team": {"game": {}, "season": {}}}

for k in ["pts", "reb", "ast", "stl", "blk", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "dreb"]:
    R["individual"]["game"][k] = top(pgn, lambda r, k=k: r[k], game_label)
for k in ["pts", "reb", "ast", "stl", "blk", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "pf"]:
    R["individual"]["season"][k] = top(season_rows, lambda s, k=k: s[k], season_label)
for k in ["pts", "reb", "ast", "stl", "blk", "fgm", "fga", "tpm", "tpa", "ftm", "fta"]:
    R["individual"]["career"][k] = top(career_full, lambda c, k=k: c[k], career_label)
R["individual"]["season"]["ppg"] = top(
    season_rows, lambda s: s["pts"] / s["gp"] if s["gp"] and s["gp"] >= MIN["season_ppg_gp"] and s["pts"] else None,
    with_detail(season_label, lambda s: f"{i(s['pts'])} pts / {i(s['gp'])} G"))
R["individual"]["season"]["fg_pct"] = top(season_rows, pct("fgm", "fga", MIN["season_fg"]),
                                          with_detail(season_label, detail("fgm", "fga")))
R["individual"]["season"]["tp_pct"] = top(season_rows, pct("tpm", "tpa", MIN["season_tp"]),
                                          with_detail(season_label, detail("tpm", "tpa")))
R["individual"]["season"]["ft_pct"] = top(season_rows, pct("ftm", "fta", MIN["season_ft"]),
                                          with_detail(season_label, detail("ftm", "fta")))
R["individual"]["career"]["gp"] = top(career_full, lambda c: c["gp"], career_label)
R["individual"]["career"]["fg_pct"] = top(career_full, pct("fgm", "fga", MIN["career_fg"]),
                                          with_detail(career_label, detail("fgm", "fga")))
R["individual"]["career"]["tp_pct"] = top(career_full, pct("tpm", "tpa", MIN["career_tp"]),
                                          with_detail(career_label, detail("tpm", "tpa")))
R["individual"]["career"]["ft_pct"] = top(career_full, pct("ftm", "fta", MIN["career_ft"]),
                                          with_detail(career_label, detail("ftm", "fta")))

# ---- team games (counting stats only from complete box scores)
team_games = defaultdict(lambda: {k: 0.0 for k in STATS})
tracked = defaultdict(set)
for r in pgn:
    t = team_games[r["game_id"]]
    for k in STATS:
        if r[k] is not None:
            t[k] += r[k]; tracked[r["game_id"]].add(k)
# Games from the program's first seasons (1914-15 to 1916-17), when scores were in the teens and twenties, count in
# head-to-head records but not in the team scoring records.
RECORDS_FROM = "1930-31"
tg_rows = []
for gid, g in games.items():
    if g["season"] < RECORDS_FROM:
        continue
    row = {"game_id": gid, "season": g["season"], "date": g["date"], "opponent": g["opponent"],
           "pts": num(g["bangor_score"]), "opp_pts": num(g["opp_score"]),
           "margin": (num(g["bangor_score"]) - num(g["opp_score"])) if g["bangor_score"] else None,
           "quarter_pts": None, "half_pts": None}
    if g["bangor_periods"]:
        labs = g["period_labels"].split("|")
        vals = [num(x) for x in g["bangor_periods"].split("|")]
        reg = [v for l, v in zip(labs, vals) if v is not None and "OT" not in l.upper()]
        if reg:
            row["quarter_pts" if len(reg) >= 4 else "half_pts"] = max(reg)
    full = g["box_score"] == "full" and g["box_complete"] == "Y"
    for k in STATS:
        if k != "pts":
            row[k] = team_games[gid][k] if (k in tracked[gid] and full) else None
    tt = TEAM_GAME.get(g["date"]) if not full else None  # team totals from a yearbook (team_game_stats.csv)
    if tt:
        for k in STATS:
            if k != "pts" and tt.get(k) is not None:
                row[k] = tt[k]
    tg_rows.append(row)
tlabel = lambda r: {"date": r["date"], "opponent": r["opponent"], "season": r["season"], "game_id": r["game_id"]}
for k in ["pts", "margin", "quarter_pts", "half_pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "reb", "ast", "stl", "blk"]:
    R["team"]["game"][k] = top(tg_rows, lambda r, k=k: r[k], tlabel)
R["team"]["game"]["fewest_opp_pts"] = top(tg_rows, lambda r: r["opp_pts"], tlabel, reverse=False)
R["team"]["game"]["fg_pct"] = top(tg_rows, lambda r: r["fgm"] / r["fga"] if r.get("fga") and r["fga"] >= 30 else None,
                                  with_detail(tlabel, detail("fgm", "fga")))

# ---- team seasons
ts = defaultdict(lambda: {"w": 0, "l": 0, "pts": 0, "opp": 0, "g": 0})
for g in games.values():
    if g["season"] < RECORDS_FROM:
        continue
    t = ts[g["season"]]
    if g["result"] in ("W", "L"):
        t["w" if g["result"] == "W" else "l"] += 1
        t["pts"] += float(g["bangor_score"]); t["opp"] += float(g["opp_score"]); t["g"] += 1
for s in season_rows:
    for k in STATS:
        if k != "pts" and s[k] is not None:
            ts[s["season"]][k] = ts[s["season"]].get(k, 0) + s[k]
for season, r in TEAM_TOTALS.items():
    t = ts[season]
    for k, col in SRC_COL.items():
        if k != "pts" and num(r.get(col)) is not None:
            t[k] = num(r.get(col))
    rs = RESULTS.get(season, [])
    # a results-only season: record and scoring from its results, when every game's score is known
    if not t["g"] and rs and len(rs) == num(r.get("GP")) and all(g["bangor_score"] and g["opp_score"] for g in rs):
        for g in rs:
            b, o = float(g["bangor_score"]), float(g["opp_score"])
            t["w" if b > o else "l"] += 1
            t["pts"] += b; t["opp"] += o; t["g"] += 1
ts_rows = [{"season": k, **v} for k, v in ts.items()]
sl = lambda r: {"season": r["season"], "detail": f"{r['w']}-{r['l']}"}
R["team"]["season"]["ppg"] = top(ts_rows, lambda r: r["pts"] / r["g"] if r["g"] else None, sl)
R["team"]["season"]["opp_ppg"] = top(ts_rows, lambda r: r["opp"] / r["g"] if r["g"] else None, sl, reverse=False)
for k in ["tpm", "tpa", "ftm", "fta", "reb", "ast", "stl", "blk"]:
    R["team"]["season"][k] = top(ts_rows, lambda r, k=k: r.get(k), sl)
R["team"]["season"]["fg_pct"] = top(ts_rows, lambda r: r["fgm"] / r["fga"] if r.get("fga") else None,
                                    lambda r: {"season": r["season"], "detail": f"{i(r['fgm'])}-{i(r['fga'])}"})
R["team"]["season"]["tp_pct"] = top(ts_rows, lambda r: r["tpm"] / r["tpa"] if r.get("tpa") else None,
                                    lambda r: {"season": r["season"], "detail": f"{i(r['tpm'])}-{i(r['tpa'])}"})
R["team"]["season"]["ft_pct"] = top(ts_rows, lambda r: r["ftm"] / r["fta"] if r.get("fta") else None,
                                    lambda r: {"season": r["season"], "detail": f"{i(r['ftm'])}-{i(r['fta'])}"})
R["team"]["season"]["games"] = top(ts_rows, lambda r: r["g"], sl)

# ---- winning streak (data era)
best, cur, start = (0, None, None), 0, None
for g in sorted(games.values(), key=lambda g: g["date"]):
    if g["result"] == "W":
        cur += 1; start = start or g
        if cur > best[0]:
            best = (cur, start, g)
    elif g["result"] == "L":
        cur, start = 0, None
R["team"]["streak"] = {"wins": best[0], "from": best[1]["date"], "to": best[2]["date"]}
R["minimums"] = MIN

with open(os.path.join(D, "records.json"), "w") as f:
    json.dump(R, f, indent=1)
print(f"player_seasons={len(season_rows)} careers={len(career_rows)} win_streak={best[0]}")
