"""Site-wide facts, the record book (computed records merged with the printed one), record badges
and the gaps list."""
from sitegen.players_index import *  # noqa: F401,F403  (everything defined before this part of the build)


# ---------------------------------------------------------------- site-wide facts
def history_totals():
    w = sum(int(h["w"] or 0) for h in history)
    l = sum(int(h["l"] or 0) for h in history)
    t = sum(int(h["t"] or 0) for h in history)
    return w, l, t


def count_note(word):
    return sum(1 for h in history if word.lower() in h["notes"].lower())


TITLE_RES = {  # what counts as each kind of title, from the record book's season notes
    "conf": re.compile(r"conference champion", re.I),
    "regional": re.compile(r"regional (tournament )?champion", re.I),
    "sectional": re.compile(r"sectional (tournament )?champion", re.I),
    "state": re.compile(r"state (champion|runner|semifinal|tour)", re.I),
}
coaches = OrderedDict()
COACH_OF = {}  # season -> coach slug
for h in history:
    c = h["coach"].strip()
    if not c:
        continue
    d = coaches.setdefault(c, {"name": c, "slug": slug(c), "w": 0, "l": 0, "t": 0, "seasons": [], "titles": 0,
                               "regional": 0, "sectional": 0, "state": 0})
    COACH_OF[h["season"]] = d["slug"]
    d["w"] += int(h["w"] or 0); d["l"] += int(h["l"] or 0); d["t"] += int(h["t"] or 0)
    d["seasons"].append(h["season"])
    if TITLE_RES["conf"].search(h["notes"]):
        d["titles"] += 1
    for k in ("regional", "sectional", "state"):
        if TITLE_RES[k].search(h["notes"]):
            d[k] += 1
for c in coaches.values():
    c["years"] = c["seasons"][0][:4] + ("–" + str(season_end_year(c["seasons"][-1])) if len(c["seasons"]) > 1 or True else "")
    g = c["w"] + c["l"] + c["t"]
    c["pct"] = f"{(c['w'] + 0.5 * c['t']) / g:.3f}".lstrip("0") if g else ""
coach_list = sorted(coaches.values(), key=lambda c: (-c["w"], c["l"]))
COACH_SLUGS = {c["name"]: c["slug"] for c in coach_list}

W, L, T = history_totals()
FACTS = {
    "w": W, "l": L, "t": T, "pct": f"{(W + 0.5 * T) / (W + L + T):.3f}".lstrip("0"),
    "seasons": len(history), "first": history[0]["season"][:4],
    "conf_titles": count_note("Conference Champions"),
    "state_titles": sum(1 for h in history if "state champion" in h["notes"].lower()),
    "regional_titles": sum(1 for h in history if re.search(r"regional (tournament )?champion", h["notes"].lower())),
    "streak": REC["team"]["streak"],
}


def season_span(seasons, open_end=True):
    """Seasons as page text: "1941–42, 1984–85 to 1997–98, 2001–02, 2002–03 and every season from 2007–08 on".
    Three or more seasons in a row are a range; a run that reaches last season (open_end) is "every season from ... on"."""
    runs = []
    for s in sorted(seasons):
        if runs and int(s[:4]) == int(runs[-1][-1][:4]) + 1:
            runs[-1].append(s)
        else:
            runs.append([s])
    lab = lambda s: s.replace("-", "–")
    parts = []
    for i, r in enumerate(runs):
        if open_end and i == len(runs) - 1 and len(r) > 1 and int(r[-1][:4]) >= int(CURRENT[:4]) - 1:
            parts.append(f"every season from {lab(r[0])} on")
        elif len(r) >= 3:
            parts.append(f"{lab(r[0])} to {lab(r[-1])}")
        else:
            parts.extend(lab(s) for s in r)
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1] if parts else ""


def _all_results_in(h):
    """True when every game of a past season has a known result (as many results as games in its record)."""
    exp = sum(int(h[k]) for k in ("w", "l", "t") if (h.get(k) or "").strip().isdigit())
    gs = [g for g in games_by_season[h["season"]] if g["result"]] if h["season"] in games_by_season \
        else RESULTS_ONLY.get(h["season"], [])
    return bool(exp) and len(gs) >= exp


# What the stat sheets and results cover, for the coverage notes on the list pages, so they stay right as seasons
# are added. "Stat sheets" are every season with player stats (season totals or game by game).
_sheet_seasons = sorted({r["season"] for r in pseasons})
FACTS.update({
    "sheets": season_span(_sheet_seasons),
    "sheets_before": season_span([s for s in _sheet_seasons if s < COVERED_FROM], open_end=False),
    "sheet_seasons": len(_sheet_seasons),
    "past_seasons": sum(1 for h in history if h["season"] != CURRENT),
    "all_results": sum(1 for h in history if h["season"] != CURRENT and _all_results_in(h)),
})

# ---------------------------------------------------------------- records (merge computed + record book)
CATS = [
    # (scope, period, stat, title, kind)   kind: int | pct | avg
    ("individual", "game", "pts", "Points", "int"),
    ("individual", "game", "reb", "Rebounds", "int"),
    ("individual", "game", "ast", "Assists", "int"),
    ("individual", "game", "stl", "Steals", "int"),
    ("individual", "game", "blk", "Blocks", "int"),
    ("individual", "game", "fgm", "Field goals made", "int"),
    ("individual", "game", "fga", "Field goals attempted", "int"),
    ("individual", "game", "tpm", "3-pointers made", "int"),
    ("individual", "game", "tpa", "3-pointers attempted", "int"),
    ("individual", "game", "ftm", "Free throws made", "int"),
    ("individual", "game", "fta", "Free throws attempted", "int"),
    ("individual", "game", "oreb", "Offensive rebounds", "int"),
    ("individual", "game", "dreb", "Defensive rebounds", "int"),
    ("individual", "season", "pts", "Points", "int"),
    ("individual", "season", "ppg", "Points per game", "avg"),
    ("individual", "season", "reb", "Rebounds", "int"),
    ("individual", "season", "ast", "Assists", "int"),
    ("individual", "season", "stl", "Steals", "int"),
    ("individual", "season", "blk", "Blocks", "int"),
    ("individual", "season", "tpm", "3-pointers made", "int"),
    ("individual", "season", "tpa", "3-pointers attempted", "int"),
    ("individual", "season", "ftm", "Free throws made", "int"),
    ("individual", "season", "fta", "Free throws attempted", "int"),
    ("individual", "season", "fg_pct", "Field goal %", "pct"),
    ("individual", "season", "tp_pct", "3-point %", "pct"),
    ("individual", "season", "ft_pct", "Free throw %", "pct"),
    ("individual", "season", "pf", "Fouls", "int"),
    ("individual", "career", "pts", "Points", "int"),
    ("individual", "career", "reb", "Rebounds", "int"),
    ("individual", "career", "ast", "Assists", "int"),
    ("individual", "career", "stl", "Steals", "int"),
    ("individual", "career", "blk", "Blocks", "int"),
    ("individual", "career", "tpm", "3-pointers made", "int"),
    ("individual", "career", "tpa", "3-pointers attempted", "int"),
    ("individual", "career", "ftm", "Free throws made", "int"),
    ("individual", "career", "fta", "Free throws attempted", "int"),
    ("individual", "career", "gp", "Games played", "int"),
    ("individual", "career", "fg_pct", "Field goal %", "pct"),
    ("individual", "career", "tp_pct", "3-point %", "pct"),
    ("individual", "career", "ft_pct", "Free throw %", "pct"),
    ("team", "game", "pts", "Points", "int"),
    ("team", "game", "margin", "Margin of victory", "int"),
    ("team", "game", "quarter_pts", "Points in a quarter", "int"),
    ("team", "game", "half_pts", "Points in a half", "int"),
    ("team", "game", "fewest_opp_pts", "Fewest points allowed", "int"),
    ("team", "game", "fgm", "Field goals made", "int"),
    ("team", "game", "fga", "Field goals attempted", "int"),
    ("team", "game", "fg_pct", "Field goal % (min. 30 att.)", "pct"),
    ("team", "game", "tpm", "3-pointers made", "int"),
    ("team", "game", "tpa", "3-pointers attempted", "int"),
    ("team", "game", "ftm", "Free throws made", "int"),
    ("team", "game", "fta", "Free throws attempted", "int"),
    ("team", "game", "reb", "Rebounds", "int"),
    ("team", "game", "oreb", "Offensive rebounds", "int"),
    ("team", "game", "dreb", "Defensive rebounds", "int"),
    ("team", "game", "ast", "Assists", "int"),
    ("team", "game", "stl", "Steals", "int"),
    ("team", "season", "wins", "Wins", "int"),
    ("team", "season", "win_pct", "Winning % (min. 10 games)", "pct"),
    ("team", "season", "ppg", "Points per game", "avg"),
    ("team", "season", "opp_ppg", "Fewest points allowed per game", "avg"),
    ("team", "season", "fg_pct", "Field goal %", "pct"),
    ("team", "season", "tpm", "3-pointers made", "int"),
    ("team", "season", "tpa", "3-pointers attempted", "int"),
    ("team", "season", "tp_pct", "3-point %", "pct"),
    ("team", "season", "ftm", "Free throws made", "int"),
    ("team", "season", "fta", "Free throws attempted", "int"),
    ("team", "season", "ft_pct", "Free throw %", "pct"),
    ("team", "season", "reb", "Rebounds", "int"),
    ("team", "season", "ast", "Assists", "int"),
    ("team", "season", "stl", "Steals", "int"),
    ("team", "season", "blk", "Blocks", "int"),
    ("team", "season", "games", "Games played", "int"),
]
LOWER_IS_BETTER = {("team", "game", "fewest_opp_pts"), ("team", "season", "opp_ppg")}
MINS = REC["minimums"]
MIN_NOTE = {
    ("individual", "season", "ppg"): f"Min. {MINS['season_ppg_gp']} games",
    ("individual", "season", "fg_pct"): f"Min. {MINS['season_fg']} attempts",
    ("individual", "season", "tp_pct"): f"Min. {MINS['season_tp']} attempts",
    ("individual", "season", "ft_pct"): f"Min. {MINS['season_ft']} attempts",
    ("individual", "career", "fg_pct"): f"Min. {MINS['career_fg']} attempts",
    ("individual", "career", "tp_pct"): f"Min. {MINS['career_tp']} attempts",
    ("individual", "career", "ft_pct"): f"Min. {MINS['career_ft']} attempts",
}


def team_season_rows_from_history():
    out = []
    for h in history:
        if h["w"] == "":
            continue
        w, l, t = int(h["w"]), int(h["l"]), int(h["t"] or 0)
        out.append({"season": h["season"], "w": w, "l": l, "t": t, "g": w + l + t})
    return out


def merged(scope, period, stat, kind):
    key = (scope, period, stat)
    reverse = key not in LOWER_IS_BETTER
    if scope == "team" and period == "season" and stat in ("wins", "win_pct"):
        rows = team_season_rows_from_history()
        if stat == "wins":
            entries = [{"value": r["w"], "season": r["season"], "detail": f"{r['w']}-{r['l']}" + (f"-{r['t']}" if r['t'] else "")}
                       for r in rows]
        else:
            entries = [{"value": (r["w"] + 0.5 * r["t"]) / r["g"], "season": r["season"], "detail": f"{r['w']}-{r['l']}"}
                       for r in rows if r["g"] >= 10]
    else:
        # a game mark whose box score is a newspaper clipping is labeled like one
        entries = [dict(e, source="news" if games_by_id.get(e.get("game_id") or "", {}).get("box_source") == "newspaper"
                        and not (scope == "team" and games_by_id[e["game_id"]]["date"] in TEAM_GAME) else "data")
                   for e in REC.get(scope, {}).get(period, {}).get(stat, [])]
    # record-book entries
    for h in hist_records:
        if (h["scope"], h["period"], h["stat"]) != key or h["value"] == "":
            continue
        # the same mark already worked out from the stats (a team mark has no name, so it matches on the season or date)
        # A career mark matches on the name alone: the book gives "Class of 1988", the stats "1985-86 to 1987-88".
        dup = any((e.get("name") or "") == (h["name"] or "") and
                  (period == "career" or (e.get("date") == h["date"] if h["date"] else e.get("season") == h["season"]))
                  for e in entries)
        if dup:
            continue
        entries.append({"value": float(h["value"]), "name": h["name"] or None, "player": slug(h["name"]) if h["name"] else None,
                        "date": h["date"] or None, "season": h["season"], "opponent": h["opponent"] or None,
                        "gp": int(h["gp"]) if h["gp"] else None, "detail": h["note"],
                        "source": "news" if (h.get("source") or "").strip().lower() == "newspaper" else "book"})
    entries.sort(key=lambda e: e["value"], reverse=reverse)
    out, rank, prev = [], 0, None
    for idx, e in enumerate(entries):
        if e["value"] != prev:
            rank = idx + 1
            if rank > 10:
                break
        prev = e["value"]
        e["rank"] = rank
        e["tied"] = False
        if kind == "pct":
            e["display"] = f"{100 * e['value']:.1f}%"
        elif kind == "avg":
            e["display"] = f"{e['value']:.1f}"
        else:
            e["display"] = fmt_int(e["value"])
        out.append(e)
    for i, e in enumerate(out):
        e["tied"] = any(o["rank"] == e["rank"] for j, o in enumerate(out) if j != i)
        if e.get("player") and e["player"] not in PLAYER_PAGES:
            e["player"] = None
        if e.get("game_id") and e["game_id"] not in games_by_id:
            e["game_id"] = None
    return out


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


BADGE_ABBR = {"pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK", "fgm": "FGM", "fga": "FGA",
              "tpm": "3PM", "tpa": "3PA", "ftm": "FTM", "fta": "FTA", "oreb": "OREB", "dreb": "DREB", "ppg": "PPG",
              "fg_pct": "FG%", "tp_pct": "3P%", "ft_pct": "FT%", "gp": "G", "margin": "MARGIN",
              "quarter_pts": "QTR PTS", "half_pts": "HALF PTS", "fewest_opp_pts": "OPP PTS", "wins": "WINS",
              "win_pct": "WIN%", "opp_ppg": "OPP PPG", "games": "G"}
NO_BADGE = {"pf"}  # in the record book, but not something to put a badge on


def partial_known(stat):
    """Players whose careers are only partly in the stat sheets (2001-02, 2002-03), with what is known for a
    counting stat: not ranked, but listed under the career lists as "at least". Skipped where the record book
    has the career total, since that one is ranked."""
    book = {slug(h["name"]) for h in hist_records if (h["scope"], h["period"], h["stat"]) == ("individual", "career", stat)
            and h["value"] and h["name"]}
    out = []
    for c in pcareers:
        v = c.get(stat)
        if c.get("partial") != "Y" or not v or c["slug"] in book:
            continue
        seasons = sorted(r["season"] for r in ps_by_player.get(c["slug"], []) if r.get(stat) is not None)
        if not seasons:
            continue
        span = (seasons[0].replace("-", "–") + " only") if len(seasons) == 1 else \
            ", ".join(s.replace("-", "–") for s in seasons) if len(seasons) == 2 else \
            f"{seasons[0][:4]}–{season_end_year(seasons[-1])}"
        out.append({"name": c["name"], "slug": c["slug"] if c["slug"] in PLAYER_PAGES else None, "value": v,
                    "display": fmt_int(v), "span": span})
    return sorted(out, key=lambda e: (-e["value"], e["name"]))


PARTIAL_STATS = {"pts", "reb", "ast", "stl", "blk", "tpm", "tpa", "ftm", "fta", "gp"}


def record_sections():
    sections = OrderedDict()
    for scope, period, stat, title, kind in CATS:
        entries = merged(scope, period, stat, kind)
        if not entries:
            continue
        partial = []
        if (scope, period) == ("individual", "career") and stat in PARTIAL_STATS:
            cutoff = min(e["value"] for e in entries) if len(entries) >= 10 else 0
            partial = [p for p in partial_known(stat) if p["value"] >= cutoff]
        sec = f"{scope}-{period}"
        sections.setdefault(sec, {"id": sec, "scope": scope, "period": period, "cats": []})
        sections[sec]["cats"].append({"title": title, "kind": kind, "entries": entries, "stat": stat,
                                      "note": MIN_NOTE.get((scope, period, stat), ""), "period": period, "scope": scope,
                                      "partial": partial})
    return sections


def collect_badges(sections):
    """Index every top-10 record-book entry by the game, season and player it belongs to."""
    out = {k: defaultdict(list) for k in ("game_ind", "game_team", "season_ind", "season_team", "player")}
    date_to_game = {}
    for g in games_by_id.values():
        date_to_game.setdefault(g["date"], g["game_id"])
    for sec in sections.values():
        scope, period = sec["scope"], sec["period"]
        for c in sec["cats"]:
            if c["stat"] in NO_BADGE:
                continue
            for e in c["entries"]:
                gid = e.get("game_id") or (date_to_game.get(e["date"]) if period == "game" and e.get("date") else None)
                b = {"rank": e["rank"], "place": ("T-" if e["tied"] else "") + ordinal(e["rank"]),
                     "title": c["title"], "abbr": BADGE_ABBR.get(c["stat"], c["title"]), "display": e["display"],
                     "period": period, "anchor": f"{sec['id']}-{c['stat']}", "season": e.get("season"),
                     "g": games_by_id.get(gid) if gid else None, "name": e.get("name"), "slug": e.get("player"),
                     "book": e.get("source") == "book", "news": e.get("source") == "news"}
                if scope == "team":
                    if period == "game" and gid:
                        out["game_team"][gid].append(b)
                    elif period == "season" and e.get("season"):
                        out["season_team"][e["season"]].append(b)
                    continue
                if not b["slug"]:
                    continue
                out["player"][b["slug"]].append(b)
                if period == "game" and gid:
                    out["game_ind"][(gid, b["slug"])].append(b)
                elif period == "season":
                    out["season_ind"][e["season"]].append(b)
    order = {"career": 0, "season": 1, "game": 2}
    for k, d in out.items():
        for v in d.values():
            v.sort(key=lambda b: ((order[b["period"]],) if k == "player" else ()) + (b["rank"], b["title"]))
    return out


def gaps_data():
    """What the site has for each season (results, box scores, player stats, roster, film), for the
    "Help fill in the gaps" page. Call after clipping_details(), which attaches newspaper details."""
    def cell(have, of, label=None):
        if not have:
            return {"level": "none", "text": "—"}
        if of and have >= of:
            return {"level": "full", "text": label or (f"All {of}" if of > 1 else "Yes")}
        return {"level": "part", "text": label or (f"{have} of {of}" if of else f"{have}")}

    rows = []
    for h in history:
        s = h["season"]
        if s == CURRENT:
            continue
        exp = sum(int(h[k]) for k in ("w", "l", "t") if (h.get(k) or "").strip().isdigit()) or None
        if s in games_by_season:
            gs = [g for g in games_by_season[s] if g["result"]]
            box = sum(1 for g in gs if g["box_score"] != "none" or g["date"] in TEAM_GAME)
            film = sum(1 for g in gs if g.get("has_video"))
        else:
            gs = RESULTS_ONLY.get(s, [])
            box = sum(1 for g in gs if g.get("leaders") or g.get("periods") or g.get("date") in TEAM_GAME)
            film = 0
        known = len(gs)
        of = exp or known
        per_game = any(pg_by_game.get(g["game_id"]) for g in games_by_season.get(s, []))
        totals = bool(ps_by_season.get(s))
        roster = len(ROSTERS.get(s, [])) or len(ps_by_season.get(s, []))
        r = {"season": s, "w": h["w"], "l": h["l"], "t": h["t"], "notes": h["notes"],
             "href": f"../seasons/{s}.html" if s in games_by_season or s in RESULTS_ONLY or s in ROSTERS else f"index.html#s{s}",
             "results": cell(known, of) if exp else ({"level": "part", "text": f"{known} games"} if known else cell(0, 0)),
             "box": cell(box, of),
             "stats": cell(2 if per_game else (1 if totals else 0), 2, "Game by game" if per_game else "Season totals"),
             "roster": cell(roster, 1, f"{roster} players"),
             "film": cell(film, of)}
        r["complete"] = all(r[k]["level"] == "full" for k in ("results", "box", "stats", "roster"))
        rows.append(r)
    big = re.compile(r"champion|state|sectional|regional|conference", re.I)
    wanted = [r for r in rows if big.search(r["notes"]) and r["results"]["level"] != "full"]
    n = len(rows)
    summary = {"n": n, "first": rows[0]["season"] if rows else "", "last": rows[-1]["season"] if rows else "",
               "results": sum(r["results"]["level"] == "full" for r in rows),
               "box": sum(r["box"]["level"] != "none" for r in rows),
               "stats": sum(r["stats"]["level"] != "none" for r in rows),
               "roster": sum(r["roster"]["level"] != "none" for r in rows),
               "film": sum(r["film"]["level"] != "none" for r in rows)}
    return rows, wanted, summary
