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
| `historical_records.csv` | Record-book marks older than (or missing from) the stat sheets. A `source` of `newspaper` labels a mark from a newspaper box score instead of the record book. |
| `season_results.csv` | Results for seasons before the stat sheets, typed in from a printed list (a yearbook page, a schedule recap, old newspaper columns): game number in order (blank when a source doesn't say which game of the season it was), opponent, score (a `result` of W or L when part of the score is lost), and the date and site (`home`/`away`/`neutral`) when the source gives them. When every game in a season has a date and site (2001–02), the season becomes a regular season: each game gets a game page, newspaper clippings in `line_scores.csv` and `newspaper_stats.csv` attach to it by date, and its games count in head-to-head and game records. Otherwise the season gets a results page in the same layout, with no game pages, and its games stay out of head-to-head records. |
| `stories/` | Archive writing about a season, such as old newspaper columns or interviews, one `.txt` file each. A few `key: value` lines (`season`, `slug`, `title`, `kicker`, `summary`, `byline`, `credit`, and `results_note`, which shows under the results) come first, then a `---` line, then the text: `# ` starts a part, `## ` a section, `> ` a note set apart, and other lines are paragraphs. Each becomes a page linked from the top of its season page. |
| `rosters.csv` | Rosters from game programs for seasons with no player stats (season, number, name, position, height, grade, source). They show on the season's results page, with the class year worked out from the grade. |
| `season_totals.csv` | Player season totals typed in from a printed season stat sheet (2001–02 and 2002–03), with the same column names as the sheets' season tabs. FGM/FGA include 3-pointers. A row named `Team` holds the sheet's printed team totals, used for the team row and team season records. Players whose careers reach back past 2007–08 are marked partial: their stats show on their pages and in season records, but not in career records or leaderboards. |
| `line_scores.csv` | Scores by quarter for games the sheets don't have them for (from Bound, newspaper clippings and so on), keyed by date. The `recap` column is a sentence or two about the game, shown on the game page in place of the automatic game summary (see *Game summaries*). `site` fills in home/away when the schedule has none, and `neutral` overrides it (a playoff game at another school); `event` names the round and place. |
| `opponent_boxscores.csv` | Opponent box scores from other sources, keyed by date. |
| `newspaper_stats.csv` | Leading scorers and rebounders from newspaper clippings (date, team, number, name and any box-score columns: fgm, fga, tpm, tpa, ftm, fta, reb, ast, blk, pts), for games with no box score. They show on the game page and in player game logs, marked as partial. They don't add to season totals that come from a season stat sheet, and don't count as a player's game highs. |
| `boxscores.csv` | Full Bangor box scores typed in from a printed stat sheet (date, team, number, name and the box-score columns), for a game the season sheet has no stats for, or only points. A printout replaces the sheet's game tab. They count like any box score on the game page, in game records and in game highs. In a season whose sheet tracks only points (2012–13), they add only points to the season totals, and a player's points and games that season come from the box scores rather than the sheet's season tab, which counted some of these games for some players. |
| `team_game_stats.csv` | Team totals for games with no box score by player (date, team, then fgm, fga, tpm, tpa, ftm, fta, oreb, dreb, reb, ast, stl, to, pf, chg, pts and source), one row for Bangor and one for the opponent, from a yearbook's game-by-game team stats (1997–98). They show as a Team stats table on the game page, and Bangor's count in the team game records. FGM/FGA include 3-pointers. |
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

**Before each game** its page shows a *Head to head* preview: Bangor's all-time record against that opponent (and at that site, and in the playoffs for a playoff game), the current streak, the last meeting and who led Bangor in it, the average score, the biggest win and worst loss, and how today's players have done against them. The home page's upcoming games show the series record. It all comes from games already in the data, so there's nothing to fill in.

**Calendar feed.** Each build writes the current season's schedule to `/schedule.ics`. The *Add to calendar* button on the season page and the home page's upcoming games subscribes to it in Google Calendar, Apple Calendar (iPhone, iPad, Mac) or Outlook. Each game is one event with the start time, location and livestream link. Time changes, postponements and final scores (`W 77–53 · Bangor vs Arcadia`) update on people's calendars the next time their calendar app checks: every few hours for Apple and Outlook, and up to a day for Google. Games without a start time are all-day events.

**Sheet check.** Each build looks for likely mistakes in the sheets: a missing final score for a game already played, a W with the lower score, a date in the wrong year, the same game listed twice, an opponent or player name spelled two ways, made shots that don't add up to a player's points, and more. The current season's findings are printed in the Vercel build log and listed at **/sheet-check**, a page that isn't linked from the site or shown to search engines. Nothing on the list stops the site from updating. To see the same list on your computer: `.venv/bin/python scripts/sheet_check.py` (add `--all` for every season).

## End of season
1. Download the final sheet (File → Download → Microsoft Excel) into `source-sheets/` as `YYYY-YY Stats.xlsx`. The build already keeps a copy there.
2. Add the season's line (record, coach, notes) to `overrides/season_history.csv`.
3. In `overrides/current_season.json`, change `season` and `sheet_url` to next year's sheet.

## Game summaries
Every finished game's page opens with a short paragraph about the game, written during the build by `scripts/recaps.py`. It uses only what's in the data: the score and where it was played, the leading scorers (and rebounds, assists and so on when there's a full box score), how the game went by quarter (a comeback, a lead that slipped away, overtime, a big quarter), a top-3 record-book mark, the opponent's top scorer, and the season record and streak afterward. It's at most five sentences and adds no adjectives the numbers can't back up. A `recap` in `overrides/line_scores.csv` replaces it for that game, so a newspaper's account always wins. There's nothing to fill in. New games get a summary as soon as the score and box score are in the sheet.

## On this day
The home page has an "On this day" card: up to three games or record-book nights from today's date in past seasons, one per year, playoff games and record nights first. Each is a one- or two-sentence summary (the same writer as the game summaries) linking to the game, or to the record book for a game with no page. The build writes them all to `static/on-this-day.js`, and the visitor's browser picks today's date in Wisconsin time, so the card stays right between rebuilds and through the summer. With nothing on today's date it shows *This week in Bangor history* (three days either way), and in the off-season *From the archives*: a few of the biggest nights, the same ones all day. New games and record-book marks with a date join automatically.

## Help fill in the gaps
`/history/gaps` (linked from the History page and in search) shows what the site has for every season: results, box scores, player stats, a roster and film. Seasons with everything are marked complete. A "Most wanted" list shows title and tournament teams whose results are still missing, and the page explains what kinds of old material help. It's all worked out from the data each build, so adding a season's results, rosters or clippings updates it automatically. Its "Share something" buttons appear once the corrections form is set up (see *Corrections form*).

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

## Data downloads
Each build writes CSV files of the data to `/downloads/`: every game, player season totals, box scores, career totals and the record book, plus each season's results and player stats. They're linked from the Seasons page (*Download the data*), each season page, the Record Book and the Career Leaders page. A blank means the stat wasn't recorded.

## Fonts
The site serves its own fonts (`site-src/static/fonts/`), so pages don't load anything from Google. They're compressed, Latin-only copies of `site-src/fonts/Inter.ttf` and `Oswald.ttf`, which the share-image drawing still uses. To remake them after changing a font, run the `fontTools` subsetter (`pip install fonttools brotli`) with the weights the CSS uses: Inter 400–700 and Oswald 500–700.

## Visitor stats
Vercel Web Analytics counts page views without cookies. To turn it on: in Vercel, open the project → **Analytics** → **Enable**. Then set `vercel_analytics` to `true` in `overrides/site.json` and commit. The counter is added only on Vercel, never to local builds.

## Broken-link check
After each build, `scripts/check_links.py` follows every link inside the site and lists any that point to a missing page, file or `#section`. In the Vercel build it only reports (in the build log), so a broken link never stops a score update. The **Check site links** GitHub workflow (`.github/workflows/check.yml`) builds the site on every push and fails if any link is broken, so GitHub shows a red X on the commit and emails you. To check on your computer after a build: `.venv/bin/python scripts/check_links.py`.

## Rebuild locally
```
./build.sh
```
