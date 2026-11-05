"""Check every link inside the built site (site/) for a page, file or #anchor that doesn't exist.

  .venv/bin/python scripts/check_links.py            # list broken links (always exits 0)
  .venv/bin/python scripts/check_links.py --strict   # exit 1 if any are broken (the GitHub check)

The Vercel build runs it without --strict, so a broken link never stops a score update; it's listed in
the build log. The "Check site links" GitHub workflow runs it with --strict on every push, so a broken
link shows up as a failed check. Works with both local (.html) and clean (/players/x) links.
Links to other sites aren't checked.
"""
import glob, os, re, sys
from collections import defaultdict
from html.parser import HTMLParser
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
SKIP = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)  # http:, mailto:, tel:, javascript:, data:, //host


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("id", "name") if tag == "a" else ("id",):
            if a.get(k):
                self.ids.add(a[k])
        for k in ("href", "src"):
            v = a.get(k)
            if v is not None and not (tag == "link" and a.get("rel") in ("canonical", "alternate")):
                self.links.append((tag, k, v.strip()))

    handle_startendtag = handle_starttag


def resolve(page_rel, target):
    """The file in site/ a link points at, or None."""
    if target.startswith("/"):
        path = os.path.normpath(os.path.join(SITE, target.lstrip("/")))
    else:
        path = os.path.normpath(os.path.join(SITE, os.path.dirname(page_rel), target))
    if not path.startswith(SITE):
        return None
    for cand in (path, path + ".html", os.path.join(path, "index.html")):
        if os.path.isfile(cand):
            return os.path.relpath(cand, SITE)
    return None


def main():
    strict = "--strict" in sys.argv
    pages = {}
    for f in sorted(glob.glob(os.path.join(SITE, "**", "*.html"), recursive=True)):
        p = Page()
        with open(f, encoding="utf-8") as fh:
            p.feed(fh.read())
        pages[os.path.relpath(f, SITE)] = p
    broken = defaultdict(list)  # (target, reason) -> pages
    n = 0
    for rel, p in pages.items():
        for tag, attr, link in p.links:
            if not link or SKIP.match(link) or link.startswith("/_vercel/"):  # served by Vercel itself
                continue
            n += 1
            path, _, frag = link.partition("#")
            path = unquote(path.split("?", 1)[0])
            dest = resolve(rel, path) if path else rel
            key = None
            if dest is None:
                key = (link, "missing page or file")
            elif frag and dest.endswith(".html") and unquote(frag) not in pages[dest].ids:
                key = (link, f"no #{frag} on {dest}")
            if key and rel not in broken[key]:
                broken[key].append(rel)
    print(f"check_links: {n:,} links on {len(pages):,} pages, {len(broken)} broken")
    for (link, why), where in sorted(broken.items(), key=lambda kv: -len(kv[1])):
        more = f" (and {len(where) - 3} more)" if len(where) > 3 else ""
        print(f"  {link}  [{why}]  on {', '.join(where[:3])}{more}")
    if strict and broken:
        sys.exit(1)


if __name__ == "__main__":
    main()
