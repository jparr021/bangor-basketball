"""What the pages show: season summaries, leaders, head-to-head, previews, charts, coaches, classes
and season leaders."""
from sitegen.render import *  # noqa: F401,F403  (everything defined before this part of the build)


def season_summary(season):
    gs = [g for g in games_by_season.get(season, []) if g["result"] in ("W", "L")] or RESULTS_ONLY.get(season, [])
    h = hist_by_season.get(season, {})
    sc = [g for g in gs if g.get("scored", True)]  # results-only games can be missing a score
    # the current season before its first result: show when it starts, not 0-0
    started = season != CURRENT or bool(gs)
    sched = sorted(g["date"] for g in games_by_season.get(season, []) if g.get("date"))
    return {
        "started": started, "starts": "" if started or not sched else sched[0],
        "season": season, "w": h.get("w", ""), "l": h.get("l", ""), "t": h.get("t", ""),
        "coach": h.get("coach", ""), "notes": h.get("notes", ""),
        "has_data": season in games_by_season or season in RESULTS_ONLY,
        "results_only": season in RESULTS_ONLY and season not in games_by_season,
        "ppg": fmt_avg(sum(g["bs"] for g in sc), len(sc)) if sc else "",
        "oppg": fmt_avg(sum(g["os"] for g in sc), len(sc)) if sc else "",
    }


def leaders(season, n=1):
    rows = ps_by_season.get(season, [])
    out = []
    for k, label in [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"), ("stl", "Steals")]:
        cands = [r for r in rows if r.get(k)]
        if not cands:
            continue
        best = max(cands, key=lambda r: r[k])
        out.append({"label": label, "name": best["name"], "slug": best["slug"], "value": fmt_int(best[k]),
                    "avg": fmt_avg(best[k], best["gp"])})
    return out


UPCOMING_ON_HOME = 4  # one full row of cards on a computer, two rows of two on a tablet


def preseason(season):
    """The home page's season card before the first game is played: the first game and a countdown to it,
    last season's record and leaders, and the players coming back."""
    first = next((g for g in games_by_season.get(season, []) if g["status"] == "upcoming"), None)
    prev = next((s for s in reversed(DATA_SEASONS) if s < season and ps_by_season.get(s)), None)
    out = {"first": first, "days": (dt.date.fromisoformat(first["date"]) - TODAY).days if first else None,
           "prev": season_summary(prev) if prev else None, "prev_leaders": leaders(prev)[:3] if prev else [],
           "returning": []}
    if prev:
        end = season_end_year(prev)
        for r in sorted(ps_by_season[prev], key=lambda r: -((r.get("pts") or 0) / (r.get("gp") or 1))):
            year, _ = grad_year(r["slug"])
            if year and year > end and r.get("gp"):
                out["returning"].append({"name": r["name"], "slug": r["slug"], "grad": year,
                                         "ppg": fmt_avg(r.get("pts"), r["gp"]), "rpg": fmt_avg(r.get("reb"), r["gp"])})
        out["returning_n"] = len(out["returning"])
        out["returning"] = out["returning"][:5]
    return out


def wl(gs):
    w = sum(g["result"] == "W" for g in gs)
    return {"w": w, "l": sum(g["result"] == "L" for g in gs), "n": len(gs)}


def streaks(gs):
    """(current streak like 'W3', longest winning streak) over finished games in date order."""
    cur_kind, cur_n, best, run = "", 0, 0, 0
    for g in gs:
        r = g["result"]
        cur_n = cur_n + 1 if r == cur_kind else 1
        cur_kind = r
        run = run + 1 if r == "W" else 0
        best = max(best, run)
    return (f"{cur_kind}{cur_n}" if cur_kind else ""), best


def margin_items(gs, xlabel, label_extremes=True):
    """Chart items for margin_chart: one per finished game, with the running record in the tooltip."""
    items, w, l = [], 0, 0
    for g in gs:
        w += g["result"] == "W"
        l += g["result"] == "L"
        m = int(g["bs"] - g["os"])
        tip = (f"{'+' if m > 0 else ('−' if m < 0 else '')}{abs(m)} · {g['result']} {g['bangor_score']}–{g['opp_score']}{' (OT)' if g['ot'] else ''}\n"
               f"{'at' if g['site'] == 'away' else 'vs'} {g['opponent']}, {fmt_date(g['date'])}")
        items.append({"margin": m, "tip": tip, "record": f"{w}–{l}", "href": g.get("href") or f"../games/{g['game_id']}.html",
                      "xlabel": xlabel(g, items[-1] if items else None), "g": g})
    if label_extremes and items:
        hi = max(items, key=lambda i: i["margin"])
        lo = min(items, key=lambda i: i["margin"])
        for it in (hi, lo):
            it["label"] = True
    return items


def month_label(g, prev):
    m = g["date"][5:7]
    return "" if prev and prev["g"]["date"][5:7] == m else dt.date.fromisoformat(g["date"]).strftime("%b")


def season_label_x(g, prev):
    s = g["season"]
    return "" if prev and prev["g"]["season"] == s else "’" + s[5:7]


def head_to_head(o):
    """Everything on an opponent page beyond the list of games."""
    gs = o["games"]
    cur, best = streaks(gs)
    out = {"streak": cur, "best_streak": best}
    out["splits"] = [(label, wl([g for g in gs if test(g)])) for label, test in [
        ("Home", lambda g: g["site"] == "home"), ("Away", lambda g: g["site"] == "away"),
        ("Neutral", lambda g: g["site"] == "neutral"), ("Playoffs", lambda g: g["game_type"] == "playoff")]]
    out["splits"] = [s for s in out["splits"] if s[1]["n"]]
    if gs:
        out["ppg"] = fmt_avg(sum(g["bs"] for g in gs), len(gs))
        out["oppg"] = fmt_avg(sum(g["os"] for g in gs), len(gs))
        margin = sum(g["bs"] - g["os"] for g in gs) / len(gs)
        out["margin"] = f"{'+' if margin > 0 else ''}{margin:.1f}"
        wins = [g for g in gs if g["result"] == "W"]
        losses = [g for g in gs if g["result"] == "L"]
        out["biggest_win"] = max(wins, key=lambda g: (g["bs"] - g["os"], g["date"])) if wins else None
        out["worst_loss"] = max(losses, key=lambda g: (g["os"] - g["bs"], g["date"])) if losses else None
        # by coach, for the coaches who've faced them most
        by_coach = OrderedDict()
        for g in gs:
            c = hist_by_season.get(g["season"], {}).get("coach", "")
            if c:
                by_coach.setdefault(c, []).append(g)
        out["coaches"] = [{"name": c, "slug": slug(c), **wl(v)} for c, v in by_coach.items()]
        out["chart"] = charts.margin_chart(margin_items(gs, season_label_x),
                                           f"Bangor's scoring margin in each game against {o['name']}")
    # Bangor players against them
    ids = {g["game_id"] for g in gs}
    rows = [r for gid in sorted(ids, key=str) for r in pg_by_game.get(gid, []) if r.get("pts") is not None]  # sorted: ties go to the earliest game
    agg = {}
    for r in rows:
        a = agg.setdefault(r["slug"], {"name": r["name"], "slug": r["slug"], "pts": 0, "gp": 0, "best": None})
        a["pts"] += r["pts"]; a["gp"] += 1
        if a["best"] is None or r["pts"] > a["best"]["pts"]:
            a["best"] = r
    top = sorted(agg.values(), key=lambda a: (-a["pts"], a["name"]))[:8]
    out["scorers"] = [{**a, "pts": fmt_int(a["pts"]), "avg": fmt_avg(a["pts"], a["gp"]), "best_pts": fmt_int(a["best"]["pts"]),
                       "best_g": games_by_id[a["best"]["game_id"]]} for a in top if a["pts"]]
    out["bangor_games"] = [{"name": r["name"], "slug": r["slug"], "pts": fmt_int(r["pts"]), "g": games_by_id[r["game_id"]]}
                           for r in sorted(rows, key=lambda r: (-r["pts"], r["date"]))[:5] if r["pts"]]
    # their players against Bangor
    orows = [r for gid in ids for r in opg_by_game.get(gid, []) if r.get("pts") is not None]
    out["opp_games"] = [{"name": r["name"], "pts": fmt_int(r["pts"]), "g": games_by_id[r["game_id"]]}
                        for r in sorted(orows, key=lambda r: (-r["pts"], r["date"]))[:5] if r["pts"]]
    oagg = {}
    for r in orows:
        a = oagg.setdefault(slug(r["name"]), {"name": r["name"], "pts": 0, "gp": 0, "seasons": set()})
        a["pts"] += r["pts"]; a["gp"] += 1; a["seasons"].add(r["season"])
    out["opp_scorers"] = [{"name": a["name"], "pts": fmt_int(a["pts"]), "gp": a["gp"], "avg": fmt_avg(a["pts"], a["gp"]),
                           "years": (lambda s: s[0][:4] + "–" + str(season_end_year(s[-1])))(sorted(a["seasons"]))}
                          for a in sorted(oagg.values(), key=lambda a: (-a["pts"], a["name"]))[:5] if a["pts"] and a["gp"] > 1]
    return out


def opponent_index():
    """Every opponent, with its finished games (date order) and upcoming games."""
    opps = OrderedDict()
    for g in sorted(list(games_by_id.values()) + DATED_RESULTS, key=lambda g: g["date"]):
        o = opps.setdefault(g["opp_slug"], {"name": g["opponent"], "slug": g["opp_slug"], "w": 0, "l": 0, "games": [],
                                            "upcoming": []})
        if g["result"] in ("W", "L"):
            o["w" if g["result"] == "W" else "l"] += 1
            o["games"].append(g)
        elif g.get("status") == "upcoming":
            o["upcoming"].append(g)
    return opps


def current_roster(g):
    """Player slugs on Bangor's roster for a game not yet played: whoever has played earlier that season, or before
    the first game, last season's players who haven't graduated."""
    season = g["season"]
    played = {r["slug"] for x in games_by_season.get(season, []) if x["date"] < g["date"]
              for r in pg_by_game.get(x["game_id"], [])}
    if played:
        return played
    earlier = [s for s in DATA_SEASONS if s < season]
    if not earlier:
        return set()
    end = season_end_year(season)
    return {r["slug"] for r in ps_by_season.get(earlier[-1], []) if (grad_year(r["slug"])[0] or 0) >= end}


def game_preview(g, o):
    """Head-to-head preview for a game that hasn't been played (or whose score isn't in yet)."""
    prior = [x for x in (o["games"] if o else []) if x["date"] < g["date"]]
    season_done = [x for x in games_by_season.get(g["season"], []) if x["date"] < g["date"] and x["result"] in ("W", "L")]
    out = {"n": len(prior), "season_rec": wl(season_done) if season_done else None,
           "since": min([DATA_SEASONS[0]] + [x["season"] for x in DATED_RESULTS])}
    if not prior:
        return out
    rec = wl(prior)
    cur, _ = streaks(prior)
    out.update(rec=rec, first=prior[0], streak=cur)
    site_games = [x for x in prior if x["site"] == g["site"]]
    out["site_rec"] = wl(site_games) if site_games and len(site_games) < len(prior) else None
    out["site_label"] = {"away": "On the road", "neutral": "At neutral sites"}.get(g["site"], "At home")
    if g["game_type"] == "playoff":
        po = [x for x in prior if x["game_type"] == "playoff"]
        out["playoff_rec"] = wl(po) if po else None
    out["this_season"] = [x for x in prior if x["season"] == g["season"]]
    last = prior[-1]
    top = max((r for r in pg_by_game.get(last.get("game_id"), []) if r.get("pts")), key=lambda r: r["pts"], default=None)
    out["last"] = {"g": last, "top": top and {"name": top["name"], "slug": top["slug"], "pts": fmt_int(top["pts"])}}
    wins = [x for x in prior if x["result"] == "W"]
    losses = [x for x in prior if x["result"] == "L"]
    out["biggest_win"] = max(wins, key=lambda x: (x["bs"] - x["os"], x["date"])) if wins else None
    out["worst_loss"] = max(losses, key=lambda x: (x["os"] - x["bs"], x["date"])) if losses else None
    for k in ("biggest_win", "worst_loss"):  # already shown as the last meeting
        if out[k] is last:
            out[k] = None
    out["ppg"] = fmt_avg(sum(x["bs"] for x in prior), len(prior))
    out["oppg"] = fmt_avg(sum(x["os"] for x in prior), len(prior))
    # current Cardinals' history against this opponent
    roster = current_roster(g)
    ids = {x.get("game_id") for x in prior}
    agg = {}
    for gid in sorted(ids, key=str):  # sorted: ties go to the earliest game
        for r in pg_by_game.get(gid, []):
            if r["slug"] not in roster or r.get("pts") is None:
                continue
            a = agg.setdefault(r["slug"], {"name": r["name"], "slug": r["slug"], "pts": 0, "gp": 0, "best": None})
            a["pts"] += r["pts"]; a["gp"] += 1
            if a["best"] is None or r["pts"] > a["best"]["pts"]:
                a["best"] = r
    out["players"] = [{**a, "pts": fmt_int(a["pts"]), "avg": fmt_avg(a["pts"], a["gp"]), "best_pts": fmt_int(a["best"]["pts"]),
                       "best_g": games_by_id[a["best"]["game_id"]]}
                      for a in sorted(agg.values(), key=lambda a: (-a["pts"], a["name"]))[:6]]
    return out


def season_charts(season, gs):
    """The game-by-game margin chart and per-player scoring lines for a season page."""
    played = [g for g in gs if g["result"] in ("W", "L") and g["bs"] is not None]
    items = margin_items(played, month_label)
    for it in items:
        it["tip"] += f"\nRecord: {it['record']}"
    margin = charts.margin_chart(items, f"Bangor's scoring margin in each {season} game") if len(items) >= 2 else ""
    # top scorers with a box score in most games
    by_player = defaultdict(dict)
    for g in played:
        for r in pg_by_game.get(g["game_id"], []):
            if r.get("pts") is not None:
                by_player[r["slug"]][g["game_id"]] = r
    lines = []
    ranked = [kv for kv in sorted(by_player.items(), key=lambda kv: -sum(r["pts"] for r in kv[1].values()))[:6]
              if len(kv[1]) >= 3]
    top = max([r["pts"] for _, rows in ranked for r in rows.values()] + [10])
    ymax = math.ceil(top / 10) * 10
    for sl, rows in ranked:
        if len(rows) < 3:
            continue
        name = next(iter(rows.values()))["name"]
        total = sum(r["pts"] for r in rows.values())
        pts = []
        for g in played:
            r = rows.get(g["game_id"])
            v = r["pts"] if r else None
            tip = (f"{fmt_int(v)} pts" if r else "Did not play") + \
                  f"\n{'at' if g['site'] == 'away' else 'vs'} {g['opponent']}, {fmt_date(g['date'])}"
            pts.append({"v": v, "tip": tip, "href": f"../games/{g['game_id']}.html"})
        avg = total / len(rows)
        lines.append({"name": name, "slug": sl, "gp": len(rows), "avg": f"{avg:.1f}",
                      "high": fmt_int(max(r["pts"] for r in rows.values())),
                      "svg": charts.game_line(pts, avg, f"{name}'s points in each {season} game", ymax)})
    return margin, [l for l in lines if l["svg"]]


def coach_page_data(c):
    seasons = [season_summary(s) for s in c["seasons"]]
    for s in seasons:
        g = int(s["w"] or 0) + int(s["l"] or 0) + int(s["t"] or 0)
        s["pct"] = (int(s["w"] or 0) + 0.5 * int(s["t"] or 0)) / g if g else None
        s["pct_txt"] = f"{s['pct']:.3f}".lstrip("0") if s["pct"] is not None else ""
    data_gs = [g for s in c["seasons"] for g in games_by_season.get(s, []) if g["result"] in ("W", "L")]
    playoff = wl([g for g in data_gs if g["game_type"] == "playoff"])
    best = max((s for s in seasons if s["pct"] is not None and int(s["w"] or 0) + int(s["l"] or 0) >= 8),
               key=lambda s: (s["pct"], int(s["w"] or 0)), default=None)
    # players: points scored in this coach's seasons
    agg = {}
    for s in c["seasons"]:
        for r in ps_by_season.get(s, []):
            if not r.get("pts"):
                continue
            a = agg.setdefault(r["slug"], {"name": r["name"], "slug": r["slug"], "pts": 0, "gp": 0, "seasons": []})
            a["pts"] += r["pts"]; a["gp"] += r.get("gp") or 0; a["seasons"].append(s)
    players = [{**a, "pts": fmt_int(a["pts"]), "avg": fmt_avg(a["pts"], a["gp"]),
                "years": a["seasons"][0][:4] + "–" + str(season_end_year(a["seasons"][-1]))}
               for a in sorted(agg.values(), key=lambda a: -a["pts"])[:10]]
    # most-played opponents
    opp = defaultdict(list)
    for g in data_gs:
        opp[g["opponent"]].append(g)
    opps = [{"name": k, "slug": slug(k), **wl(v)} for k, v in sorted(opp.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:8]]
    chart_items = [{"pct": s["pct"], "xlabel": "’" + s["season"][5:7] if len(seasons) <= 16 or i % 2 == 0 else "",
                    "href": f"../seasons/{s['season']}.html" if s["has_data"] else "",
                    "tip": f"{s['pct_txt']} · {s['w']}–{s['l']}{('–' + s['t']) if s['t'] else ''}\n"
                           f"{s['season'].replace('-', '–')}" + (f"\n{s['notes']}" if s["notes"] else "")}
                   for i, s in enumerate(seasons)]
    chart = charts.pct_columns(chart_items, f"{c['name']}'s winning percentage each season") if len(seasons) >= 2 else ""
    return {"seasons": seasons, "playoff": playoff, "best": best, "players": players, "opps": opps, "chart": chart,
            "data_games": len(data_gs)}


# ---------------------------------------------------------------- graduating classes
CLASS_OFFSET = {"SR": 0, "JR": 1, "SO": 2, "FR": 3, "12": 0, "11": 1, "10": 2, "9": 3}
GRAD_OVERRIDES = {}  # overrides/grad_years.csv: name,grad_year,note — fixes for estimated years
_gpath = os.path.join(OV, "grad_years.csv")
if os.path.exists(_gpath):
    for r in load(_gpath):
        if r.get("name") and (r.get("grad_year") or "").strip().isdigit():
            GRAD_OVERRIDES[slug(canon(r["name"]))] = int(r["grad_year"])


def grad_year(sl):
    """(year, how): from overrides, from the class column (SR/JR/...), or estimated from the last season played."""
    if sl in GRAD_OVERRIDES:
        return GRAD_OVERRIDES[sl], "set"
    for r in sorted(pg_by_player.get(sl, []), key=lambda r: r["date"], reverse=True):
        off = CLASS_OFFSET.get((r.get("class") or "").strip().upper())
        if off is not None:
            return season_end_year(r["season"]) + off, "class"
    for h in hist_records:
        m = re.search(r"Class of (\d{4})", f"{h['season']} {h['note']}")
        if m and h["name"] and slug(h["name"]) == sl:
            return int(m.group(1)), "set"
    if (career_by_player.get(sl) or {}).get("partial") == "Y":
        return None, ""  # the seasons after his last stat season have no stats, so it can't be estimated
    seasons = sorted(r["season"] for r in ps_by_player.get(sl, []))
    return (season_end_year(seasons[-1]), "estimated") if seasons else (None, "")


def book_players():
    """Record-book players with no player page: graduating year and career marks, from historical_records.csv."""
    out = {}
    for h in hist_records:
        if not h["name"] or slug(h["name"]) in PLAYER_PAGES:
            continue
        e = out.setdefault(slug(h["name"]), {"name": h["name"], "year": None, "years": "", "marks": {}, "gp": ""})
        text = f"{h['season']} {h['note']}"
        m = re.search(r"Class of (\d{4})", text)
        rng = re.search(r"(\d{4})-\d{2} to (\d{4})-\d{2}", h["season"])
        if m:
            e["year"] = e["year"] or int(m.group(1))
        elif rng:
            e["year"] = e["year"] or int(rng.group(2)) + 1
        if rng:
            e["years"] = career_years(h["season"])
        if h["period"] == "career" and h["value"]:
            e["marks"][h["stat"]] = fmt_int(h["value"])
            if h["gp"]:
                e["gp"] = h["gp"]
    return out


def classes_data(plist):
    """Every graduating class: stat-sheet players (with their pages) plus record-book players."""
    by_year = defaultdict(list)
    for p in plist:
        if p["grad"]:
            by_year[p["grad"]].append({"name": p["name"], "slug": p["slug"], "years": p["years"], "gp": p["gp"],
                                       "pts": p["pts"], "reb": p["reb"], "ast": p["ast"], "est": p["grad_how"] == "estimated",
                                       "pts_raw": p["pts_raw"], "book": False})
    for e in book_players().values():
        if e["year"]:
            m = e["marks"]
            by_year[e["year"]].append({"name": e["name"], "slug": None, "years": e["years"], "gp": e["gp"],
                                       "pts": m.get("pts", ""), "reb": m.get("reb", ""), "ast": m.get("ast", ""),
                                       "est": False, "book": True,
                                       "pts_raw": float(m["pts"].replace(",", "")) if m.get("pts") else 0})
    latest_end = season_end_year(DATA_SEASONS[-1])
    out = []
    for y in sorted(by_year, reverse=True):
        rows = sorted(by_year[y], key=lambda r: (-r["pts_raw"], r["name"]))
        out.append({"year": y, "players": rows, "current": y > latest_end, "book_only": all(r["book"] for r in rows),
                    "any_est": any(r["est"] for r in rows)})
    return out


# ---------------------------------------------------------------- team leaders by season
SEASON_LEADER_STATS = [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"), ("stl", "Steals"),
                       ("blk", "Blocks"), ("tpm", "3-pointers")]


def season_leaders_data():
    rows, led = [], {k: defaultdict(list) for k, _ in SEASON_LEADER_STATS}
    for s in sorted(set(DATA_SEASONS) | {s for s in RESULTS_ONLY if ps_by_season.get(s)}, reverse=True):
        ps = ps_by_season.get(s, [])
        cells = []
        for k, _ in SEASON_LEADER_STATS:
            vals = [r for r in ps if r.get(k)]
            if not vals:
                cells.append(None)
                continue
            top = max(r[k] for r in vals)
            who = sorted((r for r in vals if r[k] == top), key=lambda r: r["name"])
            for r in who:
                led[k][r["slug"]].append(s)
            cells.append({"value": fmt_int(top), "players": [{"name": r["name"], "slug": r["slug"],
                                                               "avg": fmt_avg(r[k], r.get("gp"))} for r in who]})
        if any(cells):
            rows.append({"s": season_summary(s), "cells": cells})
    most = []
    for k, title in SEASON_LEADER_STATS:
        ranked = sorted(((sl, ss) for sl, ss in led[k].items() if len(ss) >= 2), key=lambda kv: (-len(kv[1]), kv[1][-1]))
        if ranked:
            most.append({"title": title, "players": [{"name": PLAYER_PAGES.get(sl, sl), "slug": sl, "n": len(ss),
                                                      "seasons": ", ".join(x.replace("-", "–") for x in sorted(ss))}
                                                     for sl, ss in ranked[:5]]})
    return rows, most
