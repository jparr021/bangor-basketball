"""Pages: history and coaches, opponents, film, the search index, sheet check, admin, 404,
the calendar feed and the sitemap."""
from sitegen.views import *  # noqa: F401,F403


def history_pages():
    """History, the gaps list, and a page for each coach."""
    render("history.html", "history/index.html", seasons=[season_summary(h["season"]) for h in history],
           coaches=coach_list)
    gap_rows, wanted, gap_sum = gaps_data()
    render("gaps.html", "history/gaps.html", rows=list(reversed(gap_rows)), wanted=wanted, sm=gap_sum, form_url=FORM_URL)
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
    render("opponents.html", "opponents/index.html", opps=olist,
           first=min([DATA_SEASONS[0]] + [o["games"][0]["season"] for o in olist]))
    return olist


def film_index():
    """The game film index."""
    if FILM_GAMES or HUDL_ONLY:
        by_season = OrderedDict()
        for g in sorted(FILM_GAMES + HUDL_ONLY, key=lambda g: g["date"], reverse=True):
            by_season.setdefault(g["season"], []).append(g)
        render("film.html", "film/index.html", by_season=by_season, total=len(FILM_GAMES) + len(HUDL_ONLY),
               youtube=len(FILM_GAMES), hudl_only=len(HUDL_ONLY))


def search_index(plist, olist, classes):
    """The site search index (loaded by site.js the first time someone opens search)."""
    def season_label(s):
        return s.replace("-", "–")
    idx = []
    for p in plist:
        sub = f"Player · {p['years']}" + (f" · {p['pts']} pts" if p["pts"] else "")
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
