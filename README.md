# line-linux

Run the current Windows version of the LINE desktop app (26.x) on Linux
with Wine. LINE keeps updating itself, gets an entry in the app grid, and
screenshots paste into chats on GNOME Wayland.

Only Ubuntu 26.10 with GNOME on Wayland has been tested. See
[Compatibility](#compatibility) before using it elsewhere.

> Unofficial. LY Corporation doesn't make or endorse this project, and LINE
> is its trademark. The repository contains no LINE code or binaries. Setup
> downloads the official installer from LINE's servers.

> [!WARNING]
> This works around a security check. LINE refuses to run on Wine's
> unsigned system DLLs, so line-linux creates a self-signed certificate named
> "Microsoft Windows" and signs the DLLs in LINE's Wine prefix with it.
> Microsoft didn't issue this certificate, and line-linux never adds it to a
> trust store. Keep LINE in its own Wine prefix, which is the default, and
> never import the certificate anywhere else. [DLL signatures](#dll-signatures)
> explains the details.

## What it fixes

- The official installer and LINE stop with "Security verification failed …
  NO_SIGNATURE". Both check the signatures of Wine's DLLs, which are
  unsigned. line-linux signs them, and signs them again after a Wine upgrade.
- LINE crashes right after login. Its font engine crashes on color emoji
  fonts, so line-linux hides those fonts from Wine and uses Symbola for
  emoji.
- A dark frame stays over other apps after you switch away from LINE. These
  are LINE's shadow windows, and line-linux makes them invisible.
- LINE's own screenshot button can't capture other apps on Wayland, and
  pasted screenshots don't arrive. Super+Shift+S opens GNOME's screenshot
  tool, and a helper turns the copied image into something LINE can paste.
- Downloads land inside the Wine prefix, or `~/Downloads` fills up with
  `name:Zone.Identifier` files. line-linux links LINE's Downloads folder to
  yours and deletes those marker files.
- The app-grid entry breaks after LINE updates itself. line-linux starts LINE
  through LINE's own launcher, whose path never changes.

## Install

```bash
git clone https://github.com/xullul/line-linux.git
cd line-linux
./install.sh
```

`install.sh` runs these steps:

1. Installs missing system packages with apt, dnf, pacman or zypper, which
   asks for your sudo password. An existing Wine, for example from WineHQ,
   stays as it is. On Arch, `paru` or `yay` installs the AUR packages if you
   have one.
2. Copies the tool to `~/.local/share/line-linux/app` and links `line-linux`
   into `~/.local/bin`. You can delete the cloned folder afterwards.
3. Creates a Wine prefix only for LINE in `~/.local/share/line-linux/prefix`
   and signs its DLLs.
4. Downloads LINE's installer over HTTPS, checks its LY Corporation
   signature, and runs it. Click through it as you would on Windows.
5. Sets up fonts, links the prefix's user folders to yours, adds LINE to the
   app grid, and binds Super+Shift+S to the screenshot tool.

Then start LINE from the app grid or with `line-linux launch`.

`--yes` skips the package manager's confirmation. `--no-deps` skips system
packages. `--dry-run` only checks that the packages exist, and lists AUR
packages without checking them.

To use LINE that's already installed in another prefix such as `~/.wine`,
run `bin/line-linux prefix ~/.wine` in the cloned folder before
`./install.sh`. For a single run, use `LINE_PREFIX=~/.wine ./install.sh`.
Signing changes that prefix's DLLs for every program that uses it, so a
prefix only for LINE is safer.

### Packages

| Purpose | Debian / Ubuntu | Fedora | Arch | openSUSE |
|---|---|---|---|---|
| Wine | `wine` | `wine` | `wine` | `wine` |
| DLL signing | `osslsigncode`, `openssl` | same | `osslsigncode` (AUR), `openssl` | same |
| Download | `curl` | `curl` | `curl` | `curl` |
| Fonts | `fontconfig`, `fonts-symbola` | `fontconfig`, `gdouros-symbola-fonts` | `fontconfig`, `ttf-symbola` (AUR) | `fontconfig`, `gdouros-symbola-fonts` |
| Shadow fix, capture shortcut | `python3`, `python3-gi` | `python3`, `python3-gobject` | `python`, `python-gobject` | `python3`, `python3-gobject` |
| Pasting images into LINE | `gir1.2-gtk-4.0` | `gtk4` | `gtk4` | `typelib-1_0-Gtk-4_0` |
| Fallback capture command | `xclip` | `xclip` | `xclip` | `xclip` |

The helpers also use libX11, libXext and libxkbcommon, which every X11 or
Wayland desktop has. If `xdg-user-dirs` is installed, line-linux uses it to
find translated folder names.

## Commands

```text
line-linux setup        install, sign, fonts, folders, desktop, shortcut
line-linux launch       start LINE (re-signs DLLs first if Wine was upgraded)
line-linux install      download and run the official LINE installer
line-linux sign         sign Wine DLLs (--force to redo all)
line-linux unsign       remove the signatures again
line-linux fonts        set the emoji font
line-linux folders      make LINE's Downloads and other user folders the Linux ones
line-linux desktop      install the app-grid entry and ~/.local/bin link
line-linux shortcut     make Super+Shift+S open GNOME's screenshot tool
line-linux capture      capture via the screenshot portal (fallback)
line-linux doctor       show the state of everything
line-linux deps         install missing system packages (--yes, --dry-run)
line-linux prefix [DIR] show or save the Wine prefix to use
line-linux uninstall    remove what setup added (see below)
```

| Variable | Default | Meaning |
|---|---|---|
| `LINE_PREFIX` | the prefix saved with `line-linux prefix`, else `~/.local/share/line-linux/prefix` | Wine prefix |
| `LINE_WINE` | `wine` | Wine binary, with `wineserver` in the same folder |
| `LINE_CAPTURE_SHORTCUT` | `<Shift><Super>s` | Capture key |
| `LINE_KEEP_SHADOWS` | unset | `1` keeps LINE's window shadows |
| `LINE_KEEP_ZONE_FILES` | unset | `1` keeps Wine's `:Zone.Identifier` files next to downloads |

`uninstall` removes the DLL signatures, the app-grid entry, the
`~/.local/bin` link, the capture shortcut and the caches. In the prefix, it
removes the emoji and menu settings that line-linux created, and leaves
values that existed before. It deletes the signing certificate once no other
prefix still uses it.

`uninstall` keeps the Wine prefix with LINE and your LINE data, and the
prefix's links to your folders. Delete the prefix folder to remove LINE
completely.

## How it works

### DLL signatures

LINE 26.x checks the Authenticode signature of every Windows system DLL it
loads. It accepts a DLL only if the signer is named "Microsoft Windows". Any
other signer name fails with `UNTRUSTED_SIGNER`.

`line-linux sign` creates a self-signed certificate with that name in
`~/.local/share/line-linux/` and signs the DLLs in the prefix's `system32`
and `syswow64` folders with `osslsigncode`. It signs them before LINE's
installer runs, because the installer is a 32-bit program that checks the
DLLs in `syswow64` too.

Wine sometimes rewrites DLLs just after it creates or updates a prefix,
which replaces DLLs that were already signed. `sign` therefore repeats until
a full pass finds nothing left to sign. A DLL counts as signed only if its
signature verifies against this certificate, so `sign` notices and re-signs
any file that changed later. About 40 16-bit stubs can't be signed, and LINE
never loads them.

A Wine upgrade also rewrites the DLLs. `launch` records which Wine version
it signed for. When the version changes, it runs `wineboot -u` and signs
again before starting LINE.

line-linux changes only the DLL copies inside the LINE prefix. It doesn't
modify LINE, and it never adds the certificate to a trust store. Anyone who
can read `~/.local/share/line-linux/key.pem` could sign files that pass the
same check, so only your user can read it, and `uninstall` deletes it.

Before running LINE's installer, `install` checks three things: it arrived
over HTTPS from LINE's servers, its Authenticode signature matches its
contents, and the signer is LY Corporation. `install` doesn't validate the
certificate chain, because Linux CA bundles don't include code-signing roots.

### Emoji font crash

LINE 26.x uses Qt 6.6 with its GDI font engine. The first time the chat list
shows an emoji, Qt falls back to a color emoji font such as Noto Color Emoji.
Wine passes that font to Qt in a form that makes `QWindowsFontEngine` read
invalid memory, and LINE crashes.

Wine reads font folders directly and ignores fontconfig's `<rejectfont>`
rule. line-linux therefore gives Wine its own `FONTCONFIG_FILE`. It points
to a folder of links to every system font except color fonts, and it maps
"Segoe UI Emoji" to Symbola, so emoji show in black and white. line-linux
rebuilds the folder when system fonts change. Other programs keep using
your normal fonts.

### Window shadows

LINE draws each window's shadow as eight thin, untitled windows, 11 px wide
around main windows and 20 px around dialogs. Wine creates most of them as
override-redirect X windows, and GNOME keeps those above every app. They
stayed on screen after you switched to another app.

`launch` starts `lib/hide-shadows.py`. It treats an untitled LINE window
lying along the outside edge of a titled LINE window as a shadow. It sets
the shadow's opacity to 0 and gives it an empty X shape, so clicks pass
through. Without the opacity change, GNOME still paints a small corner wedge
for the window. If Wine changes either setting later, the helper applies it
again. It exits when LINE exits, and leaves tooltips and menus alone.

### Screen capture

To send a screenshot:

1. Press Super+Shift+S or Print. Super is the Windows key. GNOME's
   screenshot tool opens.
2. Select an area and press Enter. GNOME copies the capture.
3. In a LINE chat, press Ctrl+V. LINE asks how to paste it. Choose Image.
   Escape counts as Text and pastes a file path.

LINE's own screenshot button doesn't work on Wayland. Its overlay opens, but
Wine can't read other apps' pixels, so the magnifier shows black. The
overlay also doesn't stay above other windows, so its buttons don't respond.
Wayland blocks this on purpose, and line-linux can't change it.

Two helpers make the shortcut work:

- `lib/capture-shortcut.py` adds Super+Shift+S to GNOME Shell's screenshot
  shortcut. GNOME matches letter shortcuts against the active keyboard
  layout, so the helper also binds the same key in each configured
  non-Latin layout, such as `<Shift><Super>Thai_hohip` for Thai.
- `lib/session-helper.py` runs while LINE runs. Wine passes an image/png
  from the Linux clipboard to Windows programs under a broken format name,
  and LINE ignores plain bitmaps. LINE does paste a copied file. When the
  clipboard holds an image but no file, the helper saves a copy to
  `~/.cache/line-linux/captures/` and offers it both as image/png and as a
  file. Other apps still paste it as an image. Only your user can read the
  copies. The helper deletes copies older than a day every hour while it
  runs, and again when it starts.

The shortcut uses GNOME Shell's tool instead of the XDG screenshot portal,
because the portal doesn't answer capture requests reliably on every GNOME
version. `line-linux capture` still uses the portal as a fallback for other
desktops, and gives up after two minutes.

### Downloads and user folders

LINE has no download folder setting of its own. It saves to the Windows
Downloads folder, `C:\users\<you>\Downloads`, which LINE shows under
Settings → Chats → Download folder. In a Wine prefix, that folder is your
Linux Downloads folder only if Wine linked the two. Most Wine builds do this
when they create a prefix, but some don't, and none do if the Linux folder
didn't exist yet.

`setup` and every `launch` check that Desktop, Documents, Downloads, Music,
Pictures and Videos in the prefix link to your Linux folders, including
translated names from `xdg-user-dirs`. If a real folder with files is in the
way, line-linux moves the files to your Linux folder first. It never
overwrites a file. If two files have the same name, it keeps the folder and
prints a warning that names it.

Windows marks each download with a hidden "downloaded from the internet"
stream. Linux file systems have no such streams, so Wine writes a visible
`file:Zone.Identifier` file next to each download. While LINE runs, the
session helper deletes these files as they appear in your Downloads folder,
when a downloaded file with the same name sits next to them. It leaves older
ones alone. Set `LINE_KEEP_ZONE_FILES=1` to keep them all.

### Paths

| What | Where |
|---|---|
| LINE program | `<prefix>/drive_c/users/$USER/AppData/Local/LINE/bin/current/` |
| Launcher, same path across updates | `<prefix>/…/LINE/bin/LineLauncher.exe` |
| LINE data | `<prefix>/…/LINE/Data/` |
| Downloads | your Linux Downloads folder, `C:\users\<you>\Downloads` in LINE |
| Pasted-image copies | `~/.cache/line-linux/captures/` |
| Saved prefix choice | `~/.config/line-linux/config` |
| Signing key, font links, state | `~/.local/share/line-linux/` |
| App-grid entry | `~/.local/share/applications/line-messenger.desktop` |

`desktop` also turns off Wine's menu builder in the LINE prefix. Otherwise
Wine adds a duplicate LINE entry under `wine/Programs/LINE` each time LINE
updates.

## Repository layout

- `install.sh` installs packages, the tool and LINE in one step.
- `bin/line-linux` is the command-line tool, written in bash.
- `lib/hide-shadows.py` hides LINE's shadow windows while LINE runs.
- `lib/session-helper.py` runs with LINE, offers copied images as files and
  removes the marker files from Downloads.
- `lib/capture-shortcut.py` binds the capture key in every keyboard layout.
- `lib/portal-screenshot.py` takes a screenshot through the XDG portal, for
  the fallback command.
- `config/signing.cnf` sets the name on the signing certificate.

## Compatibility

| Setup | Status |
|---|---|
| Ubuntu 26.10, GNOME 51 on Wayland, Wine 11.0 from WineHQ, LINE 26.6.0.4004 | Tested: install through the official installer, login, chats, Thai text, emoji, settings, window shadows, Super+Shift+S with English and Thai layouts, pasting a screenshot into a chat |
| Ubuntu 24.04, Debian 13, Fedora 43, Arch, openSUSE Tumbleweed | Not tested. `install.sh --dry-run` found all official packages; AUR packages weren't checked |
| Older Wine, such as 9.0 in Ubuntu 24.04 | Not tested. `deps` warns about Wine older than 10 |
| KDE Plasma, Xfce and other desktops | Not tested. The capture key needs GNOME Shell. Use your desktop's screenshot tool with copy to clipboard instead |
| X11 sessions | Not tested. LINE's own screenshot button may work there |
| LINE's own screenshot button | Doesn't work on Wayland, see [Screen capture](#screen-capture) |
| Downloading a file from a chat with the current folder and marker-file handling | Not confirmed yet |
| Voice and video calls | Not tested |

Reports from other setups are welcome. Please include the output of
`line-linux doctor`. It shows paths relative to your home folder, but check
it before posting.

## License

[MIT](LICENSE)
