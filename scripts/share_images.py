"""Link-preview images (1200x630) for games, players, seasons, coaches and opponents.

Drawn at build time with Pillow, in the site's fonts (site-src/fonts, SIL Open Font License) and colors.
Each card: logo and site name at the top, the page's headline in the middle, the site address in a
black footer bar with a red rule. Written as small palette PNGs.
"""
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
RED, BLACK, INK, MUTED, LINE, WHITE = "#c8102e", "#111214", "#1d1f23", "#6b7078", "#e4e6ea", "#ffffff"
WIN, LOSS = "#157a3b", "#b3261e"
PAD = 64
FOOT = 72  # height of the black footer bar

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONTS = os.path.join(os.path.dirname(_HERE), "site-src", "fonts")
_LOGO_PATH = os.path.join(os.path.dirname(_HERE), "site-src", "static", "img", "cardinal.png")
_cache = {}


def font(kind, size, weight):
    key = (kind, size, weight)
    if key not in _cache:
        f = ImageFont.truetype(os.path.join(_FONTS, "Oswald.ttf" if kind == "head" else "Inter.ttf"), size)
        axes = f.get_variation_axes()
        f.set_variation_by_axes([min(max(size, 14), 32) if a["name"] == b"Optical size" else weight for a in axes])
        _cache[key] = f
    return _cache[key]


def _logo(height):
    key = ("logo", height)
    if key not in _cache:
        im = Image.open(_LOGO_PATH).convert("RGBA")
        _cache[key] = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
    return _cache[key]


def fit(draw, text, kind, size, weight, max_w, min_size=28):
    """The largest font size (down to min_size) at which text fits max_w."""
    while size > min_size and draw.textlength(text, font=font(kind, size, weight)) > max_w:
        size -= 2
    return font(kind, size, weight)


class Card:
    def __init__(self, site_host, eyebrow=""):
        self.im = Image.new("RGB", (W, H), WHITE)
        self.d = ImageDraw.Draw(self.im)
        logo = _logo(70)
        self.im.paste(logo, (PAD - 6, 44), logo)
        x = PAD - 6 + logo.width + 18
        self.d.text((x, 50), "BANGOR CARDINALS", font=font("head", 34, 600), fill=INK)
        self.d.text((x, 92), "BOYS BASKETBALL", font=font("body", 17, 600), fill=MUTED)
        self.d.rectangle([0, H - FOOT, W, H], fill=BLACK)
        self.d.rectangle([0, H - FOOT, W, H - FOOT + 6], fill=RED)
        self.d.text((PAD, H - FOOT / 2 + 3), site_host, font=font("body", 22, 500), fill="#c9cbd0", anchor="lm")
        if eyebrow:
            self.d.text((W - PAD, H - FOOT / 2 + 3), eyebrow.upper(), font=font("body", 20, 700), fill="#ff8a9a", anchor="rm")
        self.y = 170

    def eyebrow(self, text, color=RED):
        self.d.text((PAD, self.y), text.upper(), font=font("body", 26, 700), fill=color)
        self.y += 46

    def headline(self, text, size=96, color=INK, max_w=W - 2 * PAD):
        f = fit(self.d, text.upper(), "head", size, 600, max_w)
        self.d.text((PAD, self.y), text.upper(), font=f, fill=color)
        self.y += int(f.size * 1.32) + 6

    def line(self, text, size=30, color=MUTED, weight=500):
        f = fit(self.d, text, "body", size, weight, W - 2 * PAD, 22)
        while self.d.textlength(text, font=f) > W - 2 * PAD and len(text) > 4:
            text = text[:-2].rstrip(" ,·") + "…"
        self.d.text((PAD, self.y), text, font=f, fill=color)
        self.y += int(f.size * 1.5)

    def tiles(self, items, top=None):
        """Stat tiles: [(value, label), ...] in one row."""
        if not items:
            return
        top = top or self.y + 6
        gap = 20
        n = len(items)
        tw = (W - 2 * PAD - gap * (n - 1)) / n
        for i, (val, lbl) in enumerate(items):
            x0 = PAD + i * (tw + gap)
            self.d.rounded_rectangle([x0, top, x0 + tw, top + 150], radius=12, fill="#f6f6f7", outline=LINE, width=2)
            self.d.rectangle([x0 + 2, top, x0 + tw - 2, top + 6], fill=RED)
            fv = fit(self.d, str(val), "head", 64, 600, tw - 40, 30)
            self.d.text((x0 + 22, top + 26), str(val), font=fv, fill=INK)
            self.d.text((x0 + 22, top + 112), lbl.upper(), font=fit(self.d, lbl.upper(), "body", 20, 700, tw - 40, 14),
                        fill=MUTED)
        self.y = top + 170

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.im.quantize(colors=96, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)


def game_card(path, host, g, date_text, kind_text):
    c = Card(host, kind_text)
    final = g["result"] in ("W", "L")
    if final:
        c.eyebrow(f"Final{' · OT' if g.get('ot') else ''} · {date_text}")
    else:
        c.eyebrow(f"{'Today' if g.get('is_today') else 'Upcoming'} · {date_text}{' · ' + g['time'] if g.get('time') else ''}")
    opp = g["opponent"] if final else f"{'at' if g['site'] == 'away' else 'vs'} {g['opponent']}"
    rows = [("Bangor", g["bangor_score"], g["result"] == "W"), (opp, g["opp_score"], g["result"] == "L")]
    top = c.y + 4
    score_x = W - PAD
    for i, (name, score, won) in enumerate(rows):
        y = top + i * 132
        color = INK if (won or not final) else "#9aa0a8"
        name_w = W - 2 * PAD - (230 if final else 0)
        f = fit(c.d, name.upper(), "head", 104, 600, name_w, 44)
        c.d.text((PAD, y + 62), name.upper(), font=f, fill=color, anchor="lm")
        if final:
            c.d.text((score_x, y + 62), str(score), font=font("head", 116, 700), fill=color, anchor="rm")
            if won:
                c.d.rectangle([PAD - 30, y + 18, PAD - 18, y + 106], fill=RED)
    c.save(path)


def player_card(path, host, name, sub, tiles):
    c = Card(host, "Player")
    c.y = 176
    c.headline(name, 104)
    c.line(sub, 30)
    c.tiles(tiles, top=min(c.y + 6, 386))
    c.save(path)


def simple_card(path, host, eyebrow, title, sub, tiles, foot_label):
    c = Card(host, foot_label)
    c.eyebrow(eyebrow)
    c.headline(title, 84 if sub and tiles else 100)
    if sub:
        c.line(sub, 26)
    c.tiles(tiles, top=min(max(c.y + 4, 372), 386) if tiles else None)
    c.save(path)
