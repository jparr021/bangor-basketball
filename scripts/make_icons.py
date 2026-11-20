"""Make the site icons and the small logo from the full logo (site-src/static/img/cardinal.png).

Run it again only if the logo changes; the files it writes are committed:
  .venv/bin/python scripts/make_icons.py

Writes to site-src/static/img/:
  favicon.ico           browser tab icon (16, 32 and 48 px): the cardinal's head on a white rounded square
  icon-192.png, icon-512.png   home-screen icons for Android (listed in site.webmanifest)
  apple-touch-icon.png  home-screen icon for iPhone and iPad (180 px, square; iOS rounds the corners)
  cardinal-web.png      the full logo at 640 px wide, for the masthead and home page (the original is
                        1670 px and about 270 KB, more than every page needs; it's still used for
                        share images and search engines)
The build copies favicon.ico and apple-touch-icon.png to the site root too, where browsers look for
them, and writes site.webmanifest there.
"""
import os

from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(os.path.dirname(HERE), "site-src", "static", "img")

# The head sits in this box of the full logo; the outline below keeps the head and trims the wing
# strokes that cross the box. Points are relative to the box's top-left corner.
HEAD_BOX = (660, 85, 1040, 570)
HEAD_OUTLINE = [(352, 0), (380, 0), (380, 20), (308, 262), (302, 290), (165, 425), (95, 485), (62, 485),
                (62, 330), (30, 300), (25, 250), (30, 170), (110, 85), (200, 62), (300, 30)]


def cardinal_head(logo):
    head = logo.crop(HEAD_BOX)
    mask = Image.new("L", head.size, 0)
    ImageDraw.Draw(mask).polygon(HEAD_OUTLINE, fill=255)
    head.putalpha(ImageChops.multiply(head.getchannel("A"), mask))
    return head.crop(head.getbbox())


def icon(head, size, rounded=True, fill=0.86):
    """The head centred on white, drawn at 4x and scaled down for smooth edges."""
    big = size * 4
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(out)
    if rounded:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill="white")
    else:
        draw.rectangle((0, 0, big, big), fill="white")
    h = int(big * fill)
    w = round(head.width * h / head.height)
    out.alpha_composite(head.resize((w, h), Image.LANCZOS), ((big - w) // 2 + int(big * 0.02), (big - h) // 2))
    return out.resize((size, size), Image.LANCZOS)


def main():
    logo = Image.open(os.path.join(IMG, "cardinal.png")).convert("RGBA")
    head = cardinal_head(logo)

    # each size drawn on its own, so the 16 px one is as sharp as it can be
    icon(head, 48).save(os.path.join(IMG, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)],
                        append_images=[icon(head, 16), icon(head, 32)])
    for size in (192, 512):
        icon(head, size).save(os.path.join(IMG, f"icon-{size}.png"), optimize=True)
    icon(head, 180, rounded=False, fill=0.78).convert("RGB").save(os.path.join(IMG, "apple-touch-icon.png"), optimize=True)

    # 64 colours is plenty for a red, black and white logo and makes the file about 9 KB
    w = 640
    small = logo.resize((w, round(logo.height * w / logo.width)), Image.LANCZOS)
    small.quantize(64, method=Image.Quantize.FASTOCTREE).save(os.path.join(IMG, "cardinal-web.png"), optimize=True)
    print("Wrote favicon.ico, icon-192.png, icon-512.png, apple-touch-icon.png and cardinal-web.png to", IMG)


if __name__ == "__main__":
    main()
