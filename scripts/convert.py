"""Convert every season workbook in source-sheets/ into one standard dataset in data/.

Outputs (all CSV, one row per thing):
  data/games.csv                 one row per Bangor game (all seasons, incl. results-only years)
  data/player_games.csv          one row per Bangor player per game (box-score seasons)
  data/opponent_player_games.csv one row per opponent player per game (when the sheet has it)
  data/source_season_totals.csv  season totals exactly as recorded on each sheet's season tab
  data/players.csv               one row per Bangor player (name -> id), with seasons played

Blank cell = stat not tracked for that game. 0 = tracked, and it was zero.
Run:  .venv/bin/python scripts/convert.py
"""
import csv, datetime as dt, glob, os, re, sys
from collections import defaultdict, OrderedDict

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-sheets")
OUT = os.path.join(ROOT, "data")

TEAM = "Bangor"

# Opponent name clean-up: variants seen in the sheets -> one canonical name.
OPP_ALIASES = {
    "melmin": "Melrose-Mindoro",
    "melrose mindoro": "Melrose-Mindoro",
    "g-e-t": "Gale-Ettrick-Trempealeau",
    "get": "Gale-Ettrick-Trempealeau",
    "wonewoc center": "Wonewoc-Center",
    "alma center linc": "Alma Center Lincoln",
}

# Excel cuts tab names at 31 characters, which loses the 2025-26 scores that only
# live in the tab names. These are the full names, read straight from the Google Sheet.
FULL_TAB_NAMES_2025_26 = [
    "Dec 02, 2025 - Arcadia - L 67-69", "Dec 12, 2025 - New Lisbon - W 77-53",
    "Dec 22, 2025 - Melrose Mindoro - W 81-46", "Dec 23, 2025 - Westby - L 73-49",
    "Dec 26, 2025 - Glenwood City - W 71-70", "Dec 27, 2025 - Reedsburg - L 56-47",
    "Jan 08, 2026 - Necedah - W 70-50", "Jan 09, 2026 - Brookwood - W 88-47",
    "Jan 12, 2026 - Luther - L 66-40", "Jan 13, 2026 - Wonewoc-Center - W 73-64",
    "Jan 16, 2026 - Hillsboro - W 71-43", "Jan 19, 2026 - Cashton - W 84-54",
    "Jan 22, 2026 - Royall - L 61-47", "Jan 27, 2026 - Cashton - W 79-49",
    "Jan 30, 2026 - New Lisbon - W 68-60", "Feb 2, 2026 - G-E-T - L 77-39",
    "Feb 5, 2026 - Brookwood - W 65-54", "Feb 9, 2026 - Black River Falls - W 99-70",
    "Feb 10, 2026 - Necedah - W 55-41", "Feb 13, 2026 - Wonewoc-Center - W 90-69",
    "Feb 16, 2026 - De Soto - L 64-53", "Feb 19, 2026 - Hillsboro - L 73-60",
    "Feb 23, 2026 - Royall - L 76-68", "Feb 26, 2026 - Birchwood - W 94-58",  # tab says 94-68; Bound and Hudl both say 94-58
    "Mar 3, 2026 - Eleva-Strum - W 61-59", "Mar 6, 2026 - Regis - L 91-80",
]

STAT_COLS = ["min", "fgm", "fga", "tpm", "tpa", "ftm", "fta",
             "oreb", "dreb", "reb", "ast", "stl", "blk", "to", "pf", "pts", "chg"]

warnings = []


def warn(season, msg):
    warnings.append(f"{season}: {msg}")


# ---------------------------------------------------------------- helpers
def cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return v if isinstance(v, (dt.datetime, dt.date)) else str(v).strip()


def rows_of(ws):
    out = []
    for r in ws.iter_rows(values_only=True):
        r = [cell(v) for v in r]
        while r and r[-1] == "":
            r.pop()
        out.append(r)
    return out


def made_att(v):
    """'3-10', '3/10', or a date Excel made out of '3-10' (March 10) -> (3, 10).
    Returns None for untracked ('-', '---', '')."""
    if isinstance(v, (dt.datetime, dt.date)):
        return v.month, v.day
    s = str(v).strip()
    m = re.fullmatch(r"(\d+)\s*[-/]\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def num(v):
    if v is None or v == "" or v == "-" or v == "---":
        return None
    if isinstance(v, (dt.datetime, dt.date)):
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def canon_opp(name):
    n = re.sub(r"^(@|vs\.?)\s+", "", str(name).strip(), flags=re.I)
    n = re.sub(r"\s+", " ", n).strip()
    return OPP_ALIASES.get(n.lower(), n)


def slug(name):
    s = name.lower().replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def season_date(season, month, day):
    start = int(season[:4])
    year = start if month >= 8 else start + 1
    return dt.date(year, month, day)


def is_bangor(name):
    return str(name).strip().lower().startswith(TEAM.lower())


def classify_type(text):
    t = (text or "").lower()
    if any(k in t for k in ("wiaa", "regional", "sectional", "state tournament", "playoff")):
        return "playoff"
    if any(k in t for k in ("tournament", "classic", "holiday", "shootout", "invitational")):
        return "tournament"
    return "regular"


# ---------------------------------------------------------------- schedule
def link_of(v, links, rownum, colnum):
    """URL for a schedule cell: its hyperlink, or the text itself if it is a URL."""
    if (rownum, colnum) in links:
        return links[(rownum, colnum)]
    s = str(v or "").strip()
    return s if s.startswith("http") else ""


TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)?(\s*(CT|CST|CDT))?$", re.I)
TEXT_DATE_RE = re.compile(r"^\s*(?:[A-Za-z]{3,9}\.?,?\s*)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*$")


def clean_time(t):
    """'7:00 PM CT' -> '7:00 PM' (the site is all Wisconsin time)."""
    return re.sub(r"\s*(CT|CST|CDT)$", "", str(t or "").strip(), flags=re.I)


def clean_location(loc):
    """'Bangor High School High School Main Gym' (doubled by the scheduling export) -> 'Bangor High School Main Gym'."""
    loc = re.sub(r"\s+", " ", str(loc or "")).strip()
    return re.sub(r"\b(High School)( \1)+\b", r"\1", loc)


def sched_date(v):
    """A schedule date cell: a real date, or text like 'Mon11/30/26' or '11/30/2026'."""
    if isinstance(v, (dt.datetime, dt.date)):
        return v
    m = TEXT_DATE_RE.match(str(v or ""))
    if not m:
        return None
    return dt.date(2000, int(m.group(1)), int(m.group(2)))  # the year comes from the season


def parse_schedule(season, ws, links=None):
    """Return list of dicts: date, opponent, bangor_score, opp_score, result, site, location, note,
    plus time / stream_url / film_url when the schedule has those columns."""
    links = links or {}
    numbered = [(i + 1, r) for i, r in enumerate(rows_of(ws)) if any(str(c).strip() for c in r)]
    if not numbered:
        return []
    hdr = [str(h) for h in numbered[0][1]]
    col = {h.strip().lower(): i for i, h in enumerate(hdr)}
    if not any(k in col for k in ("c", "conf", "conference")):
        # the conference column often has no header: an unlabeled column holding only "C" and blanks
        for i, h in enumerate(hdr):
            vals = {str((r + [""] * (i + 1))[i]).strip().upper() for _, r in numbered[1:]}
            if i and h.strip().lower() in ("", "none") and "C" in vals and vals <= {"", "C"}:
                col["c"] = i
                break
    games = []
    for rownum, r in numbered[1:]:
        r = r + [""] * (8 - len(r))
        d = sched_date(r[0])
        if d is None:
            warn(season, f"schedule row with unreadable date skipped: {r[:4]}")
            continue
        date = season_date(season, d.month, d.day)  # sheet years are wrong; month/day are right
        g = {"date": date, "location": "", "note": "", "site": "", "time": "", "stream_url": "", "film_url": ""}

        def get(*names):
            for n in names:
                if n in col and col[n] < len(r):
                    return r[col[n]], col[n]
            return "", None

        for names, key in ((("stream", "livestream", "live stream", "watch"), "stream_url"),
                           (("film", "video", "youtube", "game film"), "film_url")):
            v, c = get(*names)
            if c is not None:
                g[key] = link_of(v, links, rownum, c + 1)
        tv, _ = get("time")
        if isinstance(tv, (dt.time, dt.datetime)):
            tv = tv.strftime("%-I:%M %p")
        g["time"] = clean_time(tv)
        res = str(r[1])
        m = re.match(r"^\s*([WLT])\s*\n?\s*(\d+)\s*-\s*(\d+)", res)
        if hdr[1] == "Result" and m:
            # Layout A: Date | "W\n69-68" (Bangor first) | [@ ]Opponent | Location | Status
            g["result"] = m.group(1)
            g["bangor_score"], g["opp_score"] = int(m.group(2)), int(m.group(3))
            opp = str(r[2])
            g["site"] = "away" if opp.strip().startswith("@") else "home"
            g["opponent"] = canon_opp(opp)
            g["location"] = str(r[3])
            g["note"] = str(r[4])
        elif hdr[1] == "Result" and num(r[2]) is not None and num(r[4]) is not None:
            # Layout B (2003-04, 2011-12): Date | Team1 | Score1 | Team2 | Score2 | [event]
            t1, s1, t2, s2 = str(r[1]), num(r[2]), str(r[3]), num(r[4])
            if is_bangor(t1):
                g["bangor_score"], g["opp_score"], g["opponent"] = s1, s2, canon_opp(t2)
                g["site"] = "away"  # listed first = visitor (same convention as box scores)
            elif is_bangor(t2):
                g["bangor_score"], g["opp_score"], g["opponent"] = s2, s1, canon_opp(t1)
                g["site"] = "home"
            else:
                warn(season, f"schedule row without Bangor: {r[:6]}")
                continue
            g["result"] = "W" if g["bangor_score"] > g["opp_score"] else "L"
            g["location"] = str(r[5])
        elif hdr[1] == "Result" and res.strip() in ("-", ""):
            g["result"] = ""
            g["opponent"] = canon_opp(r[2])
            g["site"] = "away" if str(r[2]).strip().startswith("@") else "home"
            g["location"] = str(r[3])
            g["note"] = "No result recorded"
        elif hdr[1].startswith("Opponent"):
            # Current-season layout (2025-26 on): Date | [@|vs] Opponent | Result | C | Caption | Location ...
            opp, _ = get("opponent(s)", "opponent")
            opp = str(opp)
            g["site"] = "away" if opp.strip().startswith("@") else "home"
            g["opponent"] = canon_opp(opp)
            conf, _ = get("c", "conf", "conference")
            g["conference"] = "Y" if str(conf).strip().upper() in ("C", "Y", "YES") else "N"
            g["note"] = str(get("caption", "notes", "event")[0])
            g["location"] = clean_location(get("location")[0])
            res = str(get("result")[0]).strip()
            m2 = re.match(r"^\s*([WL])\s+(\d+)\s*-\s*(\d+)", res)
            if m2:
                g["result"] = m2.group(1)
                hi, lo = max(int(m2.group(2)), int(m2.group(3))), min(int(m2.group(2)), int(m2.group(3)))
                g["bangor_score"], g["opp_score"] = (hi, lo) if g["result"] == "W" else (lo, hi)
            else:
                g["result"] = ""
                if TIME_RE.match(res) and not g["time"]:
                    g["time"] = clean_time(res)
                elif res.upper() in ("PPD", "POSTPONED"):
                    g["note"] = g["note"] or "Postponed"
                elif res.upper() in ("CANCELED", "CANCELLED", "CXL"):
                    g["note"] = g["note"] or "Canceled"
        else:
            warn(season, f"unrecognized schedule row: {r[:6]}")
            continue
        games.append(g)
    return games


# ---------------------------------------------------------------- box-score game tabs
HDR = ["#", "Name", "MIN", "FG", "FT", "3PT", "REB", "AST", "TO", "STL", "BLK", "PF", "PTS"]


def parse_box_tab(season, tab, rows):
    """Parse a MaxPreps-style game tab. Returns dict or None if the tab has no game."""
    flat = [r for r in rows if r]
    if not flat or str(flat[0][0]).strip() in ("No Stats",):
        return None
    d0 = flat[0][0]
    if isinstance(d0, str):
        # a date left as text, sometimes with the weekday clipped ("ri, Dec 07, 2018" for "Fri, Dec 07, 2018")
        m = re.search(r"\b([A-Z][a-z]{2})[a-z]* (\d{1,2}), (\d{4})\b", d0)
        try:
            d0 = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y") if m else d0
        except ValueError:
            pass
    if not isinstance(d0, (dt.datetime, dt.date)):
        return None
    game = {"date": d0.date() if isinstance(d0, dt.datetime) else d0, "event": "",
            "teams": [], "scores": {}, "periods": {}, "period_labels": [], "box": {}}
    i = 1
    # header lines until the line-score / team sections
    pre = []
    while i < len(flat) and str(flat[i][0]).strip() != "FINAL":
        pre.append(str(flat[i][0])); i += 1
    i += 1  # FINAL
    # skip "Stream" / "NFHS Stream" / "Watch Game" style link lines
    while i < len(flat) and not re.match(r"^.*\S\s+\d+$", str(flat[i][0])):
        i += 1
    for _ in range(2):
        m = re.match(r"^(.*\S)\s+(\d+)$", str(flat[i][0])) if i < len(flat) else None
        if not m:
            warn(season, f"{tab}: could not read final score line")
            return None
        game["teams"].append(m.group(1)); game["scores"][m.group(1)] = int(m.group(2)); i += 1
    game["event"] = " / ".join(p for p in pre if p)
    # optional line score
    if i < len(flat) and flat[i][0] == "" and len(flat[i]) > 1:
        labels = [str(x) for x in flat[i][1:]]
        game["period_labels"] = labels[:-1]  # drop "T"
        i += 1
        for _ in range(2):
            r = flat[i]
            game["periods"][str(r[0])] = [num(x) for x in r[1:-1]]
            i += 1
    # team sections
    while i < len(flat):
        name = str(flat[i][0]).strip()
        if name in ("Game Details",) or name.startswith("Venue:"):
            break
        if name in game["teams"] and len(flat[i]) == 1:
            i += 1
            if i < len(flat) and str(flat[i][0]).strip() == "No Data Available":
                game["box"][name] = None; i += 1; continue
            if i < len(flat) and [str(x) for x in flat[i][:3]] == HDR[:3]:
                i += 1
                players, totals = [], None
                while i < len(flat):
                    r = flat[i] + [""] * 13
                    if str(r[1]).strip() == "Totals" or str(r[0]).strip() == "Totals":
                        totals = r; i += 1; break
                    if len(flat[i]) == 1 and not num(flat[i][0]):
                        break
                    players.append(r[:13]); i += 1
                game["box"][name] = {"players": players, "totals": totals}
                continue
        i += 1
    return game


def box_rows_to_stats(season, tab, team_rows):
    """Turn a team's raw box rows into stat dicts, blanking columns that weren't tracked."""
    out = []
    for r in team_rows["players"]:
        jersey, name = str(r[0]).strip(), str(r[1]).strip()
        if not name:
            continue
        fg, ft, tp = made_att(r[3]), made_att(r[4]), made_att(r[5])
        s = {"number": jersey, "name": name,
             "min": num(r[2]),
             "fgm": fg[0] if fg else None, "fga": fg[1] if fg else None,
             "ftm": ft[0] if ft else None, "fta": ft[1] if ft else None,
             "tpm": tp[0] if tp else None, "tpa": tp[1] if tp else None,
             "reb": num(r[6]), "ast": num(r[7]), "to": num(r[8]), "stl": num(r[9]),
             "blk": num(r[10]), "pf": num(r[11]), "pts": num(r[12]),
             "oreb": None, "dreb": None, "chg": None}
        out.append(s)
    if not out:
        return out
    tot = lambda k: sum((p[k] or 0) for p in out)
    tracked = {
        "min": tot("min") > 0,
        "shooting": tot("fga") + tot("fta") > 0,
        "reb": tot("reb") > 0, "ast": tot("ast") > 0, "to": tot("to") > 0,
        "stl": tot("stl") > 0, "pf": tot("pf") > 0,
    }
    tracked["blk"] = tracked["reb"] or tracked["stl"]
    for p in out:
        if not tracked["min"]:
            p["min"] = None
        if not tracked["shooting"]:
            for k in ("fgm", "fga", "ftm", "fta", "tpm", "tpa"):
                p[k] = None
        for k in ("reb", "ast", "to", "stl", "pf", "blk"):
            if not tracked[k]:
                p[k] = None
    return out


# ---------------------------------------------------------------- 2025-26 stat-app tabs
def parse_app_tab(season, rows):
    hdr = [str(h) for h in rows[0]]
    col = {h: i for i, h in enumerate(hdr)}
    out = []
    for r in rows[1:]:
        if not r or not str(r[0]).strip():
            continue
        r = r + [""] * len(hdr)
        who = str(r[0])
        if who.strip() == "Team":
            continue
        parts = [p.strip() for p in who.split(",")]
        jersey, name, cls = (parts + ["", "", ""])[:3]
        fg, tp, ft = made_att(r[col["FGMA"]]), made_att(r[col["3PMA"]]), made_att(r[col["FTMA"]])
        g = lambda k: num(r[col[k]]) if k in col else None
        out.append({"number": jersey, "name": name, "class": cls,
                    "min": None,  # all zeros in this export = not tracked
                    "fgm": fg[0], "fga": fg[1], "tpm": tp[0], "tpa": tp[1], "ftm": ft[0], "fta": ft[1],
                    "oreb": g("ORB"), "dreb": g("DRB"), "reb": g("RBD"), "ast": g("AST"),
                    "stl": g("STL"), "blk": g("BLK"), "chg": g("CHG"), "to": g("TO"),
                    "pf": g("FL"), "pts": g("PTS")})
    return out


# ---------------------------------------------------------------- season "Player Stats" tab
def parse_player_stats_tab(season, ws):
    rows = rows_of(ws)
    # some seasons (2011-12) have everything shifted one column right
    if all((not r) or r[0] == "" for r in rows):
        rows = [r[1:] for r in rows]
    by_player = OrderedDict()
    hdr = None
    for r in rows:
        if not r:
            continue
        if len(r) == 1:
            hdr = None; continue
        if str(r[0]) == "#" and len(r) > 2:
            hdr = [str(h) for h in r]
            # "3PM" was auto-formatted into a time ("3:00 PM" / 15:00:00) in the sheets
            hdr = ["3PM" if (h in ("15:00:00", "3:00 PM") or "15:00" in h) else h for h in hdr]
            continue
        if hdr:
            rec = dict(zip(hdr, r))
            key = (str(rec.get("Name", "")).strip())
            d = by_player.setdefault(key, {"season": season, "number": str(rec.get("#", "")), "name": key})
            for h, v in rec.items():
                if h in ("#", "Name"):
                    continue
                d[h] = num(v)
    return list(by_player.values())


def schedule_links(path):
    """Hyperlinks on the Schedule tab ({(row, col): url}). Read-only mode can't see links,
    so only open the file fully when the schedule has a stream/film column."""
    ro = openpyxl.load_workbook(path, read_only=True)
    if "Schedule" not in ro.sheetnames:
        return {}
    head = " ".join(str(c or "").lower() for r in ro["Schedule"].iter_rows(max_row=3, values_only=True) for c in r)
    if not any(w in head for w in ("stream", "watch", "film", "video", "youtube")):
        return {}
    ws = openpyxl.load_workbook(path, data_only=True)["Schedule"]
    return {(c.row, c.column): c.hyperlink.target for row in ws.iter_rows() for c in row
            if c.hyperlink is not None and c.hyperlink.target}


def load_extra_boxscores():
    """Opponent box scores and line scores added from other sources (e.g. Bound for 2025-26),
    keyed by game date. Used only where the season sheet doesn't have them."""
    opp, lines = defaultdict(list), {}
    p1 = os.path.join(ROOT, "overrides", "opponent_boxscores.csv")
    p2 = os.path.join(ROOT, "overrides", "line_scores.csv")
    if os.path.exists(p1):
        with open(p1) as f:
            for r in csv.DictReader(f):
                d = {"number": r["number"], "name": r["name"], "min": None}
                for k in STAT_COLS:
                    if k != "min":
                        d[k] = num(r.get(k))
                opp[r["date"]].append(d)
        for rows in opp.values():  # a column that is all zeros for the team wasn't tracked
            for k in ("to", "pf", "chg", "blk", "oreb", "dreb"):
                if all(not (x.get(k) or 0) for x in rows):
                    for x in rows:
                        x[k] = None
    if os.path.exists(p2):
        with open(p2) as f:
            for r in csv.DictReader(f):
                lines[r["date"]] = r
    # Leading scorers and rebounders from newspaper clippings, for games with no box score
    news = defaultdict(lambda: {"bangor": [], "opp": []})
    p3 = os.path.join(ROOT, "overrides", "newspaper_stats.csv")
    if os.path.exists(p3):
        with open(p3) as f:
            for r in csv.DictReader(f):
                d = {"number": (r.get("number") or "").strip(), "name": r["name"].strip(),
                     **{k: num(r.get(k)) for k in STAT_COLS}}
                news[r["date"]]["bangor" if r["team"].strip().lower() == "bangor" else "opp"].append(d)
    # Full Bangor box scores typed in from a printed stat sheet, for games the season sheet has no tab for
    box = defaultdict(list)
    p4 = os.path.join(ROOT, "overrides", "boxscores.csv")
    if os.path.exists(p4):
        with open(p4) as f:
            for r in csv.DictReader(f):
                box[r["date"]].append({"number": (r.get("number") or "").strip(), "name": r["name"].strip(),
                                       **{k: num(r.get(k)) for k in STAT_COLS}})
    return opp, lines, news, box



RESULT_SCHEDULES = {}
# Games in each season by the record book (overrides/season_history.csv), to tell a complete printed
# schedule from a few known games
RECORD_GAMES = {}
if os.path.exists(os.path.join(ROOT, "overrides", "season_history.csv")):
    with open(os.path.join(ROOT, "overrides", "season_history.csv")) as f:
        for r in csv.DictReader(f):
            n = sum(int(r.get(k) or 0) for k in ("w", "l", "t") if (r.get(k) or "").strip().isdigit())
            if n:
                RECORD_GAMES[r["season"]] = n


def dated_results(sheet_seasons):
    """Seasons in overrides/season_results.csv (a printed results list) where every game has a date and a
    site, and that have no season sheet: these become regular games, like a schedule with no game tabs."""
    p = os.path.join(ROOT, "overrides", "season_results.csv")
    if not os.path.exists(p):
        return []
    by_season = defaultdict(list)
    with open(p) as f:
        for r in csv.DictReader(f):
            by_season[r["season"]].append(r)
    for season, rows in by_season.items():
        if season in sheet_seasons or not all(r.get("date") and r.get("site") and r.get("bangor_score") and r.get("opp_score") for r in rows):
            continue
        if season in RECORD_GAMES and len(rows) != RECORD_GAMES[season]:
            continue  # only some of the season's games are known: it stays a results page
        sched = {}
        # a season whose list marks its non-conference games ("Non-conference" as the note) has the rest
        # flagged as conference games
        marked = any(r.get("note", "").strip().lower() == "non-conference" for r in rows)
        for i, r in enumerate(rows):
            d = dt.date.fromisoformat(r["date"])
            nonconf = r.get("note", "").strip().lower() == "non-conference"
            # tournament and play-off games aren't conference games either
            post = re.search(r"tournament|district|regional|sectional|play-?off|state", r.get("note", ""), re.I)
            b, o = num(r["bangor_score"]), num(r["opp_score"])
            res = (r.get("result") or "").strip().upper() or (("W" if b > o else "L") if b is not None and o is not None else "")
            # keyed by (date, row) so two games on one day (a tournament doubleheader) both stay
            sched[(d, i)] = {"date": d, "opponent": canon_opp(r["opponent"]), "site": r["site"], "location": "",
                        "note": "" if nonconf else r.get("note", ""),
                        "conference": ("N" if nonconf or post else "Y") if marked else "", "bangor_score": b if b is not None else "",
                        "opp_score": o if o is not None else "", "result": res, "time": "", "stream_url": "",
                        "film_url": "", "ot": r.get("ot", ""), "source": r.get("source", "")}
        RESULT_SCHEDULES[season] = sched
    return list(RESULT_SCHEDULES)

# ---------------------------------------------------------------- main
def main():
    extra_opp, extra_lines, extra_news, extra_box = load_extra_boxscores()
    os.makedirs(OUT, exist_ok=True)
    games_out, pg_out, opp_out, totals_out = [], [], [], []
    sources = [p for p in sorted(glob.glob(os.path.join(SRC, "*.xlsx")))]
    sheet_seasons = {re.match(r"(\d{4}-\d{2})", os.path.basename(p)).group(1) for p in sources}
    sources += [s for s in sorted(dated_results(sheet_seasons))]
    for path in sources:
        if path in RESULT_SCHEDULES:  # a season known from a printed schedule recap: no sheet, no game tabs
            season = path
            sched_by_date, tab_games = RESULT_SCHEDULES[path], {}
        else:
            season = re.match(r"(\d{4}-\d{2})", os.path.basename(path)).group(1)
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            sched = parse_schedule(season, wb["Schedule"], schedule_links(path)) if "Schedule" in wb.sheetnames else []
            sched_by_date = {}
            for g in sched:
                sched_by_date.setdefault(g["date"], g)

            if "Player Stats" in wb.sheetnames:
                totals_out += parse_player_stats_tab(season, wb["Player Stats"])
            if season == "2025-26" and "2025-26 Totals" in wb.sheetnames:
                for r in rows_of(wb["2025-26 Totals"])[1:]:
                    if r and str(r[0]).strip() and str(r[0]) != "Grand Total":
                        parts = [p.strip() for p in str(r[0]).split(",")]
                        totals_out.append({"season": season, "number": parts[0], "name": parts[1],
                                           "PTS": num(r[1]), "OFF": num(r[2]), "DEF": num(r[3]),
                                           "REB": num(r[4]), "AST": num(r[5])})

            tab_games = {}  # date -> game dict
            for tab in wb.sheetnames:
                mt = re.match(r"^([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", tab)
                if not mt:
                    continue
                rows = rows_of(wb[tab])
                nonempty = [r for r in rows if r]
                if nonempty and str(nonempty[0][0]) == "Athlete":
                    rows = nonempty
                    full = next((f for f in FULL_TAB_NAMES_2025_26
                                 if f.startswith(tab.rstrip()) or tab.startswith(f[:31])), None) if season == "2025-26" else None
                    date = dt.datetime.strptime(f"{mt.group(1)} {mt.group(2)} {mt.group(3)}", "%b %d %Y").date()
                    players = parse_app_tab(season, rows)
                    name = full or tab
                    m = re.match(r".*? - (.+?)(?: - ([WL]) (\d+)-(\d+))?$", name)
                    opp = canon_opp(m.group(1)) if m else ""
                    wl, bs, os_ = "", "", ""
                    sg = sched_by_date.get(date)
                    bangor_pts = sum(p["pts"] or 0 for p in players)
                    if m and m.group(2) and full:
                        a, b = int(m.group(3)), int(m.group(4))
                        wl = m.group(2)
                        hi, lo = max(a, b), min(a, b)
                        bs, os_ = (hi, lo) if wl == "W" else (lo, hi)
                    elif sg and sg.get("result") in ("W", "L"):
                        # Current season: the Schedule tab's Result column is the source of truth
                        wl, bs, os_ = sg["result"], sg["bangor_score"], sg["opp_score"]
                        opp = sg["opponent"] or opp
                    elif m and m.group(2) and len(tab) < 31:
                        a, b = int(m.group(3)), int(m.group(4))
                        wl = m.group(2)
                        hi, lo = max(a, b), min(a, b)
                        bs, os_ = (hi, lo) if wl == "W" else (lo, hi)
                    else:
                        warn(season, f"'{tab}': no final score found. Put the result (e.g. 'W 77-53') in the "
                                     f"Schedule tab's Result column. Using Bangor's {bangor_pts} points from the box score.")
                        bs = bangor_pts
                    if opp and sg and canon_opp(sg["opponent"]).lower() != opp.lower() and not full:
                        opp = sg["opponent"]
                    tab_games[date] = {"date": date, "opponent": opp, "bangor_score": bs, "opp_score": os_,
                                       "result": wl, "event": "", "players": players, "opp_players": None,
                                       "periods": None, "source_tab": name, "box": "full"}
                    continue
                g = parse_box_tab(season, tab, rows)
                if not g:
                    continue
                bteam = next((t for t in g["teams"] if is_bangor(t)), None)
                oteam = next((t for t in g["teams"] if not is_bangor(t)), None)
                if not bteam or not oteam:
                    warn(season, f"{tab}: could not find Bangor and opponent in {g['teams']}")
                    continue
                bbox = g["box"].get(bteam)
                obox = g["box"].get(oteam)
                players = box_rows_to_stats(season, tab, bbox) if bbox else None
                opp_players = box_rows_to_stats(season, tab, obox) if obox else None
                # line score: blank out fake ones (whole score in period 1, zeros after)
                periods = None
                if g["periods"]:
                    bp, op = g["periods"].get(bteam), g["periods"].get(oteam)
                    fake = lambda p: p is None or (len(p) > 1 and all((x or 0) == 0 for x in p[1:]))
                    fake2 = lambda p: p is not None and (p[0] or 0) == 0 and len(p) == 2  # "0 | 51" halves
                    both_zero = bp and op and any((a or 0) == 0 and (b or 0) == 0 for a, b in zip(bp, op))
                    if not (fake(bp) or fake(op) or fake2(bp) or fake2(op) or both_zero):
                        periods = {"labels": g["period_labels"], "bangor": bp, "opp": op}
                bs, os_ = g["scores"][bteam], g["scores"][oteam]
                site = "away" if g["teams"].index(bteam) == 0 else "home"
                tab_games[g["date"]] = {
                    "date": g["date"], "opponent": canon_opp(oteam), "bangor_score": bs, "opp_score": os_,
                    "result": "W" if bs > os_ else "L", "event": g["event"], "players": players,
                    "opp_players": opp_players, "periods": periods, "source_tab": tab, "tab_site": site,
                    "box": None}

        # ---- merge schedule + tabs into one game list
        all_dates = sorted(set(sched_by_date) | set(tab_games))
        for n, key in enumerate(all_dates, 1):
            s, t = sched_by_date.get(key), tab_games.get(key)
            date = key[0] if isinstance(key, tuple) else key  # printed results are keyed (date, row)
            gid = f"{season}-{n:02d}"
            base = t or s
            g = {"game_id": gid, "season": season, "date": date.isoformat(),
                 "opponent": base["opponent"],
                 "site": (s or {}).get("site") or (t or {}).get("tab_site", ""),
                 "location": (s or {}).get("location", ""),
                 "event": (t or {}).get("event", "") or (s or {}).get("note", ""),
                 "conference": (s or {}).get("conference", ""),
                 "bangor_score": base.get("bangor_score", ""), "opp_score": base.get("opp_score", ""),
                 "result": base.get("result", ""), "ot": str((s or {}).get("ot") or ""),
                 "period_labels": "", "bangor_periods": "", "opp_periods": "",
                 "time": (s or {}).get("time", ""), "stream_url": (s or {}).get("stream_url", ""),
                 "film_url": (s or {}).get("film_url", ""),
                 "box_score": "none", "box_points": "", "box_complete": "", "box_source": "", "recap": "", "source": "results" if season in RESULT_SCHEDULES else ("schedule" if not t else ("tab" if not s else "schedule+tab"))}
            if t and "postpone" in g["event"].lower():
                warn(season, f"{date} vs {g['opponent']}: schedule says postponed, but a game tab with a "
                             f"result exists (using the game tab)")
                g["event"] = ""
            if s and t and s.get("bangor_score") not in (None, "") and \
                    (s["bangor_score"], s["opp_score"]) != (t["bangor_score"], t["opp_score"]):
                warn(season, f"{date} vs {g['opponent']}: schedule says {s['bangor_score']}-{s['opp_score']}, "
                             f"game tab says {t['bangor_score']}-{t['opp_score']} (using game tab)")
            if s and t and canon_opp(s["opponent"]).lower() != t["opponent"].lower():
                warn(season, f"{date}: schedule opponent '{s['opponent']}' vs tab opponent '{t['opponent']}'")
            # neutral site: tournaments / playoffs played away from either school
            xl = extra_lines.get(g["date"])
            if xl and xl.get("site") and (not (s or {}).get("site") or xl["site"] == "neutral"):
                g["site"] = xl["site"]  # "neutral" overrides the schedule's home/away (a playoff site)
            if xl and xl.get("event") and not (t or {}).get("event"):
                g["event"] = xl["event"]
            ev = " ".join([g["location"], g["event"]])
            g["game_type"] = classify_type(ev)
            loc = g["location"].lower()
            if g["game_type"] in ("tournament", "playoff") and loc and "bangor" not in loc and \
                    canon_opp(g["opponent"]).lower().split()[0] not in loc:
                g["site"] = "neutral"
            periods = (t or {}).get("periods")
            if not periods and xl and xl.get("period_labels"):
                periods = {"labels": xl["period_labels"].split("|"),
                           "bangor": [num(x) for x in xl["bangor_periods"].split("|")],
                           "opp": [num(x) for x in xl["opp_periods"].split("|")]}
            if xl and xl.get("recap"):
                g["recap"] = xl["recap"]
            opp_players = (t or {}).get("opp_players") or extra_opp.get(g["date"])
            players = (t or {}).get("players")
            if extra_box.get(g["date"]):  # a full box score from a printed stat sheet: it replaces a tab
                players = extra_box[g["date"]]  # that has only points (and is often missing some)
                g["box_source"] = "printout"
                if extra_opp.get(g["date"]):  # the printout's opponent box too, with the tab's first names
                    tab_opp = (t or {}).get("opp_players") or []
                    full = {}
                    for q in tab_opp:
                        full.setdefault(q["name"].split()[-1].lower(), []).append(q["name"])
                    opp_players = []
                    for q in extra_opp[g["date"]]:
                        names = full.get(q["name"].lower(), [])
                        opp_players.append(dict(q, name=names[0]) if len(names) == 1 and " " not in q["name"] else q)
            nw = extra_news.get(g["date"])
            if nw and not players:  # newspaper leaders only: points and rebounds for a few players
                players = nw["bangor"]
                opp_players = opp_players or nw["opp"]
                g["box_source"] = "newspaper"
            if periods:
                p = periods
                g["period_labels"] = "|".join(p["labels"])
                g["bangor_periods"] = "|".join("" if x is None else str(x) for x in p["bangor"])
                g["opp_periods"] = "|".join("" if x is None else str(x) for x in p["opp"])
                g["ot"] = str(sum(1 for l in p["labels"] if "OT" in l.upper()) or "")
            if players:
                pts_known = sum((p["pts"] or 0) for p in players)
                # a newspaper clipping is a full box score only when it gives every player's shooting, not
                # just a few leading scorers with one player's field goals
                full = (all if g["box_source"] == "newspaper" else any)(p["fga"] is not None for p in players)
                g["box_score"] = "full" if full else "points"
                g["box_points"] = pts_known
                g["box_complete"] = "Y" if pts_known == g["bangor_score"] else "N"
                if g["bangor_score"] not in ("", None) and pts_known != g["bangor_score"] and not g["box_source"]:
                    warn(season, f"{date} vs {g['opponent']}: Bangor players' points add to {pts_known}, "
                                 f"final score {g['bangor_score']}")
                for p in players:
                    row = {"game_id": gid, "season": season, "date": g["date"], "opponent": g["opponent"],
                           "player_id": slug(p["name"]), "name": p["name"], "number": p["number"],
                           "class": p.get("class", "")}
                    for k in STAT_COLS:
                        row[k] = "" if p.get(k) is None else p[k]
                    pg_out.append(row)
            for p in (opp_players or []):
                row = {"game_id": gid, "season": season, "date": g["date"], "team": g["opponent"],
                       "name": p["name"], "number": p["number"]}
                for k in STAT_COLS:
                    row[k] = "" if p.get(k) is None else p[k]
                opp_out.append(row)
            games_out.append(g)

    # ---- players
    seasons_by_player = defaultdict(set)
    names_by_player = defaultdict(set)
    for r in pg_out:
        seasons_by_player[r["player_id"]].add(r["season"])
        names_by_player[r["player_id"]].add(r["name"])
    for r in totals_out:
        if r.get("name"):
            seasons_by_player[slug(r["name"])].add(r["season"])
            names_by_player[slug(r["name"])].add(r["name"])
    players_out = []
    for pid in sorted(seasons_by_player):
        ss = sorted(seasons_by_player[pid])
        players_out.append({"player_id": pid, "name": sorted(names_by_player[pid])[0],
                            "first_season": ss[0], "last_season": ss[-1],
                            "seasons": "|".join(ss), "grad_year": "", "notes": ""})
        span = int(ss[-1][:4]) - int(ss[0][:4])
        if span >= 4:
            warn("players", f"'{pid}' appears {ss[0]} to {ss[-1]} ({len(ss)} seasons) — "
                            f"possibly two different people with the same name")

    write(os.path.join(OUT, "games.csv"), games_out)
    write(os.path.join(OUT, "player_games.csv"), pg_out)
    write(os.path.join(OUT, "opponent_player_games.csv"), opp_out)
    write(os.path.join(OUT, "players.csv"), players_out)
    keys = ["season", "number", "name"]
    extra = sorted({k for r in totals_out for k in r} - set(keys))
    write(os.path.join(OUT, "source_season_totals.csv"), totals_out, keys + extra)
    with open(os.path.join(OUT, "conversion_warnings.txt"), "w") as f:
        f.write("\n".join(warnings) + "\n")
    print(f"games={len(games_out)} player_games={len(pg_out)} opponent_rows={len(opp_out)} "
          f"players={len(players_out)} warnings={len(warnings)}")


def write(path, rows, fields=None):
    if not rows:
        return
    fields = fields or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
