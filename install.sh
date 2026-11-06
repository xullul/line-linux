#!/usr/bin/env bash
# Install everything needed to run LINE on Linux, then LINE itself.
#
#   curl -fsSL https://raw.githubusercontent.com/xullul/line-linux/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/xullul/line-linux/main/install.sh | bash -s -- --yes
#
# or from a clone: ./install.sh [options]
#
#   --yes      don't ask the package manager for confirmation
#   --no-deps  skip system packages
#   --dry-run  only check that the packages can be installed
#
# line-linux is copied to ~/.local/share/line-linux/app; a clone can be
# deleted afterwards. Run `line-linux uninstall` to undo.
set -euo pipefail

# Everything runs inside main, so that when this script is piped into bash,
# bash has read all of it before the first command runs.
main() {
  local repo=${LINE_LINUX_REPO:-xullul/line-linux} ref=${LINE_LINUX_REF:-main}
  local app=${XDG_DATA_HOME:-$HOME/.local/share}/line-linux/app
  local deps=1 dry=0 yes=() arg
  for arg in "$@"; do
    case $arg in
      --yes|-y) yes=(--yes) ;;
      --no-deps) deps=0 ;;
      --dry-run) dry=1 ;;
      -h|--help) usage; return 0 ;;
      *) echo "unknown option: $arg (see --help)" >&2; return 2 ;;
    esac
  done

  if (( EUID == 0 )); then
    echo "Run this as your normal user; sudo is used only to install packages." >&2
    return 1
  fi

  # Piped into bash, stdin is the script. sudo, the package manager and the
  # WineHQ question read from the terminal instead.
  if [[ ! -t 0 ]] && (: </dev/tty) 2>/dev/null; then
    exec </dev/tty
  fi

  # Use the folder this script is in when it's a line-linux checkout;
  # otherwise download line-linux from GitHub.
  local src= tmp=
  if [[ -n ${BASH_SOURCE[0]:-} && -f ${BASH_SOURCE[0]} ]]; then
    src=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
    [[ -x $src/bin/line-linux ]] || src=
  fi
  if [[ -z $src ]]; then
    command -v curl >/dev/null && command -v tar >/dev/null ||
      { echo "Downloading line-linux needs curl and tar. Install them, then run this again." >&2; return 1; }
    tmp=$(mktemp -d)
    # shellcheck disable=SC2064 # expand $tmp now
    trap "rm -rf '$tmp'" EXIT
    # LINE_LINUX_ARCHIVE points at another archive, for testing.
    local url=${LINE_LINUX_ARCHIVE:-https://github.com/$repo/archive/$ref.tar.gz} proto=()
    [[ -n ${LINE_LINUX_ARCHIVE:-} ]] || proto=(--proto '=https' --proto-redir '=https')
    printf '\033[1;32m==>\033[0m Downloading line-linux from %s\n' "$url"
    curl -fsSL "${proto[@]}" "$url" | tar -xz -C "$tmp" --strip-components=1
    [[ -x $tmp/bin/line-linux ]] || { echo "The download doesn't contain line-linux" >&2; return 1; }
    src=$tmp
  fi

  if (( dry )); then
    "$src/bin/line-linux" deps --dry-run
    return
  fi

  (( deps )) && "$src/bin/line-linux" deps "${yes[@]}"

  if [[ $src != "$app" ]]; then
    rm -rf "$app.new"
    mkdir -p "$app.new"
    cp -r "$src/bin" "$src/lib" "$src/config" "$src/LICENSE" "$src/README.md" "$app.new/"
    rm -rf "$app"
    mv "$app.new" "$app"
  fi

  "$app/bin/line-linux" setup
}

usage() {
  cat <<'EOF'
Install line-linux and its packages, then run the official LINE installer.

  curl -fsSL https://raw.githubusercontent.com/xullul/line-linux/main/install.sh | bash
  curl -fsSL https://raw.githubusercontent.com/xullul/line-linux/main/install.sh | bash -s -- --yes
  ./install.sh [options]          (from a clone)

  --yes      don't ask the package manager for confirmation
  --no-deps  skip system packages
  --dry-run  only check that the packages can be installed

line-linux is copied to ~/.local/share/line-linux/app. Run `line-linux uninstall` to undo.
EOF
}

main "$@"
