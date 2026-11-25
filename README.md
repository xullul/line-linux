# line-linux

Install and run the official Windows LINE desktop app (26.x) on Linux with Wine.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/xullul/line-linux/main/install.sh | bash
```

Or from a clone:

```bash
git clone https://github.com/xullul/line-linux.git
cd line-linux
./install.sh
```

Run as your normal user; setup uses `sudo` only for system packages. It installs
dependencies, copies `line-linux` to `~/.local/share/line-linux/app`, installs
LINE into `~/.local/share/line-linux/prefix`, and adds an app-grid entry. Pass
`--yes`, `--no-deps`, or `--dry-run` to `./install.sh` (or after `bash -s --`
when piping to Bash).

## What it does

Plain Wine cannot run current LINE releases. `line-linux` sets up a dedicated
Wine prefix and keeps these fixes in place across Wine and LINE updates:

- Signs Wine's DLL copies inside LINE's prefix with a local self-signed
  certificate so LINE starts, and re-signs them after Wine updates.
- Hides Linux color emoji fonts from Wine (which crash LINE after login) and
  maps `Segoe UI Emoji` to Symbola. Other apps keep their normal fonts.
- Configures `LineMediaPlayer.exe` to use its bundled C++ runtime DLL so chat
  photos open, and opens downloaded videos (MP4, M4V, MOV, WebM, MKV) in your
  Linux video player.
- Hides LINE's floating X11 drop-shadow windows while keeping resize edges
  working on the active window.
- Exposes copied images as clipboard files so LINE can paste them, and binds
  `Super+Shift+S` to GNOME's screenshot tool across configured keyboard layouts.
- Links LINE's user folders (including Downloads) to your Linux folders, deletes
  Wine's `:Zone.Identifier` marker files, adds an app-grid entry for
  `LineLauncher.exe`, and suppresses Wine's duplicate menu entries.

## Requirements

LINE 26.x requires Wine 9.0 or newer (older Wine stops the installer at 1%).

`line-linux deps` installs packages with `apt`, `dnf`, `pacman`, or `zypper`. On
Debian, Ubuntu, and their derivatives, setup offers the
[WineHQ](https://gitlab.winehq.org/wine/wine/-/wikis/Download) repository when
distro Wine is older than 9.0. On Arch, it uses `paru` or `yay` for AUR
packages (`osslsigncode` and `ttf-symbola`, or `font-symbola` if `ttf-symbola`
is unavailable).

For `--no-deps` or other distributions:

| Purpose | Debian / Ubuntu | Fedora | Arch | openSUSE |
|---|---|---|---|---|
| Wine | `wine` (`wine32:i386` for distro Wine) | `wine` | `wine` | `wine` |
| DLL signing | `osslsigncode`, `openssl` | `osslsigncode`, `openssl` | `osslsigncode` (AUR), `openssl` | `osslsigncode`, `openssl` |
| Fonts | `fontconfig`, `fonts-symbola` | `fontconfig`, `gdouros-symbola-fonts` | `fontconfig`, `ttf-symbola` (AUR) | `fontconfig`, `gdouros-symbola-fonts` |
| Helpers | `python3`, `python3-gi` | `python3`, `python3-gobject` | `python`, `python-gobject` | `python3`, `python3-gobject` |
| Image paste (optional) | `gir1.2-gtk-4.0` | `gtk4` | `gtk4` | `typelib-1_0-Gtk-4_0` |

Setup also uses `curl` and `gawk`. Optional extras are `xclip` (for
`line-linux capture`) and `mpv` (fallback video player). Tested on Ubuntu,
Debian, Fedora, openSUSE Tumbleweed, and Arch with GNOME on Wayland and KDE
Plasma on Wayland and X11.

## Commands

```text
line-linux launch              start LINE and re-sign DLLs if needed
line-linux doctor              check Wine, signing, folders, and desktop setup
line-linux prefix [DIR [WINE]] show or set the Wine prefix and optional Wine binary
line-linux folders             repair Linux user-folder links
line-linux setup               install LINE and configure desktop integration
line-linux deps                install missing system packages (--yes, --dry-run)
line-linux install             download and run the official LINE installer
line-linux sign                sign Wine DLLs (--force to re-sign all)
line-linux unsign              remove line-linux signatures from the prefix
line-linux fonts               configure the Symbola emoji font replacement
line-linux desktop             install the app-grid entry and ~/.local/bin symlink
line-linux shortcut            bind the GNOME screenshot shortcut
line-linux capture             take a screenshot via the XDG portal
line-linux uninstall           remove line-linux integration, keeping LINE data
```

| Environment variable | Effect |
|---|---|
| `LINE_PREFIX` | Override the saved Wine prefix (default: `~/.local/share/line-linux/prefix`) |
| `LINE_WINE` | Override the prefix's Wine binary for one run (default: `wine` on `PATH`) |
| `LINE_CAPTURE_SHORTCUT` | GNOME screenshot shortcut (default: `<Shift><Super>s`) |
| `LINE_KEEP_SHADOWS=1` | Leave LINE's window shadows visible |
| `LINE_KEEP_ZONE_FILES=1` | Keep `:Zone.Identifier` files next to downloads |

To use a separate Wine build for LINE without changing system Wine, quit LINE
and run `line-linux prefix ~/.local/share/line-linux/prefix /path/to/wine/bin/wine`
(pass `wine` as the second argument to revert). `line-linux uninstall` removes
the launcher, desktop entry, GNOME shortcut, caches, DLL signatures, and
registry entries added by `line-linux`, keeping the Wine prefix and LINE data.

## Limitations

- LINE's built-in screenshot button cannot capture other apps on Wayland.
- Inline video previews do not play inside chats; downloaded videos open in your
  Linux player.
- Maximized photo previews can disappear or freeze on Wine 11.0 under GNOME
  Wayland (fixed in Wine 11.22).
- Voice and video calls are untested.

## DLL signing

LINE requires Windows system DLLs to carry an Authenticode signature from
"Microsoft Windows". `line-linux` generates a local self-signed certificate with
that name in `~/.local/share/line-linux/` (readable only by your user) and signs
only the DLL copies inside LINE's prefix. System Wine and LINE's own files stay
untouched. Keep LINE in its own prefix and do not import this certificate into
any trust store.

Setup downloads `LineInst.exe` over HTTPS from `line-scdn.net` and checks its
Authenticode digest and LY Corporation (or LINE Corporation) signer.

## License

[MIT](LICENSE). Unofficial project not affiliated with or endorsed by LY
Corporation; this repository contains no LINE code or binaries.
