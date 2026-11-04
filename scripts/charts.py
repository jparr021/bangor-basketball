"""Small inline SVG charts for the site, drawn at build time (no JavaScript libraries).

Every chart mark that has a value carries a data-tip (shown by site.js on hover and keyboard focus)
and sits inside a link or focusable target. The same values are always in a table on the page too.

Colors: wins #157a3b and losses #e07a3f pass the colorblind checks as a pair (deutan/protan safe);
the usual green/red pair does not. Polarity is also carried by position (above or below the zero line).
"""
import math
from html import escape

from markupsafe import Markup

WIN, LOSS, ACCENT = "#157a3b", "#e07a3f", "#c8102e"
GRID, AXIS, INK, MUTED = "#e4e6ea", "#b9bdc4", "#1d1f23", "#6b7078"
FONT = 'font-family="Inter, -apple-system, Segoe UI, Roboto, sans-serif"'


def _a(s):
    """Escape for an attribute; newlines become line breaks in the tooltip."""
    return escape(str(s), quote=True).replace("\n", "&#10;")


def _nice_step(span, max_ticks=4):
    for step in (1, 2, 5, 10, 20, 25, 50, 100):
        if span / step <= max_ticks:
            return step
    return 100


def _bar_path(x, w, y0, y1, r=4):
    """A bar from baseline y0 to tip y1, rounded only at the tip (y1 above or below y0)."""
    h = abs(y1 - y0)
    r = min(r, h, w / 2)
    if y1 < y0:  # grows up
        return (f"M{x:.1f},{y0:.1f}V{y1 + r:.1f}Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f}"
                f"H{x + w - r:.1f}Q{x + w:.1f},{y1:.1f} {x + w:.1f},{y1 + r:.1f}V{y0:.1f}Z")
    return (f"M{x:.1f},{y0:.1f}V{y1 - r:.1f}Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f}"
            f"H{x + w - r:.1f}Q{x + w:.1f},{y1:.1f} {x + w:.1f},{y1 - r:.1f}V{y0:.1f}Z")


def margin_chart(items, title):
    """Scoring margin for each game, as columns above (wins) and below (losses) a zero line.

    items: [{"margin": int, "tip": str, "href": str, "xlabel": str or "", "label": bool}]
    """
    if not items:
        return ""
    n = len(items)
    slot = 26 if n > 12 else 34
    bar = min(18, slot - 6)
    left, right, top, bottom, plot_h = 34, 10, 16, 26, 170
    width = left + n * slot + right
    hi = max([i["margin"] for i in items] + [0])
    lo = min([i["margin"] for i in items] + [0])
    step = _nice_step(max(hi - lo, 10), 5)
    ymax = max(step, math.ceil(hi / step) * step) if hi > 0 else 0
    ymin = min(-step, math.floor(lo / step) * step) if lo < 0 else 0
    if ymax == ymin:
        ymax = step
    # leave room under the deepest loss for its label, clear of the month labels
    if lo < 0 and (lo - ymin) < 0.1 * (ymax - ymin):
        ymin -= step

    def y(v):
        return top + (ymax - v) / (ymax - ymin) * plot_h

    height = top + plot_h + bottom
    out = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
           f'aria-label="{_a(title)}" style="min-width:{min(width, 560)}px;max-width:{width}px" {FONT}>']
    for v in range(ymin, ymax + 1, step):
        yy = y(v)
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{AXIS if v == 0 else GRID}" '
                   f'stroke-width="1"/>')
        out.append(f'<text x="{left - 6}" y="{yy + 4:.1f}" text-anchor="end" font-size="11" fill="{MUTED}">'
                   f'{"+" if v > 0 else ("−" if v < 0 else "")}{abs(v)}</text>')
    y0 = y(0)
    for i, it in enumerate(items):
        x = left + i * slot + (slot - bar) / 2
        m = it["margin"]
        color = WIN if m > 0 else LOSS
        out.append(f'<a class="chart-hit" href="{_a(it["href"])}" data-tip="{_a(it["tip"])}" aria-label="{_a(it["tip"])}">'
                   f'<rect x="{left + i * slot}" y="{top}" width="{slot}" height="{plot_h}" fill="transparent"/>')
        if m:
            out.append(f'<path class="chart-mark" d="{_bar_path(x, bar, y0, y(m))}" fill="{color}"/>')
        else:
            out.append(f'<rect class="chart-mark" x="{x}" y="{y0 - 1.5:.1f}" width="{bar}" height="3" rx="1.5" fill="{MUTED}"/>')
        out.append("</a>")
        if it.get("label") and m:
            ty = y(m) - 5 if m > 0 else y(m) + 14
            out.append(f'<text x="{x + bar / 2:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="11" font-weight="600" '
                       f'fill="{INK}">{"+" if m > 0 else "−"}{abs(m)}</text>')
        if it.get("xlabel"):
            out.append(f'<text x="{left + i * slot + 2}" y="{top + plot_h + 18}" font-size="11" fill="{MUTED}">'
                       f'{escape(it["xlabel"])}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def game_line(points, avg, title, ymax=None):
    """One player's points in each of the team's games: a 2px line with a gap where he didn't play.

    points: [{"v": number or None, "tip": str, "href": str}], in game order.
    ymax: share one scale across a set of these so the players compare fairly.
    """
    n = len(points)
    vals = [p["v"] for p in points if p["v"] is not None]
    if n < 2 or not vals:
        return ""
    width, height, left, right, top, bottom = 320, 92, 6, 26, 14, 8
    ymax = ymax or max(10, math.ceil(max(vals) / 10) * 10)
    plot_w, plot_h = width - left - right, height - top - bottom

    def x(i):
        return left + i * plot_w / (n - 1)

    def y(v):
        return top + (1 - v / ymax) * plot_h

    out = [f'<svg class="chart-svg spark" viewBox="0 0 {width} {height}" role="img" aria-label="{_a(title)}" {FONT}>',
           f'<line x1="{left}" x2="{width - right}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="{AXIS}" stroke-width="1"/>']
    if avg:
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{y(avg):.1f}" y2="{y(avg):.1f}" stroke="{GRID}" stroke-width="1"/>'
                   f'<text x="{width - right + 4}" y="{y(avg) + 4:.1f}" font-size="10" fill="{MUTED}">avg</text>')
    # the line, broken into runs of games he played
    runs, cur = [], []
    for i, p in enumerate(points):
        if p["v"] is None:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append((x(i), y(p["v"])))
    if cur:
        runs.append(cur)
    for r in runs:
        if len(r) == 1:
            out.append(f'<circle cx="{r[0][0]:.1f}" cy="{r[0][1]:.1f}" r="2.5" fill="{ACCENT}"/>')
        else:
            d = "M" + "L".join(f"{a:.1f},{b:.1f}" for a, b in r)
            out.append(f'<path d="{d}" fill="none" stroke="{ACCENT}" stroke-width="2" stroke-linejoin="round" '
                       f'stroke-linecap="round"/>')
    # the season high gets a dot and its value
    hi_i = max((i for i, p in enumerate(points) if p["v"] is not None), key=lambda i: (points[i]["v"], -i))
    hx, hy = x(hi_i), y(points[hi_i]["v"])
    out.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="4" fill="{ACCENT}" stroke="#fff" stroke-width="2"/>'
               f'<text x="{min(max(hx, 10), width - right - 6):.1f}" y="{hy - 7:.1f}" text-anchor="middle" font-size="11" '
               f'font-weight="600" fill="{INK}">{int(points[hi_i]["v"])}</text>')
    # hover / focus targets, one per game
    colw = plot_w / (n - 1)
    for i, p in enumerate(points):
        out.append(f'<a class="chart-hit" href="{_a(p["href"])}" data-tip="{_a(p["tip"])}" aria-label="{_a(p["tip"])}">'
                   f'<rect x="{x(i) - colw / 2:.1f}" y="0" width="{colw:.1f}" height="{height}" fill="transparent"/>')
        if p["v"] is not None:
            out.append(f'<circle class="chart-dot" cx="{x(i):.1f}" cy="{y(p["v"]):.1f}" r="4" fill="{ACCENT}" '
                       f'stroke="#fff" stroke-width="2"/>')
        out.append("</a>")
    out.append("</svg>")
    return Markup("".join(out))


def pct_columns(items, title):
    """Winning percentage for each season, as columns, with a hairline at .500.

    items: [{"pct": 0..1 or None, "tip": str, "href": str or "", "xlabel": str}]
    """
    items = [i for i in items if i["pct"] is not None]
    if not items:
        return ""
    n = len(items)
    slot = 30 if n > 10 else 40
    bar = min(20, slot - 8)
    left, right, top, bottom, plot_h = 38, 10, 18, 26, 140
    width = max(left + n * slot + right, 220)
    height = top + plot_h + bottom

    def y(v):
        return top + (1 - v) * plot_h

    out = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
           f'aria-label="{_a(title)}" style="min-width:{min(width, 480)}px;max-width:{width}px" {FONT}>']
    for v in (0, .5, 1):
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
                   f'stroke="{AXIS if v in (0, .5) else GRID}" stroke-width="1"/>'
                   f'<text x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end" font-size="11" fill="{MUTED}">'
                   f'{"1.000" if v == 1 else ("0" if v == 0 else ".500")}</text>')
    for i, it in enumerate(items):
        x = left + i * slot + (slot - bar) / 2
        tag_open = f'<a class="chart-hit" href="{_a(it["href"])}"' if it.get("href") else '<g class="chart-hit" tabindex="0"'
        out.append(f'{tag_open} data-tip="{_a(it["tip"])}" aria-label="{_a(it["tip"])}">'
                   f'<rect x="{left + i * slot}" y="{top}" width="{slot}" height="{plot_h}" fill="transparent"/>')
        if it["pct"] > 0:
            out.append(f'<path class="chart-mark" d="{_bar_path(x, bar, y(0), y(it["pct"]))}" fill="{ACCENT}"/>')
        out.append("</a>" if it.get("href") else "</g>")
        if it.get("xlabel"):
            out.append(f'<text x="{x + bar / 2:.1f}" y="{top + plot_h + 18}" text-anchor="middle" font-size="11" '
                       f'fill="{MUTED}">{escape(it["xlabel"])}</text>')
    out.append("</svg>")
    return Markup("".join(out))
