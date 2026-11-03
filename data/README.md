# Bangor Boys Basketball — standard dataset

Generated from `source-sheets/*.xlsx` by `scripts/convert.py`. Don't hand-edit these files:
fix the source sheet (or the alias and override tables in `convert.py`), then re-run:

```
.venv/bin/python scripts/convert.py && .venv/bin/python scripts/validate.py
```

**Blank = not tracked. 0 = tracked, and it was zero.** Averages and records only count games where a stat was tracked.

| File | One row per | Key columns |
|---|---|---|
| `games.csv` | Bangor game (2002-03 →) | game_id, season, date, opponent, site (home/away/neutral), game_type (regular/tournament/playoff), conference, bangor_score, opp_score, result, ot, period scores, box_score (full / points / none), box_complete |
| `player_games.csv` | Bangor player per game | game_id, player_id, name, number, class, min, fgm, fga, tpm, tpa, ftm, fta, oreb, dreb, reb, ast, stl, blk, to, pf, pts, chg |
| `opponent_player_games.csv` | opponent player per game | same stats, plus team |
| `source_season_totals.csv` | player per season, as recorded on the sheet's Player Stats tab | used for checking, and for season totals in seasons where some games have no box score |
| `players.csv` | Bangor player | player_id, name, seasons, grad_year (to fill in) |
| `validation_report.md` | — | converted data checked against the sheets' own season totals |
| `conversion_warnings.txt` | — | anything odd the converter noticed in the source |

## What each era has
- **2002-03 → 2006-07**: results only.
- **2007-08 → 2013-14**: points per player (a few games have no box score).
- **2014-15 → 2025-26**: full box scores. Minutes appear in some seasons. Offensive and defensive rebounds appear per game only in 2025-26; in earlier seasons the split is only in the season totals.
