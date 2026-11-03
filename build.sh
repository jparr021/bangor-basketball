#!/bin/sh
# Rebuild everything: current-season sheet -> season spreadsheets -> data -> records -> website (site/).
# Usage:  ./build.sh
set -e
cd "$(dirname "$0")"
.venv/bin/python scripts/fetch_current.py
.venv/bin/python scripts/convert.py
.venv/bin/python scripts/validate.py > /dev/null
.venv/bin/python scripts/records.py
.venv/bin/python scripts/build_site.py
echo "Done. Open site/index.html, or publish the site/ folder."
