""""On this day" on the home page: games and record nights from today's date in past seasons."""
from sitegen.downloads import *  # noqa: F401,F403  (everything defined before this part of the build)


# ---------------------------------------------------------------- "On this day" (home page)
# Every dated game and record-book game mark, by month and day. The home page picks today's (in Wisconsin
# time) in the visitor's browser, so it stays right between rebuilds and all summer.
OTD = defaultdict(list)


def otd_add(date, weight, text, url):
    if date and text:
        OTD[date[5:]].append([int(date[:4]), weight, str(Markup(text).unescape()) if isinstance(text, Markup) else text, url])


def otd_game(g, url, text, badges):
    """A finished game: its short summary, weighted so playoff games and record nights come first."""
    if g.get("result") not in ("W", "L") or not g.get("date"):
        return
    ev = (g.get("event") or "").lower()
    w = 1 + (g["result"] == "W")
    w += 3 if g.get("game_type") == "playoff" else 0
    w += 2 if g.get("game_type") == "playoff" and ("final" in ev or "state" in ev) else 0
    w += 1 if g.get("ot") else 0
    w += 1 if g.get("bs") is not None and abs(g["bs"] - g["os"]) >= 30 else 0
    w += 1 if g["date"] < "2007" else 0  # older games are rarer
    # only marks the summary can name (points, rebounds, assists ...), so the weight matches the text
    top = min((b["rank"] for b in badges if b["anchor"].rsplit("-", 1)[-1] in recaps.STAT_NOUN), default=None)
    w += 0 if top is None else (6 if top == 1 else 4 if top <= 3 else 2 if top <= 5 else 0)
    otd_add(g["date"], w, text, url)


_OTD_VERB = {"pts": ("scored", "points"), "reb": ("had", "rebounds"), "ast": ("had", "assists"), "stl": ("had", "steals"),
             "blk": ("had", "blocks"), "tpm": ("made", "3-pointers"), "fgm": ("made", "field goals"), "ftm": ("made", "free throws")}


def otd_records(sections, dated_games):
    """Record-book game marks from games with no page of their own (mostly before the stat sheets).
    One per player per night: the highest-ranked (points first on a tie)."""
    best = {}
    for sec in sections.values():
        if sec["scope"] != "individual" or sec["period"] != "game":
            continue
        for c in sec["cats"]:
            if c["stat"] not in _OTD_VERB:
                continue
            verb, noun = _OTD_VERB[c["stat"]]
            for e in c["entries"]:
                d = e.get("date")
                if not d or not e.get("name") or e["rank"] > 5 or e.get("game_id") or d in dated_games:
                    continue
                place = {1: "the most", 2: "the second-most", 3: "the third-most", 4: "the fourth-most", 5: "the fifth-most"}[e["rank"]]
                text = (f"{e['name']} {verb} {e['display']} {noun}{' against ' + e['opponent'] if e.get('opponent') else ''}, "
                        f"{'tied for ' if e['tied'] else ''}{place} in a game in Bangor history.")
                key, rank = (d, e["name"]), (e["rank"], list(_OTD_VERB).index(c["stat"]))
                if key not in best or rank < best[key][0]:
                    best[key] = (rank, d, 3 + (6 if e["rank"] == 1 else 4 if e["rank"] <= 3 else 2), text,
                                 f"records/index.html#{sec['id']}-{c['stat']}")
    for _, d, w, text, url in best.values():
        otd_add(d, w, text, url)


def write_otd(sections):
    dated = {}
    for s_, gs in RESULTS_ONLY.items():
        if s_ in games_by_season:
            continue
        for g in gs:
            if g.get("date") and g.get("scored"):
                dated[g["date"]] = True
                otd_game(g, f"seasons/{s_}.html#g{g['anchor']}", recaps.write(g, [], [], [], [], False, link=False, short=True), [])
    dated.update({g["date"]: True for g in games_by_id.values()})
    otd_records(sections, dated)
    for v in OTD.values():
        v.sort(key=lambda it: (-it[1], -it[0]))
    with open(os.path.join(OUT, "static", "on-this-day.js"), "w") as f:
        f.write("window.BANGOR_OTD=" + json.dumps(OTD, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + ";\n")
