# Bangor Cardinals Boys Basketball — history site

A static website with Bangor High School (WI) boys basketball history: every season, box scores, player pages, the record book, coaches, opponents, game film and live streams. It's hosted on Vercel.

## Folders
| Folder | What's in it |
|---|---|
| `source-sheets/` | One Excel file per season, downloaded from Google Sheets. **This is the raw data.** |
| `overrides/` | Things maintained by hand (see below). |
| `data/` | Generated. The cleaned-up standard dataset (see `data/README.md`). |
| `scripts/` | The converter, checks, record calculations, site builder and film matcher. |
| `site-src/` | Page templates, styles and the logo. |
| `site/` | Generated. The finished website (Vercel builds this itself). |

### `overrides/`
| File | What it's for |
|---|---|
| `current_season.json` | The current season and its Google Sheet link. |
| `season_history.csv` | Year-by-year record, coach and notes from the record book, 1914 to today. |
| `historical_records.csv` | Record-book marks older than (or missing from) the stat sheets. |
| `career_totals.csv` | Official career totals where the stat sheets are incomplete. |
| `game_film.csv` | YouTube film for each game (filled by the film matcher, editable by hand). |

## During the season (automatic)
1. The current season's Google Sheet is shared as **Anyone with the link → Viewer**, and its link is in `overrides/current_season.json`.
2. After each game, add the game's stats tab as usual. Put the final score in the **Schedule** tab's *Result* column (for example `W 77-53`).
3. The Schedule tab can also have:
   - a **Time** column (or just leave the time, like `7:00 PM`, in the Result column until the game is played)
   - a **Stream** column with the livestream link. Paste the link, or link the text "Watch".
   - a **Film** column with the YouTube link.
4. Every 3 hours (November–March), GitHub tells Vercel to rebuild. Vercel downloads the sheet and republishes. To refresh right away: GitHub → Actions → *Refresh site* → **Run workflow**.

New games flow into season stats, player pages, career totals and the record book automatically.

## End of season
1. Download the final sheet (File → Download → Microsoft Excel) into `source-sheets/` as `YYYY-YY Stats.xlsx`. The build already keeps a copy there.
2. Add the season's line (record, coach, notes) to `overrides/season_history.csv`.
3. In `overrides/current_season.json`, change `season` and `sheet_url` to next year's sheet.

## Game film
**Automatic:** every 3 hours, GitHub checks the YouTube channel for new videos (`.github/workflows/film.yml`). It matches them to games by the date and opponent in the title, for example *Bangor vs Necedah - February 10, 2026*, and republishes the site. It only adds film and never removes any. To check right away: GitHub → Actions → *Add new YouTube game film* → **Run workflow**.

**Priority on a game page:** YouTube film plays right on the page. Hudl full-game replays and recaps (`overrides/hudl_video.csv`) appear as buttons, and drop to "Also on Hudl" once a game has YouTube film.

**By hand:** matches are saved in `overrides/game_film.csv`. Anything uncertain goes to `data/film_review.csv`, including a new video for a game that already has film. To fix, swap or add one, edit `game_film.csv` and set `matched_by` to `manual`. Manual rows are never overwritten. To re-match the whole channel:
```
.venv/bin/python scripts/match_film.py "https://www.youtube.com/channel/UCMQOY87AZs0Hl4VQc61JTKg"
```

## Web address, link previews and search
- Page addresses are clean (`/players/hayden-massman`). Old `.html` links redirect automatically.
- Each page has a link preview (title, description, logo image) for texts and social posts. There's also a `sitemap.xml` and `robots.txt` for Google.
- These use the site's production address, which Vercel supplies at build time. **Adding a custom domain needs no code change.** Add it in Vercel (Project → Settings → Domains), set it as the primary domain, and the next build uses it everywhere. After switching, submit `https://<your-domain>/sitemap.xml` in Google Search Console.

## Rebuild locally
```
./build.sh
```
