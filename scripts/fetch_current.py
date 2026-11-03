"""Download the current season's Google Sheet (shared as 'anyone with the link can view')
into source-sheets/ so the build picks up the latest games.

Settings live in overrides/current_season.json. If the download fails, the build carries on
with whatever copy is already in source-sheets/ (it never deletes data).
"""
import json, os, re, sys, urllib.request, zipfile, io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "overrides", "current_season.json")


def main():
    with open(CFG) as f:
        cfg = json.load(f)
    url, season = cfg.get("sheet_url", "").strip(), cfg.get("season", "").strip()
    if not url:
        print("fetch_current: no sheet_url set; skipping")
        return
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url)
    if not m or not re.fullmatch(r"\d{4}-\d{2}", season):
        print("fetch_current: sheet_url or season in overrides/current_season.json doesn't look right; skipping")
        return
    export = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
    dest = os.path.join(ROOT, "source-sheets", f"{season} Stats.xlsx")
    try:
        req = urllib.request.Request(export, headers={"User-Agent": "bangor-bb-site-builder"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        zipfile.ZipFile(io.BytesIO(body))  # make sure it's a real spreadsheet, not a sign-in page
    except Exception as e:  # noqa: BLE001 - keep the build going on any failure
        print(f"fetch_current: could not download the {season} sheet ({e}). "
              f"Is it shared as 'Anyone with the link'? Using the existing copy if there is one.")
        return
    with open(dest, "wb") as f:
        f.write(body)
    print(f"fetch_current: downloaded {season} sheet ({len(body) // 1024} KB)")


if __name__ == "__main__":
    main()
