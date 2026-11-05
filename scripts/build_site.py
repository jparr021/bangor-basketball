"""Build the static website into site/ from data/ and overrides/.

Run the whole pipeline:
  .venv/bin/python scripts/convert.py && .venv/bin/python scripts/records.py && .venv/bin/python scripts/build_site.py
"""
import csv, datetime as dt, glob, json, math, os, posixpath, re, shutil
from collections import defaultdict, OrderedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape

import charts
import share_images
import sheet_check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OV = os.path.join(ROOT, "overrides")
SRC = os.path.join(ROOT, "site-src")
OUT = os.path.join(ROOT, "site")

PLAYER_ALIASES = {"Konnor Kaiser": "Connor Kaiser"}

# The site's public address, used for share previews, canonical links and the sitemap.
# On Vercel this comes from the project's production domain automatically: the
# *.vercel.app address today, and a custom domain as soon as one is added. SITE_URL overrides it.
_vercel_host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
SITE_URL = (os.environ.get("SITE_URL") or (f"https://{_vercel_host}" if _vercel_host
                                           else "https://bangor-basketball.vercel.app")).rstrip("/")
# Clean links (/players/hayden-massman instead of players/hayden-massman.html) when building on
# Vercel, which serves them (vercel.json cleanUrls). Local builds keep .html links so the files
# open straight from disk. Set CLEAN_URLS=1 to force clean links.
CLEAN_URLS = os.environ.get("VERCEL") == "1" or os.environ.get("CLEAN_URLS") == "1"


# ---------------------------------------------------------------- helpers
def load(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def slug(name):
    s = str(name).lower().replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def canon(name):
    name = str(name).strip()
    return PLAYER_ALIASES.get(name, name)


def fmt_int(v):
    if v is None or v == "":
        return ""
    v = float(v)
    return f"{int(v):,}" if v.is_integer() else f"{v:.1f}"


def fmt_pct(m, a):
    if m is None or a in (None, 0):
        return ""
    return f"{100 * m / a:.1f}%"


def fmt_avg(t, g):
    if t is None or not g:
        return ""
    return f"{t / g:.1f}"


def fmt_date(iso, style="short"):
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso)
    if style == "long":
        return d.strftime("%A, %B %-d, %Y")
    return d.strftime("%b %-d, %Y")


def season_end_year(season):
    return int(season[:4]) + 1


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
        gs.sort(key=lambda r: int(r["game"]))


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

# Results-only games with a date and site (a printed schedule recap) count in the head-to-head records on
# opponent pages. They have no box score, so they link to the game's row on the season page.
DATED_RESULTS = []
for s, gs in RESULTS_ONLY.items():
    if s in games_by_season or not all(g.get("date") and g.get("site") for g in gs):
        continue
    for g in gs:
        g.update(game_id="", box_score="none", has_video=False, href=f"../seasons/{s}.html#g{g['game']}",
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
    if r.get("date") and youtube_id(r.get("youtube_url")):
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
        if not r.get("url"):
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
        entries = [dict(e, source="news" if games_by_id.get(e.get("game_id") or "", {}).get("box_source") == "newspaper" else "data")
                   for e in REC.get(scope, {}).get(period, {}).get(stat, [])]
    # record-book entries
    for h in hist_records:
        if (h["scope"], h["period"], h["stat"]) != key or h["value"] == "":
            continue
        dup = any(e.get("name") == h["name"] and (e.get("date") == h["date"] if h["date"] else e.get("season") == h["season"])
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


# ---------------------------------------------------------------- players
PLAYER_PAGES = {}
for slug_, rows in pg_by_player.items():
    PLAYER_PAGES[slug_] = rows[0]["name"]
for r in pseasons:
    PLAYER_PAGES.setdefault(r["slug"], r["name"])


def season_stat_row(r):
    gp = r.get("gp")
    d = {"gp": fmt_int(gp)}
    for k in ["pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "to", "pf", "fgm", "fga", "tpm", "tpa", "ftm", "fta"]:
        d[k] = fmt_int(r.get(k))
    d["ppg"] = fmt_avg(r.get("pts"), gp)
    d["rpg"] = fmt_avg(r.get("reb"), gp)
    d["apg"] = fmt_avg(r.get("ast"), gp)
    d["fg_pct"] = fmt_pct(r.get("fgm"), r.get("fga"))
    d["tp_pct"] = fmt_pct(r.get("tpm"), r.get("tpa"))
    d["ft_pct"] = fmt_pct(r.get("ftm"), r.get("fta"))
    return d


SEASON_COLS = [  # (key, header, needs)
    ("gp", "G", "gp"), ("pts", "PTS", "pts"), ("ppg", "PPG", "pts"),
    ("reb", "REB", "reb"), ("rpg", "RPG", "reb"), ("ast", "AST", "ast"), ("apg", "APG", "ast"),
    ("stl", "STL", "stl"), ("blk", "BLK", "blk"), ("to", "TO", "to"),
    ("fgm", "FGM", "fga"), ("fga", "FGA", "fga"), ("fg_pct", "FG%", "fga"),
    ("tpm", "3PM", "tpa"), ("tpa", "3PA", "tpa"), ("tp_pct", "3P%", "tpa"),
    ("ftm", "FTM", "fta"), ("fta", "FTA", "fta"), ("ft_pct", "FT%", "fta"),
]
BOX_COLS = [("min", "MIN"), ("pts", "PTS"), ("fg", "FG"), ("tp", "3PT"), ("ft", "FT"), ("oreb", "OREB"),
            ("dreb", "DREB"), ("reb", "REB"), ("ast", "AST"), ("stl", "STL"), ("blk", "BLK"), ("to", "TO"),
            ("pf", "PF"), ("chg", "CHG")]


def cols_for(raw_rows):
    return [(k, h) for k, h, need in SEASON_COLS if any(r.get(need) is not None for r in raw_rows)]


def box_row(r):
    def ma(m, a):
        return "" if r.get(a) is None else f"{int(r[m])}-{int(r[a])}"
    d = {k: fmt_int(r.get(k)) for k in ["min", "pts", "oreb", "dreb", "reb", "ast", "stl", "blk", "to", "pf", "chg"]}
    d["fg"], d["tp"], d["ft"] = ma("fgm", "fga"), ma("tpm", "tpa"), ma("ftm", "fta")
    if not d["tp"] and r.get("tpm") is not None:  # makes without attempts (a newspaper box score)
        d["tp"] = fmt_int(r["tpm"])
    return d


def box_cols(rows):
    need = {"fg": ("fga",), "tp": ("tpa", "tpm"), "ft": ("fta",)}
    return [(k, h) for k, h in BOX_COLS
            if any(any(r.get(n) is not None for n in need.get(k, (k,))) for r in rows)]


def box_totals(rows):
    t = {}
    for k in STATS + ["min"]:
        vals = [r[k] for r in rows if r.get(k) is not None]
        t[k] = sum(vals) if vals else None
    return t


# ---------------------------------------------------------------- full career leaderboards
LEADER_STATS = [  # (stat, title, short, tracked-from note)
    ("pts", "Points", "PTS", "Points are in the stat sheets from 2007–08."),
    ("reb", "Rebounds", "REB", "Rebounds are in the stat sheets from 2014–15."),
    ("ast", "Assists", "AST", "Assists are in the stat sheets from 2014–15."),
    ("stl", "Steals", "STL", "Steals are in the stat sheets from 2014–15."),
    ("blk", "Blocks", "BLK", "Blocks are in the stat sheets from 2014–15."),
    ("tpm", "3-pointers", "3PM", "3-pointers made are in the stat sheets from 2014–15."),
    ("ftm", "Free throws", "FTM", "Free throws made are in the stat sheets from 2014–15."),
    ("gp", "Games played", "G", "Games played are counted from the stat sheets, 2007–08 on."),
]


PER_GAME_MIN = 30  # games (where the stat was recorded) to be ranked by per-game average


def career_years(season_text):
    """'1998-99 to 2001-02' -> '1998–2002'; 'Class of 1953' stays."""
    m = re.match(r"(\d{4})-\d{2} to (\d{4})-\d{2}", season_text or "")
    return f"{m.group(1)}–{int(m.group(2)) + 1}" if m else (season_text or "")


def career_boards():
    """Every player's career total for each stat, ranked: stat sheets plus record-book careers."""
    latest = DATA_SEASONS[-1]
    cls_last = {}
    for r in sorted(pg, key=lambda r: r["date"]):
        if r.get("class"):
            cls_last[r["slug"]] = (r["season"], r["class"])
    boards = []
    for stat, title, short, note in LEADER_STATS:
        entries = {}
        for c in pcareers:
            v = c.get(stat)
            if not v or c.get("partial") == "Y":  # stats for only part of the career (2002-03)
                continue
            rows = ps_by_player.get(c["slug"], [])
            seasons = sorted(r["season"] for r in rows)
            ov = c.get("override_note") or ""
            gp = c.get("gp") or 0
            tracked = gp if f"{stat}:" in ov or stat in ("pts", "gp") else sum(r["gp"] or 0 for r in rows if r.get(stat) is not None)
            last_season, cls = cls_last.get(c["slug"], ("", ""))
            entries[c["slug"]] = {
                "name": c["name"], "slug": c["slug"] if c["slug"] in PLAYER_PAGES else None, "value": v,
                "years": f"{seasons[0][:4]}–{season_end_year(seasons[-1])}" if seasons else "",
                "gp": int(gp) if gp else "", "avg": fmt_avg(v, tracked) if stat != "gp" else "",
                "avg_raw": v / tracked if tracked and stat != "gp" else None, "avg_gp": int(tracked or 0),
                "book": f"{stat}:" in ov, "active": bool(seasons) and seasons[-1] == latest and last_season == latest and cls not in ("SR", "Sr", "12"),
            }
        for h in hist_records:
            if (h["scope"], h["period"], h["stat"]) != ("individual", "career", stat) or not h["value"] or not h["name"]:
                continue
            sl = slug(h["name"])
            v = float(h["value"])
            if sl in entries and (entries[sl]["value"] or 0) >= v:
                continue
            prev = entries.get(sl, {})
            gp = int(h["gp"]) if h["gp"] else prev.get("gp", "")
            entries[sl] = {"name": h["name"], "slug": sl if sl in PLAYER_PAGES else None, "value": v,
                           "years": prev.get("years") or career_years(h["season"]), "gp": gp,
                           "avg": fmt_avg(v, gp) if gp and stat != "gp" else "", "book": True, "active": False,
                           "avg_raw": v / int(gp) if gp and stat != "gp" else None, "avg_gp": int(gp or 0)}
        ranked = sorted(entries.values(), key=lambda e: (-e["value"], e["name"]))
        rank, prev_v = 0, None
        for i, e in enumerate(ranked):
            if e["value"] != prev_v:
                rank = i + 1
            prev_v = e["value"]
            e["rank"] = rank
            e["display"] = fmt_int(e["value"])
        for e in ranked:
            e["tied"] = sum(1 for o in ranked if o["rank"] == e["rank"]) > 1
        per_game = []
        if stat != "gp":
            qual = sorted((e for e in ranked if e["avg_raw"] is not None and e["avg_gp"] >= PER_GAME_MIN),
                          key=lambda e: (-round(e["avg_raw"], 1), -e["value"], e["name"]))
            rank, prev_v = 0, None
            for i, e in enumerate(qual):
                a = round(e["avg_raw"], 1)
                if a != prev_v:
                    rank = i + 1
                prev_v = a
                per_game.append(dict(e, pg_rank=rank))
            for e in per_game:
                e["pg_tied"] = sum(1 for o in per_game if o["pg_rank"] == e["pg_rank"]) > 1
        boards.append({"stat": stat, "title": title, "short": short, "note": note, "entries": ranked,
                       "has_avg": stat != "gp", "per_game": per_game, "partial": partial_known(stat)})
    return boards


# ---------------------------------------------------------------- render
env = Environment(loader=FileSystemLoader(os.path.join(SRC, "templates")), autoescape=select_autoescape(["html"]))
env.filters["d"] = fmt_date
env.filters["n"] = fmt_int
BUILT = TODAY.strftime("%B %-d, %Y")
BUILD_ID = dt.datetime.now().strftime("%Y%m%d%H%M")  # cache-buster for the search index


PAGES = []  # every page written, for the sitemap


def clean_path(path):
    """'players/x.html' -> '/players/x', 'seasons/index.html' -> '/seasons', 'index.html' -> '/'."""
    p = path[:-5] if path.endswith(".html") else path
    if p == "index":
        return "/"
    if p.endswith("/index"):
        p = p[:-6]
    return "/" + p


LOCAL_LINK_RE = re.compile(r'\b(href|src)="([^"#?:]+)([?#][^"]*)?"')


def absolute_links(html, page):
    """Rewrite relative links into root-relative clean URLs, resolved from the page's own path."""
    def fix(m):
        attr, target, tail = m.group(1), m.group(2), m.group(3) or ""
        if target.startswith("/"):
            return m.group(0)
        full = posixpath.normpath(posixpath.join(posixpath.dirname(page), target))
        url = clean_path(full) if attr == "href" and full.endswith(".html") else "/" + full
        return f'{attr}="{url}{tail}"'
    return LOCAL_LINK_RE.sub(fix, html)


SHARE_HOST = re.sub(r"^https?://", "", SITE_URL)


def share(kind, key, draw, alt, *args):
    """Draw one link-preview image into site/static/share/ and return (absolute URL, alt text) for render().
    The URL carries a short hash of the image, so a preview that changed (a new score) is fetched fresh."""
    import hashlib
    rel = f"static/share/{kind}/{key}.png"
    full = os.path.join(OUT, rel)
    draw(full, SHARE_HOST, *args)
    with open(full, "rb") as f:
        v = hashlib.md5(f.read()).hexdigest()[:8]
    return {"share_image": f"{SITE_URL}/{rel}?v={v}", "share_alt": alt}


def game_share(g):
    kind = {"playoff": "Playoff", "tournament": "Tournament"}.get(g["game_type"], "Conference" if g["conference"] == "Y" else "")
    where = {"away": "Away", "neutral": "Neutral site"}.get(g["site"], "Home")
    label = " · ".join(x for x in (kind, where) if x)
    d = dt.date.fromisoformat(g["date"])
    when = d.strftime("%b %-d, %Y") if g["result"] else d.strftime("%a, %b %-d, %Y")
    if g["result"] in ("W", "L"):
        alt = f"Final: Bangor {g['bangor_score']}, {g['opponent']} {g['opp_score']}, {fmt_date(g['date'])}"
    else:
        alt = f"Bangor {'at' if g['site'] == 'away' else 'vs'} {g['opponent']}, {fmt_date(g['date'])}"
    return share("games", g["game_id"], share_images.game_card, alt, g, when, label)


def render(tpl, path, **ctx):
    depth = path.count("/")
    ctx.setdefault("root", "../" * depth)
    ctx["built"] = BUILT
    ctx["facts"] = FACTS
    ctx["latest_season"] = DATA_SEASONS[-1]
    ctx["has_film"] = bool(FILM_GAMES or HUDL_ONLY)
    ctx["site_url"] = SITE_URL
    ctx["clean"] = CLEAN_URLS
    ctx["build_id"] = BUILD_ID
    ctx["page_url"] = SITE_URL + clean_path(path)
    ctx["coach_slugs"] = COACH_SLUGS
    ctx["current_season"] = CURRENT
    ctx["gameday"] = GAMEDAY
    ctx["cal"] = CAL_LINKS
    ctx["corrections_url"] = corrections_link(ctx["page_url"])
    html = env.get_template(tpl).render(**ctx)
    if CLEAN_URLS:
        html = absolute_links(html, path)
    PAGES.append(path)
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(html)


def season_summary(season):
    gs = [g for g in games_by_season.get(season, []) if g["result"] in ("W", "L")] or RESULTS_ONLY.get(season, [])
    h = hist_by_season.get(season, {})
    sc = [g for g in gs if g.get("scored", True)]  # results-only games can be missing a score
    return {
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
    rows = [r for gid in ids for r in pg_by_game.get(gid, []) if r.get("pts") is not None]
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
    for gid in ids:
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


CAL_FILE = "schedule.ics"
CAL_HOST = re.sub(r"^https?://", "", SITE_URL)
_VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Chicago
BEGIN:DAYLIGHT
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
TZNAME:CDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
TZNAME:CST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""


def _ics_text(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line):
    """Lines longer than 75 bytes continue on the next line after a space (RFC 5545)."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode()); cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def calendar_feed(season):
    """The season's schedule as an iCalendar feed people can subscribe to. Each game keeps the same UID,
    so a changed time or a final score updates the event already on their calendar."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Bangor Cardinals Boys Basketball//Schedule//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:Bangor Boys Basketball {season.replace('-', '–')}",
             "X-WR-CALDESC:Bangor Cardinals varsity boys basketball schedule and results",
             "X-WR-TIMEZONE:America/Chicago", "REFRESH-INTERVAL;VALUE=DURATION:PT3H", "X-PUBLISHED-TTL:PT3H"]
    lines += _VTIMEZONE.split("\n")
    for g in games_by_season.get(season, []):
        d = dt.date.fromisoformat(g["date"])
        where = "at" if g["site"] == "away" else "vs"
        title = f"Bangor {where} {g['opponent']}"
        if g["result"] in ("W", "L"):
            title = f"{g['result']} {g['bangor_score']}–{g['opp_score']} · {title}"
        off = re.search(r"postpon|cancel", g["event"], re.I)
        if off:
            title += f" ({'Postponed' if 'postpon' in off.group(0).lower() else 'Canceled'})"
        url = SITE_URL + clean_path(f"games/{g['game_id']}.html")  # the live site always has clean URLs
        kind = {"playoff": "Playoff", "tournament": "Tournament"}.get(g["game_type"], "")
        tags = " · ".join(x for x in (kind, "Conference" if g["conference"] == "Y" else "",
                                      "" if off else g["event"]) if x)
        desc = [tags] if tags else []
        if g["stream_url"] and g["status"] != "final":
            desc.append(f"Watch live: {g['stream_url']}")
        desc.append(f"Game page: {url}")
        tm = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", g["time"] or "", re.I)
        ev = ["BEGIN:VEVENT", f"UID:{g['game_id']}@{CAL_HOST}", f"DTSTAMP:{stamp}"]
        if tm:
            h = int(tm.group(1)) % 12 + (12 if (tm.group(3) or "PM").upper() == "PM" else 0)
            start = dt.datetime.combine(d, dt.time(h, int(tm.group(2))))
            ev += [f"DTSTART;TZID=America/Chicago:{start:%Y%m%dT%H%M%S}",
                   f"DTEND;TZID=America/Chicago:{start + dt.timedelta(hours=2):%Y%m%dT%H%M%S}"]
        else:
            ev += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}"]
        ev += [f"SUMMARY:{_ics_text(title)}", f"DESCRIPTION:{_ics_text(chr(10).join(desc))}", f"URL:{url}"]
        if g["location"]:
            ev.append(f"LOCATION:{_ics_text(g['location'])}")
        if off and "cancel" in off.group(0).lower():
            ev.append("STATUS:CANCELLED")
        ev += ["TRANSP:TRANSPARENT", "END:VEVENT"]
        lines += ev
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(l) for l in lines) + "\r\n"


def calendar_links():
    """Subscribe links for the season calendar: Google, Apple (webcal) and Outlook, plus the plain feed URL."""
    from urllib.parse import quote
    feed = f"{SITE_URL}/{CAL_FILE}"
    webcal = f"webcal://{CAL_HOST}/{CAL_FILE}"
    return {"feed": feed, "webcal": webcal,
            "google": f"https://calendar.google.com/calendar/r?cid={quote(webcal, safe='')}",
            "outlook": f"https://outlook.live.com/calendar/0/addfromweb?url={quote(feed, safe='')}"
                       f"&name={quote('Bangor Boys Basketball')}"}


CAL_LINKS = calendar_links()


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(SRC, "static"), os.path.join(OUT, "static"))

    # ---- records first: game, season and player pages show their record-book entries
    sections = record_sections()
    B = collect_badges(sections)
    render("records.html", "records/index.html", sections=list(sections.values()), mins=MINS)

    # ---- head-to-head previews for games not yet played (game pages and the home page's upcoming list)
    opps = opponent_index()
    PREVIEWS = {g["game_id"]: game_preview(g, opps.get(g["opp_slug"]))
                for g in games_by_id.values() if g["status"] in ("upcoming", "pending")}

    # ---- home
    latest = DATA_SEASONS[-1]
    top_career = merged("individual", "career", "pts", "int")[:5]
    top_game = merged("individual", "game", "pts", "int")[:5]
    champs = [h for h in history if "state champion" in h["notes"].lower() or "state runner" in h["notes"].lower()
              or "state semifinal" in h["notes"].lower() or "state tournament" in h["notes"].lower()]
    recent = [season_summary(s) for s in reversed(DATA_SEASONS[-6:])]
    render("home.html", "index.html", latest=season_summary(latest), latest_leaders=leaders(latest),
           latest_games=[g for g in games_by_season[latest] if g["status"] == "final"][-5:][::-1],
           upcoming=[{**g, "preview": PREVIEWS.get(g["game_id"])} for g in UPCOMING[:6]], top_career=top_career, top_game=top_game,
           champs=champs, recent=recent)

    # ---- seasons index
    all_seasons = [season_summary(h["season"]) for h in reversed(history)]
    render("seasons.html", "seasons/index.html", seasons=all_seasons)

    # ---- season pages
    PAGE_SEASONS = sorted(set(DATA_SEASONS) | set(RESULTS_ONLY))

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
    for s in [s for s in RESULTS_ONLY if s not in games_by_season]:
        gs = RESULTS_ONLY[s]
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
            items.append({"margin": m, "record": g["record"], "href": f"#g{g['game']}",
                          "xlabel": g["game"] if g["game"] == "1" or int(g["game"]) % 5 == 0 else "",
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
        tiles.append((f"{ss['ppg']}–{ss['oppg']}", "Average score"))
        sh = share("seasons", s, share_images.simple_card, f"Bangor Cardinals {s.replace('-', '–')} season: {rec}{' in known games' if known else ''}",
                   f"Season{' · Coach ' + ss['coach'] if ss['coach'] else ''}", s.replace("-", "–"), ss["notes"], tiles, "Season")
        if STORIES.get(s):
            st = STORIES[s]
            render("story.html", f"seasons/{st['slug']}.html", st=st, s=ss, **share(
                "seasons", st["slug"], share_images.simple_card, st["title"], st["kicker"], s.replace("-", "–"),
                ss["notes"], [(f"{w}–{l}", "Record in known games")], "Season"))
        render("season_results.html", f"seasons/{s}.html", s=ss, games=gs, w=w, l=l, sources=sources,
               dated=all(g.get("date") for g in gs), any_dates=any(g.get("date") for g in gs),
               in_h2h=all(g.get("date") and g.get("site") for g in gs),
               any_sites=any(g.get("site") for g in gs), story=STORIES.get(s), **results_players(s, gs),
               roster=ROSTERS.get(s, []),
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
        tiles = [(f"{ss['w']}–{ss['l']}", "Record")] if ss["w"] != "" else []
        if ss["ppg"]:
            tiles.append((f"{ss['ppg']}–{ss['oppg']}", "Average score"))
        lead = next((l for l in leaders(s) if l["label"] == "Points"), None)
        if lead:
            tiles.append((lead["name"], f"Leading scorer · {lead['value']} pts"))
        sh = share("seasons", s, share_images.simple_card, f"Bangor Cardinals {s.replace('-', '–')} season: {ss['w']}–{ss['l']}",
                   f"Season{' · Coach ' + ss['coach'] if ss['coach'] else ''}", s.replace("-", "–"), ss["notes"], tiles, "Season")
        render("season.html", f"seasons/{s}.html", s=ss, games=gs, players=prow, cols=cols, **sh,
               margin_svg=margin_svg, scoring_lines=scoring_lines,
               team=team_row, leaders=leaders(s), partial=partial,
               **pager(s),
               source_note=any(r.get("source") == "season tab" for r in players),
               team_badges=B["season_team"].get(s, []), player_badges=B["season_ind"].get(s, []),
               game_badges=[b for g in gs for b in B["game_team"].get(g["game_id"], [])])

    # ---- game pages
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
        render("game.html", f"games/{gid}.html", g=g, **game_share(g),
               record_badges=sorted(B["game_team"].get(gid, []) + ind, key=lambda b: (b["rank"], b["title"])),
               bangor=[{"name": r["name"], "slug": r["slug"], "number": r["number"], "cls": r.get("class", ""),
                        "badges": B["game_ind"].get((gid, r["slug"]), []), **box_row(r)} for r in bangor],
               bcols=box_cols(bangor), btot=box_row(bt) if bangor else None,
               opp=[{"name": r["name"], "number": r["number"], **box_row(r)} for r in opp],
               ocols=box_cols(opp), otot=box_row(ot) if opp else None, periods=periods, preview=PREVIEWS.get(gid),
               opp_complete=bool(opp) and ot.get("pts") == g["os"])

    # ---- players
    plist = []
    for sl, name in PLAYER_PAGES.items():
        c = career_by_player.get(sl)
        seasons = sorted(r["season"] for r in ps_by_player.get(sl, []))
        if not seasons:
            continue
        plist.append({"slug": sl, "name": name, "first": seasons[0], "last": seasons[-1],
                      "years": seasons[0][:4] + "–" + str(season_end_year(seasons[-1])),
                      "gp": fmt_int(c["gp"]) if c else "", "pts": fmt_int(c["pts"]) if c else "",
                      "pts_raw": (c or {}).get("pts") or 0,
                      "reb": fmt_int(c["reb"]) if c else "", "ast": fmt_int(c["ast"]) if c else "",
                      **dict(zip(("grad", "grad_how"), grad_year(sl)))})
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
        cls = next((r.get("class") for r in reversed(log) if r.get("class")), "")
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
        render("player.html", f"players/{sl}.html", name=name, seasons=srows, career=crow, cols=cols, log=by_season,
               news_log=news_log,
               lcols=lcols, highs=highs, numbers=numbers, cls=cls, years=plist[-1]["years"],
               grad=plist[-1]["grad"], grad_est=plist[-1]["grad_how"] == "estimated",
               partial=bool(partial_stats), part_career=part, span=span, book_career=book_career,
               override=(c or {}).get("override_note", ""), record_badges=B["player"].get(sl, []),
               player_news=player_news, **sh)
    plist.sort(key=lambda p: p["name"].split()[-1] + " " + p["name"])
    render("players.html", "players/index.html", players=plist)
    render("leaders.html", "records/career-leaders.html", boards=career_boards(), latest_season=DATA_SEASONS[-1],
           pg_min=PER_GAME_MIN)
    classes = classes_data(plist)
    render("classes.html", "players/classes.html", classes=classes)
    srows, smost = season_leaders_data()
    render("season_leaders.html", "records/season-leaders.html", rows=srows, most=smost,
           stats=SEASON_LEADER_STATS)

    # ---- history & coaches
    render("history.html", "history/index.html", seasons=[season_summary(h["season"]) for h in history],
           coaches=coach_list)
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
        render("coach.html", f"coaches/{c['slug']}.html", c=c, d=coach_page_data(c), **sh,
               prev=chrono[i - 1] if i else None, next=chrono[i + 1] if i + 1 < len(chrono) else None)

    # ---- opponents
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
        render("opponent.html", f"opponents/{o['slug']}.html", o=o, **sh)
    olist = sorted((o for o in opps.values() if o["games"]), key=lambda o: (-(o["w"] + o["l"]), o["name"]))
    render("opponents.html", "opponents/index.html", opps=olist,
           first=min([DATA_SEASONS[0]] + [g["season"] for g in DATED_RESULTS]))

    # ---- game film index
    if FILM_GAMES or HUDL_ONLY:
        by_season = OrderedDict()
        for g in sorted(FILM_GAMES + HUDL_ONLY, key=lambda g: g["date"], reverse=True):
            by_season.setdefault(g["season"], []).append(g)
        render("film.html", "film/index.html", by_season=by_season, total=len(FILM_GAMES) + len(HUDL_ONLY),
               youtube=len(FILM_GAMES), hudl_only=len(HUDL_ONLY))

    # ---- site search index (loaded by site.js the first time someone opens search)
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
        idx.append({"t": o["name"], "s": f"Opponent · Bangor is {o['w']}–{o['l']}", "u": f"opponents/{o['slug']}.html",
                    "k": "opponent"})
    for h in reversed(history):
        s = h["season"]
        rec = f"{h['w']}–{h['l']}" + (f"–{h['t']}" if h["t"] and h["t"] != "0" else "") if h["w"] != "" else ""
        sub = " · ".join(x for x in ["Season", rec, f"Coach {h['coach']}" if h["coach"] else "", h["notes"]] if x)
        url = f"seasons/{s}.html" if s in games_by_season or s in RESULTS_ONLY else f"history/index.html#s{s}"
        idx.append({"t": f"{season_label(s)} season", "s": sub, "u": url, "k": "season",
                    "x": f"{s} {s[:4]} {season_end_year(s)} {h['coach']} {h['notes']}"})
    for cl in classes:
        idx.append({"t": f"Class of {cl['year']}", "s": f"Graduating class · {len(cl['players'])} player"
                    + ("s" if len(cl["players"]) > 1 else ""), "u": f"players/classes.html#c{cl['year']}", "k": "page",
                    "x": f"{cl['year']} seniors graduates"})
    for t, u, x in [("Team leaders by season", "records/season-leaders.html", "season leaders scoring leader rebounding"),
                    ("Graduating classes", "players/classes.html", "class of seniors graduates roster"),
                    ("Record Book", "records/index.html", "records top 10"), ("Career Leaders", "records/career-leaders.html", "leaderboard all-time career points rebounds assists list"), ("History & Coaches", "history/index.html", "coaches"),
                    ("All seasons", "seasons/index.html", ""), ("All players", "players/index.html", "roster"),
                    ("All opponents", "opponents/index.html", "")] + ([("Game film", "film/index.html", "video youtube hudl")]
                                                                     if FILM_GAMES or HUDL_ONLY else []):
        idx.append({"t": t, "s": "Page", "u": u, "k": "page", "x": x})
    with open(os.path.join(OUT, "static", "search-index.js"), "w") as f:
        f.write("window.BANGOR_SEARCH=" + json.dumps(idx, ensure_ascii=False, separators=(",", ":")) + ";\n")

    # ---- sheet check: likely mistakes in the stat sheets, in the build log and on /sheet-check (unlisted)
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

    # ---- 404 page. Vercel serves it for any missing address, at any depth, so its links start at the site root
    # (clean URLs make every link root-relative anyway; locally, root="/" does it).
    render("404.html", "404.html", root="" if CLEAN_URLS else "/", season=DATA_SEASONS[-1],
           next_game=next((g for g in UPCOMING if g["season"] == CURRENT), None))
    PAGES.remove("404.html")

    # ---- the current season's schedule as a calendar feed (subscribe links on the season and home pages)
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
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")

    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"site built: {n} files in {OUT}")


if __name__ == "__main__":
    build()
