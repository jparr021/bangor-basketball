"""Find local news stories about Bangor boys basketball games and link them to the games.

Usage:
  .venv/bin/python scripts/match_stories.py              # the last 21 days (what the scheduled workflow runs)
  .venv/bin/python scripts/match_stories.py --days 60    # a longer recent window
  .venv/bin/python scripts/match_stories.py --all        # every season since 2002-03 (backfill; takes a while)
  .venv/bin/python scripts/match_stories.py --season 2017-18

Sources: WKBT News 8 (news8000.com), WXOW 19 (wxow.com) and the La Crosse Tribune (which includes
the old Coulee News). All three run the same publishing system, whose public search returns each
story's headline, date, tagged schools and text. A story is linked to a game when:
  - its headline mentions Bangor,
  - it's about boys basketball (girls-only stories are skipped),
  - the opponent is named in the headline or story, within a few days of a Bangor game against them,
  - and the final score appears in it, or it says "boys". Anything less certain goes to review.

Add-only: rows already in overrides/news_stories.csv are never changed or removed, and rows marked
matched_by=manual are yours. Nothing is written if every source fails.

Writes:
  overrides/news_stories.csv   linked stories (game stories, and player features like Play of the Week)
  data/stories_review.csv      stories it wasn't sure about, with the reason (add good ones to the file above)
"""
import csv, datetime as dt, html, json, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORIES = os.path.join(ROOT, "overrides", "news_stories.csv")
REVIEW = os.path.join(ROOT, "data", "stories_review.csv")
FIELDS = ["published", "outlet", "kind", "title", "url", "access", "game_date", "opponent", "player", "matched_by"]
REVIEW_FIELDS = ["published", "outlet", "kind", "title", "url", "reason", "candidates"]
UA = "bangor-bb-site-builder (+https://bangor-basketball.vercel.app)"

SOURCES = [  # (outlet name, site, search words, access)
    ("WKBT News 8", "www.news8000.com", "bangor", "free"),
    ("WXOW 19", "www.wxow.com", "bangor", "free"),
    ("La Crosse Tribune", "lacrossetribune.com", "bangor basketball", "subscriber"),
]
# extra names for opponents seen in headlines and stories (school nicknames only where confirmed)
OPP_ALIASES = {
    "Gale-Ettrick-Trempealeau": ["get", "g e t", "redhawks"], "Melrose-Mindoro": ["mel min", "melmin", "mel-min"],
    "Black River Falls": ["brf"], "Wonewoc-Center": ["wonewoc"], "Cochrane-Fountain City": ["c fc", "cfc"],
    "Alma Center Lincoln": ["lincoln", "acl"], "Blair-Taylor": ["blair"], "Gilmanton/Independence": ["gilmanton"],
    "Luther": ["onalaska luther"], "Aquinas": ["la crosse aquinas"], "McDonell Central": ["mcdonell"],
    "Green Bay NEW Lutheran": ["new lutheran", "n e w lutheran"], "Royall": ["panthers"],
    "Coulee Christian/Providence": ["coulee christian"],
}
OTHER_SPORTS = re.compile(r"\b(wrestl|volleyball|football|softball|baseball|track|cross country|golf|soccer|hockey|"
                          r"swim|gymnast|fire|crash|police|sheriff|maine)\w*", re.I)


def norm(s):
    return " " + re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip() + " "


def text_of(v):
    if isinstance(v, list):
        v = " ".join(str(x) for x in v)
    return html.unescape(re.sub(r"<[^>]+>", " ", str(v or "")))


def search(site, words, d1, d2):
    """Every search result between two dates (pages of 50)."""
    rows, seen = [], set()
    for page in range(20):
        q = urllib.parse.urlencode({"f": "json", "q": words, "l": 50, "o": page * 50, "s": "start_time", "sd": "desc",
                                    "d1": d1.isoformat(), "d2": d2.isoformat()})
        data = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(f"https://{site}/search/?{q}", headers={"User-Agent": UA})
                body = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
                if body.strip():
                    data = json.loads(body, strict=False)
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(4 * (attempt + 1))
        if data is None:
            raise RuntimeError(f"{site} search failed")
        for r in data.get("rows", []):
            if r.get("uuid") not in seen:
                seen.add(r.get("uuid"))
                rows.append(r)
        time.sleep(1.5)  # be polite
        if len(data.get("rows", [])) < 50:
            break
    return rows


def main():
    args = sys.argv[1:]
    with open(os.path.join(ROOT, "data", "games.csv")) as f:
        games = [g for g in csv.DictReader(f) if g["result"]]
    for g in games:
        g["d"] = dt.date.fromisoformat(g["date"])
    with open(os.path.join(ROOT, "data", "player_seasons.csv")) as f:
        players = sorted({r["name"] for r in csv.DictReader(f)}, key=len, reverse=True)
    opp_terms = {}
    for o in {g["opponent"] for g in games}:
        terms = {norm(o).strip(), norm(o.split("/")[0]).strip(), norm(o.split("-")[0]).strip()} | \
                {norm(a).strip() for a in OPP_ALIASES.get(o, [])}
        opp_terms[o] = {t for t in terms if len(t) >= 3}

    # which dates to search
    today = dt.date.today()
    if "--all" in args or "--season" in args:
        seasons = sorted({g["season"] for g in games})
        if "--season" in args:
            seasons = [args[args.index("--season") + 1]]
        windows = [(dt.date(int(s[:4]), 11, 1), dt.date(int(s[:4]) + 1, 3, 31)) for s in seasons]
    else:
        days = int(args[args.index("--days") + 1]) if "--days" in args else 21
        windows = [(today - dt.timedelta(days=days), today)]

    existing = []
    if os.path.exists(STORIES):
        with open(STORIES) as f:
            existing = list(csv.DictReader(f))
    have = {r["url"] for r in existing}
    old_review = []
    if os.path.exists(REVIEW):
        with open(REVIEW) as f:
            old_review = [r for r in csv.DictReader(f) if r["url"] not in have]

    found, review, failures = [], [], 0
    for outlet, site, words, access in SOURCES:
        rows = []
        for d1, d2 in windows:
            try:
                rows += search(site, words, d1, d2)
            except RuntimeError as e:
                failures += 1
                print(f"  {e} for {d1}..{d2}")
        print(f"{outlet}: {len(rows)} results")
        for r in rows:
            if r.get("type") not in ("article", "video"):
                continue
            title = html.unescape(r.get("title") or "").strip()
            url = r.get("url") or ""
            if "bangor" not in title.lower() or url in have:
                continue
            body = text_of(r.get("subheadline")) + " " + text_of(r.get("content"))
            full = title + " " + body
            nt, nf = norm(title), norm(full[:2500])
            if OTHER_SPORTS.search(title) or (" maine " in nf):
                continue
            published = dt.date.fromisoformat(r["starttime"]["iso8601"][:10])
            kind = "video" if r["type"] == "video" else "article"
            base = {"published": published.isoformat(), "outlet": outlet, "kind": kind, "title": title, "url": url,
                    "access": access, "game_date": "", "opponent": "", "player": "", "matched_by": ""}

            # player features, e.g. "News 8 Play of the Week Winner: Sawyer Jacobson, Bangor Boys Basketball"
            if "play of the week" in title.lower() and "girls" not in title.lower():
                who = next((p for p in players if norm(p) in nt), None)
                if who:
                    found.append(dict(base, player=who, matched_by="player feature"))
                else:
                    review.append(dict(base, reason="Play of the Week: player not recognized", candidates=""))
                continue

            girls = " girls " in nf or " lady " in nf
            boys = " boys " in nf
            if girls and not boys:
                continue  # Bangor girls story
            if " basketball " not in nf and not any(abs((g["d"] - published).days) <= 1 for g in games):
                continue  # not basketball and no game nearby
            scores = set(re.findall(r"\b(\d{2,3})\s*[-–]\s*(\d{2,3})\b", title + " " + body[:1500]))
            scores |= {(a, b) for a, b in re.findall(r"\b[A-Z][\w.'-]*(?: [A-Z][\w.'-]*)* (\d{2,3}), Bangor (\d{2,3})\b", title)}
            scores |= {(b, a) for b, a in re.findall(r"\bBangor (\d{2,3}), [A-Z][\w.'-]*(?: [A-Z][\w.'-]*)* (\d{2,3})\b", title)}

            def score_match(g):
                return (g["bangor_score"], g["opp_score"]) in scores or (g["opp_score"], g["bangor_score"]) in scores

            near = [g for g in games if 0 <= (published - g["d"]).days <= 7]
            in_title = [g for g in near if any(f" {t} " in nt for t in opp_terms[g["opponent"]])]
            in_text = [g for g in near if any(f" {t} " in nf for t in opp_terms[g["opponent"]])]
            cands = in_title or in_text
            # older games (published 4-7 days later) only count with the score in the story
            cands = [g for g in cands if (published - g["d"]).days <= 3 or score_match(g)]
            if len(cands) > 1:
                cands = [g for g in cands if score_match(g)] or cands
            if len(cands) == 1:
                g = cands[0]
                link = dict(base, game_date=g["date"], opponent=g["opponent"])
                if score_match(g):
                    found.append(dict(link, matched_by="opponent + score"))
                elif boys and (g in in_title or " basketball " in nt or
                               (" boys " in nt and not any(f" {t} " in nt for o, ts in opp_terms.items()
                                                           if o != g["opponent"] for t in ts))):
                    found.append(dict(link, matched_by="opponent + boys"))
                elif boys:
                    review.append(dict(base, reason="says boys, but the headline names neither the opponent nor basketball",
                                       candidates=f"{g['date']} {g['opponent']}"))
                elif scores:
                    review.append(dict(base, reason="the score in the story doesn't match this game (girls game?)",
                                       candidates=f"{g['date']} {g['opponent']} {g['bangor_score']}-{g['opp_score']}"))
                else:
                    review.append(dict(base, reason="opponent matches, but nothing says boys or gives the score",
                                       candidates=f"{g['date']} {g['opponent']}", _link=link))
            elif len(cands) > 1:
                review.append(dict(base, reason=f"{len(cands)} possible games",
                                   candidates="; ".join(f"{g['date']} {g['opponent']}" for g in cands)))
            else:
                recent = [g for g in near if (published - g["d"]).days <= 2]
                if recent and (boys or " basketball " in nf):
                    review.append(dict(base, reason="no opponent named; nearest game listed",
                                       candidates="; ".join(f"{g['date']} {g['opponent']}" for g in recent)))

    # highlight videos have no text: link one when the same outlet has a confirmed boys story on that game
    confirmed = {(r["outlet"], r["game_date"]) for r in found + existing if r.get("game_date")}
    still = []
    for r in review:
        link = r.pop("_link", None)
        if link and (link["outlet"], link["game_date"]) in confirmed:
            found.append(dict(link, matched_by="opponent + same outlet's boys story"))
        else:
            still.append(r)
    review = still

    if failures == len(SOURCES) * len(windows):
        print("every search failed; nothing changed")
        return
    # one row per story URL
    new, urls = [], set(have)
    for r in found:
        if r["url"] not in urls:
            urls.add(r["url"])
            new.append(r)
    rows = sorted(existing + new, key=lambda r: (r["game_date"] or r["published"], r["outlet"], r["title"]))
    with open(STORIES, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)
    rev, seen = [], set(urls)
    for r in review + old_review:
        if r["url"] not in seen:
            seen.add(r["url"])
            rev.append({k: r.get(k, "") for k in REVIEW_FIELDS})
    rev.sort(key=lambda r: r["published"], reverse=True)
    with open(REVIEW, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        w.writeheader(); w.writerows(rev)
    print(f"linked {len(new)} new stories ({len(rows)} total); {len(rev)} to review in data/stories_review.csv")
    for r in new:
        print(f"  NEW: {r['game_date'] or r['player']:<16} {r['outlet']:<18} {r['title'][:70]}")


if __name__ == "__main__":
    main()
