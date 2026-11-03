import glob, os, openpyxl, re, collections
for path in sorted(glob.glob("source-sheets/*.xlsx")):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Schedule"]
    rows = [[("" if v is None else str(v)) for v in r] for r in ws.iter_rows(values_only=True)]
    rows = [r for r in rows if any(c.strip() for c in r)]
    hdr = rows[0]; body = rows[1:]
    res = collections.Counter()
    odd = []
    for r in body:
        x = r[1] if len(r) > 1 else ""
        m = re.match(r"^([WLT])\s*\n?\s*(\d+)-(\d+)", x)
        if m: res[m.group(1)] += 1
        else: odd.append((r[0][:10], x.replace("\n"," "), r[2] if len(r)>2 else ""))
    ps = [s for s in wb.sheetnames if s == "Player Stats"]
    sections = []
    if ps:
        for r in wb["Player Stats"].iter_rows(values_only=True):
            r = [c for c in r if c is not None]
            if len(r) == 1: sections.append(str(r[0]))
    print(f"{os.path.basename(path)[:7]} hdr={[h for h in hdr if h]} games={len(body)} {dict(res)} odd={odd[:4]} PS={sections[:8]}")
