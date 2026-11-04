"""Link GX3 Media photo galleries (gx3media.smugmug.com) to Bangor games.

GX3's SmugMug site doesn't allow automated crawling, so the gallery list in overrides/gx3_galleries.csv
is collected by hand (season, gallery title, link). This script matches each gallery to a game and adds it
to overrides/news_stories.csv as a "photos" row. Run it after adding galleries:
  .venv/bin/python scripts/match_gx3.py

Gallery titles look like "02-23-26 Royall @ Bangor BBB2526", "Bangor @ Necedah BBB1617" or
"D5 StateF - Bangor vs McDonell BBB1718". A date in the title is used when present; otherwise the
opponent, home/away and season. Anything it can't place is printed for you to add by hand.
"""
import csv, datetime as dt, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match_stories import OPP_ALIASES, FIELDS, STORIES, norm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GALLERIES = os.path.join(ROOT, "overrides", "gx3_galleries.csv")
SKIP = re.compile(r"practice|team photo|basketball team", re.I)


def main():
    games = [g for g in csv.DictReader(open(os.path.join(ROOT, "data", "games.csv"))) if g["result"]]
    terms = {}
    for o in {g["opponent"] for g in games}:
        ts = {norm(o).strip(), norm(o.split("/")[0]).strip(), norm(o.split("-")[0]).strip()} | \
             {norm(a).strip() for a in OPP_ALIASES.get(o, [])}
        terms[o] = {t for t in ts if len(t) >= 3}
    rows = list(csv.DictReader(open(STORIES))) if os.path.exists(STORIES) else []
    have = {r["url"] for r in rows}
    added, unplaced = [], []
    for gal in csv.DictReader(open(GALLERIES)):
        title, url, season = gal["gallery"].strip(), gal["url"].strip(), gal["season"].strip()
        if url in have or SKIP.search(title):
            continue
        core = re.sub(r"\s*BBB\s*\d{4}.*$", "", title)                     # drop "BBB2526" and anything after
        m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{2})\s+", core)
        date = None
        if m:
            date = dt.date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2)))
            core = core[m.end():]
        core = re.split(r"\s+-\s+|:\s+", core)[-1]                         # drop "D5 StateF - " / "Westby tny: "
        core = re.sub(r"^(DIV|D\d)\s+\w+(\s+\w+)?\s+(?=\S+.*(@| vs ))", "", core) if " - " not in title else core
        if "@" in core:
            a, b = [x.strip() for x in core.split("@", 1)]
            site = "home" if b.lower().startswith("bangor") else "away"
            opp = a if site == "home" else b
        elif re.search(r"\bvs\b", core):
            a, b = [x.strip() for x in re.split(r"\bvs\b", core, 1)]
            opp, site = (b if a.lower().startswith("bangor") else a), "neutral"
        else:
            unplaced.append((title, "no teams found")); continue
        nopp = norm(re.sub(r"^(DIV|D\d)\s+(Sectional Semifinal|Regional)\s+", "", opp))
        cands = [g for g in games if g["season"] == season and any(f" {t} " in nopp for t in terms[g["opponent"]])]
        if date:
            cands = [g for g in cands if abs((dt.date.fromisoformat(g["date"]) - date).days) <= 1] or \
                    [g for g in games if g["date"] == date.isoformat()]
        elif len(cands) > 1 and site != "neutral":
            cands = [g for g in cands if g["site"] == site] or cands
        if len(cands) > 1 and re.search(r"\b(D\d|DIV)\b", title):
            # older seasons label playoff games "regular": the postseason starts in late February
            cands = [g for g in cands if g["game_type"] == "playoff"] or \
                    [g for g in cands if g["date"][5:] >= "02-20" and g["date"][5:7] in ("02", "03")] or cands
        if len(cands) == 1:
            g = cands[0]
            added.append({"published": g["date"], "outlet": "GX3 Media", "kind": "photos", "title": re.sub(r"^\d{1,2}-\d{1,2}-\d{2}\s+|\s*BBB\s*\d{4}.*$", "", title), "url": url,
                          "access": "free", "game_date": g["date"], "opponent": g["opponent"], "player": "",
                          "matched_by": "gx3 " + ("date" if date else "opponent + site + season")})
        else:
            unplaced.append((title, f"{len(cands)} possible games: " + "; ".join(f"{g['date']} {g['opponent']} ({g['site']})" for g in cands)))
    rows = sorted(rows + added, key=lambda r: (r["game_date"] or r["published"], r["outlet"], r["title"]))
    with open(STORIES, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    print(f"linked {len(added)} galleries; {len(unplaced)} couldn't be placed")
    for t, why in unplaced:
        print(f"  ?? {t}  ->  {why}")


if __name__ == "__main__":
    main()
