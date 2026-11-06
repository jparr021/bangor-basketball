"""Load the data (data/*.csv, overrides/) into games, player rows, rosters, film, stories and photos."""
from sitegen.common import *  # noqa: F401,F403  (everything defined before this part of the build)


# ---------------------------------------------------------------- load data
games = load(os.path.join(DATA, "games.csv"))
pg = load(os.path.join(DATA, "player_games.csv"))
opg = load(os.path.join(DATA, "opponent_player_games.csv"))
pseasons = load(os.path.join(DATA, "player_seasons.csv"))
pcareers = load(os.path.join(DATA, "player_careers.csv"))
history = load(os.path.join(OV, "season_history.csv"))
hist_records = load(os.path.join(OV, "historical_records.csv"))
with open(os.path.join(DATA, "records.json")) as f:
    REC = json.load(f)

STATS = ["pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "to", "pf", "chg"]
for r in pg:
    r["name"] = canon(r["name"])
    r["slug"] = slug(r["name"])
    for k in STATS + ["min"]:
        r[k] = num(r.get(k))
for r in opg:
    for k in STATS + ["min"]:
        r[k] = num(r.get(k))
for r in pseasons + pcareers:
    for k in STATS + ["gp"]:
        r[k] = num(r.get(k))
    r["slug"] = slug(r["name"])

# Seasons before the stat sheets known only from a printed list of results (a yearbook page): no dates,
# home/away or box scores, so they stay out of games.csv and get a results-only season page.
RESULTS_ONLY = defaultdict(list)
if os.path.exists(os.path.join(OV, "season_results.csv")):
    for r in load(os.path.join(OV, "season_results.csv")):
        r["bs"], r["os"] = num(r["bangor_score"]), num(r["opp_score"])
        r["scored"] = r["bs"] is not None and r["os"] is not None
        # a game whose score is partly lost gives its result in the result column
        r["result"] = (r.get("result") or "").strip().upper() or (
            ("W" if r["bs"] > r["os"] else ("L" if r["bs"] < r["os"] else "T")) if r["scored"] else "")
        r["opp_slug"] = slug(r["opponent"])
        nt = (r.get("note") or "").lower()
        r["game_type"] = "playoff" if re.search(r"regional|sectional|district|state|wiaa", nt) else (
            "tournament" if "tournament" in nt else "regular")
        RESULTS_ONLY[r["season"]].append(r)
    for gs in RESULTS_ONLY.values():
        # a game whose place in the season isn't known has no game number: it sorts by date
        gs.sort(key=lambda r: (int(r["game"]) if r["game"] else 0, r.get("date") or ""))
        for r in gs:
            r["anchor"] = r["game"] or (r.get("date") or "").replace("-", "")


def clipping_details():
    """Quarter scores, a recap and leading scorers from newspaper clippings (line_scores.csv and
    newspaper_stats.csv) for results-only games, which have no game page: shown on the season page."""
    by_date = {g["date"]: g for gs in RESULTS_ONLY.values() for g in gs if g.get("date")}
    lp, np_ = os.path.join(OV, "line_scores.csv"), os.path.join(OV, "newspaper_stats.csv")
    for r in (load(lp) if os.path.exists(lp) else []):
        g = by_date.get(r["date"])
        if not g:
            continue
        if r.get("period_labels"):
            labels = r["period_labels"].split("|")
            g["periods"] = {"labels": [("Q" + l if l.isdigit() else l) for l in labels],
                            "bangor": r["bangor_periods"].split("|"), "opp": r["opp_periods"].split("|")}
        g["recap"] = r.get("recap", "")
        g["clip_source"] = r.get("source", "")
    for r in (load(np_) if os.path.exists(np_) else []):
        g = by_date.get(r["date"])
        if not g:
            continue
        bits = [f"{int(float(r[k]))} {lab}" for k, lab in (("tpm", "3PM"), ("reb", "reb"), ("ast", "ast"), ("blk", "blk"))
                if r.get(k) not in ("", None) and float(r[k])]
        side = "bangor" if r["team"].strip().lower() == "bangor" else "opp"
        g.setdefault("leaders", {"bangor": [], "opp": []})[side].append(
            {"name": r["name"], "slug": slug(r["name"]), "pts": fmt_int(num(r["pts"])) if r.get("pts") else "",
             "extra": ", ".join(bits), "pts_raw": num(r.get("pts")) or 0})
    for g in by_date.values():  # a clipping that lists every Bangor player's points
        if g.get("leaders") and g.get("bs") is not None:
            g["clip_complete"] = sum(p["pts_raw"] for p in g["leaders"]["bangor"]) == g["bs"]

# Rosters from game programs (overrides/rosters.csv), for seasons with no player stats: number, name,
# position, height and grade, with the class year worked out from the grade.
ROSTERS = defaultdict(list)
if os.path.exists(os.path.join(OV, "rosters.csv")):
    for r in load(os.path.join(OV, "rosters.csv")):
        gr = num(r.get("grade"))
        r["class_year"] = int(r["season"][:4]) + 1 + (12 - int(gr)) if gr else ""
        r["slug"] = slug(r["name"])
        ROSTERS[r["season"]].append(r)
    for rs in ROSTERS.values():
        rs.sort(key=lambda r: int(num(r["number"]) or 0))

# Team totals for a game with no player box score (overrides/team_game_stats.csv): one row for Bangor and
# one for the opponent, from a yearbook's game-by-game team stats.
TEAM_GAME = defaultdict(dict)
if os.path.exists(os.path.join(OV, "team_game_stats.csv")):
    for r in load(os.path.join(OV, "team_game_stats.csv")):
        side = "bangor" if r["team"].strip().lower() == "bangor" else "opp"
        TEAM_GAME[r["date"]][side] = {**{k: num(r.get(k)) for k in STATS}, "source": r.get("source", "")}

# The printed team totals line of a season stat sheet (a "Team" row in overrides/season_totals.csv)
TEAM_LINE = {}
_TCOL = {"pts": "PTS", "fgm": "FGM", "fga": "FGA", "tpm": "3PM", "tpa": "3PA", "ftm": "FTM", "fta": "FTA", "oreb": "OFF",
         "dreb": "DEF", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK", "to": "TO", "pf": "PF"}
if os.path.exists(os.path.join(OV, "season_totals.csv")):
    for r in load(os.path.join(OV, "season_totals.csv")):
        if r["name"].strip().lower() == "team":
            TEAM_LINE[r["season"]] = {k: num(r.get(c)) for k, c in _TCOL.items()}

games_by_id = OrderedDict((g["game_id"], g) for g in sorted(games, key=lambda g: g["date"]))
games_by_season = defaultdict(list)
for g in games_by_id.values():
    g["bs"], g["os"] = num(g["bangor_score"]), num(g["opp_score"])
    g["opp_slug"] = slug(g["opponent"])
    games_by_season[g["season"]].append(g)
# Archive stories for a season (overrides/stories/*.txt): "key: value" lines, then "---", then the text.
# "# " starts a part, "## " a section, "> " a note set apart; other lines are paragraphs.
def load_story(path):
    with open(path, encoding="utf-8") as f:
        head, _, body = f.read().partition("\n---\n")
    st = dict(l.split(": ", 1) for l in head.strip().splitlines() if ": " in l)
    parts, cur = [], None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("## ") or line.startswith("# "):
            cur = {"title": line.lstrip("# ").strip(), "level": 2 if line.startswith("# ") else 3, "blocks": []}
            parts.append(cur)
            continue
        if cur is None:
            cur = {"title": "", "level": 3, "blocks": []}
            parts.append(cur)
        cur["blocks"].append(("note", line[2:]) if line.startswith("> ") else ("p", line))
    st["parts"] = parts
    return st


STORIES = {}
for _p in sorted(glob.glob(os.path.join(OV, "stories", "*.txt"))):
    _st = load_story(_p)
    STORIES[_st["season"]] = _st

def complete_schedule(s, gs):
    """A printed results list with every game's date and site, and every game the record book counts."""
    if not all(g.get("date") and g.get("site") and g.get("scored") for g in gs):
        return False  # a game with no date, site or score keeps the season a results page
    h = next((r for r in load(os.path.join(OV, "season_history.csv")) if r["season"] == s), None)
    n = sum(int(h[k]) for k in ("w", "l", "t") if h and (h.get(k) or "").strip().isdigit()) if h else 0
    return not n or len(gs) == n


# Results-only games with a date and site (a printed schedule recap) count in the head-to-head records on
# opponent pages. They have no box score, so they link to the game's row on the season page.
DATED_RESULTS = []
for s, gs in RESULTS_ONLY.items():
    if s in games_by_season or not complete_schedule(s, gs):
        continue
    for g in gs:
        g.update(game_id="", box_score="none", has_video=False, href=f"../seasons/{s}.html#g{g['anchor']}",
                 game_type="playoff" if re.search(r"regional|sectional|state", g.get("note", ""), re.I) else "regular")
        DATED_RESULTS.append(g)
# every opponent in games.csv (or a dated results-only game) gets a page
OPP_PAGES = {g["opp_slug"] for g in games_by_id.values()} | {g["opp_slug"] for g in DATED_RESULTS}
pg_by_game = defaultdict(list)
pg_by_player = defaultdict(list)
for r in pg:
    pg_by_game[r["game_id"]].append(r)
    pg_by_player[r["slug"]].append(r)
opg_by_game = defaultdict(list)
for r in opg:
    opg_by_game[r["game_id"]].append(r)
ps_by_season = defaultdict(list)
ps_by_player = defaultdict(list)
for r in pseasons:
    ps_by_season[r["season"]].append(r)
    ps_by_player[r["slug"]].append(r)
career_by_player = {r["slug"]: r for r in pcareers}
hist_by_season = OrderedDict((h["season"], h) for h in history)
DATA_SEASONS = sorted(games_by_season)
try:
    from zoneinfo import ZoneInfo
    NOW = dt.datetime.now(ZoneInfo("America/Chicago"))  # Wisconsin time, even on Vercel's UTC servers
except Exception:  # noqa: BLE001
    NOW = dt.datetime.now()
TODAY = NOW.date()

# ---- site settings (overrides/site.json): the corrections form
SETTINGS = {}
if os.path.exists(os.path.join(OV, "site.json")):
    with open(os.path.join(OV, "site.json")) as f:
        SETTINGS = json.load(f)
FORM_URL = (SETTINGS.get("corrections_form_url") or "").strip()
FORM_FIELD = re.sub(r"\D", "", str(SETTINGS.get("corrections_page_field") or ""))
# Vercel Web Analytics (overrides/site.json "vercel_analytics"): only on Vercel, where /_vercel/insights exists
ANALYTICS = SETTINGS.get("vercel_analytics") is True and os.environ.get("VERCEL") == "1"


# ---- photos (overrides/photos.csv, image files in overrides/photos/): team photos on season pages and
# headshots on player pages. Pages without one show a placeholder asking for it.
PHOTO_DIR = os.path.join(OV, "photos")
TEAM_PHOTOS = defaultdict(list)
PLAYER_PHOTOS = {}
if os.path.exists(os.path.join(OV, "photos.csv")):
    for _r in load(os.path.join(OV, "photos.csv")):
        _img = (_r.get("image") or "").strip()
        _kind = (_r.get("kind") or "").strip().lower()
        if not _img:
            continue
        _p = {"src": _img, "local": not re.match(r"https?://", _img), "url": _img, "w": None, "h": None,
              "caption": (_r.get("caption") or "").strip(), "credit": (_r.get("credit") or "").strip()}
        if _kind == "team" and (_r.get("season") or "").strip():
            TEAM_PHOTOS[_r["season"].strip()].append(_p)
        elif _kind == "player" and (_r.get("player") or "").strip():
            PLAYER_PHOTOS.setdefault(slug(canon(_r["player"])), _p)


def publish_photos():
    """Copy each photo in overrides/photos/ into the site, shrunk to a web size (team photos 1600 px wide,
    headshots 600 px) as a JPEG. A photo whose file is missing is dropped (and listed in the build log)."""
    from PIL import Image, ImageOps
    out_dir = os.path.join(OUT, "static", "photos")
    os.makedirs(out_dir, exist_ok=True)
    for photos, max_w in ((p for ps in TEAM_PHOTOS.values() for p in ps), 1600), (PLAYER_PHOTOS.values(), 600):
        for p in list(photos):
            if not p["local"]:
                continue
            path = os.path.join(PHOTO_DIR, p["src"])
            if not os.path.exists(path):
                print(f"photos: {p['src']} is listed in overrides/photos.csv but isn't in overrides/photos/")
                p["missing"] = True
                continue
            name = slug(os.path.splitext(p["src"])[0]) + ".jpg"
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                if im.width > max_w:
                    im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
                im.save(os.path.join(out_dir, name), "JPEG", quality=82, optimize=True, progressive=True)
                p["w"], p["h"] = im.width, im.height
            # a version in the address: a browser that asked for the photo before it was published (the admin
            # page's list does, right after an upload) may have kept the "not found" for a day (static files
            # are cached for a day); a new address skips that
            import hashlib
            with open(os.path.join(out_dir, name), "rb") as f:
                v = hashlib.md5(f.read()).hexdigest()[:8]
            p["url"] = f"static/photos/{name}?v={v}"
    for s in list(TEAM_PHOTOS):
        TEAM_PHOTOS[s] = [p for p in TEAM_PHOTOS[s] if not p.get("missing")]
    for k in [k for k, p in PLAYER_PHOTOS.items() if p.get("missing")]:
        del PLAYER_PHOTOS[k]


def corrections_link(page_url):
    """The corrections form, with the visitor's page filled in when the form's 'Page' question is set up."""
    if not FORM_URL:
        return ""
    if not FORM_FIELD:
        return FORM_URL
    from urllib.parse import quote
    return f"{FORM_URL}{'&' if '?' in FORM_URL else '?'}usp=pp_url&entry.{FORM_FIELD}={quote(page_url, safe='')}"


# ---- current season: live W-L from the games, even before the record book is updated
with open(os.path.join(OV, "current_season.json")) as f:
    CURRENT = json.load(f).get("season", "")
if CURRENT in games_by_season:
    done = [g for g in games_by_season[CURRENT] if g["result"] in ("W", "L")]
    h = hist_by_season.get(CURRENT)
    if h is None:
        prev = history[-1] if history else {}
        h = {"season": CURRENT, "w": "", "l": "", "t": "", "coach": prev.get("coach", ""), "notes": ""}
        history.append(h)
        hist_by_season[CURRENT] = h
    h["w"] = str(sum(g["result"] == "W" for g in done))
    h["l"] = str(sum(g["result"] == "L" for g in done))

# ---- game status, livestreams and film
YT_RE = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|embed/|live/|shorts/))([A-Za-z0-9_-]{11})")


def youtube_id(url):
    m = YT_RE.search(url or "")
    return m.group(1) if m else ""


film_by_date = defaultdict(list)
for r in load(os.path.join(OV, "game_film.csv")):
    if r.get("date") and youtube_id(r.get("youtube_url")) and r.get("matched_by") != "removed":
        film_by_date[r["date"].strip()].append(r)
for g in games_by_id.values():
    d = dt.date.fromisoformat(g["date"])
    # pending: a current-season game that has been played but whose score isn't on the sheet yet
    off = re.search(r"postpon|cancel|no result", g["event"], re.I)
    g["status"] = "final" if g["result"] else ("upcoming" if d >= TODAY and not off else
                                               "pending" if g["season"] == CURRENT and not off else "no_result")
    g["is_today"] = d == TODAY
    films = film_by_date.get(g["date"], [])
    if len(films) > 1:  # double-header etc.: match on opponent
        films = [f for f in films if slug(f["opponent"]) == g["opp_slug"]] or films[:1]
    g["film_id"] = youtube_id(g.get("film_url")) or (youtube_id(films[0]["youtube_url"]) if films else "")
    g["film_title"] = films[0].get("title", "") if films else ""
# Hudl replays / recaps (overrides/hudl_video.csv). YouTube always wins the main spot;
# Hudl stays as a secondary link. A current-season Hudl stream link becomes the replay.
hudl = defaultdict(dict)
hpath = os.path.join(OV, "hudl_video.csv")
if os.path.exists(hpath):
    for r in load(hpath):
        hudl[r["date"]][r["kind"]] = r
GAME_VIDEO_RE = re.compile(r"hudl\.com/.*/watch\?|youtube\.com/(watch|live/)|youtu\.be/|nfhsnetwork\.com/events/"
                           r"|justagame\.com/watch/", re.I)
for g in games_by_id.values():
    h = hudl.get(g["date"], {})
    url = g.get("stream_url") or ""
    # a stream link only counts as a replay if it points at one specific game (not a channel/school page)
    g["replayable"] = bool(GAME_VIDEO_RE.search(url))  # the live link stays useful as a replay after the game
    g["replay_url"] = url if g["status"] == "final" and g["replayable"] else ""
    full = h.get("full")
    if not full and g["replay_url"] and "hudl.com" in url:
        full = {"url": url, "access": "free"}
    g["hudl_full"] = full
    g["hudl_recap"] = h.get("recap")
    g["has_video"] = bool(g["film_id"] or full or g["hudl_recap"])
# Local news stories (overrides/news_stories.csv, filled by scripts/match_stories.py). A headline that
# an outlet posted as both an article and a video becomes one entry with both links.
STORIES_BY_DATE = defaultdict(OrderedDict)
FEATURES_BY_PLAYER = defaultdict(list)
spath = os.path.join(OV, "news_stories.csv")
if os.path.exists(spath):
    for r in sorted(load(spath), key=lambda r: (r["published"], r["kind"] != "article")):
        if not r.get("url") or r.get("matched_by") == "removed":  # removed on the admin page
            continue
        if r.get("player") and not r.get("game_date"):
            FEATURES_BY_PLAYER[slug(canon(r["player"]))].append(r)
            continue
        key = (r["outlet"], re.sub(r"\W+", " ", r["title"].lower()).strip())
        s = STORIES_BY_DATE[r.get("game_date", "")].setdefault(
            key, {"outlet": r["outlet"], "title": r["title"], "access": r.get("access", ""), "links": []})
        if all(l["url"] != r["url"] for l in s["links"]):
            s["links"].append({"kind": r["kind"], "url": r["url"]})
for g in games_by_id.values():
    entries = list(STORIES_BY_DATE.get(g["date"], {}).values())
    # a station's highlight video (its own headline) folds into that station's written recap of the game
    for s in [e for e in entries if all(l["kind"] == "video" for l in e["links"])]:
        recap = next((e for e in entries if e["outlet"] == s["outlet"] and any(l["kind"] == "article" for l in e["links"])), None)
        if recap:
            recap["links"] += [l for l in s["links"] if l not in recap["links"]]
            entries.remove(s)
    g["stories"] = sorted(entries, key=lambda s: (s["access"] == "subscriber", s["outlet"], s["title"]))
FILM_GAMES = [g for g in games_by_id.values() if g["film_id"]]
HUDL_ONLY = [g for g in games_by_id.values() if not g["film_id"] and (g["hudl_full"] or g["hudl_recap"])]
UPCOMING = [g for g in games_by_id.values() if g["status"] == "upcoming"]
# Game-day banner candidates. Pages are rebuilt every few hours, so the next few days' games are written
# into every page and site.js shows the one that is on today's date (Wisconsin time) when a visitor opens it.
GAMEDAY = [g for g in UPCOMING if g["season"] == CURRENT and (dt.date.fromisoformat(g["date"]) - TODAY).days <= 2]


def site(g):
    return {"home": "vs", "away": "@", "neutral": "vs"}.get(g["site"], "vs")


def stat_cols(rows, keys):
    """Only show columns that have at least one tracked value."""
    return [k for k in keys if any(r.get(k) is not None for r in rows)]
