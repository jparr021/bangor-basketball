"""Pages: history and coaches, opponents, film, the search index, sheet check, admin, 404,
the calendar feed and the sitemap."""
from sitegen.views import *  # noqa: F401,F403


def history_pages():
    """History, the gaps list, and a page for each coach."""
    sh = page_share("history", f"Bangor Cardinals boys basketball history since {FACTS['first']}",
                    "History", f"Since {FACTS['first']}",
                    f"{len(coach_list)} head coaches · {FACTS['w']:,}–{FACTS['l']:,} all time ({FACTS['pct']})",
                    [(FACTS["conf_titles"], "Conference titles"), (FACTS["regional_titles"], "Regional titles"),
                     (sum(c["state"] for c in coach_list), "State trips"),
                     (FACTS["state_titles"], "State title" + ("s" if FACTS["state_titles"] > 1 else ""))])
    render("history.html", "history/index.html", seasons=[season_summary(h["season"]) for h in history],
           coaches=coach_list, **sh)
    gap_rows, wanted, gap_sum = gaps_data()
    # names we can't pin down from the sources (overrides/identify.csv), for alumni to help with
    ipath = os.path.join(OV, "identify.csv")
    identify = [{**r, "href": f"../seasons/{r['season']}.html"} for r in load(ipath)] if os.path.exists(ipath) else []
    sh = page_share("gaps", "What's still missing from Bangor Cardinals boys basketball history",
                    "Help fill the gaps", "What's missing",
                    f"{len(wanted)} big seasons still missing results · old programs, clippings and photos wanted",
                    [(f"{gap_sum['results']} of {gap_sum['n']}", "Seasons with every result"),
                     (gap_sum["stats"], "Seasons with player stats"), (gap_sum["roster"], "Seasons with a roster")])
    render("gaps.html", "history/gaps.html", rows=list(reversed(gap_rows)), wanted=wanted, sm=gap_sum, form_url=FORM_URL,
           identify=identify, **sh)
    honors_page()
    chrono = sorted(coach_list, key=lambda c: c["seasons"][0])
    for i, c in enumerate(chrono):
        rec = f"{c['w']}–{c['l']}" + (f"–{c['t']}" if c["t"] else "")
        tiles = ([(rec, "Record")] if c["w"] + c["l"] + c["t"] else []) + [(v, lbl) for v, lbl in ((c["titles"], "Conference titles"),
                                                             (c["regional"], "Regional titles"), (c["state"], "State trips")) if v]
        span = c["seasons"][0].replace("-", "–") + (f" to {c['seasons'][-1].replace('-', '–')}" if len(c["seasons"]) > 1 else "")
        sh = share("coaches", c["slug"], share_images.simple_card, f"Coach {c['name']}: {rec} at Bangor",
                   f"Head coach · {span}", c["name"],
                   f"{len(c['seasons'])} season{'s' if len(c['seasons']) > 1 else ''}" + (f" · {c['pct']} winning percentage" if c["pct"] else ""),
                   tiles[:4], "Coach")
        render("coach.html", f"coaches/{c['slug']}.html", c=c,
               ld=[ld_person(c["name"], f"coaches/{c['slug']}.html", role="Head coach", years=span),
                   ld_crumbs(("History", "history/index.html"), (c["name"], f"coaches/{c['slug']}.html"))], d=coach_page_data(c), **sh,
               prev=chrono[i - 1] if i else None, next=chrono[i + 1] if i + 1 < len(chrono) else None)


def honors_page():
    """All-Conference picks, area and state honors, team awards and captains, season by season (honors.csv)."""
    if not HONORS:
        return
    seasons = sorted({h["season"] for h in HONORS}, reverse=True)
    by = lambda s, g: [h for h in HONORS_BY_SEASON[s] if h["group"] == g]
    conf = [{"season": s, "picks": [h for h in by(s, "conf") if "honorable" not in h["honor"]],
             "hm": [h for h in by(s, "conf") if "honorable" in h["honor"]]} for s in seasons if by(s, "conf")]
    award_cols = [("MVP", ("Most Valuable Player", "Offensive MVP")), ("Defensive MVP", ("Defensive MVP",)),
                  ("Best rebounder", ("Best rebounder",)), ("Best free-throw shooter", ("Best free-throw shooter",)),
                  ("Most improved", ("Most improved",)), ("Spirit award", ("Spirit award",))]
    shown = {h for _, hs in award_cols for h in hs}
    awards = [{"season": s, "cols": [[h for h in by(s, "award") if h["honor"] in hs] for _, hs in award_cols],
               "other": [h for h in by(s, "award") if h["honor"] not in shown]} for s in seasons if by(s, "award")]
    captains = [{"season": s, "list": by(s, "captain")} for s in seasons if by(s, "captain")]
    area = [h for h in reversed(HONORS) if h["group"] == "area"]
    # players picked All-Conference (any team, or honorable mention) more than once
    count = defaultdict(list)
    for h in HONORS:
        if h["group"] == "conf":
            count[(h["slug"] or h["name"], h["name"])].append(h)
    most = sorted(({"name": n, "slug": k if k in PLAYER_PAGES else None, "list": hs} for (k, n), hs in count.items() if len(hs) > 1),
                  key=lambda m: (-len(m["list"]), -sum("honorable" not in h["honor"] for h in m["list"]), m["name"]))
    sm = {"picks": sum(len(c["picks"]) for c in conf), "hm": sum(len(c["hm"]) for c in conf),
          "players": len({h["slug"] or h["name"] for h in HONORS}), "seasons": len(seasons)}
    top = most[0] if most else None
    sh = page_share("honors", "Bangor Cardinals boys basketball honors: All-Conference picks, team awards and captains",
                    "Honors & awards", "All-Conference & more",
                    f"Most honored: {top['name']}, All-Conference {len(top['list'])} times" if top
                    else f"{sm['seasons']} seasons of honors",
                    [(sm["picks"], "All-Conference picks"), (sm["hm"], "Honorable mentions"),
                     (sm["players"], "Players honored")])
    render("honors.html", "history/honors.html", conf=conf, awards=awards, award_cols=[c for c, _ in award_cols],
           captains=captains, area=area, most=most, sm=sm, form_url=FORM_URL, **sh,
           ld=[ld_crumbs(("History", "history/index.html"), ("Honors", "history/honors.html"))])


def opponent_pages(opps):
    """A page for every opponent on the schedule (a game page links to it), even before the first
    meeting, and the opponents list."""
    # every opponent on the schedule gets a page (a game page links to it), even before the first meeting
    for o in opps.values():
        o["last"] = o["games"][-1] if o["games"] else None
        o["h2h"] = head_to_head(o)
        sh = {}
        if o["games"]:
            h2 = o["h2h"]
            tiles = [(f"{o['w']}–{o['l']}", "Bangor's record"), (f"{h2['ppg']}–{h2['oppg']}", "Average score")]
            if h2["streak"]:
                tiles.append(((("Won " if h2["streak"][0] == "W" else "Lost ") + h2["streak"][1:]), "Current streak"))
            sh = share("opponents", o["slug"], share_images.simple_card, f"Bangor vs {o['name']}: {o['w']}–{o['l']}",
                       "Head to head", f"vs {o['name']}",
                       f"{o['w'] + o['l']} meeting{'s' if o['w'] + o['l'] != 1 else ''} since {o['games'][0]['season'].replace('-', '–')}", tiles, "Opponent")
        render("opponent.html", f"opponents/{o['slug']}.html", o=o,
               ld=[ld_crumbs(("Opponents", "opponents/index.html"), (o["name"], f"opponents/{o['slug']}.html"))], **sh)
    olist = sorted((o for o in opps.values() if o["games"]), key=lambda o: (-(o["w"] + o["l"]), o["name"]))
    first = min([DATA_SEASONS[0]] + [o["games"][0]["season"] for o in olist])
    sh = {}
    if olist:
        top = olist[0]
        sh = page_share("opponents", "Bangor Cardinals boys basketball's record against every opponent",
                        "Head to head", "Every opponent",
                        f"Most played: {top['name']}, {top['w']}–{top['l']} in {top['w'] + top['l']} games",
                        [(len(olist), "Opponents"), (f"{sum(o['w'] + o['l'] for o in olist):,}", "Games"),
                         (first.replace("-", "–"), "Results since")])
    render("opponents.html", "opponents/index.html", opps=olist, first=first, **sh)
    return olist


def film_index():
    """The game film index."""
    if FILM_GAMES or HUDL_ONLY:
        by_season = OrderedDict()
        for g in sorted(FILM_GAMES + HUDL_ONLY, key=lambda g: g["date"], reverse=True):
            by_season.setdefault(g["season"], []).append(g)
        total = len(FILM_GAMES) + len(HUDL_ONLY)
        sh = page_share("film", "Bangor Cardinals boys basketball game film and highlights", "Watch", "Game film",
                        f"{len(by_season)} season{'s' if len(by_season) != 1 else ''} of games and highlights",
                        [(total, "Games on film"), (len(FILM_GAMES), "On YouTube"), (len(HUDL_ONLY), "On Hudl only")])
        render("film.html", "film/index.html", by_season=by_season, total=total,
               youtube=len(FILM_GAMES), hudl_only=len(HUDL_ONLY), **sh)


def search_index(plist, olist, classes):
    """The site search index (loaded by site.js the first time someone opens search)."""
    def season_label(s):
        return s.replace("-", "–")
    idx = []
    for p in plist:
        when = p["years"] or (f"Class of {p['grad']}" if p.get("grad") else "")
        sub = "Player" + (f" · {when}" if when else "") + (f" · {p['pts']} pts" if p["pts"] else "")
        idx.append({"t": p["name"], "s": sub, "u": f"players/{p['slug']}.html", "k": "player"})
    book_only = OrderedDict()  # record-book names with no player page (mostly pre-2007)
    book_career = {}  # first career stat each record-book-only player appears in (for the search link)
    for h in hist_records:
        if h["name"] and slug(h["name"]) not in PLAYER_PAGES:
            book_only.setdefault(h["name"], set()).add(h["season"])
            if h["period"] == "career" and h["value"]:
                book_career.setdefault(h["name"], h["stat"])
    for name, seasons in book_only.items():
        cls = sorted(s for s in seasons if s.startswith("Class of"))
        yrs = sorted(s for s in seasons if re.fullmatch(r"\d{4}-\d{2}", s))
        when = cls[0] if cls else (season_label(yrs[0]) + (f" to {season_label(yrs[-1])}" if yrs[-1] != yrs[0] else "")
                                   if yrs else "")
        idx.append({"t": name, "s": "Record book" + (f" · {when}" if when else ""), "u": f"records/career-leaders.html#{book_career[name]}" if name in book_career else "records/index.html",
                    "k": "player"})
    for c in coach_list:
        rec = f"{c['w']}–{c['l']}" + (f"–{c['t']}" if c["t"] else "")
        idx.append({"t": c["name"], "s": f"Coach · {c['years']} · {rec}", "u": f"coaches/{c['slug']}.html", "k": "coach"})
    for o in olist:
        rec = f"Bangor is {o['w']}–{o['l']}"
        idx.append({"t": o["name"], "s": f"Opponent · {rec}", "u": f"opponents/{o['slug']}.html",
                    "k": "opponent"})
    for h in reversed(history):
        s = h["season"]
        rec = f"{h['w']}–{h['l']}" + (f"–{h['t']}" if h["t"] and h["t"] != "0" else "") if h["w"] != "" else ""
        sub = " · ".join(x for x in ["Season", rec, f"Coach {h['coach']}" if h["coach"] else "", h["notes"]] if x)
        url = f"seasons/{s}.html" if s in games_by_season or s in RESULTS_ONLY or s in ROSTERS else f"history/index.html#s{s}"
        idx.append({"t": f"{season_label(s)} season", "s": sub, "u": url, "k": "season",
                    "x": f"{s} {s[:4]} {season_end_year(s)} {h['coach']} {h['notes']}"})
    for cl in classes:
        idx.append({"t": f"Class of {cl['year']}", "s": f"Graduating class · {len(cl['players'])} player"
                    + ("s" if len(cl["players"]) > 1 else ""), "u": f"players/classes.html#c{cl['year']}", "k": "page",
                    "x": f"{cl['year']} seniors graduates"})
    for t, u, x in [("Team leaders by season", "records/season-leaders.html", "season leaders scoring leader rebounding"),
                    ("Graduating classes", "players/classes.html", "class of seniors graduates roster"),
                    ("Record Book", "records/index.html", "records top 10"), ("Career Leaders", "records/career-leaders.html", "leaderboard all-time career points rebounds assists list"), ("History & Coaches", "history/index.html", "coaches"),
                    ("Honors and awards", "history/honors.html", "all-conference all conference captains mvp awards honorable mention all-state"),
                    ("Help fill in the gaps", "history/gaps.html", "missing share programs yearbooks clippings photos film contribute"),
                    ("All seasons", "seasons/index.html", ""), ("All players", "players/index.html", "roster"),
                    ("All opponents", "opponents/index.html", "")] + ([("Game film", "film/index.html", "video youtube hudl")]
                                                                     if FILM_GAMES or HUDL_ONLY else []):
        idx.append({"t": t, "s": "Page", "u": u, "k": "page", "x": x})
    with open(os.path.join(OUT, "static", "search-index.js"), "w") as f:
        f.write("window.BANGOR_SEARCH=" + json.dumps(idx, ensure_ascii=False, separators=(",", ":")) + ";\n")


def sheet_check_page():
    """Sheet check: likely mistakes in the stat sheets, in the build log and on /sheet-check (unlisted)."""
    findings = sheet_check.run(CURRENT, TODAY, PLAYER_ALIASES)
    cur, fixes, checks = sheet_check.summary(findings, CURRENT)
    print(f"sheet check ({CURRENT}): {fixes} to fix, {checks} to check. Full list: {SITE_URL}/sheet-check")
    for f_ in cur:
        print(f"  {f_['level'].upper():5} {f_['text']}")
    earlier = OrderedDict()
    for f_ in findings:
        if f_["season"] != CURRENT:
            earlier.setdefault(f_["season"], []).append(f_)
    render("sheet_check.html", "sheet-check.html", current=cur, fixes=fixes, checks=checks, earlier=earlier,
           built_at=NOW.strftime("%B %-d, %Y at %-I:%M %p"))
    PAGES.remove("sheet-check.html")  # kept out of the sitemap


def admin_page(plist, PAGE_SEASONS):
    """The admin page (/admin). Its server side is api/admin.js, on Vercel only."""
    admin_players = sorted(({"name": p["name"], "slug": p["slug"], "years": p["years"], "grad": p.get("grad") or "",
                             "how": p.get("grad_src") or ""} for p in plist),
                           key=lambda p: p["name"])
    admin_games = [{"id": g["game_id"], "date": g["date"], "season": g["season"], "opponent": g["opponent"],
                    "site": g["site"], "label": f"{fmt_date(g['date'])} {'at' if g['site'] == 'away' else 'vs'} {g['opponent']}"}
                   for g in games_by_id.values()]
    admin_outlets = sorted({r["outlet"] for r in load(spath) if r.get("outlet")}) if os.path.exists(spath) else []
    admin_data = {"players": admin_players, "games": admin_games, "outlets": admin_outlets, "current": CURRENT,
                  "game_seasons": sorted({g["season"] for g in games_by_id.values()}, reverse=True),
                  "all_seasons": sorted({h["season"] for h in history}, reverse=True)}
    render("admin.html", "admin/index.html", seasons=sorted(PAGE_SEASONS, reverse=True), players=admin_players,
           admin_json=Markup(json.dumps(admin_data, ensure_ascii=False).replace("</", "<\\/")))
    PAGES.remove("admin/index.html")


def not_found_page():
    """The 404 page. Vercel serves it for any missing address, at any depth, so its links start at
    the site root."""
    # (clean URLs make every link root-relative anyway; locally, root="/" does it).
    render("404.html", "404.html", root="" if CLEAN_URLS else "/", season=DATA_SEASONS[-1],
           next_game=next((g for g in UPCOMING if g["season"] == CURRENT), None))
    PAGES.remove("404.html")


def feeds_and_sitemap():
    """The current season's schedule as a calendar feed (subscribe links on the season and home
    pages), the game dates file, the sitemap and robots.txt."""
    with open(os.path.join(OUT, CAL_FILE), "w", newline="") as f:
        f.write(calendar_feed(CURRENT))

    # ---- the current season's game dates, read by the GitHub refresh workflow to rebuild often on game nights
    with open(os.path.join(OUT, "game-days.json"), "w") as f:
        json.dump(sorted({g["date"] for g in games_by_season.get(CURRENT, [])}), f)

    # ---- sitemap and robots.txt, so search engines find every player, game and season page
    with open(os.path.join(OUT, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for p in sorted(PAGES, key=lambda p: (p.count("/"), p)):
            f.write(f"  <url><loc>{SITE_URL}{clean_path(p)}</loc></url>\n")
        f.write("</urlset>\n")
    with open(os.path.join(OUT, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\nDisallow: /admin\n\nSitemap: {SITE_URL}/sitemap.xml\n")
