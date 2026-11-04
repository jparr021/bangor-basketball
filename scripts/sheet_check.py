"""Sheet check: likely mistakes in the stat sheets, found while the site builds.

Nothing here stops the build or changes any data. build_site.py prints the current season's findings
in the build log and writes them to a page that isn't linked from the site or listed for search
engines: /sheet-check. Run on its own for the same list in the terminal:

    .venv/bin/python scripts/sheet_check.py            # current season
    .venv/bin/python scripts/sheet_check.py --all      # every season

Each finding is a "fix" (something is certainly wrong, like a W with the lower score) or a
"check" (worth a look, like two player names one letter apart).
"""
import csv, datetime as dt, json, os, re, sys
from collections import defaultdict
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
OFF_RE = re.compile(r"postpon|cancel|no result", re.I)


def _load(name):
    path = os.path.join(D, name)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def _n(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower().replace("'", "").replace(".", "")).strip("-")


def _similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _fmt(iso):
    return dt.date.fromisoformat(iso).strftime("%b %-d")


def run(current, today, aliases=None):
    """Return findings: dicts with season, level ('fix' or 'check'), game_id ('' if none), text."""
    aliases = aliases or {}
    games = _load("games.csv")
    pg = _load("player_games.csv")
    out = []

    def add(season, level, text, game_id=""):
        out.append({"season": season, "level": level, "text": text, "game_id": game_id})

    # ---- warnings the converter already raised while reading the spreadsheets
    conv = os.path.join(D, "conversion_warnings.txt")
    if os.path.exists(conv):
        with open(conv) as f:
            for line in f:
                line = line.strip()
                m = re.match(r"^(\d{4}-\d{2}|players): (.*)$", line)
                if not m:
                    continue
                season, text = m.groups()
                text = re.sub(r"\b(\d{4}-\d{2}-\d{2})\b", lambda d: _fmt(d.group(1)), text)
                if season == "players":
                    season = re.findall(r"\d{4}-\d{2}", text)[-1] if re.findall(r"\d{4}-\d{2}", text) else current
                    add(season, "check", text[0].upper() + text[1:])
                else:
                    level = "check" if re.search(r"players' points add to|says postponed", text) else "fix"
                    add(season, level, text[0].upper() + text[1:])

    # ---- games
    seen = defaultdict(list)
    opp_seasons = defaultdict(set)
    for g in games:
        opp_seasons[g["opponent"]].add(g["season"])
    for g in games:
        s, gid, d = g["season"], g["game_id"], dt.date.fromisoformat(g["date"])
        where = f"{_fmt(g['date'])} vs {g['opponent']}"
        seen[(g["date"], _slug(g["opponent"]))].append(g)
        bs, os_, res = _n(g["bangor_score"]), _n(g["opp_score"]), g["result"]
        off = OFF_RE.search(g.get("event", ""))
        if res and (bs is None or os_ is None):
            add(s, "fix", f"{where}: marked {res} but the score is missing.", gid)
        elif res == "W" and bs <= os_ or res == "L" and bs >= os_:
            add(s, "fix", f"{where}: marked {res} but the score is {bs:g}–{os_:g}.", gid)
        if res and d > today:
            add(s, "fix", f"{where}: has a final score, but the date is in the future. Is the date right?", gid)
        if not res and d < today and s == current and not off:
            days = (today - d).days
            add(s, "fix" if days > 2 else "check",
                f"{where}: played {days} day{'s' if days != 1 else ''} ago, but there's no final score yet. "
                f"Enter it as \"W 64-52\" in the Result column, or \"PPD\" / \"Canceled\".", gid)
        y = int(s[:4])
        if not (dt.date(y, 10, 15) <= d <= dt.date(y + 1, 3, 31)):
            add(s, "fix", f"{where}: the date {d:%b %-d, %Y} is outside the {s} season. Is the year right?", gid)
        if g["site"] not in ("home", "away", "neutral"):
            add(s, "check", f"{where}: can't tell whether it's home or away.", gid)
        if g.get("stream_url") and not re.match(r"https?://", g["stream_url"]):
            add(s, "fix", f"{where}: the livestream link isn't a web address: {g['stream_url'][:60]}", gid)
    for (date, _), gs in seen.items():
        if len(gs) > 1:
            g = gs[0]
            add(g["season"], "fix", f"{_fmt(date)} vs {g['opponent']}: listed {len(gs)} times.", g["game_id"])

    # an opponent seen in only one season whose name is nearly another opponent's: probably a typo
    names = sorted(opp_seasons)
    for a in names:
        if len(opp_seasons[a]) != 1:
            continue
        for b in names:
            if b != a and len(opp_seasons[b]) > len(opp_seasons[a]) and _similar(a, b) >= 0.85:
                add(next(iter(opp_seasons[a])), "check",
                    f"Opponent \"{a}\" appears only this season. Is it the same school as \"{b}\"? "
                    f"Spelling it the same way keeps the head-to-head record together.")
                break

    # ---- Bangor box scores
    by_season_names = defaultdict(lambda: defaultdict(int))
    numbers = defaultdict(lambda: defaultdict(set))
    for r in pg:
        name = aliases.get(r["name"].strip(), r["name"].strip())
        s = r["season"]
        by_season_names[s][name] += 1
        if r.get("number"):
            numbers[s][r["number"].strip()].add(name)
        v = {k: _n(r.get(k)) for k in ("fgm", "fga", "tpm", "tpa", "ftm", "fta", "pts", "oreb", "dreb", "reb")}
        who = f"{_fmt(r['date'])} vs {r['opponent']}, {name}"
        for made, att, lbl in (("fgm", "fga", "field goals"), ("tpm", "tpa", "3-pointers"), ("ftm", "fta", "free throws")):
            if v[made] is not None and v[att] is not None and v[made] > v[att]:
                add(s, "fix", f"{who}: {v[made]:g} {lbl} made but only {v[att]:g} tried.", r["game_id"])
        if v["tpm"] is not None and v["fgm"] is not None and v["tpm"] > v["fgm"]:
            add(s, "check", f"{who}: {v['tpm']:g} 3-pointers but {v['fgm']:g} field goals. "
                            f"Field goals should include the 3-pointers.", r["game_id"])
        if None not in (v["fgm"], v["ftm"], v["pts"]):
            # the sheets count FGM as all field goals (3s included), so points = 2*FGM + 3PM + FTM
            exp = 2 * v["fgm"] + (v["tpm"] or 0) + v["ftm"]
            if exp != v["pts"]:
                add(s, "check", f"{who}: {v['pts']:g} points, but the made shots add to {exp:g}.", r["game_id"])
        if None not in (v["oreb"], v["dreb"], v["reb"]) and v["oreb"] + v["dreb"] != v["reb"]:
            add(s, "check", f"{who}: {v['reb']:g} rebounds, but offensive + defensive is {v['oreb'] + v['dreb']:g}.",
                r["game_id"])
        for k, x in v.items():
            if x is not None and x < 0:
                add(s, "fix", f"{who}: a negative number ({k.upper()} {x:g}).", r["game_id"])

    # two names a letter or two apart, in the same season or the season before: likely one player
    seasons = sorted(by_season_names)
    for i, s in enumerate(seasons):
        here = by_season_names[s]
        pool = dict(here)
        prev = by_season_names[seasons[i - 1]] if i else {}
        if i:
            for nm in by_season_names[seasons[i - 1]]:
                pool.setdefault(nm, 0)
        flagged = set()
        for a in here:
            for b in pool:
                if a == b or _slug(a) == _slug(b) or (b, a) in flagged:
                    continue
                if b in here and min(here[a], here[b]) > 2:
                    continue  # both played a real share of the season: two players (brothers, cousins)
                if b not in here and a in prev:
                    continue  # a isn't new this season
                if _similar(a, b) >= 0.88 or a.split()[-1:] == b.split()[-1:] and _similar(a, b) >= 0.8:
                    flagged.add((a, b))
                    if b in here:
                        txt = f"\"{a}\" ({here[a]} games) and \"{b}\" ({here[b]} games) are both on the {s} sheets."
                    else:
                        txt = f"\"{a}\" is new in {s}; \"{b}\" played the season before."
                    add(s, "check", txt + " If it's one player, spell the name the same way everywhere "
                                          "(or add it to PLAYER_ALIASES in scripts/build_site.py).")
        for num, nms in numbers[s].items():
            if len(nms) > 1:
                add(s, "check", f"#{num} is worn by {' and '.join(sorted(nms))} in {s}. "
                                f"Fine if the number changed hands; otherwise a name or number is off.")

    # newest season first, fixes before checks, then in date order
    order = {"fix": 0, "check": 1}
    gdate = {g["game_id"]: g["date"] for g in games}
    out.sort(key=lambda f: (f["season"] != current, -int(f["season"][:4]), order[f["level"]], gdate.get(f["game_id"], "")))
    return out


def summary(findings, current):
    cur = [f for f in findings if f["season"] == current]
    fixes = sum(f["level"] == "fix" for f in cur)
    return cur, fixes, len(cur) - fixes


if __name__ == "__main__":
    with open(os.path.join(ROOT, "overrides", "current_season.json")) as f:
        current = json.load(f).get("season", "")
    found = run(current, dt.date.today())
    show = found if "--all" in sys.argv else [f for f in found if f["season"] == current]
    for f in show:
        print(f"{f['season']}  {f['level'].upper():5}  {f['text']}")
    print(f"{len(show)} finding(s)")
