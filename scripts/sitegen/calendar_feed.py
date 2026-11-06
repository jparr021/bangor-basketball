"""The current season's schedule as a calendar feed (schedule.ics) and its subscribe links."""
from sitegen.stats import *  # noqa: F401,F403  (everything defined before this part of the build)


CAL_FILE = "schedule.ics"
CAL_HOST = re.sub(r"^https?://", "", SITE_URL)
_VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Chicago
BEGIN:DAYLIGHT
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
TZNAME:CDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
TZNAME:CST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""


def _ics_text(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line):
    """Lines longer than 75 bytes continue on the next line after a space (RFC 5545)."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode()); cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def calendar_feed(season):
    """The season's schedule as an iCalendar feed people can subscribe to. Each game keeps the same UID,
    so a changed time or a final score updates the event already on their calendar."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Bangor Cardinals Boys Basketball//Schedule//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:Bangor Boys Basketball {season.replace('-', '–')}",
             "X-WR-CALDESC:Bangor Cardinals varsity boys basketball schedule and results",
             "X-WR-TIMEZONE:America/Chicago", "REFRESH-INTERVAL;VALUE=DURATION:PT3H", "X-PUBLISHED-TTL:PT3H"]
    lines += _VTIMEZONE.split("\n")
    for g in games_by_season.get(season, []):
        d = dt.date.fromisoformat(g["date"])
        where = "at" if g["site"] == "away" else "vs"
        title = f"Bangor {where} {g['opponent']}"
        if g["result"] in ("W", "L"):
            title = f"{g['result']} {g['bangor_score']}–{g['opp_score']} · {title}"
        off = re.search(r"postpon|cancel", g["event"], re.I)
        if off:
            title += f" ({'Postponed' if 'postpon' in off.group(0).lower() else 'Canceled'})"
        url = SITE_URL + clean_path(f"games/{g['game_id']}.html")  # the live site always has clean URLs
        kind = {"playoff": "Playoff", "tournament": "Tournament"}.get(g["game_type"], "")
        tags = " · ".join(x for x in (kind, "Conference" if g["conference"] == "Y" else "",
                                      "" if off else g["event"]) if x)
        desc = [tags] if tags else []
        if g["stream_url"] and g["status"] != "final":
            desc.append(f"Watch live: {g['stream_url']}")
        desc.append(f"Game page: {url}")
        tm = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", g["time"] or "", re.I)
        ev = ["BEGIN:VEVENT", f"UID:{g['game_id']}@{CAL_HOST}", f"DTSTAMP:{stamp}"]
        if tm:
            h = int(tm.group(1)) % 12 + (12 if (tm.group(3) or "PM").upper() == "PM" else 0)
            start = dt.datetime.combine(d, dt.time(h, int(tm.group(2))))
            ev += [f"DTSTART;TZID=America/Chicago:{start:%Y%m%dT%H%M%S}",
                   f"DTEND;TZID=America/Chicago:{start + dt.timedelta(hours=2):%Y%m%dT%H%M%S}"]
        else:
            ev += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}"]
        ev += [f"SUMMARY:{_ics_text(title)}", f"DESCRIPTION:{_ics_text(chr(10).join(desc))}", f"URL:{url}"]
        if g["location"]:
            ev.append(f"LOCATION:{_ics_text(g['location'])}")
        if off and "cancel" in off.group(0).lower():
            ev.append("STATUS:CANCELLED")
        ev += ["TRANSP:TRANSPARENT", "END:VEVENT"]
        lines += ev
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(l) for l in lines) + "\r\n"


def calendar_links():
    """Subscribe links for the season calendar: Google, Apple (webcal) and Outlook, plus the plain feed URL."""
    from urllib.parse import quote
    feed = f"{SITE_URL}/{CAL_FILE}"
    webcal = f"webcal://{CAL_HOST}/{CAL_FILE}"
    return {"feed": feed, "webcal": webcal,
            "google": f"https://calendar.google.com/calendar/r?cid={quote(webcal, safe='')}",
            "outlook": f"https://outlook.live.com/calendar/0/addfromweb?url={quote(feed, safe='')}"
                       f"&name={quote('Bangor Boys Basketball')}"}


CAL_LINKS = calendar_links()
