"""Build the static website into site/ from data/ and overrides/.

Run the whole pipeline:
  .venv/bin/python scripts/convert.py && .venv/bin/python scripts/records.py && .venv/bin/python scripts/build_site.py
"""
import csv, datetime as dt, json, os, re, shutil
from collections import defaultdict, OrderedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OV = os.path.join(ROOT, "overrides")
SRC = os.path.join(ROOT, "site-src")
OUT = os.path.join(ROOT, "site")

PLAYER_ALIASES = {"Konnor Kaiser": "Connor Kaiser"}


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


coaches = OrderedDict()
for h in history:
    c = h["coach"].strip()
    if not c:
        continue
    d = coaches.setdefault(c, {"name": c, "w": 0, "l": 0, "t": 0, "seasons": [], "titles": 0})
    d["w"] += int(h["w"] or 0); d["l"] += int(h["l"] or 0); d["t"] += int(h["t"] or 0)
    d["seasons"].append(h["season"])
    if "conference champions" in h["notes"].lower():
        d["titles"] += 1
for c in coaches.values():
    c["years"] = c["seasons"][0][:4] + ("–" + str(season_end_year(c["seasons"][-1])) if len(c["seasons"]) > 1 or True else "")
    g = c["w"] + c["l"] + c["t"]
    c["pct"] = f"{(c['w'] + 0.5 * c['t']) / g:.3f}".lstrip("0") if g else ""
coach_list = sorted(coaches.values(), key=lambda c: (-c["w"], c["l"]))

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


# ---------------------------------------------------------------- render
env = Environment(loader=FileSystemLoader(os.path.join(SRC, "templates")), autoescape=select_autoescape(["html"]))
env.filters["d"] = fmt_date
env.filters["n"] = fmt_int
BUILT = TODAY.strftime("%B %-d, %Y")


def render(tpl, path, **ctx):
    depth = path.count("/")
    ctx.setdefault("root", "../" * depth)
    ctx["built"] = BUILT
    ctx["facts"] = FACTS
    ctx["latest_season"] = DATA_SEASONS[-1]
    ctx["has_film"] = bool(FILM_GAMES or HUDL_ONLY)
    html = env.get_template(tpl).render(**ctx)
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


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(SRC, "static"), os.path.join(OUT, "static"))

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
        render("season.html", f"seasons/{s}.html", s=season_summary(s), games=gs, players=prow, cols=cols,
               team=team_row, leaders=leaders(s), partial=partial,
               prev=DATA_SEASONS[i - 1] if i else None, next=DATA_SEASONS[i + 1] if i + 1 < len(DATA_SEASONS) else None,
               source_note=any(r.get("source") == "season tab" for r in players))

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
        render("game.html", f"games/{gid}.html", g=g,
               bangor=[{"name": r["name"], "slug": r["slug"], "number": r["number"], "cls": r.get("class", ""), **box_row(r)} for r in bangor],
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
                      "reb": fmt_int(c["reb"]) if c else "", "ast": fmt_int(c["ast"]) if c else ""})
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
            by_season.setdefault(r["season"], []).append({"g": g, **box_row(r)})
        lcols = box_cols(log)
        highs = []
        for k, label in [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"), ("stl", "Steals"), ("blk", "Blocks"),
                         ("tpm", "3-pointers")]:
            cands = [r for r in log if r.get(k) is not None]
            if cands and max(r[k] for r in cands) > 0:
                best = max(cands, key=lambda r: (r[k], r["date"]))
                highs.append({"label": label, "value": fmt_int(best[k]), "g": games_by_id[best["game_id"]]})
        numbers = sorted({r.get("number") for r in rows if r.get("number")}, key=lambda x: int(x) if x.isdigit() else 999)
        cls = next((r.get("class") for r in reversed(log) if r.get("class")), "")
        render("player.html", f"players/{sl}.html", name=name, seasons=srows, career=crow, cols=cols, log=by_season,
               lcols=lcols, highs=highs, numbers=numbers, cls=cls, years=plist[-1]["years"],
               partial=bool(partial_stats),
               override=(c or {}).get("override_note", ""))
    plist.sort(key=lambda p: p["name"].split()[-1] + " " + p["name"])
    render("players.html", "players/index.html", players=plist)

    # ---- records
    sections = OrderedDict()
    for scope, period, stat, title, kind in CATS:
        entries = merged(scope, period, stat, kind)
        if not entries:
            continue
        sec = f"{scope}-{period}"
        sections.setdefault(sec, {"id": sec, "scope": scope, "period": period, "cats": []})
        sections[sec]["cats"].append({"title": title, "kind": kind, "entries": entries,
                                      "note": MIN_NOTE.get((scope, period, stat), ""), "period": period, "scope": scope})
    render("records.html", "records/index.html", sections=list(sections.values()), mins=MINS)

    # ---- history & coaches
    render("history.html", "history/index.html", seasons=[season_summary(h["season"]) for h in history],
           coaches=coach_list)

    # ---- opponents
    opps = OrderedDict()
    for g in games_by_id.values():
        if not g["result"]:
            continue
        o = opps.setdefault(g["opp_slug"], {"name": g["opponent"], "slug": g["opp_slug"], "w": 0, "l": 0, "games": []})
        o["w" if g["result"] == "W" else "l"] += 1
        o["games"].append(g)
    olist = sorted(opps.values(), key=lambda o: (-(o["w"] + o["l"]), o["name"]))
    for o in olist:
        o["last"] = o["games"][-1]
        render("opponent.html", f"opponents/{o['slug']}.html", o=o)
    render("opponents.html", "opponents/index.html", opps=olist, first=DATA_SEASONS[0])

    # ---- game film index
    if FILM_GAMES or HUDL_ONLY:
        by_season = OrderedDict()
        for g in sorted(FILM_GAMES + HUDL_ONLY, key=lambda g: g["date"], reverse=True):
            by_season.setdefault(g["season"], []).append(g)
        render("film.html", "film/index.html", by_season=by_season, total=len(FILM_GAMES) + len(HUDL_ONLY),
               youtube=len(FILM_GAMES), hudl_only=len(HUDL_ONLY))

    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"site built: {n} files in {OUT}")


if __name__ == "__main__":
    build()
