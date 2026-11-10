"""Templates and page writing: render(), link rewriting for clean URLs, and share images."""
from sitegen.jsonld import *  # noqa: F401,F403  (everything defined before this part of the build)


# ---------------------------------------------------------------- render
env = Environment(loader=FileSystemLoader(os.path.join(SRC, "templates")), autoescape=select_autoescape(["html"]))
env.filters["d"] = fmt_date
env.filters["n"] = fmt_int
BUILT = TODAY.strftime("%B %-d, %Y")
BUILD_ID = dt.datetime.now().strftime("%Y%m%d%H%M")  # cache-buster for the search index


PAGES = []  # every page written, for the sitemap


LOCAL_LINK_RE = re.compile(r'\b(href|src)="([^"#?:]+)([?#][^"]*)?"')


def absolute_links(html, page):
    """Rewrite relative links into root-relative clean URLs, resolved from the page's own path."""
    def fix(m):
        attr, target, tail = m.group(1), m.group(2), m.group(3) or ""
        if target.startswith("/"):
            return m.group(0)
        full = posixpath.normpath(posixpath.join(posixpath.dirname(page), target))
        url = clean_path(full) if attr == "href" and full.endswith(".html") else "/" + full
        return f'{attr}="{url}{tail}"'
    return LOCAL_LINK_RE.sub(fix, html)


SHARE_HOST = re.sub(r"^https?://", "", SITE_URL)


def share(kind, key, draw, alt, *args):
    """Draw one link-preview image into site/static/share/ and return (absolute URL, alt text) for render().
    The URL carries a short hash of the image, so a preview that changed (a new score) is fetched fresh."""
    import hashlib
    rel = f"static/share/{kind}/{key}.png"
    full = os.path.join(OUT, rel)
    draw(full, SHARE_HOST, *args)
    with open(full, "rb") as f:
        v = hashlib.md5(f.read()).hexdigest()[:8]
    return {"share_image": f"{SITE_URL}/{rel}?v={v}", "share_alt": alt}


def page_share(key, alt, eyebrow, title, sub, tiles, foot=""):
    """The link-preview card for a list or hub page (home, records, honors, ...): a headline, one line and up to
    four stat tiles, so a shared link to it shows what's there instead of the plain logo."""
    tiles = [(v, lbl) for v, lbl in tiles if v not in (None, "", 0, "0")][:4]
    return share("pages", key, share_images.simple_card, alt, eyebrow, title, sub, tiles, foot)


def last_name(name):
    return name.split()[-1] if name else ""


def game_share(g):
    kind = {"playoff": "Playoff", "tournament": "Tournament"}.get(g["game_type"], "Conference" if g["conference"] == "Y" else "")
    where = {"away": "Away", "neutral": "Neutral site"}.get(g["site"], "Home")
    label = " · ".join(x for x in (kind, where) if x)
    d = dt.date.fromisoformat(g["date"])
    when = d.strftime("%b %-d, %Y") if g["result"] else d.strftime("%a, %b %-d, %Y")
    if g["result"] in ("W", "L"):
        alt = f"Final: Bangor {g['bangor_score']}, {g['opponent']} {g['opp_score']}, {fmt_date(g['date'])}"
    else:
        alt = f"Bangor {'at' if g['site'] == 'away' else 'vs'} {g['opponent']}, {fmt_date(g['date'])}"
    return share("games", g["game_id"], share_images.game_card, alt, g, when, label)


def render(tpl, path, **ctx):
    ctx["jsonld"] = ld_json(ctx.pop("ld", []))
    depth = path.count("/")
    ctx.setdefault("root", "../" * depth)
    ctx["built"] = BUILT
    ctx["facts"] = FACTS
    ctx["latest_season"] = DATA_SEASONS[-1]
    ctx["has_film"] = bool(FILM_GAMES or HUDL_ONLY)
    ctx["site_url"] = SITE_URL
    ctx["clean"] = CLEAN_URLS
    ctx["build_id"] = BUILD_ID
    ctx["page_url"] = SITE_URL + clean_path(path)
    ctx["coach_slugs"] = COACH_SLUGS
    ctx.setdefault("player_pages", PLAYER_PAGES)
    ctx["current_season"] = CURRENT
    ctx["gameday"] = GAMEDAY
    ctx["cal"] = CAL_LINKS
    ctx["corrections_url"] = corrections_link(ctx["page_url"])
    ctx["analytics"] = ANALYTICS
    html = env.get_template(tpl).render(**ctx)
    if CLEAN_URLS:
        html = absolute_links(html, path)
    PAGES.append(path)
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(html)
