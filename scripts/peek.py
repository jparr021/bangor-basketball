import sys, openpyxl
path, tab = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
names = [s for s in wb.sheetnames if s.startswith(tab)]
for nm in names[:1]:
    print("##", nm)
    for i, r in enumerate(wb[nm].iter_rows(values_only=True)):
        if i >= n: break
        r = [("" if v is None else str(v)) for v in r]
        while r and r[-1] == "": r.pop()
        if r: print(i+1, r)
