"""Build the static website into site/ from data/ and overrides/.

Run the whole pipeline:
  .venv/bin/python scripts/convert.py && .venv/bin/python scripts/records.py && .venv/bin/python scripts/build_site.py
"""
import csv, datetime as dt, json, math, os, posixpath, re, shutil
from collections import defaultdict, OrderedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape

import charts

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

games_by_id = OrderedDict((g["game_id"], g) for g in sorted(games, key=lambda g: g["date"]))
games_by_season = defaultdict(list)
for g in games_by_id.values():
    g["bs"], g["os"] = num(g["bangor_score"]), num(g["opp_score"])
    g["opp_slug"] = slug(g["opponent"])
    games_by_season[g["season"]].append(g)
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
    TODAY = dt.datetime.now(ZoneInfo("America/Chicago")).date()  # Wisconsin time, even on Vercel's UTC servers
except Exception:  # noqa: BLE001
    TODAY = dt.date.today()

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
    g["status"] = "final" if g["result"] else ("upcoming" if d >= TODAY else "no_result")
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
    g["replay_url"] = url if g["status"] == "final" and GAME_VIDEO_RE.search(url) else ""
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
        entries = [dict(e, source="data") for e in REC.get(scope, {}).get(period, {}).get(stat, [])]
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
                        "gp": int(h["gp"]) if h["gp"] else None, "detail": h["note"], "source": "book"})
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


def record_sections():
    sections = OrderedDict()
    for scope, period, stat, title, kind in CATS:
        entries = merged(scope, period, stat, kind)
        if not entries:
            continue
        sec = f"{scope}-{period}"
        sections.setdefault(sec, {"id": sec, "scope": scope, "period": period, "cats": []})
        sections[sec]["cats"].append({"title": title, "kind": kind, "entries": entries, "stat": stat,
                                      "note": MIN_NOTE.get((scope, period, stat), ""), "period": period, "scope": scope})
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
                     "book": e.get("source") == "book"}
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
    return d


def box_cols(rows):
    need = {"fg": "fga", "tp": "tpa", "ft": "fta"}
    return [(k, h) for k, h in BOX_COLS if any(r.get(need.get(k, k)) is not None for r in rows)]


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
            if not v:
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
                           "avg": fmt_avg(v, gp) if gp and stat != "gp" else "", "book": True, "active": False}
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
        boards.append({"stat": stat, "title": title, "short": short, "note": note, "entries": ranked,
                       "has_avg": stat != "gp"})
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
    html = env.get_template(tpl).render(**ctx)
    if CLEAN_URLS:
        html = absolute_links(html, path)
    PAGES.append(path)
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(html)


def season_summary(season):
    gs = [g for g in games_by_season.get(season, []) if g["result"] in ("W", "L")]
    h = hist_by_season.get(season, {})
    return {
        "season": season, "w": h.get("w", ""), "l": h.get("l", ""), "t": h.get("t", ""),
        "coach": h.get("coach", ""), "notes": h.get("notes", ""),
        "has_data": season in games_by_season,
        "ppg": fmt_avg(sum(g["bs"] for g in gs), len(gs)) if gs else "",
        "oppg": fmt_avg(sum(g["os"] for g in gs), len(gs)) if gs else "",
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
        items.append({"margin": m, "tip": tip, "record": f"{w}–{l}", "href": f"../games/{g['game_id']}.html",
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
    for s in reversed(DATA_SEASONS):
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


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(SRC, "static"), os.path.join(OUT, "static"))

    # ---- records first: game, season and player pages show their record-book entries
    sections = record_sections()
    B = collect_badges(sections)
    render("records.html", "records/index.html", sections=list(sections.values()), mins=MINS)

    # ---- home
    latest = DATA_SEASONS[-1]
    top_career = merged("individual", "career", "pts", "int")[:5]
    top_game = merged("individual", "game", "pts", "int")[:5]
    champs = [h for h in history if "state champion" in h["notes"].lower() or "state runner" in h["notes"].lower()
              or "state semifinal" in h["notes"].lower() or "state tournament" in h["notes"].lower()]
    recent = [season_summary(s) for s in reversed(DATA_SEASONS[-6:])]
    render("home.html", "index.html", latest=season_summary(latest), latest_leaders=leaders(latest),
           latest_games=[g for g in games_by_season[latest] if g["status"] == "final"][-5:][::-1],
           upcoming=UPCOMING[:6], top_career=top_career, top_game=top_game,
           champs=champs, recent=recent)

    # ---- seasons index
    all_seasons = [season_summary(h["season"]) for h in reversed(history)]
    render("seasons.html", "seasons/index.html", seasons=all_seasons)

    # ---- season pages
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
        render("season.html", f"seasons/{s}.html", s=season_summary(s), games=gs, players=prow, cols=cols,
               margin_svg=margin_svg, scoring_lines=scoring_lines,
               team=team_row, leaders=leaders(s), partial=partial,
               prev=DATA_SEASONS[i - 1] if i else None, next=DATA_SEASONS[i + 1] if i + 1 < len(DATA_SEASONS) else None,
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
        ind = [b for r in bangor for b in B["game_ind"].get((gid, r["slug"]), [])]
        ind += [b for (bg, bs), bl in B["game_ind"].items() if bg == gid and bs not in {r["slug"] for r in bangor} for b in bl]
        render("game.html", f"games/{gid}.html", g=g,
               record_badges=sorted(B["game_team"].get(gid, []) + ind, key=lambda b: (b["rank"], b["title"])),
               bangor=[{"name": r["name"], "slug": r["slug"], "number": r["number"], "cls": r.get("class", ""),
                        "badges": B["game_ind"].get((gid, r["slug"]), []), **box_row(r)} for r in bangor],
               bcols=box_cols(bangor), btot=box_row(bt) if bangor else None,
               opp=[{"name": r["name"], "number": r["number"], **box_row(r)} for r in opp],
               ocols=box_cols(opp), otot=box_row(ot) if opp else None, periods=periods)

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
                                                          **box_row(r)})
        lcols = box_cols(log)
        highs = []
        for k, label in [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"), ("stl", "Steals"), ("blk", "Blocks"),
                         ("tpm", "3-pointers")]:
            cands = [r for r in log if r.get(k) is not None]
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
        render("player.html", f"players/{sl}.html", name=name, seasons=srows, career=crow, cols=cols, log=by_season,
               lcols=lcols, highs=highs, numbers=numbers, cls=cls, years=plist[-1]["years"],
               grad=plist[-1]["grad"], grad_est=plist[-1]["grad_how"] == "estimated",
               partial=bool(partial_stats),
               override=(c or {}).get("override_note", ""), record_badges=B["player"].get(sl, []),
               player_news=player_news)
    plist.sort(key=lambda p: p["name"].split()[-1] + " " + p["name"])
    render("players.html", "players/index.html", players=plist)
    render("leaders.html", "records/career-leaders.html", boards=career_boards(), latest_season=DATA_SEASONS[-1])
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
        render("coach.html", f"coaches/{c['slug']}.html", c=c, d=coach_page_data(c),
               prev=chrono[i - 1] if i else None, next=chrono[i + 1] if i + 1 < len(chrono) else None)

    # ---- opponents
    opps = OrderedDict()
    for g in games_by_id.values():
        o = opps.setdefault(g["opp_slug"], {"name": g["opponent"], "slug": g["opp_slug"], "w": 0, "l": 0, "games": [],
                                            "upcoming": []})
        if g["result"] in ("W", "L"):
            o["w" if g["result"] == "W" else "l"] += 1
            o["games"].append(g)
        elif g["status"] == "upcoming":
            o["upcoming"].append(g)
    # every opponent on the schedule gets a page (a game page links to it), even before the first meeting
    for o in opps.values():
        o["last"] = o["games"][-1] if o["games"] else None
        o["h2h"] = head_to_head(o)
        render("opponent.html", f"opponents/{o['slug']}.html", o=o)
    olist = sorted((o for o in opps.values() if o["games"]), key=lambda o: (-(o["w"] + o["l"]), o["name"]))
    render("opponents.html", "opponents/index.html", opps=olist, first=DATA_SEASONS[0])

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
        url = f"seasons/{s}.html" if s in games_by_season else f"history/index.html#s{s}"
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
