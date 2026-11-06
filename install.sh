#!/usr/bin/env bash
# Install everything needed to run LINE on Linux, then LINE itself.
#
#   ./install.sh            install missing packages (asks for sudo), install
#                           line-linux, run the official LINE installer
#   ./install.sh --yes      don't ask the package manager for confirmation
#   ./install.sh --no-deps  skip system packages
#   ./install.sh --dry-run  only check that the packages can be installed
#
# line-linux is copied to ~/.local/share/line-linux/app, so this folder can be
# deleted afterwards. Run `line-linux uninstall` to undo.
set -euo pipefail

SRC=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
APP=${XDG_DATA_HOME:-$HOME/.local/share}/line-linux/app

deps=1 dry=0 yes=()
for arg in "$@"; do
  case $arg in
    --yes|-y) yes=(--yes) ;;
    --no-deps) deps=0 ;;
    --dry-run) dry=1 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

if (( EUID == 0 )); then
  echo "Run this as your normal user; sudo is used only to install packages." >&2
  exit 1
fi

if (( dry )); then
  exec "$SRC/bin/line-linux" deps --dry-run
fi

(( deps )) && "$SRC/bin/line-linux" deps "${yes[@]}"

if [[ $SRC != "$APP" ]]; then
  rm -rf "$APP.new"
  mkdir -p "$APP.new"
  cp -r "$SRC/bin" "$SRC/lib" "$SRC/config" "$SRC/LICENSE" "$SRC/README.md" "$APP.new/"
  rm -rf "$APP"
  mv "$APP.new" "$APP"
fi

exec "$APP/bin/line-linux" setup
