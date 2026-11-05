#!/bin/sh
# Rebuild everything: current-season sheet -> season spreadsheets -> data -> records -> website (site/) -> link check.
# Usage:  ./build.sh
set -e
cd "$(dirname "$0")"
.venv/bin/python scripts/fetch_current.py
.venv/bin/python scripts/convert.py
.venv/bin/python scripts/validate.py > /dev/null
.venv/bin/python scripts/records.py
.venv/bin/python scripts/build_site.py
.venv/bin/python scripts/check_links.py   # lists broken links; never stops the build
echo "Done. Open site/index.html, or publish the site/ folder."
