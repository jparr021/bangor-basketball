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
| `season_results.csv` | Results for seasons before the stat sheets, typed in from a printed list (a yearbook page): game number in printed order, opponent, score, and the date and site (`home`/`away`) when the source gives them. These seasons get a results-only page (no box scores). When every game in a season has a date and site, its games also count in the head-to-head records on opponent pages; otherwise they stay out. |
| `season_totals.csv` | Player season totals typed in from a printed season stat sheet (2001–02 and 2002–03), with the same column names as the sheets' season tabs. FGM/FGA include 3-pointers. A row named `Team` holds the sheet's printed team totals, used for the team row and team season records. Players whose careers reach back past 2007–08 are marked partial: their stats show on their pages and in season records, but not in career records or leaderboards. |
| `grad_years.csv` | Class years (name, grad_year, note) for players the sheets don't give one for, or to fix an estimated year. |
| `career_totals.csv` | Official career totals where the stat sheets are incomplete. |
| `game_film.csv` | YouTube film for each game (filled by the film matcher, editable by hand). |
| `site.json` | The corrections form link for the footer (see *Corrections form*). |
| `news_stories.csv` | Local news stories linked to games and players (filled by the story finder, editable by hand). |

## During the season (automatic)
1. The current season's Google Sheet is shared as **Anyone with the link → Viewer**, and its link is in `overrides/current_season.json`.
2. After each game, add the game's stats tab as usual. Put the final score in the **Schedule** tab's *Result* column (for example `W 77-53`).
3. The Schedule tab can also have:
   - a **Time** column (or just leave the time, like `7:00 PM`, in the Result column until the game is played)
   - a **Stream** column with the livestream link. Paste the link, or link the text "Watch".
   - a **Film** column with the YouTube link.
4. Every 3 hours (November–March), GitHub tells Vercel to rebuild. Vercel downloads the sheet and republishes. On game nights it also rebuilds every 20 minutes from about 7 to 11:40 pm, so the final score appears soon after it's entered. To refresh right away: GitHub → Actions → *Refresh site* → **Run workflow**.

New games flow into season stats, player pages, career totals and the record book automatically.

**On game day** every page shows a "Game today" banner under the menu, with the livestream link. Pages correct their own labels to the visitor's time (Wisconsin time): *Today*, then *Live now* from just before the start time until about 2¼ hours later, then *Score coming soon* until the score is in the sheet and the next rebuild runs. Without a start time, the game counts as over at 10:30 pm. After the game, a livestream link to that one game becomes *Watch replay*; a link to a channel page is hidden.

**Sheet check.** Each build looks for likely mistakes in the sheets: a missing final score for a game already played, a W with the lower score, a date in the wrong year, the same game listed twice, an opponent or player name spelled two ways, made shots that don't add up to a player's points, and more. The current season's findings are printed in the Vercel build log and listed at **/sheet-check**, a page that isn't linked from the site or shown to search engines. Nothing on the list stops the site from updating. To see the same list on your computer: `.venv/bin/python scripts/sheet_check.py` (add `--all` for every season).

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

## Local news stories
**Automatic:** every 3 hours from November through March, GitHub checks WKBT News 8, WXOW 19 and the La Crosse Tribune for stories about Bangor boys basketball (`.github/workflows/stories.yml`). It links a story to a game when the headline mentions Bangor, the story names the opponent within a few days of a game against them, and the story gives the final score or says "boys". Girls stories are skipped. A station's highlight video is linked when the same station already has a confirmed boys story on that game. "Play of the Week" features go on the player's page. It only adds stories and never removes any. To check right away: GitHub → Actions → *Add new local news stories* → **Run workflow**.

**Where they show:** a "Game coverage" section on the game page, a *News* link on the season schedule and home page, and an "In the news" section on player pages (features, plus game stories whose headline names the player). Tribune articles are marked "may need a subscription".

**GX3 Media photo galleries** (gx3media.smugmug.com): SmugMug doesn't allow automated crawling, so the gallery list is kept by hand in `overrides/gx3_galleries.csv` (season, gallery title as GX3 names it, link). 99 galleries from 2009-10 to 2025-26 are in it. After adding new ones, run:
```
.venv/bin/python scripts/match_gx3.py
```
It places each gallery by the date in its title, or by opponent + home/away + season (and late-season games for playoff galleries), adds it to `news_stories.csv`, and lists any it can't place. GX3 has one whole-season gallery for 2007-08 and 2008-09 (`BaHSBBB0708`, `BaHSBBB0809` in the Bangor school folders), which aren't linked to single games. Galleries show in a game's coverage list as "Photo gallery". Any other outlet's gallery can be added straight to `news_stories.csv` with `kind` set to `photos`.

**By hand:** stories are saved in `overrides/news_stories.csv`. Uncertain ones go to `data/stories_review.csv` with the reason. To add or fix one, add a row to `news_stories.csv` (`game_date` and `opponent` for a game story, or `player` for a feature) and set `matched_by` to `manual`. To search past seasons again:
```
.venv/bin/python scripts/match_stories.py --all
```

## Corrections form
The footer on every page can show a "Spot an error, or have an old photo, program or clipping to share?" link to a Google Form. It stays hidden until the form exists.
1. Create a Google Form (forms.google.com) with questions like *Your name*, *Email (optional)*, *Page*, *What should be fixed or added?* and a file upload for photos.
2. Click **Send**, choose the link icon and copy the link into `corrections_form_url` in `overrides/site.json`.
3. Optional: so the form fills in the page the visitor came from, open the form's ⋮ menu → **Get pre-filled link**, type anything in the *Page* question, click **Get link**, and copy the number after `entry.` into `corrections_page_field`.
4. Commit the change. The next build adds the link to every page. Answers collect in the form's Responses tab (or a linked Google Sheet).

## Web address, link previews and search
- Page addresses are clean (`/players/hayden-massman`). Old `.html` links redirect automatically.
- Each page has a link preview (title, description and image) for texts and social posts. Game, player, season, coach and opponent pages get their own preview image (the score, career stats, record and so on), drawn during the build by `scripts/share_images.py` in the site's fonts (`site-src/fonts`). Other pages use the logo. There's also a `sitemap.xml` and `robots.txt` for Google.
- These use the site's production address, which Vercel supplies at build time. **Adding a custom domain needs no code change.** Add it in Vercel (Project → Settings → Domains), set it as the primary domain, and the next build uses it everywhere. After switching, submit `https://<your-domain>/sitemap.xml` in Google Search Console.

## Rebuild locally
```
./build.sh
```
