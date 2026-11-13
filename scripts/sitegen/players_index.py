"""Which players get a page: everyone in the stat sheets, plus players known only from rosters,
the record book and newspaper clippings (the archive players)."""
from sitegen.data import *  # noqa: F401,F403  (everything defined before this part of the build)


# ---------------------------------------------------------------- players
PLAYER_PAGES = {}
for slug_, rows in pg_by_player.items():
    PLAYER_PAGES[slug_] = rows[0]["name"]
for r in pseasons:
    PLAYER_PAGES.setdefault(r["slug"], r["name"])

# Players from before the stat sheets: known only from rosters (rosters.csv), the record book
# (historical_records.csv) and newspaper clippings of results-only games (newspaper_stats.csv). Each gets a
# shorter player page. A name with no first name or initial ("Schroeder") gets none, since it can't be told
# apart from another player of the same name.
ARCHIVE = OrderedDict()


def _season_span(a, b):
    return [f"{y}-{str(y + 1)[2:]}" for y in range(int(a[:4]), int(b[:4]) + 1)]


def _archive(name, sl=None):
    name = canon(name)
    sl = sl or slug(name)  # a roster line can carry its own page (overrides/same_names.csv)
    if not sl or sl in PLAYER_PAGES and sl not in ARCHIVE or len(name.split()) < 2:
        return None
    return ARCHIVE.setdefault(sl, {"slug": sl, "name": name, "roster": [], "book": [], "clips": [], "seasons": set(),
                                   "grad": None, "grad_how": ""})


for _s, _rs in ROSTERS.items():
    if _s == CURRENT:  # a new player on this season's roster gets a stat-sheet page once he plays, not an archive page
        continue
    for _r in _rs:
        _a = _archive(_r["name"], _r["slug"])
        if _a:
            _a["roster"].append(_r)
            _a["seasons"].add(_s)
            if _r["class_year"] and not _a["grad"]:
                _a["grad"], _a["grad_how"] = _r["class_year"], "grade"
for _h in hist_records:
    _a = _archive(_h["name"]) if _h["name"] else None
    if not _a:
        continue
    _a["book"].append(_h)
    _txt = f"{_h['season']} {_h['note']}"
    _cls = re.search(r"Class of (\d{4})", _txt)
    _rng = re.search(r"(\d{4}-\d{2}) to (\d{4}-\d{2})", _h["season"])
    if _cls and _a["grad_how"] != "book":
        _a["grad"], _a["grad_how"] = int(_cls.group(1)), "book"  # the record book's class year wins over a grade
    if _rng:
        _a["seasons"].update(_season_span(*_rng.groups()))
        if not _a["grad"]:
            _a["grad"], _a["grad_how"] = season_end_year(_rng.group(2)), "book"
    elif re.fullmatch(r"\d{4}-\d{2}", _h["season"]):
        _a["seasons"].add(_h["season"])
_ro_by_date = {g["date"]: g for gs in RESULTS_ONLY.values() for g in gs if g.get("date")}
if os.path.exists(os.path.join(OV, "newspaper_stats.csv")):
    for _r in load(os.path.join(OV, "newspaper_stats.csv")):
        _g = _ro_by_date.get(_r["date"])
        _a = _archive(_r["name"]) if _g and _r["team"].strip().lower() == "bangor" else None
        if _a:
            _a["clips"].append({"g": _g, **{k: num(_r.get(k)) for k in ("pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta",
                                                                          "reb", "ast", "blk")},
                                "number": _r.get("number", ""), "source": _r.get("source", "")})
            _a["seasons"].add(_g["season"])
for _sl, _a in ARCHIVE.items():
    PLAYER_PAGES[_sl] = _a["name"]

# Honors (overrides/honors.csv: season, name, honor, note): All-Conference picks, area and state honors, team
# awards and captains, from the coach's season summaries. Each links to the player's page for that season:
# the roster or stat-sheet player of that name, else a roster line with his initial ("L. Friell" for Lee Friell).
HONOR_GROUPS = [
    ("conf", ["All-Conference 1st team", "All-Conference 2nd team", "All-Conference", "All-Conference honorable mention"]),
    ("area", ["All-State honorable mention", "All-Coulee Region", "All-Coulee Region honorable mention", "All-tournament team"]),
    ("award", ["Most Valuable Player", "Offensive MVP", "Defensive MVP", "Best rebounder", "Best free-throw shooter",
               "Most improved", "Spirit award", "Sportsmanship award"]),
    ("captain", ["Captain"]),
]
HONOR_ORDER = {h: i for i, h in enumerate(h for _, hs in HONOR_GROUPS for h in hs)}
HONOR_GROUP = {h: g for g, hs in HONOR_GROUPS for h in hs}


def _honor_slug(season, name):
    for r in ROSTERS.get(season, []):
        if r["name"].strip() == name:
            return r["slug"]
    for r in pseasons:
        if r["season"] == season and r["name"] == name:
            return r["slug"]
    first, last = name.split()[0], name.split()[-1]
    initial = {r["slug"] for r in ROSTERS.get(season, []) if r["name"].strip() == f"{first[0]}. {last}"}
    if len(initial) == 1:  # two "T. Oliver"s that season: can't tell which, so his own page
        return initial.pop()
    sl = slug(name)
    return sl if sl in PLAYER_PAGES else None


HONORS = []
if os.path.exists(os.path.join(OV, "honors.csv")):
    for _r in load(os.path.join(OV, "honors.csv")):
        HONORS.append({**_r, "slug": _honor_slug(_r["season"], _r["name"].strip()),
                       "group": HONOR_GROUP.get(_r["honor"], "award"), "order": HONOR_ORDER.get(_r["honor"], 99)})
HONORS.sort(key=lambda h: (h["season"], h["order"]))
HONORS_BY_PLAYER, HONORS_BY_SEASON = defaultdict(list), defaultdict(list)
for _h in HONORS:
    HONORS_BY_SEASON[_h["season"]].append(_h)
    if _h["slug"]:
        HONORS_BY_PLAYER[_h["slug"]].append(_h)
