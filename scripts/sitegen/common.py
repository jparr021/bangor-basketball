"""Paths, settings from the environment, and small helpers shared by every part of the build."""


import csv, datetime as dt, glob, json, math, os, posixpath, re, shutil
from collections import defaultdict, OrderedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

import charts
import recaps
import share_images
import sheet_check

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/sitegen/ -> project
DATA = os.path.join(ROOT, "data")
OV = os.path.join(ROOT, "overrides")
SRC = os.path.join(ROOT, "site-src")
OUT = os.path.join(ROOT, "site")

PLAYER_ALIASES = {"Konnor Kaiser": "Connor Kaiser"}

# The site's public address, used for share previews, canonical links and the sitemap.
# On Vercel this comes from the project's production domain automatically: the
# *.vercel.app address today, and a custom domain as soon as one is added. SITE_URL overrides it.
_vercel_host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
SITE_URL = (os.environ.get("SITE_URL") or (f"https://{_vercel_host}" if _vercel_host
                                           else "https://bangor-basketball.vercel.app")).rstrip("/")
# Clean links (/players/hayden-massman instead of players/hayden-massman.html) when building on
# Vercel, which serves them (vercel.json cleanUrls). Local builds keep .html links so the files
# open straight from disk. Set CLEAN_URLS=1 to force clean links.
CLEAN_URLS = os.environ.get("VERCEL") == "1" or os.environ.get("CLEAN_URLS") == "1"


# ---------------------------------------------------------------- helpers
def load(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def slug(name):
    s = str(name).lower().replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def canon(name):
    name = str(name).strip()
    return PLAYER_ALIASES.get(name, name)


def fmt_int(v):
    if v is None or v == "":
        return ""
    v = float(v)
    return f"{int(v):,}" if v.is_integer() else f"{v:.1f}"


def fmt_pct(m, a):
    if m is None or a in (None, 0):
        return ""
    return f"{100 * m / a:.1f}%"


def fmt_avg(t, g):
    if t is None or not g:
        return ""
    return f"{t / g:.1f}"


def fmt_date(iso, style="short"):
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso)
    if style == "long":
        return d.strftime("%A, %B %-d, %Y")
    return d.strftime("%b %-d, %Y")


def season_end_year(season):
    return int(season[:4]) + 1


def clean_path(path):
    """'players/x.html' -> '/players/x', 'seasons/index.html' -> '/seasons', 'index.html' -> '/'."""
    p = path[:-5] if path.endswith(".html") else path
    if p == "index":
        return "/"
    if p.endswith("/index"):
        p = p[:-6]
    return "/" + p
