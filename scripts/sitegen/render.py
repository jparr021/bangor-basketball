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


# Drawing ~2,000 share images is most of the build's time, and almost all of them are the same from one build to
# the next. Each image is kept in a cache, named by a hash of everything that goes into it (the card's text and
# tiles, plus share_images.py, the fonts and the logo), and copied from there when nothing changed. The cache is
# under node_modules/ because that's the one folder Vercel keeps between builds for a site with no framework.
# SHARE_CACHE=0 turns it off.
SHARE_CACHE = os.path.join(ROOT, "node_modules", ".cache", "share-images")
SHARE_STATS = {"reused": 0, "drawn": 0, "used": set()}


def _share_version():
    import hashlib
    h = hashlib.md5(SHARE_HOST.encode())
    files = [os.path.join(ROOT, "scripts", "share_images.py"), share_images._LOGO_PATH]
    files += sorted(os.path.join(share_images._FONTS, f) for f in os.listdir(share_images._FONTS))
    for p in files:
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


SHARE_VERSION = _share_version() if os.environ.get("SHARE_CACHE", "1") != "0" else None


def share(kind, key, draw, alt, *args):
    """Draw one link-preview image into site/static/share/ (or copy it from the cache when nothing in it changed)
    and return (absolute URL, alt text) for render().
    The URL carries a short hash of the image, so a preview that changed (a new score) is fetched fresh."""
    import hashlib
    rel = f"static/share/{kind}/{key}.png"
    full = os.path.join(OUT, rel)
    cached = None
    if SHARE_VERSION:
        spec = json.dumps([SHARE_VERSION, draw.__name__, args], ensure_ascii=False, default=str)
        cached = os.path.join(SHARE_CACHE, hashlib.md5(spec.encode()).hexdigest() + ".png")
        SHARE_STATS["used"].add(os.path.basename(cached))
    if cached and os.path.exists(cached):
        os.makedirs(os.path.dirname(full), exist_ok=True)
        shutil.copyfile(cached, full)
        SHARE_STATS["reused"] += 1
    else:
        draw(full, SHARE_HOST, *args)
        SHARE_STATS["drawn"] += 1
        if cached:
            os.makedirs(SHARE_CACHE, exist_ok=True)
            shutil.copyfile(full, cached)
    with open(full, "rb") as f:
        v = hashlib.md5(f.read()).hexdigest()[:8]
    return {"share_image": f"{SITE_URL}/{rel}?v={v}", "share_alt": alt}


def finish_share_cache():
    """Drop cached images no page used this build (so the cache doesn't grow), and report what was reused."""
    if SHARE_VERSION and os.path.isdir(SHARE_CACHE):
        for f in os.listdir(SHARE_CACHE):
            if f not in SHARE_STATS["used"]:
                os.remove(os.path.join(SHARE_CACHE, f))
    stats = {"reused": SHARE_STATS["reused"], "drawn": SHARE_STATS["drawn"], "built": dt.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(OUT, "static", "share", "cache.json"), "w") as f:
        json.dump(stats, f)
    print(f"share images: {stats['reused']} reused, {stats['drawn']} drawn")


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
    # only what the card draws, so the cache key doesn't change when the game picks up film or a news story
    card = {k: g.get(k) for k in ("result", "ot", "is_today", "time", "opponent", "site", "bangor_score", "opp_score")}
    return share("games", g["game_id"], share_images.game_card, alt, card, when, label)


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
