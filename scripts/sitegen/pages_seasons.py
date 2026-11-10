"""Pages: home, the seasons list, each season, and each game."""
from sitegen.views import *  # noqa: F401,F403


def home(PREVIEWS):
    """The home page."""
    latest = DATA_SEASONS[-1]
    top_career = merged("individual", "career", "pts", "int")[:5]
    top_game = merged("individual", "game", "pts", "int")[:5]
    champs = [h for h in history if "state champion" in h["notes"].lower() or "state runner" in h["notes"].lower()
              or "state semifinal" in h["notes"].lower() or "state tournament" in h["notes"].lower()]
    recent = [season_summary(s) for s in reversed(DATA_SEASONS[-6:])]
    latest_games = [g for g in games_by_season[latest] if g["status"] == "final"][-5:][::-1]
    render("home.html", "index.html", latest=season_summary(latest), latest_leaders=leaders(latest),
           latest_games=latest_games, preseason=None if latest_games else preseason(latest),
           upcoming=[{**g, "preview": PREVIEWS.get(g["game_id"])} for g in UPCOMING[:UPCOMING_ON_HOME]],
           top_career=top_career, top_game=top_game, champs=champs, recent=recent,
           ld=[{"@type": "WebSite", "@id": SITE_URL + "/#site", "name": "Bangor Cardinals Boys Basketball",
                "url": SITE_URL + "/", "about": ld_team_ref()},
               {**ld_team(), "coach": {"@type": "Person", "name": season_summary(latest)["coach"]}}])


def seasons_index():
    """The list of every season."""
    all_seasons = [season_summary(h["season"]) for h in reversed(history)]
    render("seasons.html", "seasons/index.html", seasons=all_seasons)


def season_pages(B):
    """A page for each season: full seasons from the stat sheets, and results-only seasons."""
    PAGE_SEASONS = sorted(set(DATA_SEASONS) | set(RESULTS_ONLY) | set(ROSTERS))

    def pager(s):
        i = PAGE_SEASONS.index(s)
        return {"prev": PAGE_SEASONS[i - 1] if i else None, "next": PAGE_SEASONS[i + 1] if i + 1 < len(PAGE_SEASONS) else None}

    def results_players(s, gs):
        """Player stats for a results-only season, from a printed season stat sheet (season_totals.csv)."""
        players = sorted(ps_by_season.get(s, []), key=lambda r: -(r.get("pts") or 0))
        tot = {k: sum(r[k] for r in players if r.get(k) is not None) if any(r.get(k) is not None for r in players) else None
               for k in STATS}
        line = TEAM_LINE.get(s)
        if line:
            tot.update({k: v for k, v in line.items() if v is not None})
        tot["gp"] = len(gs)
        return {"players": [{"name": r["name"], "slug": r["slug"], "number": r.get("number", ""), **season_stat_row(r)}
                            for r in players],
                "cols": cols_for(players), "team": season_stat_row(tot), "leaders": leaders(s) if players else [],
                "player_badges": B["season_ind"].get(s, []), "team_badges": B["season_team"].get(s, []),
                "team_line": bool(line)}

    clipping_details()
    # results-only seasons, and seasons known only from a roster (team photo) with no results yet
    for s in sorted({s for s in set(RESULTS_ONLY) | set(ROSTERS) if s not in games_by_season}):
        gs = RESULTS_ONLY.get(s, [])
        ss = season_summary(s)
        w, l = sum(g["result"] == "W" for g in gs), sum(g["result"] == "L" for g in gs)
        items, rw, rl = [], 0, 0
        for g in gs:
            rw += g["result"] == "W"
            rl += g["result"] == "L"
            g["record"] = f"{rw}–{rl}"
            if not g["scored"]:
                continue
            m = int(g["bs"] - g["os"])
            items.append({"margin": m, "record": g["record"], "href": f"#g{g['anchor']}",
                          "xlabel": g["game"] if g["game"] and (g["game"] == "1" or int(g["game"]) % 5 == 0) else "",
                          "tip": f"{'+' if m > 0 else ('−' if m < 0 else '')}{abs(m)} · {g['result']} {g['bangor_score']}–{g['opp_score']}"
                                 f"{' (OT)' if g['ot'] else ''}\n"
                                 f"{fmt_date(g['date']) if g.get('date') else 'Game ' + g['game']}: "
                                 f"{'@ ' if g.get('site') == 'away' else ('vs ' if g.get('site') else '')}{g['opponent']}"})
        if items:
            for it in (max(items, key=lambda i: i["margin"]), min(items, key=lambda i: i["margin"])):
                it["label"] = True
        margin_svg = charts.margin_chart(items, f"Bangor's scoring margin in each {s.replace('-', '–')} game") if items else ""
        sources = sorted({g["source"] for g in gs if g.get("source")})
        known = ss["w"] == ""  # no full-season record: show the record in the games that are known
        rec = f"{w}–{l}" if known else f"{ss['w']}–{ss['l']}"
        tiles = [(rec, "Record in known games" if known else "Record")]
        if gs:
            tiles.append((f"{ss['ppg']}–{ss['oppg']}", "Average score"))
        elif known:  # a season known only from its team photos: no record to show
            tiles = []
        title = f"Bangor Cardinals {s.replace('-', '–')} season" + (f": {rec}{' in known games' if known else ''}" if tiles else "")
        sh = share("seasons", s, share_images.simple_card, title,
                   f"Season{' · Coach ' + ss['coach'] if ss['coach'] else ''}", s.replace("-", "–"), ss["notes"], tiles, "Season")
        if STORIES.get(s):
            st = STORIES[s]
            render("story.html", f"seasons/{st['slug']}.html", st=st, s=ss, **share(
                "seasons", st["slug"], share_images.simple_card, st["title"], st["kicker"], s.replace("-", "–"),
                ss["notes"], [(f"{w}–{l}", "Record in known games")], "Season"))
        render("season_results.html", f"seasons/{s}.html", ld=[ld_crumbs(("Seasons", "seasons/index.html"), (s.replace("-", "–"), f"seasons/{s}.html"))], s=ss, games=gs, w=w, l=l, sources=sources,
               dated=all(g.get("date") for g in gs), any_dates=any(g.get("date") for g in gs),
               in_h2h=True, honors=HONORS_BY_SEASON.get(s, []),
               any_sites=any(g.get("site") for g in gs), story=STORIES.get(s), **results_players(s, gs),
               roster=ROSTERS.get(s, []), team_photos=TEAM_PHOTOS.get(s, []),
               margin_svg=margin_svg, opp_pages=OPP_PAGES, player_pages=PLAYER_PAGES, **pager(s), **sh)

    for i, s in enumerate(DATA_SEASONS):
        gs = games_by_season[s]
        players = sorted(ps_by_season.get(s, []), key=lambda r: -(r.get("pts") or 0))
        cols = cols_for(players)
        prow = [{"name": r["name"], "slug": r["slug"], "number": r.get("number", ""), **season_stat_row(r)} for r in players]
        tot = {k: sum(r[k] for r in players if r.get(k) is not None) if any(r.get(k) is not None for r in players) else None
               for k in STATS}
        tot["gp"] = len([g for g in gs if g["result"]])
        team_row = season_stat_row(tot)
        partial = [g for g in gs if g["box_score"] == "none" and g["result"]]
        margin_svg, scoring_lines = season_charts(s, gs)
        ss = season_summary(s)
        tiles = ([(f"{ss['w']}–{ss['l']}", "Record")] if ss["w"] != "" and ss["started"]
                 else [(fmt_date(ss["starts"]), "First game")] if ss["starts"] else [])
        if ss["ppg"]:
            tiles.append((f"{ss['ppg']}–{ss['oppg']}", "Average score"))
        lead = next((l for l in leaders(s) if l["label"] == "Points"), None)
        if lead:
            tiles.append((lead["name"], f"Leading scorer · {lead['value']} pts"))
        sh = share("seasons", s, share_images.simple_card, f"Bangor Cardinals {s.replace('-', '–')} season: {ss['w']}–{ss['l']}",
                   f"Season{' · Coach ' + ss['coach'] if ss['coach'] else ''}", s.replace("-", "–"), ss["notes"], tiles, "Season")
        render("season.html", f"seasons/{s}.html", ld=[ld_crumbs(("Seasons", "seasons/index.html"), (s.replace("-", "–"), f"seasons/{s}.html"))], s=ss, games=gs, players=prow, cols=cols, **sh,
               margin_svg=margin_svg, scoring_lines=scoring_lines, honors=HONORS_BY_SEASON.get(s, []),
               team_game_stats=any(g["date"] in TEAM_GAME for g in gs), roster=ROSTERS.get(s, []),
               player_pages=PLAYER_PAGES, team_photos=TEAM_PHOTOS.get(s, []),
               team=team_row, leaders=leaders(s), partial=partial,
               **pager(s),
               source_note=any(r.get("source") == "season tab" for r in players),
               team_badges=B["season_team"].get(s, []), player_badges=B["season_ind"].get(s, []),
               game_badges=[b for g in gs for b in B["game_team"].get(g["game_id"], [])])
    return PAGE_SEASONS


def game_pages(B, PREVIEWS):
    """A page for each game."""
    for gid, g in games_by_id.items():
        bangor = sorted(pg_by_game.get(gid, []), key=lambda r: (-(r["pts"] or 0)))
        opp = sorted(opg_by_game.get(gid, []), key=lambda r: (-(r["pts"] or 0)))
        periods = None
        if g["period_labels"]:
            labels = g["period_labels"].split("|")
            periods = {"labels": [("Q" + l if len(labels) >= 4 and l.isdigit() else ("H" + l if l.isdigit() else l)) for l in labels],
                       "bangor": g["bangor_periods"].split("|"), "opp": g["opp_periods"].split("|")}
        bt = box_totals(bangor)
        ot = box_totals(opp)
        if g.get("box_source") == "newspaper":  # a clipping total is only shown when every player's number is known
            for tot, rows_ in ((bt, bangor), (ot, opp)):
                for k in list(tot):
                    if any(r.get(k) is None for r in rows_):
                        tot[k] = None
        ind = [b for r in bangor for b in B["game_ind"].get((gid, r["slug"]), [])]
        ind += [b for (bg, bs), bl in B["game_ind"].items() if bg == gid and bs not in {r["slug"] for r in bangor} for b in bl]
        auto_recap = "" if g["recap"] else recaps.write(g, bangor, opp, games_by_season[g["season"]], ind,
                                                         final_season=g["season"] != CURRENT)
        otd_game(g, f"games/{gid}.html", recaps.write(g, bangor, opp, [], ind, False, link=False, short=True),
                 [b for b in ind if b["period"] == "game"])
        render("game.html", f"games/{gid}.html", g=g,
               ld=[ld_game(g), ld_crumbs(("Seasons", "seasons/index.html"), (g["season"].replace("-", "–"), f"seasons/{g['season']}.html"),
                                         (f"{'at' if g['site'] == 'away' else 'vs'} {g['opponent']}, {fmt_date(g['date'])}", f"games/{gid}.html"))], **game_share(g), auto_recap=auto_recap,
               record_badges=sorted(B["game_team"].get(gid, []) + ind, key=lambda b: (b["rank"], b["title"])),
               bangor=[{"name": r["name"], "slug": r["slug"], "number": r["number"], "cls": r.get("class", ""),
                        "badges": B["game_ind"].get((gid, r["slug"]), []), **box_row(r)} for r in bangor],
               bcols=box_cols(bangor), btot=box_row(bt) if bangor else None,
               opp=[{"name": r["name"], "number": r["number"], **box_row(r)} for r in opp],
               ocols=box_cols(opp), otot=box_row(ot) if opp else None, periods=periods, preview=PREVIEWS.get(gid),
               opp_complete=bool(opp) and ot.get("pts") == g["os"],
               team_stats=team_stats_rows(g, bangor))
