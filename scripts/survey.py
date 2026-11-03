"""Survey every season workbook: tabs, and the header shape of game tabs."""
import sys, glob, os, re
import openpyxl

def rows(ws, n=None):
    out = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if n and i >= n: break
        out.append([("" if v is None else str(v)) for v in r])
    return out

for path in sorted(glob.glob("source-sheets/*.xlsx")):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    names = wb.sheetnames
    game_tabs = [s for s in names if re.match(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}", s)]
    other = [s for s in names if s not in game_tabs]
    print(f"\n=== {os.path.basename(path)}: {len(game_tabs)} game tabs; other tabs: {other}")
    # classify game tab Bangor-box availability
    kinds = {}
    for g in game_tabs:
        rs = rows(wb[g])
        flat = [" | ".join(c for c in r if c) for r in rs]
        txt = "\n".join(flat)
        if "Athlete" in txt: k = "app-export"
        elif "No Data Available" in txt:
            # which team has no data? find line before it
            idx = flat.index("No Data Available")
            k = "nodata:" + ("bangor" if flat[idx-1].strip() == "Bangor" else "opp")
            if txt.count("No Data Available") == 2: k = "nodata:both"
        elif "#" in txt and "Name" in txt: k = "boxscore"
        else: k = "other"
        kinds.setdefault(k, []).append(g)
    for k, v in kinds.items():
        print(f"   {k}: {len(v)}")
    # print header rows of first game tab of each kind
    for k, v in kinds.items():
        rs = rows(wb[v[0]], 14)
        print(f"   -- sample [{k}] {v[0]}")
        for r in rs:
            r = [c for c in r if c != ""]
            if r: print("      ", r[:16])
