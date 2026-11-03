# Record book check

This compares the *Unofficial* Bangor Boys Basketball Recordbook (Google Sheet) with the stats sheets for each season, 2002-03 to 2025-26. The check was run on Nov 3, 2026.

**What the sheets can verify:**
- Team results: from 2002-03.
- Player points: from 2007-08.
- All other player stats (rebounds, assists, steals, blocks, shooting): from 2014-15.

Anything older is outside the data. Those entries are listed under "Can't check", not as wrong.

---

## Status after your second update (re-checked Nov 3, 2026)

**Fixed and confirmed:**
- "Augie" Zabel and "Ellenburg" spelled consistently.
- Canon O'Heron's grad year is 2015 on the Career Rebounds and Career Assists tabs.
- Hank Reader's 10 assists vs. Richland Center added.
- "\*\*" removed from McDonald's 20 free throw attempts and Reader's 449 career 3-point attempts.
- Drew Johnson's 351 is gone from the Points/Rebounds/Assists tab.

**Settled by you:** Canon O'Heron's career totals (1,733 points, 573 rebounds, 180 assists) and Connor Kaiser's (1,284 points, 503 rebounds, 334 assists) are correct. Not all of their games were entered on the stats website. These totals now come from `overrides/career_totals.csv`, and the site will use them instead of the totals from the stats sheets.

**Still open:**
- **Connor Kaiser 2011-12 is still listed twice** in season points: 522 in 25 games, and 482 in 23 games. Since his sheet data is incomplete, 522 may be the real total and 482 the incomplete one. Which should stay?
- **Canon O'Heron still shows grad year 2014** in the three career columns (points, rebounds, assists) of the "Individual Records - Points, Rebounds, Assists" tab.
- **Not yet added:** the 9-assist games by Dustin McDonald (vs. Tomah, 1/14/2023), Hayden Massman (vs. Brookwood, 1/9/2026) and Alex Felch (vs. Black River Falls, 2/9/2026).
- **Unchanged questions:** win/loss for 2003-04 through 2005-06, and 2017-18 team rebounds (1,111 vs. 1,107).

## Status after your first update (re-checked Nov 3, 2026)

**Fixed and confirmed:**
- Birchwood 3-point records now dated 2/26/2026.
- Luke Reader's 9-steal game now dated 12/17/15.
- 2024-25 is now 11-15. Nick Meacham is now 61-40, and the all-time total is now 1166-843-1.
- Drew Johnson's career rebounds are now 311 on the Career Rebounds tab.
- "Connnor" corrected to Connor.
- 1968-69 team free throw % now reads 92.6% (25-27). The numbers now agree with each other, but this is before the data, so the sheets can't confirm it.
- Canon O'Heron's grad year is now 2015 on the Career Scoring tab.
- Team assists in a game: 32 vs. Wonewoc-Center added.
- Hayden Massman's 11 assists added as tied for the single-game record.
- Grant Manke's 299 career free throws added as tied for the record.
- "\*\*" removed from the 36 team steals vs. La Farge.

**Still open:**
- **Connor Kaiser 2011-12 is still listed twice** in season points (522 in 25 games and 482 in 23 games). The same "25 games" count also appears on his 2011-12 rebounds (236) and assists (147) lines. The sheets show 23 games.
- **Canon O'Heron's grad year still says 2014** in three places: the Career Rebounds tab, the Career Assists tab, and the career columns on the "Individual Records - Points, Rebounds, Assists" tab.
- **Drew Johnson still shows 351 rebounds** in the career column on the "Individual Records - Points, Rebounds, Assists" tab. He has 311 on the Career Rebounds tab.
- **Spellings:**
  - "Gunner Ellen**berg**" on the Career Rebounds tab.
  - "Auggie Zabel" on the Points/Rebounds/Assists tab, but "Augie Zabel" on the Individual Records tab.
- **Not yet added:**
  - Hank Reader, 10 assists vs. Richland Center, 12/26/2019.
  - 9-assist games: Dustin McDonald vs. Tomah, 1/14/2023; Hayden Massman vs. Brookwood, 1/9/2026; Alex Felch vs. Black River Falls, 2/9/2026.
- **"\*\*" can come off** Dustin McDonald's 20 free throw attempts and Luke Reader's 449 career 3-point attempts. The sheets confirm both.
- **Optional:** fill in "Unknown" for career free throws attempted (Grant Manke, 437) and career 3-point % (Luke Reader, 43.7%), and "N/A" for team free throws made and attempted in a season (338 and 514, 2017-18). All three are best since 2014-15.
- **Questions still waiting on you:** Canon O'Heron's 1,733 and Connor Kaiser's 1,284 career points; win/loss for 2003-04 through 2005-06; team rebounds of 1,111 vs. 1,107 in 2017-18.

---

## 1. Likely errors to fix (original findings)

| # | Where in the record book | Book says | Sheets say | Notes |
|---|---|---|---|---|
| 1 | Team records: most 3-pointers made and attempted in a game | vs. Birchwood, **2/26/2025** | vs. Birchwood, **2/26/2026** | Wrong year. The game was in the 2025-26 playoffs. |
| 2 | Season points list | Connor Kaiser 2011-12 is listed **twice**: 522 points in 25 games, and 482 in 23 games | 2011-12: **482 points in 23 games**. 2010-11: 382 in 21 games. | The 522 entry is a duplicate or a typo. Removing it moves everyone below it up one rank. |
| 3 | Career scoring, rebounds and assists lists | Canon O'Heron, grad year **2014** | He played 2014-15 (seasons 2011-12 to 2014-15) | Should be **2015**. The individual records page already writes "(15)". |
| 4 | Individual game steals | Luke Reader, 9, vs. New Lisbon, **12/15/15** | That game was **12/17/2015** | Wrong date. |
| 5 | All-Time Win/Loss, 2024-25 | **11-14** | **11-15** (26 games) | All 26 games have box scores. The extra loss also changes Nick Meacham's coaching record to **61-40** and the all-time total to **843** losses. |
| 6 | Career rebounds | Drew Johnson **351** | **311** (2014-15 to 2017-18, all with full stats) | 351 is the same as the Caleb Miedema line next to it, so it may have been copied. |
| 7 | Team season free throw % | "73% (25-27)", 1968-69 | Can't check (before the data) | Doesn't add up: 25 of 27 is **92.6%**, not 73%. Either the percentage or the attempts are wrong. |
| 8 | Team season rebounds | **1,111** (2017-18) | **1,107** | Small gap. The book may include team rebounds that aren't credited to any player. Worth a look. |
| 9 | Spelling | "Gunner Ellen**berg**", "Conn**n**or Kaiser", "Auggie Zabel" and "Augie Zabel" | Ellen**burg**, Connor, (one spelling) | Typos. |

## 2. Records missing from your book

| Record | What the sheets show |
|---|---|
| **Team assists in a game** (book: 31 vs. Alma Center Lincoln, 1987) | **32 vs. Wonewoc-Center, 1/10/2023.** This is a new record. 30 vs. Necedah (2/24/2020) and 30 vs. Black River Falls (2/9/2026) are next. |
| **Individual assists in a game**, tied for the record at 11 | **Hayden Massman, 11 vs. Wonewoc-Center, 2/13/2026** ties Luke Reader's record. |
| Individual assists in a game, 10 | **Hank Reader, 10 vs. Richland Center, 12/26/2019** |
| Individual assists in a game, 9 | **Dustin McDonald** vs. Tomah 1/14/2023. **Hayden Massman** vs. Brookwood 1/9/2026. **Alex Felch** vs. Black River Falls 2/9/2026. |
| **Career free throws made** (book: 299, Bob Steigerwald) | **Grant Manke also has 299**, a tie for the record. |
| Career free throws attempted (book: "Unknown") | Grant Manke, **437** (best since 2014-15). |
| Career 3-point % (min. 75 attempts) (book: "Unknown") | Luke Reader, **43.7% (196-449)** (best since 2014-15). |
| Team free throws made and attempted in a season (book: "N/A") | 2017-18: **338 made, 514 attempted** (most since 2014-15). |

## 3. Confirmed, matching the sheets exactly

Three records your book marks "\*\* Unverified" are now confirmed:
- Dustin McDonald, **20 free throw attempts** vs. Cashton, 2/20/2023.
- Luke Reader, **449 career 3-point attempts**.
- **36 team steals** vs. La Farge, 2/27/2018.

Also confirmed:
- **Single game:**
  - Every points entry from 2011 on: Canon O'Heron 41/38/38/34, Brody Edwards 38, Grant Manke 37/36/36/35, Connor Kaiser 36, Luke Reader 36/35, Dustin McDonald 35/34.
  - Every rebound entry from 2014 on: Chase Horstman 22/19/18/18, Grant Manke 21 and the 19s and 18s, Kyle Wingert 20.
  - Assists: Luke Reader 11, Tanner Jones 10, and all the 2015+ nines.
  - Canon O'Heron's 18 field goals.
  - Tanner Jones's 17 and Hayden Massman's 16 three-point attempts.
- **Season:**
  - Points: Manke 634 and 589, O'Heron 607, Massman 558, McDonald 530, Reader 519 and 473, Kaiser 482.
  - Rebounds: every entry from 2014 on.
  - Assists: Zane Langrehr 139, Luke Reader 122 and 106, Tanner Jones 118, Jaymeson Freit 117, Hayden Massman 117, Canon O'Heron 110, Caleb Miedema 99.
  - Shooting: Manke 73.9% (249-337), Tanner Jones 70 threes, Hayden Massman 193 three-point attempts, Luke Reader 87.1% (74-85) free throws.
  - Five players tied at 30 games played in 2021-22.
- **Career:**
  - Points: Manke 1,694, Reader 1,633, McDonald 1,119, Z. Langrehr 1,105, T. Jones 1,081, Massman 1,052, D. Johnson 1,034, Miedema 1,029, H. Reader 1,014, plus every player below them on the list from 2007 on.
  - Rebounds: every player whose whole career is from 2014-15 on, except Drew Johnson (see Error 6).
  - Assists: every player whose whole career is from 2014-15 on.
  - Luke Reader: 196 threes, 80.2% free throws, 104 games.
- **Team:**
  - 105 points vs. La Farge.
  - 46 field goals vs. Wonewoc-Center.
  - 50.9% field goal shooting in 2019-20.
  - 210 threes made and 661 attempted in 2025-26.
  - 491 assists in 2019-20.
  - 362 steals in 2017-18.
  - 30 games in 2021-22.
- **Win/loss:** every season from 2006-07 to 2025-26 matches except 2024-25. Jordan Laufenberg's 189-80 and Jacob Pederson's 93-12 coaching records are confirmed.

## 4. Can't check, or the sheets disagree with each other

| Entry | Why |
|---|---|
| **Canon O'Heron, 1,733 career points** | The sheets add up to only **1,547** (239 + 290 + 411 + 607). But 2012-13 and 2013-14 have games with missing or partial box scores, so 1,547 is a minimum, not the true total. Your number may come from a more complete source. What's the source for 1,733? |
| **Connor Kaiser, 1,284 career points in 86 games** | The sheets give **1,203 in 81 games**: 87 (2008-09), 252, 382, 482. The 2008-09 season is listed under "Konnor Kaiser" and the book says those stats were missing, so the sheets *add* that season. Even so, they come out 81 points lower. The duplicate 522 season (Error 2) may be part of the gap. |
| Connor Kaiser's 2011-12 rebounds (236) and assists (147), Adam Wuensch's rebounds, Canon O'Heron's 2012-13 rebounds, Connor Kaiser's 9-assist games, his 9 threes vs. Hillsboro, and his 16-16 free throws | The sheets only have points before 2014-15. |
| Win/loss 2003-04 (book 2-19), 2004-05 (6-16), 2005-06 (14-6) | Your schedule sheets show **2-18, 5-15 and 14-7**. Either the schedule sheets are missing games or the book is off. Those sheets have results only, so I can't tell which. |
| Everything before 2002-03 | Before the data. These will be kept on the site as historical records exactly as given. |

## 5. Small games-played differences (low priority)

The sheets and the book count games played slightly differently for a few players (for example, Zane Langrehr 95 vs. 96, Samuel Cropp 63 vs. 64, Kyle Wingert 52 vs. 53, Jaymeson Freit 47 vs. 48). The box scores sometimes list a player who sat the whole game with all zeros. The site could count only games where the player recorded a stat. Your call.
