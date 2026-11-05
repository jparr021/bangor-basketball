"""A short written summary of a finished game, built only from what the data says.

Used on game pages that have no hand-written recap (the `recap` column of overrides/line_scores.csv).
Every sentence comes straight from the score, the quarter scores, the box scores, the season's results
and the record book, so it never says anything the numbers don't show.
"""
import re

from markupsafe import Markup, escape

WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
ORD_WORDS = {1: "", 2: "second-", 3: "third-", 4: "fourth-", 5: "fifth-"}
STAT_NOUN = {"pts": "points", "reb": "rebounds", "ast": "assists", "stl": "steals", "blk": "blocks",
             "tpm": "3-pointers", "fgm": "field goals"}


def _n(v):
    return int(v) if v is not None else None


def _count(n):
    return WORDS.get(n, str(n))


def _poss(name):
    return name + ("'" if name.endswith("s") else "'s")


def _player(r, link):
    name = escape(r["name"])
    return Markup(f'<a href="../players/{r["slug"]}.html">{name}</a>') if link and r.get("slug") else name


def _and(items):
    items = [Markup(i) if isinstance(i, Markup) else escape(i) for i in items]
    if len(items) <= 2:
        return Markup(" and ").join(items)
    return Markup(", ").join(items[:-1]) + Markup(", and ") + items[-1]


def _setting(g):
    """'in the WIAA regional final', 'at the Westby Tournament', 'at home', 'on the road' or ''."""
    ev = (g.get("event") or "").strip()
    low = ev.lower()
    if g.get("game_type") == "playoff":
        if "state" in low:
            return "in the state championship game" if "championship" in low or "final" in low else "at the WIAA state tournament"
        for rnd in ("sectional", "regional"):
            if rnd in low:
                if "semifinal" in low:
                    return f"in a WIAA {rnd} semifinal"
                if "final" in low:
                    return f"in the WIAA {rnd} final"
                return f"in a WIAA {rnd} game"
        return "in the WIAA playoffs"
    if g.get("game_type") == "tournament":
        m = re.search(r"\(([^)]*(?:tournament|classic)[^)]*)\)", ev, re.I)
        name = m.group(1) if m else (re.split(r"\s+at\s+", ev)[0] if re.search(r"tournament|classic", ev, re.I) else "")
        if name:
            return "at the " + name.strip()
    return {"home": "at home", "away": "on the road"}.get(g.get("site"), "")


def _periods(g):
    labels = (g.get("period_labels") or "").split("|")
    try:
        b = [int(x) for x in g["bangor_periods"].split("|")]
        o = [int(x) for x in g["opp_periods"].split("|")]
    except (KeyError, ValueError, AttributeError):
        return None
    if len(b) != len(o) or len(b) != len(labels) or sum(b) != g["bs"] or sum(o) != g["os"]:
        return None
    reg = sum(1 for l in labels if l.isdigit())
    if reg not in (2, 4):
        return None
    return labels, b, o, reg


def _flow(g, win):
    """One sentence on how the game went, from the quarter scores (or nothing notable)."""
    p = _periods(g)
    if not p:
        return ""
    labels, b, o, reg = p
    half = reg // 2
    hb, ho = sum(b[:half]), sum(o[:half])
    opp = escape(g["opponent"])
    if g.get("ot") and reg < len(b):
        rb, ro = sum(b[:reg]), sum(o[:reg])
        if rb == ro:
            return f"The game was tied {rb}–{ro} at the end of regulation."
    if reg == 4:
        tb, to = sum(b[:3]), sum(o[:3])
        fb, fo = b[3], o[3]
        if win and tb < to:
            return f"Bangor trailed {to}–{tb} after three quarters and outscored {opp} {fb}–{fo} in the fourth."
        if win and hb < ho:
            return f"Bangor trailed {ho}–{hb} at halftime and came back."
        if not win and tb > to:
            return f"Bangor led {tb}–{to} after three quarters, but {opp} won the fourth {fo}–{fb}."
        if not win and hb > ho:
            return f"Bangor led {hb}–{ho} at halftime, but {opp} outscored the Cardinals {sum(o[half:])}–{sum(b[half:])} after the break."
        if win and tb == to:
            return f"The game was tied {tb}–{to} after three quarters before Bangor won the fourth {fb}–{fo}."
        # a big quarter that decided it
        names = ["first", "second", "third", "fourth"]
        diffs = [(b[i] - o[i], i) for i in range(4)]
        d, i = max(diffs) if win else min(diffs)
        if abs(d) >= 12 and abs(g["bs"] - g["os"]) >= 10:
            if win:
                return f"A {b[i]}–{o[i]} {names[i]} quarter broke the game open."
            return f"{opp} outscored Bangor {o[i]}–{b[i]} in the {names[i]} quarter."
        if win and all(sum(b[:k + 1]) > sum(o[:k + 1]) for k in range(4)) and hb - ho >= 10:
            return f"Bangor led {hb}–{ho} at halftime and was ahead after every quarter."
    elif win and hb < ho:
        return f"Bangor trailed {ho}–{hb} at halftime and came back."
    elif not win and hb > ho:
        return f"Bangor led {hb}–{ho} at halftime, but {opp} won the second half {sum(o[half:])}–{sum(b[half:])}."
    return ""


def _line(r, full):
    """'15 points and 11 rebounds' — points plus any standout numbers."""
    bits = [f"{_n(r['pts'])} point{'s' if _n(r['pts']) != 1 else ''}"]
    if full:
        for k, noun, cut in (("reb", "rebounds", 10), ("ast", "assists", 7), ("blk", "blocks", 4), ("stl", "steals", 5)):
            if r.get(k) is not None and r[k] >= cut:
                bits.append(f"{_n(r[k])} {noun}")
    return " and ".join(bits) if len(bits) <= 2 else ", ".join(bits[:-1]) + " and " + bits[-1]


def _record_book(rows, badges, link):
    """'Canon O'Heron's 41 points are the second-most in a game in Bangor history.' for a top-3 mark."""
    best = None
    by_slug = {r["slug"]: r for r in rows}
    for b in badges:
        stat = (b.get("anchor") or "").rsplit("-", 1)[-1]
        if b.get("period") != "game" or stat not in STAT_NOUN or b["rank"] > 3 or b.get("slug") not in by_slug:
            continue
        r = by_slug[b["slug"]]
        if r.get(stat) is None:
            continue
        if best is None or (b["rank"], list(STAT_NOUN).index(stat)) < (best[0]["rank"], list(STAT_NOUN).index(best[1])):
            best = (b, stat, r)
    if not best:
        return "", None
    b, stat, r = best
    most = f"{'tied for ' if b['place'].startswith('T-') else ''}the {ORD_WORDS[b['rank']]}most"
    who = _player(r, link)
    return Markup(f"{who}{escape(_poss(r['name'])[len(r['name']):])} {_n(r[stat])} {STAT_NOUN[stat]} "
                  f"{'are' if _n(r[stat]) != 1 else 'is'} {most} in a game in Bangor history."), (r["slug"], stat)


def _context(g, season_games, final_season):
    """'The win moved Bangor to 12–4 and extended its winning streak to six.'"""
    done = [x for x in season_games if x.get("result") in ("W", "L")]
    if g not in done:
        return ""
    upto = done[:done.index(g) + 1]
    w = sum(x["result"] == "W" for x in upto)
    l = len(upto) - w
    rec = f"{w}–{l}"
    res = g["result"]
    streak = 0
    for x in reversed(upto):
        if x["result"] != res:
            break
        streak += 1
    before = 0
    for x in reversed(upto[:-1]):
        if x["result"] == res:
            break
        before += 1
    noun = "win" if res == "W" else "loss"
    if len(upto) == 1:
        return f"Bangor opened the season with a {noun}."
    if final_season and g is done[-1]:
        if res == "L" and g.get("game_type") == "playoff":
            return f"The loss ended Bangor's season at {rec}."
        if res == "W" and g.get("game_type") == "playoff" and "state" in (g.get("event") or "").lower():
            return f"The win gave Bangor the state championship and a {rec} record."
        return f"Bangor finished the season {rec}."
    tail = ""
    if streak >= 3:
        tail = f" and extended its {'winning' if res == 'W' else 'losing'} streak to {_count(streak)}"
    elif before >= 3:
        tail = f" and ended a {_count(before)}-game {'losing' if res == 'W' else 'winning'} streak"
    return f"The {noun} {'moved Bangor to' if res == 'W' else 'dropped Bangor to'} {rec}{tail}."


def write(g, bangor, opp, season_games, badges, final_season, link=True, short=False):
    """The summary as safe HTML (player names link to their pages), or '' for a game without a final score.
    short=True gives just the result, the leading scorer and any record-book mark (for "On this day")."""
    if g.get("result") not in ("W", "L") or g.get("bs") is None or g.get("os") is None:
        return ""
    win = g["result"] == "W"
    bs, os_ = _n(g["bs"]), _n(g["os"])
    margin = abs(bs - os_)
    opp_name = escape(g["opponent"])
    where = _setting(g)
    ot = {1: " in overtime", 2: " in double overtime"}.get(_n(float(g["ot"])) if g.get("ot") else 0, "")
    if g.get("ot") and not ot:
        ot = f" in {int(float(g['ot']))} overtimes"

    scored = [r for r in bangor if r.get("pts") is not None]
    top, tops = None, []
    if scored and g.get("box_score") != "none":
        hi = max(r["pts"] for r in scored)
        tops = [r for r in scored if r["pts"] == hi]
        top = tops[0] if len(tops) == 1 else None
    full = g.get("box_score") == "full" and g.get("box_source") != "newspaper"

    out = []  # (priority, sentence): the lower the priority, the sooner it's dropped to keep the paragraph short
    flow = _flow(g, win)
    if win:
        verb = "rolled past" if margin >= 20 and "trailed" not in flow else ("edged" if margin <= 3 else "beat")
        lede = Markup(f"Bangor {verb} {opp_name} {bs}–{os_}{ot}{' ' + where if where else ''}")
        if top and top["pts"] >= 10:
            lede += Markup(f" behind {_line(top, full)} from ") + _player(top, link)
        elif len(tops) in (2, 3) and tops[0]["pts"] >= 10:
            lede += Markup(f" behind {_n(tops[0]['pts'])} points each from ") + _and([_player(r, link) for r in tops])
        out.append((9, lede + "."))
    else:
        verb = "fell to" if margin <= 3 else "lost to"
        out.append((9, Markup(f"Bangor {verb} {opp_name} {os_}–{bs}{ot}{' ' + where if where else ''}.")))
        if top and top["pts"] >= 8:
            out.append((8, _player(top, link) + Markup(f" led the Cardinals with {_line(top, full)}.")))
        elif len(tops) in (2, 3) and tops[0]["pts"] >= 8:
            out.append((8, _and([_player(r, link) for r in tops]) + Markup(f" each scored {_n(tops[0]['pts'])} to lead the Cardinals.")))

    if flow:
        out.append((6, Markup(flow)))

    book, book_key = _record_book(bangor, badges, link)

    # the next scorers in double figures, and anyone with a big game elsewhere on the stat sheet
    if scored and g.get("box_score") != "none":
        named = {r["slug"] for r in tops}
        rest = sorted([r for r in scored if r["slug"] not in named and r["pts"] >= 10], key=lambda r: -r["pts"])[:2]
        if rest:
            parts = [_player(r, link) + Markup(" " + ("added " if i == 0 else "had ") + _line(r, full)) for i, r in enumerate(rest)]
            out.append((5, Markup(", and ").join(parts) + "."))
            named |= {r["slug"] for r in rest}
        if full:
            for k, noun, cut in (("ast", "assists", 8), ("reb", "rebounds", 12), ("blk", "blocks", 5), ("stl", "steals", 6)):
                cand = [r for r in bangor if r["slug"] not in named and r.get(k) is not None and r[k] >= cut]
                if cand:
                    r = max(cand, key=lambda r: r[k])
                    if (r["slug"], k) != book_key:  # the record-book line says it already
                        out.append((3, _player(r, link) + Markup(f" had {_n(r[k])} {noun}.")))
                    break
            tpm = [r["tpm"] for r in bangor if r.get("tpm") is not None]
            if tpm and sum(tpm) >= 10:
                out.append((2, Markup(f"Bangor made {int(sum(tpm))} 3-pointers.")))

    if book:
        out.append((7, book))

    o_scored = [r for r in opp if r.get("pts") is not None]
    if o_scored:
        ot_ = max(o_scored, key=lambda r: r["pts"])
        if ot_["pts"] >= 15 and sum(1 for r in o_scored if r["pts"] == ot_["pts"]) == 1:
            out.append((1, Markup(f"{escape(ot_['name'])} led {opp_name} with {_n(ot_['pts'])}.")))

    if short:
        return Markup(" ").join(x[1] for x in out if x[0] in (9, 8, 7))

    ctx = _context(g, season_games, final_season)
    if ctx:
        out.append((10, Markup(ctx)))

    # keep it to a short paragraph: at most five sentences, dropping the least telling first
    while len(out) > 5:
        out.remove(min(out, key=lambda x: x[0]))
    out = [x[1] for x in out]
    return Markup(" ").join(out)
