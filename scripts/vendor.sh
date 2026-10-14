#!/usr/bin/env bash
# Copy tg_botkit into a project:  scripts/vendor.sh ../tg-propertyfate
# The project commits the copy (src/tg_botkit/), so its Docker build needs no access to this private repo.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
dst=${1:?project directory}/src/tg_botkit
[ -d "${1}/src" ] || { echo "no src/ in $1" >&2; exit 1; }
rm -rf "$dst"; mkdir -p "$dst"
cp "$here"/src/tg_botkit/*.py "$dst"/
printf 'Vendored copy of ExiosV/tg-botkit %s. Do not edit here: change tg-botkit and rerun scripts/vendor.sh.\n' \
  "$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$here/src/tg_botkit/__init__.py")" > "$dst/VENDORED.txt"
echo "vendored $(cat "$dst/VENDORED.txt")"
