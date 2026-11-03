"""Match YouTube videos from a channel or playlist to Bangor games.

Usage:
  .venv/bin/python scripts/match_film.py "https://www.youtube.com/@YourChannel"   [--dates] [--add-only]

--add-only (used by the scheduled GitHub workflow): keep every film row already in the list, and
only add videos for games that don't have film yet. Never removes anything. If YouTube returns no
videos (blocked, outage), nothing is written.

It lists every video (titles only, which is quick; with --dates it also reads each video's upload
date, which is slower but matches more), works out the game from the date and opponent in the title,
and writes:
  overrides/game_film.csv  matched videos (rows you added or fixed by hand, matched_by=manual, are kept)
  data/film_review.csv     everything it wasn't sure about, with the reason, for you to check
"""
import csv, datetime as dt, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILM = os.path.join(ROOT, "overrides", "game_film.csv")
REVIEW = os.path.join(ROOT, "data", "film_review.csv")
YTDLP = os.path.join(ROOT, ".venv", "bin", "yt-dlp")
if not os.path.exists(YTDLP):
    YTDLP = "yt-dlp"  # e.g. on GitHub's servers, installed with pip
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
OPP_NICKNAMES = {  # extra spellings seen in titles -> canonical opponent
    "get": "Gale-Ettrick-Trempealeau", "g-e-t": "Gale-Ettrick-Trempealeau",
    "melmin": "Melrose-Mindoro", "mel-min": "Melrose-Mindoro", "brf": "Black River Falls",
    "wonewoc": "Wonewoc-Center", "c-fc": "Cochrane-Fountain City", "cfc": "Cochrane-Fountain City",
    "acl": "Alma Center Lincoln", "lincoln": "Alma Center Lincoln", "blair": "Blair-Taylor",
    "mel min": "Melrose-Mindoro", "gilmanton": "Gilmanton/Independence",
}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def season_of(d):
    y = d.year if d.month >= 8 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def title_date(t):
    """Find a game date in a video title."""
    t = t.lower()
    m = re.search(r"\b(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})\b", t)
    if m:
        return safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", t)
    if m:
        y = int(m.group(3)); y = y + 2000 if y < 100 else y
        return safe(y, int(m.group(1)), int(m.group(2)))
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*[,.]?\s+(20\d\d)\b", t)
    if m:
        return safe(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    return None


def safe(y, m, d):
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def title_season(t):
    m = re.search(r"\b(20\d\d)\s*[-/]\s*(\d\d)\b", t)
    if m and (int(m.group(1)) + 1) % 100 == int(m.group(2)):
        return f"{m.group(1)}-{m.group(2)}"
    return None


def list_videos(url, with_dates):
    cmd = [YTDLP, "--flat-playlist", "-J", url] if not with_dates else [YTDLP, "-J", "--skip-download", "--ignore-errors", url]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    vids = []

    def walk(e):
        for x in e.get("entries") or []:
            if x.get("entries"):
                walk(x)
            elif x.get("id"):
                vids.append({"id": x["id"], "title": x.get("title") or "",
                             "upload": x.get("upload_date") or ""})
    walk(data)
    return vids


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    url, with_dates, add_only = sys.argv[1], "--dates" in sys.argv, "--add-only" in sys.argv
    with open(os.path.join(ROOT, "data", "games.csv")) as f:
        games = [g for g in csv.DictReader(f) if g["result"]]
    opp_names = {}
    for g in games:
        opp_names[norm(g["opponent"])] = g["opponent"]
    for k, v in OPP_NICKNAMES.items():
        opp_names[norm(k)] = v
    names_by_len = sorted(opp_names, key=len, reverse=True)

    keep = []
    if os.path.exists(FILM):
        with open(FILM) as f:
            keep = [r for r in csv.DictReader(f) if add_only or r.get("matched_by") == "manual"]
    have_film = {(r["date"], r["opponent"]) for r in keep} if add_only else set()
    kept_ids = {re.search(r"([A-Za-z0-9_-]{11})$", r["youtube_url"]).group(1) for r in keep
                if re.search(r"([A-Za-z0-9_-]{11})$", r["youtube_url"])}

    try:
        vids = list_videos(url, with_dates)
    except Exception as e:  # noqa: BLE001
        print(f"could not list videos ({e}); nothing changed")
        return
    print(f"{len(vids)} videos found")
    if not vids:
        print("YouTube returned no videos; nothing changed")
        return
    matched, review = [], []
    for v in vids:
        if v["id"] in kept_ids:
            continue
        t = v["title"]
        nt = " " + norm(t) + " "
        opp = next((opp_names[n] for n in names_by_len if f" {n} " in nt), None)
        d = title_date(t)
        cands = []
        how = ""
        if d:
            gap = lambda g: abs((dt.date.fromisoformat(g["date"]) - d).days)
            cands = [g for g in games if gap(g) == 0 and (not opp or g["opponent"] == opp)]
            how = "title date + opponent" if opp else "title date"
            if not cands and opp:
                # title date a little off: same opponent within 3 days
                cands = [g for g in games if g["opponent"] == opp and gap(g) <= 3]
                how = "opponent, title date off by a day or two"
        elif opp:
            s = title_season(t)
            cands = [g for g in games if g["opponent"] == opp and (not s or g["season"] == s)]
            if v["upload"]:
                up = dt.datetime.strptime(v["upload"], "%Y%m%d").date()
                near = [g for g in cands if 0 <= (up - dt.date.fromisoformat(g["date"])).days <= 10]
                cands = near or cands
                how = "opponent + upload date"
            else:
                how = "opponent + season" if s else "opponent only"
        if len(cands) == 1:
            g = cands[0]
            if how.startswith("opponent, title date off"):
                review.append({"title": t, "youtube_url": f"https://www.youtube.com/watch?v={v['id']}",
                               "upload_date": v["upload"], "reason": "matched, but the title's date is off by a day or two (please confirm)",
                               "candidates": f"{g['date']} {g['opponent']}"})
            matched.append({"date": g["date"], "opponent": g["opponent"],
                            "youtube_url": f"https://www.youtube.com/watch?v={v['id']}", "title": t, "matched_by": how})
        else:
            reason = "no date or opponent in title" if not cands and not (d or opp) else \
                     ("no Bangor game on that date/opponent" if not cands else f"{len(cands)} possible games")
            review.append({"title": t, "youtube_url": f"https://www.youtube.com/watch?v={v['id']}",
                           "upload_date": v["upload"], "reason": reason,
                           "candidates": "; ".join(f"{g['date']} {g['opponent']}" for g in cands[:5])})
    # one video per game: if two videos land on the same game, send both to review
    by_game = {}
    for r in matched:
        by_game.setdefault((r["date"], r["opponent"]), []).append(r)
    final = []
    for k, rs in by_game.items():
        if len(rs) == 1 and k in have_film:
            review.append({"title": rs[0]["title"], "youtube_url": rs[0]["youtube_url"], "upload_date": "",
                           "reason": "this game already has film; add it by hand to swap", "candidates": f"{k[0]} {k[1]}"})
        elif len(rs) == 1:
            final.append(rs[0])
        else:
            for r in rs:
                review.append({"title": r["title"], "youtube_url": r["youtube_url"], "upload_date": "",
                               "reason": f"{len(rs)} videos matched the same game", "candidates": f"{k[0]} {k[1]}"})
    rows = sorted(keep + final, key=lambda r: r["date"])
    with open(FILM, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "opponent", "youtube_url", "title", "matched_by"])
        w.writeheader(); w.writerows(rows)
    with open(REVIEW, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["title", "youtube_url", "upload_date", "reason", "candidates"])
        w.writeheader(); w.writerows(review)
    print(f"matched {len(final)} new + {len(keep)} kept; {len(review)} need review -> data/film_review.csv")
    for r in final:
        print(f"  NEW: {r['date']} {r['opponent']}  <-  {r['title']}")


if __name__ == "__main__":
    main()
