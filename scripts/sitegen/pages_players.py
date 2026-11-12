"""Pages: each player (stat-sheet and archive players), the players list, career and season
leaders, and graduating classes."""
from sitegen.views import *  # noqa: F401,F403


def player_pages(B):
    """Player pages (stat-sheet players, then players from before the stat sheets: rosters, record
    book, newspaper clippings), the players list, career and season leaders, and graduating classes."""
    plist = []
    for sl, name in PLAYER_PAGES.items():
        c = career_by_player.get(sl)
        seasons = sorted(r["season"] for r in ps_by_player.get(sl, []))
        if not seasons:
            continue
        # seasons on a roster (team photo, program) with no stats: an old player with one stat sheet
        roster_seasons = []
        for s_, rs_ in sorted(ROSTERS.items()):
            r_ = next((r for r in rs_ if r["slug"] == sl), None)
            if r_ and s_ not in seasons:
                h = hist_by_season.get(s_, {})
                roster_seasons.append({
                    "season": s_, "number": r_.get("number", ""), "source": r_.get("source", ""),
                    "position": "" if "photo" in (r_.get("position") or "").lower() else (r_.get("position") or ""),
                    "record": (f"{h['w']}–{h['l']}" + (f"–{h['t']}" if (h.get("t") or "0") != "0" else "")) if h.get("w") else "",
                    "notes": h.get("notes", ""),
                    "href": f"../seasons/{s_}.html" if s_ in games_by_season or s_ in RESULTS_ONLY or s_ in ROSTERS
                    else f"../history/index.html#s{s_}"})
        seasons = sorted(seasons + [r["season"] for r in roster_seasons])
        plist.append({"slug": sl, "name": name, "first": seasons[0], "last": seasons[-1],
                      "years": seasons[0][:4] + "–" + str(season_end_year(seasons[-1])),
                      "gp": fmt_int(c["gp"]) if c else "", "pts": fmt_int(c["pts"]) if c else "",
                      "pts_raw": (c or {}).get("pts") or 0,
                      "reb": fmt_int(c["reb"]) if c else "", "ast": fmt_int(c["ast"]) if c else "",
                      **dict(zip(("grad", "grad_how"), grad_year(sl))),
                      "grad_src": "override" if sl in GRAD_OVERRIDES else grad_year(sl)[1]})  # for the admin page
        rows = sorted(ps_by_player[sl], key=lambda r: r["season"])
        cols = cols_for(rows + ([c] if c else []))
        srows = [{"season": r["season"], "number": r.get("number", ""), "source": r.get("source", ""),
                  **season_stat_row(r)} for r in rows]
        crow = season_stat_row(c) if c else None
        partial_stats = []
        if c:
            # per-game averages only over the seasons where that stat was tracked
            ov = c.get("override_note") or ""
            for k, avg in (("reb", "rpg"), ("ast", "apg")):
                tracked_gp = sum(r["gp"] or 0 for r in rows if r.get(k) is not None)
                if f"{k}:" not in ov and tracked_gp and tracked_gp < (c["gp"] or 0):
                    crow[avg] = fmt_avg(c[k], tracked_gp)
            partial_stats = [h for k, h, need in SEASON_COLS
                             if need not in ("gp", "pts") and any(r.get(need) is None for r in rows)
                             and any(r.get(need) is not None for r in rows)]
        log = sorted(pg_by_player.get(sl, []), key=lambda r: r["date"])
        by_season = OrderedDict()
        for r in log:
            g = games_by_id[r["game_id"]]
            by_season.setdefault(r["season"], []).append({"g": g, "badges": B["game_ind"].get((r["game_id"], sl), []),
                                                          "sort": {"fg": r.get("fgm"), "tp": r.get("tpm"), "ft": r.get("ftm"),
                                                                   "margin": (g["bs"] or 0) - (g["os"] or 0)},
                                                          **box_row(r)})
        lcols = box_cols(log)
        highs = []
        for k, label in [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"), ("stl", "Steals"), ("blk", "Blocks"),
                         ("tpm", "3-pointers")]:
            # a few leading scorers from newspaper clippings don't make a game high
            cands = [r for r in log if r.get(k) is not None and games_by_id[r["game_id"]].get("box_source") != "newspaper"]
            if cands and max(r[k] for r in cands) > 0:
                best = max(cands, key=lambda r: (r[k], r["date"]))
                highs.append({"label": label, "value": fmt_int(best[k]), "g": games_by_id[best["game_id"]]})
        # in the news: features about the player, and game stories whose headline names them
        # (a last name alone counts only if no teammate in that game shares it)
        player_news = [{"outlet": f["outlet"], "title": f["title"], "access": f.get("access", ""),
                        "links": [{"kind": f["kind"], "url": f["url"]}], "published": f["published"], "g": None}
                       for f in FEATURES_BY_PLAYER.get(sl, [])]
        last = name.split()[-1].lower()
        for r in log:
            g = games_by_id[r["game_id"]]
            if not g["stories"]:
                continue
            same_last = sum(1 for o in pg_by_game[g["game_id"]] if o["name"].split()[-1].lower() == last)
            for s in g["stories"]:
                words = re.findall(r"[a-z']+", s["title"].lower().replace("’", "'"))
                hit = name.lower() in s["title"].lower() or (same_last == 1 and (last in words or f"{last}'s" in words))
                if hit:
                    player_news.append(dict(s, g=g, published=g["date"]))
        player_news.sort(key=lambda s: s["published"], reverse=True)
        numbers = sorted({r.get("number") for r in rows if r.get("number")}, key=lambda x: int(x) if x.isdigit() else 999)
        # class (SR/JR/...) from the player's last game that records one, labeled with that game's season
        # (not the newest season, which a player who graduated or hasn't played yet isn't part of)
        cls_row = next((r for r in reversed(log) if r.get("class")), None)
        cls, cls_season = (cls_row["class"], cls_row["season"]) if cls_row else ("", "")
        p_ = plist[-1]
        sub = " · ".join(x for x in [p_["years"], ("#" + ", #".join(numbers)) if numbers else "",
                                     f"Class of {p_['grad']}" if p_["grad"] and p_["grad_how"] != "estimated" else ""] if x)
        tiles = []
        if crow:
            for k, lbl in (("pts", "Career points"), ("reb", "Rebounds"), ("ast", "Assists")):
                if crow.get(k):
                    tiles.append((crow[k], lbl))
            if len(tiles) < 3 and crow.get("ppg"):
                tiles.append((crow["ppg"], "Points per game"))
            if crow.get("gp"):
                tiles.append((crow["gp"], "Games"))
        part = (c or {}).get("partial") == "Y"
        span = ((rows[0]["season"].replace("-", "–") if len(rows) == 1 else
                 f"{rows[0]['season'][:4]}–{season_end_year(rows[-1]['season'])}") if rows else "")
        if part:
            tiles = [(v, f"Points, {span}" if l == "Career points" else l) for v, l in tiles]
        book_career = [{"stat": h["stat"], "value": fmt_int(h["value"]), "gp": h["gp"], "season": career_years(h["season"]),
                        "note": h["note"]}
                       for h in hist_records if h["scope"] == "individual" and h["period"] == "career" and h["value"]
                       and h["name"] and slug(h["name"]) == sl]
        sh = share("players", sl, share_images.player_card, f"{name}, Bangor Cardinals boys basketball, {p_['years']}",
                   name, sub, tiles[:4])
        news_log = {s for s, rs in by_season.items()
                    if rs and all(r["g"].get("box_source") == "newspaper" for r in rs)}
        render("player.html", f"players/{sl}.html", edit={"kind": "player", "name": name, "slug": sl, "plain": slug(name) == sl},
ld=[ld_person(name, f"players/{sl}.html", image=(PLAYER_PHOTOS.get(sl) or {}).get("url"), years=plist[-1]["years"]), ld_crumbs(("Players", "players/index.html"), (name, f"players/{sl}.html"))],
               name=name, seasons=srows, career=crow, cols=cols, log=by_season,
               news_log=news_log,
               lcols=lcols, highs=highs, numbers=numbers, cls=cls, cls_season=cls_season, years=plist[-1]["years"],
               grad=plist[-1]["grad"], grad_est=plist[-1]["grad_how"] == "estimated",
               partial=bool(partial_stats), part_career=part, span=span, book_career=book_career,
               override=(c or {}).get("override_note", ""), record_badges=B["player"].get(sl, []),
               player_news=player_news, headshot=PLAYER_PHOTOS.get(sl), roster_seasons=roster_seasons,
               honors=HONORS_BY_PLAYER.get(sl, []), **sh)
    # ---- players from before the stat sheets (rosters, record book, newspaper clippings)
    for sl, a in ARCHIVE.items():
        roster_by = {r["season"]: r for r in a["roster"]}
        clips = sorted(a["clips"], key=lambda c: c["g"]["date"])
        seasons, numbers, positions = [], [], []
        for s in sorted(a["seasons"]):
            r = roster_by.get(s, {})
            num_ = r.get("number") or next((c["number"] for c in clips if c["g"]["season"] == s and c["number"]), "")
            pos = "" if "photo" in (r.get("position") or "").lower() else (r.get("position") or "")
            h = hist_by_season.get(s, {})
            rec = (f"{h['w']}–{h['l']}" + (f"–{h['t']}" if (h.get("t") or "0") != "0" else "")) if h.get("w") else ""
            src = r.get("source") or ("Newspaper clippings" if any(c["g"]["season"] == s for c in clips) else "Record book")
            seasons.append({"season": s, "number": num_, "position": pos, "height": r.get("height", ""),
                            "grade": r.get("grade", ""), "record": rec, "notes": h.get("notes", ""), "source": src,
                            "href": f"../seasons/{s}.html" if s in games_by_season or s in RESULTS_ONLY or s in ROSTERS
                            else f"../history/index.html#s{s}"})
            for x, lst in ((num_, numbers), (pos, positions)):
                if x and x not in lst:
                    lst.append(x)
        book_career = [{"stat": h["stat"], "value": fmt_int(h["value"]), "gp": h["gp"], "season": career_years(h["season"]),
                        "note": h["note"]} for h in a["book"] if h["period"] == "career" and h["value"]]
        marks = {b["stat"]: b for b in book_career}
        tiles = [{"label": f"Career {lbl}", "value": marks[k]["value"],
                  "sub": (f"{fmt_avg(float(marks[k]['value'].replace(',', '')), int(marks[k]['gp']))} per game"
                          if marks[k]["gp"] else "Record book")}
                 for k, lbl in (("pts", "points"), ("reb", "rebounds"), ("ast", "assists")) if k in marks]
        gp = next((b["gp"] for b in book_career if b["gp"]), "")
        if gp:
            tiles.append({"label": "Games played", "value": gp, "sub": "Record book"})
        if not tiles and seasons:
            tiles.append({"label": "Seasons on file", "value": str(len(seasons)),
                          "sub": f"{seasons[0]['season'][:4]}–{season_end_year(seasons[-1]['season'])}"})
        years = (seasons[0]["season"].replace("-", "–") if len(seasons) == 1 else
                 f"{seasons[0]['season'][:4]}–{season_end_year(seasons[-1]['season'])}") if seasons else ""
        clip_cols = [(k, h) for k, h in (("pts", "PTS"), ("fgm", "FGM"), ("tpm", "3PM"), ("ftm", "FTM"), ("fta", "FTA"),
                                         ("reb", "REB"), ("ast", "AST"), ("blk", "BLK"))
                     if any(c.get(k) is not None for c in clips)]
        clips = [{**c, **{k: fmt_int(c[k]) for k, _ in clip_cols}} for c in clips]
        sources = [x for x, have in (("game programs and team photos" if any("program" in r["source"].lower() for r in a["roster"])
                                      else "team photos and line-ups", a["roster"]),
                                     ("the Bangor record book", a["book"]), ("newspaper clippings", clips)) if have]
        player_news = [{"outlet": f["outlet"], "title": f["title"], "access": f.get("access", ""),
                        "links": [{"kind": f["kind"], "url": f["url"]}], "published": f["published"], "g": None}
                       for f in FEATURES_BY_PLAYER.get(sl, [])]
        grad = GRAD_OVERRIDES.get(sl, a["grad"])  # overrides/grad_years.csv wins, as for stat-sheet players
        plist.append({"slug": sl, "name": a["name"], "years": years or (f"Class of {grad}" if grad else ""),
                      "gp": gp, "pts": marks.get("pts", {}).get("value", ""), "reb": marks.get("reb", {}).get("value", ""),
                      "ast": marks.get("ast", {}).get("value", ""),
                      "pts_raw": float(marks["pts"]["value"].replace(",", "")) if "pts" in marks else 0,
                      "grad": grad, "grad_how": "set" if grad else "", "archive": True,
                      "grad_src": "override" if sl in GRAD_OVERRIDES else a["grad_how"]})
        sub = " · ".join(x for x in [years, ("#" + ", #".join(numbers)) if numbers else "",
                                     f"Class of {grad}" if grad else ""] if x)
        sh = share("players", sl, share_images.player_card, f"{a['name']}, Bangor Cardinals boys basketball"
                   + (f", {years}" if years else ""), a["name"], sub, [(t["value"], t["label"]) for t in tiles[:4]])
        render("player_archive.html", f"players/{sl}.html", edit={"kind": "player", "name": a["name"], "slug": sl, "plain": slug(a["name"]) == sl},
ld=[ld_person(a["name"], f"players/{sl}.html", image=(PLAYER_PHOTOS.get(sl) or {}).get("url"), years=years), ld_crumbs(("Players", "players/index.html"), (a["name"], f"players/{sl}.html"))],
               name=a["name"], years=years, numbers=numbers,
               positions=positions, grad=grad, seasons=seasons, book_career=book_career, tiles=tiles, clips=clips,
               clip_cols=clip_cols, record_badges=B["player"].get(sl, []), player_news=player_news, sources=sources,
               headshot=PLAYER_PHOTOS.get(sl), honors=HONORS_BY_PLAYER.get(sl, []), **sh)
    plist.sort(key=lambda p: p["name"].split()[-1] + " " + p["name"])
    classes = classes_data(plist)
    boards = career_boards()
    lead = {b["stat"]: b["entries"][0] for b in boards if b["entries"]}
    sh = page_share("players", "Every known Bangor Cardinals varsity boys basketball player",
                    "Players", "Every player", f"Varsity players since {FACTS['first']}, with career stats",
                    [(f"{len(plist):,}", "Players"), (len(classes), "Graduating classes"),
                     (lead["pts"]["display"] if "pts" in lead else None, f"Career points · {last_name(lead.get('pts', {}).get('name'))}")])
    render("players.html", "players/index.html", players=plist, **sh)
    sh = page_share("career-leaders", "Bangor Cardinals boys basketball career leaders",
                    "Record book", "Career leaders", "Every player ranked by career totals",
                    [(lead[k]["display"], f"{lbl} · {last_name(lead[k]['name'])}")
                     for k, lbl in (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists")) if k in lead])
    render("leaders.html", "records/career-leaders.html", boards=boards, latest_season=DATA_SEASONS[-1],
           pg_min=PER_GAME_MIN, **sh)
    years = [c["year"] for c in classes if c["year"]]
    sh = page_share("classes", "Bangor Cardinals boys basketball players by graduating class",
                    "Players", "Players by class", f"Every graduating class from {min(years)} to {max(years)}" if years else "",
                    [(len(classes), "Classes"), (f"{sum(len(c['players']) for c in classes):,}", "Players with a class year")])
    render("classes.html", "players/classes.html", classes=classes, **sh)
    srows, smost = season_leaders_data()
    top = next((m["players"][0] for m in smost if m["title"].lower().startswith("point")), None)
    sh = page_share("season-leaders", "Bangor Cardinals boys basketball team leaders by season",
                    "Record book", "Team leaders by season",
                    f"Led the team in scoring most often: {top['name']}, {top['n']} seasons" if top
                    else "Each season's top scorer, rebounder and more",
                    [(len(srows), "Seasons"), (srows[-1]["s"]["season"].replace("-", "–") if srows else None, "First season")])
    render("season_leaders.html", "records/season-leaders.html", rows=srows, most=smost,
           stats=SEASON_LEADER_STATS, **sh)
    return plist, classes
