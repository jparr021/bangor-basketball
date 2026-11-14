"""Build the static website into site/ from data/ and overrides/.

Run the whole pipeline:
  .venv/bin/python scripts/convert.py && .venv/bin/python scripts/records.py && .venv/bin/python scripts/build_site.py

The build lives in scripts/sitegen/, one module per part, each building on the one before:
  common         paths, settings, small helpers
  data           loading data/*.csv and overrides/
  players_index  which players get a page
  record_book    site facts, records, badges, gaps
  downloads      CSV downloads
  on_this_day    the home page's "On this day"
  stats          stat rows, box scores, career leaderboards
  calendar_feed  schedule.ics
  jsonld         structured data for search engines
  render         templates, page writing, share images
  views          season summaries, head-to-head, previews, charts, coaches, classes
and the pages themselves in pages_seasons, pages_players and pages_other.
"""
from sitegen.views import *  # noqa: F401,F403
from sitegen.pages_seasons import home, seasons_index, season_pages, game_pages
from sitegen.pages_players import player_pages
from sitegen.pages_other import (history_pages, opponent_pages, film_index, search_index, sheet_check_page,
                                 admin_page, not_found_page, feeds_and_sitemap)


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(SRC, "static"), os.path.join(OUT, "static"))
    publish_photos()

    # ---- records first: game, season and player pages show their record-book entries
    sections = record_sections()
    B = collect_badges(sections)
    career, game = merged("individual", "career", "pts", "int")[:1], merged("individual", "game", "pts", "int")[:1]
    sh = page_share("records", "The Bangor Cardinals boys basketball record book", "Record book", "Top 10 in every category",
                    f"Career scoring record: {career[0]['name']}, {career[0]['display']} points" if career else "",
                    [(career[0]["display"] if career else None, f"Career points · {last_name(career[0]['name'] if career else '')}"),
                     (game[0]["display"] if game else None, f"Points in a game · {last_name(game[0]['name'] if game else '')}"),
                     (FACTS["streak"]["wins"], "Straight wins")])
    render("records.html", "records/index.html", sections=list(sections.values()), mins=MINS, **sh)
    write_downloads(sections)

    # ---- head-to-head previews for games not yet played (game pages and the home page's upcoming list)
    opps = opponent_index()
    PREVIEWS = {g["game_id"]: game_preview(g, opps.get(g["opp_slug"]))
                for g in games_by_id.values() if g["status"] in ("upcoming", "pending")}

    home(PREVIEWS)
    seasons_index()
    PAGE_SEASONS = season_pages(B)
    game_pages(B, PREVIEWS)
    write_otd(sections)
    plist, classes = player_pages(B)
    history_pages()
    olist = opponent_pages(opps)
    film_index()
    search_index(plist, olist, classes)
    sheet_check_page()
    admin_page(plist, PAGE_SEASONS)
    not_found_page()
    feeds_and_sitemap()
    finish_share_cache()

    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"site built: {n} files in {OUT}")


if __name__ == "__main__":
    build()
