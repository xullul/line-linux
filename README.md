# line-linux

Run the Windows version of LINE Desktop (26.x) on Linux with Wine.

This is an unofficial project. LY Corporation does not endorse it, and LINE
is its trademark. This repository contains no LINE code or binaries. Setup
downloads the official installer from LINE's servers.

> [!WARNING]
> line-linux works around LINE's DLL signature check. It signs DLLs in the
> LINE Wine prefix with a self-signed certificate named "Microsoft Windows".
> Microsoft did not issue it, and line-linux does not add it to a trust store.
> Keep LINE in a dedicated prefix (the default). Never import this certificate.
> See [DLL signatures](#dll-signatures) for details.

## What it fixes

- Starts LINE and its installer under Wine, and avoids a color emoji font crash.
- Opens chat images and sends downloaded video attachments to your Linux player.
- Uses your Linux Downloads folder and GNOME's screenshot tool, and hides
  LINE's window shadows without disabling resize handles.

## Install

Run as your normal user. Setup uses sudo only for system packages.

```bash
curl -fsSL https://raw.githubusercontent.com/xullul/line-linux/main/install.sh | bash
```

Or use a clone:

```bash
git clone https://github.com/xullul/line-linux.git
cd line-linux
./install.sh
```

LINE needs Wine 9.0 or later. If the distribution's Wine is too old, setup
can offer [WineHQ](https://gitlab.winehq.org/wine/wine/-/wikis/Download) on
Debian, Ubuntu and their derivatives. If that option is unavailable, install
a newer Wine yourself. See [Compatibility](#compatibility) for tested setups.

Setup copies line-linux to `~/.local/share/line-linux/app`, creates a dedicated
prefix at `~/.local/share/line-linux/prefix`, and runs LINE's official
installer. Click through the installer, then open LINE from the app grid or
run `line-linux launch`. You can delete the clone after setup.

| Installer option | What it does |
|---|---|
| `--yes` | Skips package-manager confirmation and the WineHQ prompt |
| `--no-deps` | Skips system package installation |
| `--dry-run` | Checks package availability without installing; lists AUR packages without checking them |

When piping to Bash, pass options after `bash -s --`, for example
`curl -fsSL … | bash -s -- --no-deps`.

To use an existing LINE installation, run `bin/line-linux prefix DIR` in the
clone before setup, or set `LINE_PREFIX` for one run. Avoid sharing `~/.wine`
with LINE: signing changes DLL copies used by every program in that prefix.

### Packages

| Purpose | Debian / Ubuntu | Fedora | Arch | openSUSE |
|---|---|---|---|---|
| Wine | `wine`, plus `wine32:i386` for distro Wine when needed | `wine` | `wine` | `wine` |
| DLL signing | `osslsigncode`, `openssl` | same | `osslsigncode` (AUR), `openssl` | same |
| Fonts | `fontconfig`, `fonts-symbola` | `fontconfig`, `gdouros-symbola-fonts` | `fontconfig`, `ttf-symbola` (AUR) | `fontconfig`, `gdouros-symbola-fonts` |
| Desktop helpers | `python3`, `python3-gi` | `python3`, `python3-gobject` | `python`, `python-gobject` | `python3`, `python3-gobject` |
| Paste images | `gir1.2-gtk-4.0` | `gtk4` | `gtk4` | `typelib-1_0-Gtk-4_0` |

Setup also checks for `curl` and `gawk`. Symbola, GTK 4, `xclip` (fallback
capture) and `mpv` (fallback video player) are optional. The desktop helpers
use libX11, libXext and libxkbcommon.

On Arch, setup uses `paru` or `yay` for AUR packages. Without either, build
[osslsigncode](https://aur.archlinux.org/osslsigncode.git) and
[font-symbola](https://aur.archlinux.org/font-symbola.git) with `makepkg -si`.
Use `font-symbola` if the older `ttf-symbola` source is unavailable.

## Use LINE

### Image previews

LINE opens chat photos in `LineMediaPlayer.exe`. Under Wine 11.0, the viewer
can exit on startup because one C++ runtime function is unimplemented.
line-linux tells only the viewer to use LINE's bundled `msvcp140_2.dll`,
with Wine's copy as a fallback.

### Maximize

On GNOME Wayland with Wine running through XWayland, Wine 11.0 sometimes hid
the maximized image preview or left its controls unresponsive. With Wine 11.22,
the photo stayed visible and maximize, restore, minimize, reopen and close
worked. If you see the Wine 11.0 behavior, try
[Wine 11.22 in LINE's own prefix](#separate-wine-build).

The older `Decorated=N` setting applies to the main `LINE.exe` window, not the
viewer. Wine 9.0 reads it; Wine 10.0 and 11.0 do not.

### Separate Wine build

If LINE already has a dedicated prefix, quit LINE before switching its Wine
build. Install or unpack Wine first, then pass the path to its `wine` binary:

```bash
line-linux prefix "$HOME/.local/share/line-linux/prefix" /path/to/wine-11.22/bin/wine
line-linux launch
```

This saves the binary for that prefix only. It does not install Wine, copy
LINE data or change the system Wine. The next launch updates and signs the
selected prefix as needed. Re-saving the same prefix without a Wine path
keeps its saved binary; selecting a different prefix does not carry it over.
To use the `wine` on PATH again, pass `wine` as the second argument.

### Downloads and user folders

The photo preview's Save As defaults to your Linux Downloads folder after
setup. line-linux uses `xdg-user-dir DOWNLOAD` when configured and otherwise
uses `~/Downloads`.
LINE shows the Windows path under **Settings → Chats → Download folder**.

Setup and launch check the prefix's links to Desktop, Documents, Downloads,
Music, Pictures and Videos. If a real folder is in the way, line-linux moves
its files without overwriting yours. If a filename collision prevents linking
Downloads, it keeps both files and points new saves directly to the Linux
folder. Run `line-linux folders` to repair the mappings yourself.

Wine can leave a `file:Zone.Identifier` marker next to a download. The
session helper removes new markers in Downloads when the matching file
exists. It leaves older markers alone.

### Screen capture

1. On GNOME, press Super+Shift+S or Print. Super is the Windows key.
2. Select an area and press Enter to copy the screenshot.
3. In LINE, press Ctrl+V and choose **Image**. Escape chooses Text and pastes
   the file path instead.

LINE's own screenshot button cannot capture other apps on Wayland. On other
desktops, copy an image with your screenshot tool, or try `line-linux capture`
with `xclip` and the XDG screenshot portal.

The GNOME shortcut also works in configured non-Latin keyboard layouts. The
clipboard helper offers a copied image as both an image and a file, because
LINE under Wine can paste the file. It keeps private copies in
`~/.cache/line-linux/captures/` and removes them after a day.

### Video attachments

Downloaded MP4, M4V, MOV, WebM and MKV files open in the default Linux app
through Wine's `winebrowser.exe` when no Windows association exists. This
does not fix inline video previews. Both AV1 and H.264/AAC MP4s were sent as
file attachments in testing. Uninstall removes only associations added by
line-linux.

### Quit LINE

Closing the main window can leave LINE running in the tray. To exit,
right-click the LINE tray icon and choose **Quit**, not **Sign out**.
The right-click menu works on GNOME 51 with Wine 11.22 through XWayland.

## Commands

```text
line-linux launch              start LINE and re-sign DLLs if needed
line-linux doctor              check Wine, signing, folders and desktop setup
line-linux prefix [DIR [WINE]] show or set the prefix and its optional Wine binary
line-linux folders             repair Linux user-folder mappings
line-linux setup               install LINE and configure desktop integration
line-linux deps                install missing packages (--yes, --dry-run)
line-linux install             download and run the official LINE installer
line-linux sign                sign Wine DLLs (--force to redo all)
line-linux unsign              remove line-linux's signatures
line-linux fonts               set the emoji font
line-linux desktop             install the app-grid entry and command link
line-linux shortcut            set the GNOME capture shortcut
line-linux capture             capture via the XDG screenshot portal
line-linux uninstall            remove setup changes, leaving LINE data
```

| Variable | Effect |
|---|---|
| `LINE_PREFIX` | Override the saved prefix (default: `~/.local/share/line-linux/prefix`) |
| `LINE_WINE` | Override the saved Wine binary for this run; otherwise use the binary saved for the selected prefix or `wine` on PATH |
| `LINE_CAPTURE_SHORTCUT` | Set the GNOME capture shortcut (default: `<Shift><Super>s`) |
| `LINE_KEEP_SHADOWS=1` | Keep LINE's window shadows |
| `LINE_KEEP_ZONE_FILES=1` | Keep new `:Zone.Identifier` markers |

`uninstall` removes the launcher, shortcuts, caches and signatures. It also
removes app integration settings that line-linux added to the registry. It
keeps the prefix, LINE data and folder mappings. It deletes the signing
certificate only when no other prefix uses it.

## How it works

### DLL signatures

LINE and its 32-bit installer reject Windows system DLLs without an
Authenticode signature from a signer named "Microsoft Windows". `line-linux
sign` signs the prefix's copies in `system32` and `syswow64` with a local
certificate. It does not modify LINE or the system Wine installation.

Wine can replace DLLs during a prefix update, so `launch` re-signs them
before starting LINE. Wine can also queue replacements for its next boot;
line-linux runs `wineboot -r` to apply them before signing. It checks each
signature against the local certificate. The 16-bit stubs cannot be signed,
but LINE does not load them. Only your user can read the signing key.

Setup verifies that the installer came from LINE over HTTPS, that the
signature matches its contents, and that the signer is LY Corporation or
LINE Corporation. It does not check the certificate chain because Linux
CA bundles do not include code-signing roots.

### Emoji font crash

LINE's Qt font engine can crash on color emoji fonts under Wine. line-linux
uses a separate fontconfig view without color fonts and maps Segoe UI Emoji
to Symbola. It rebuilds the view when system fonts change. Other apps are
unaffected.

### Window shadows

Wine can leave LINE's shadow windows above other apps after you switch away.
The shadow helper hides them. Only the focused LINE window's shadows accept
clicks, so you can still use them to resize it. Click the window first if
another app has focus.

### Paths

| What | Where |
|---|---|
| LINE program | `<prefix>/drive_c/users/$USER/AppData/Local/LINE/bin/current/` |
| Launcher, unchanged across LINE updates | `<prefix>/…/LINE/bin/LineLauncher.exe` |
| LINE data | `<prefix>/…/LINE/Data/` |
| Downloads | Your Linux Downloads folder |
| Pasted-image copies | `~/.cache/line-linux/captures/` |
| Saved prefix and Wine binary | `~/.config/line-linux/config` |
| Signing key, font links and state | `~/.local/share/line-linux/` |
| App-grid entry | `~/.local/share/applications/line-messenger.desktop` |

The desktop command disables Wine's menu builder in the LINE prefix to
prevent duplicate LINE entries after updates.

## Repository layout

- `install.sh` installs packages, line-linux and LINE.
- `bin/line-linux` is the launcher and command-line tool.
- `lib/` contains the shadow, clipboard, Downloads and screenshot helpers.
- `config/signing.cnf` sets the name on the signing certificate.

## Compatibility

Wine 9.0 is the minimum for LINE 26.x. On Wine 8.0 or older the installer can
stop at 1%. The minimum does not guarantee every desktop feature works.

### Distributions

Tested with LINE 26.6.0.4004 on 2026-11-06. "Starts" means installation
finished and LINE reached the sign-in screen. Only the first row was tested
past sign-in in this distribution test.

| Distribution | Wine | Result |
|---|---|---|
| Ubuntu 26.10 | 11.0 from WineHQ | Login, chats, Thai text, emoji, settings and screenshot paste |
| Ubuntu 26.04 | 10.0 (Ubuntu) | Starts with the piped installer |
| Ubuntu 24.04 | 9.0 (Ubuntu) | Starts with `wine32:i386` |
| Ubuntu 22.04 | 11.0 from WineHQ | Starts; distro Wine 6.0 is too old |
| Ubuntu 20.04 | 10.0 from WineHQ | Starts; no GTK 4 clipboard helper |
| Debian 13 | 10.0 (Debian) | Starts with `wine32:i386` |
| Debian 12 | 11.0 from WineHQ | Starts; replaces distro Wine 8.0 if installed |
| Fedora 43 | 11.0 Staging (Fedora) | Starts |
| openSUSE Tumbleweed | 11.20 (openSUSE) | Starts |
| Arch | 11.21 (Arch) | Starts; signing and Symbola packages from the AUR |
| Linux Mint 22.3 | | Not tested |

Wine 9.0 or later was not available for Ubuntu 18.04, Ubuntu 16.04 or
AlmaLinux in the repositories checked. Ubuntu 26.10 was tested on real
hardware, other distributions in Podman with a virtual display. Debian 13
and Kubuntu 24.04 were also tested as live systems in a VM.

### Desktops

| Desktop | Result |
|---|---|
| GNOME 51 on Wayland (Ubuntu 26.10) | Window shadows, capture shortcut with English and Thai layouts, and screenshot paste verified |
| KDE Plasma 6.3 on Wayland (Debian 13 live VM) | Starts. Shadows hidden, launcher and taskbar icon present, copied images offered as files. Use Spectacle for capture; focus LINE before pasting |
| KDE Plasma 5.27 on X11 (Kubuntu 24.04 live VM) | Starts. Shadows hidden, launcher and taskbar icon present |
| Xfce and other desktops | Not tested. Use your desktop's screenshot tool to copy captures |

### Features

| Feature | Status |
|---|---|
| Open a chat photo | Verified with Wine 11.0 and 11.22 on Ubuntu 26.10, LINE 26.6.0.4004 |
| Maximize, restore, minimize and close a photo preview | Verified with Wine 11.22 on GNOME 51 through XWayland; see [Maximize](#maximize) for the Wine 11.0 issue |
| Preview Save As default | Verified in Linux Downloads on the same Wine 11.22 setup |
| LINE's own screenshot button | Does not work on Wayland; not tested on X11 |
| Download a chat file and remove its marker | Not confirmed |
| Voice and video calls | Not tested |

For a report from another setup, include `line-linux doctor` output. Check
it for private paths before posting.

## License

[MIT](LICENSE)
