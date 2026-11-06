"""Structured data (JSON-LD) for search engines."""
from sitegen.calendar_feed import *  # noqa: F401,F403  (everything defined before this part of the build)


# ---- structured data (JSON-LD) for search engines
SCHOOL = {"@type": "HighSchool", "name": "Bangor High School",
          "address": {"@type": "PostalAddress", "addressLocality": "Bangor", "addressRegion": "WI", "addressCountry": "US"}}


def ld_url(path):
    return SITE_URL + clean_path(path)


def ld_team():
    return {"@type": "SportsTeam", "@id": SITE_URL + "/#team", "name": "Bangor Cardinals boys basketball",
            "alternateName": "Bangor Cardinals", "sport": "Basketball", "url": SITE_URL + "/",
            "logo": SITE_URL + "/static/img/cardinal.png", "memberOf": SCHOOL,
            "location": {"@type": "Place", "name": "Bangor High School", "address": SCHOOL["address"]}}


def ld_team_ref():
    return {"@type": "SportsTeam", "@id": SITE_URL + "/#team", "name": "Bangor Cardinals boys basketball", "url": SITE_URL + "/"}


def ld_start(date, time=""):
    """An ISO start time in Wisconsin time, or just the date when the tipoff time isn't known."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP])M", time or "", re.I)
    if not m:
        return date
    from zoneinfo import ZoneInfo
    h = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "P" else 0)
    y, mo, d = map(int, date.split("-"))
    return dt.datetime(y, mo, d, h, int(m.group(2)), tzinfo=ZoneInfo("America/Chicago")).isoformat()


def ld_game(g):
    bangor = ld_team_ref()
    opp = {"@type": "SportsTeam", "name": g["opponent"]}
    if g["opp_slug"] in OPP_PAGES:
        opp["url"] = ld_url(f"opponents/{g['opp_slug']}.html")
    home, away = (opp, bangor) if g["site"] == "away" else (bangor, opp)
    name = f"Bangor {'at' if g['site'] == 'away' else 'vs'} {g['opponent']}"
    ev = {"@type": "SportsEvent", "name": f"{name} (boys basketball)", "sport": "Basketball",
          "url": ld_url(f"games/{g['game_id']}.html"), "startDate": ld_start(g["date"], g.get("time")),
          "competitor": [bangor, opp], "organizer": SCHOOL}
    if g["site"] != "neutral":
        ev["homeTeam"], ev["awayTeam"] = home, away
    if g.get("location"):
        ev["location"] = {"@type": "Place", "name": g["location"]}
        if g["site"] == "home":
            ev["location"]["address"] = SCHOOL["address"]
    if g["status"] in ("upcoming", "pending"):
        ev["eventStatus"] = "https://schema.org/EventScheduled"
        ev["eventAttendanceMode"] = "https://schema.org/OfflineEventAttendanceMode"
    elif g["result"] in ("W", "L"):
        ev["description"] = (f"Final: Bangor {g['bangor_score']}, {g['opponent']} {g['opp_score']}"
                             f" ({'win' if g['result'] == 'W' else 'loss'}).")
    return ev


def ld_person(name, path, role="Player", image=None, years=""):
    p = {"@type": "Person", "name": name, "url": ld_url(path),
         "memberOf": ld_team_ref() if role == "Player" else None,
         "worksFor": ld_team_ref() if role != "Player" else None,
         "jobTitle": role if role != "Player" else None,
         "description": f"Bangor Cardinals boys basketball {role.lower()}" + (f", {years}" if years else "") + "."}
    if image:
        p["image"] = image if re.match(r"https?://", image) else SITE_URL + "/" + image
    return {k: v for k, v in p.items() if v is not None}


def ld_crumbs(*crumbs):
    """Home > ... > this page. Each crumb is (name, path)."""
    items = [("Home", "index.html")] + list(crumbs)
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": ld_url(p)} for i, (n, p) in enumerate(items)]}


def ld_json(items):
    items = [i for i in items if i]
    if not items:
        return ""
    data = {"@context": "https://schema.org", "@graph": items} if len(items) > 1 else {"@context": "https://schema.org", **items[0]}
    # "</" can't appear inside a script tag
    return Markup(json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
