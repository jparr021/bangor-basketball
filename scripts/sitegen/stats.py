"""Stat rows and columns for tables, box scores, and the career leaderboards."""
from sitegen.on_this_day import *  # noqa: F401,F403  (everything defined before this part of the build)


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
    ("fgm", "FGM", "fgm"), ("fga", "FGA", "fga"),  # FGM alone: an old sheet with no attempts ("fg_pct", "FG%", "fga"),
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


def team_stats_rows(g, bangor):
    """Bangor's and the opponent's team totals for a game without a Bangor box score."""
    tg = TEAM_GAME.get(g["date"])
    if not tg or (bangor and g.get("box_source") != "newspaper"):  # a clipping's leaders don't replace team totals
        return None
    rows = [(name, tg[side]) for side, name in (("bangor", "Bangor"), ("opp", g["opponent"])) if tg.get(side)]
    cols = box_cols([r for _, r in rows])
    return {"rows": [{"name": n, **box_row(r)} for n, r in rows], "cols": cols,
            "source": next((r["source"] for _, r in rows if r.get("source")), "")}


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
            # an old career counted complete but missing this stat for a season (1994-95 assists and steals)
            if c["first_season"] < COVERED_FROM and stat in (c.get("untracked") or "").split("|"):
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
