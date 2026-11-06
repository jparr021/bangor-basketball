"""CSV downloads (site/downloads/)."""
from sitegen.record_book import *  # noqa: F401,F403  (everything defined before this part of the build)


# ---------------------------------------------------------------- CSV downloads (site/downloads/)
DL_STATS = [("gp", "G"), ("pts", "PTS"), ("fgm", "FGM"), ("fga", "FGA"), ("tpm", "3PM"), ("tpa", "3PA"), ("ftm", "FTM"),
            ("fta", "FTA"), ("oreb", "OREB"), ("dreb", "DREB"), ("reb", "REB"), ("ast", "AST"), ("stl", "STL"),
            ("blk", "BLK"), ("to", "TO"), ("pf", "PF")]


def _dl_num(v):
    if v is None or v == "":
        return ""
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:.3f}".rstrip("0")


def _dl_write(name, header, rows):
    path = os.path.join(OUT, "downloads", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # the marker lets Excel read · and – correctly
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_downloads(sections):
    """Plain CSV files of the site's data, for anyone who wants to work with the numbers themselves.
    Blank = not recorded. FGM/FGA include 3-pointers."""
    site_word = {"home": "Home", "away": "Away", "neutral": "Neutral"}
    game_head = ["Season", "Date", "Opponent", "Site", "Type", "Result", "Bangor", "Opponent score", "OT", "Event, location or note"]

    def game_row(g):
        return [g["season"], g.get("date") or "", g["opponent"], site_word.get(g.get("site"), ""),
                (g.get("game_type") or "regular").capitalize(), g.get("result") or "", g.get("bangor_score") or "",
                g.get("opp_score") or "", g.get("ot") or "", g.get("event") or g.get("location") or g.get("note") or ""]

    every = [game_row(g) for g in games_by_id.values() if g["result"]]
    every += [game_row(g) for s, gs in RESULTS_ONLY.items() if s not in games_by_season for g in gs]
    every.sort(key=lambda r: r[0])  # by season; each season keeps its own game order
    _dl_write("bangor-games.csv", game_head, every)
    for s, gs in list(games_by_season.items()) + [(s, gs) for s, gs in RESULTS_ONLY.items() if s not in games_by_season]:
        rows = [game_row(g) for g in gs if g["result"]]
        if rows:
            _dl_write(f"{s}-games.csv", game_head, rows)

    ps_head = ["Season", "Player", "Number"] + [h for _, h in DL_STATS]
    allps = []
    for s in sorted(ps_by_season):
        rows = [[s, r["name"], r.get("number", "")] + [_dl_num(r.get(k)) for k, _ in DL_STATS]
                for r in sorted(ps_by_season[s], key=lambda r: -(r.get("pts") or 0))]
        allps += rows
        _dl_write(f"{s}-player-stats.csv", ps_head, rows)
    _dl_write("bangor-player-seasons.csv", ps_head, allps)

    box_stats = [k for k, _ in DL_STATS if k != "gp"]
    _dl_write("bangor-box-scores.csv", ["Season", "Date", "Opponent", "Player", "Number", "MIN"] + [h for k, h in DL_STATS if k != "gp"],
              [[r["season"], r["date"], r["opponent"], r["name"], r.get("number", ""), _dl_num(r.get("min"))]
               + [_dl_num(r.get(k)) for k in box_stats] for r in sorted(pg, key=lambda r: (r["date"], -(r["pts"] or 0)))])

    _dl_write("bangor-career-totals.csv", ["Player", "First season", "Last season", "Seasons"] + [h for _, h in DL_STATS]
              + ["Partial career", "Note"],
              [[c["name"], c["first_season"], c["last_season"], c["n_seasons"]] + [_dl_num(c.get(k)) for k, _ in DL_STATS]
               + ["Yes" if c.get("partial") == "Y" else "", c.get("override_note") or ""]
               for c in sorted(pcareers, key=lambda c: -(c.get("pts") or 0))])

    book = []
    for sec in sections.values():
        for c in sec["cats"]:
            for e in c["entries"]:
                g = games_by_id.get(e.get("game_id") or "")
                book.append([sec["scope"].capitalize(), {"game": "Single game"}.get(sec["period"], sec["period"].capitalize()),
                             c["title"], ("T-" if e["tied"] else "") + str(e["rank"]), e["display"], e.get("name") or "",
                             e.get("season") or (g or {}).get("season", ""), e.get("date") or (g or {}).get("date", ""),
                             e.get("opponent") or (g or {}).get("opponent", ""), e.get("detail") or "",
                             {"book": "Record book", "news": "Newspaper"}.get(e.get("source"), "Stat sheets")])
    _dl_write("bangor-record-book.csv", ["Scope", "Period", "Category", "Rank", "Value", "Player", "Season", "Date",
                                         "Opponent", "Detail", "Source"], book)
