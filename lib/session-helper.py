"""Background helpers that run alongside LINE under Wine.

  python3 session-helper.py --downloads ~/Downloads

Clipboard images: under Wine, an image copied on Linux (for example by GNOME's screenshot tool)
doesn't paste into LINE: Wine passes image/png on under a broken format name,
and LINE ignores a plain bitmap. LINE does accept a copied *file*. So while
LINE runs, this helper watches the clipboard and, when it holds an image but
no file, saves the image under ~/.cache/line-linux/captures and offers it as
both image/png (other apps keep pasting it as an image) and text/uri-list
(Wine turns that into a Windows file drop, which LINE pastes as an image).

Downloads: when a Windows program saves a download, it marks it as coming
from the internet with an NTFS stream, "file:Zone.Identifier". Wine has no
streams on Linux file systems and writes a separate visible file with that
name next to every download. Marker files that appear in the Downloads folder
while LINE runs are deleted; older ones are left alone. Leave out
--downloads to keep them.

Exits once LINE has quit and the clipboard no longer holds our content.
"""
import argparse
import fcntl
import os
import sys
import tempfile
import time

os.environ["GDK_BACKEND"] = "x11"  # Wine reads the X11 clipboard

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                     "line-linux", "captures")
KEEP_SECONDS = 24 * 3600


def line_running():
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    if b"\\LINE.exe" in f.read().split(b"\0")[0]:
                        return True
            except OSError:
                pass
    return False


def open_lock(name):
    """Open a lock file in a private per-user folder, never through a symlink."""
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "line-linux")
    os.makedirs(base, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(base, name), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    return os.fdopen(fd, "r+")


def remove_old_captures():
    """Delete this helper's own saved images once they are a day old."""
    if not os.path.isdir(CACHE):
        return True
    cutoff = time.time() - KEEP_SECONDS
    for name in os.listdir(CACHE):
        if not (name.startswith("capture-") and name.endswith(".png")):
            continue
        path = os.path.join(CACHE, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass
    return True  # keep the hourly GLib timer


class ClipboardBridge:
    def __init__(self, clipboard):
        self.clipboard = clipboard
        clipboard.connect("changed", self.on_changed)
        self.on_changed(clipboard)

    def on_changed(self, clipboard):
        if clipboard.is_local():
            return
        formats = clipboard.get_formats()
        if formats.contain_mime_type("text/uri-list") or not formats.contain_mime_type("image/png"):
            return
        clipboard.read_async(["image/png"], GLib.PRIORITY_DEFAULT, None, self.on_read)

    def on_read(self, clipboard, result):
        try:
            stream, _mime = clipboard.read_finish(result)
        except GLib.Error:
            return
        out = Gio.MemoryOutputStream.new_resizable()
        flags = Gio.OutputStreamSpliceFlags.CLOSE_SOURCE | Gio.OutputStreamSpliceFlags.CLOSE_TARGET
        out.splice_async(stream, flags, GLib.PRIORITY_DEFAULT, None, self.on_spliced)

    def on_spliced(self, out, result):
        try:
            out.splice_finish(result)
        except GLib.Error:
            return
        png = out.steal_as_bytes()
        if not png.get_size():
            return
        # Copied images can be private: keep them readable only by the user.
        os.makedirs(CACHE, mode=0o700, exist_ok=True)
        os.chmod(CACHE, 0o700)
        fd, path = tempfile.mkstemp(prefix=time.strftime("capture-%Y%m%d-%H%M%S-"), suffix=".png", dir=CACHE)
        with os.fdopen(fd, "wb") as f:
            f.write(png.get_data())
        uri = GLib.Bytes.new((GLib.filename_to_uri(path, None) + "\r\n").encode())
        self.clipboard.set_content(Gdk.ContentProvider.new_union([
            Gdk.ContentProvider.new_for_bytes("image/png", png),
            Gdk.ContentProvider.new_for_bytes("text/uri-list", uri),
        ]))


class DownloadTidy:
    SUFFIX = ":Zone.Identifier"

    def __init__(self, folder):
        self.folder = folder
        self.monitor = Gio.File.new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.monitor.connect("changed", self.on_changed)

    def on_changed(self, _monitor, file, other, event):
        if event == Gio.FileMonitorEvent.RENAMED and other is not None:
            file = other
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.MOVED_IN,
                     Gio.FileMonitorEvent.RENAMED):
            self.tidy(file.get_path())

    def tidy(self, path):
        if not path or not path.endswith(self.SUFFIX):
            return
        if not os.path.exists(path[: -len(self.SUFFIX)]):
            return  # not a marker next to a downloaded file
        try:
            if os.path.getsize(path) <= 4096:
                with open(path, "rb") as f:
                    if f.read(64).lstrip(b"\xef\xbb\xbf").startswith(b"[ZoneTransfer]"):
                        os.remove(path)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--downloads", help="folder where LINE saves downloads")
    args = parser.parse_args()
    Gtk.init()
    display = Gdk.Display.get_default()
    if display is None:
        sys.exit("cannot open X display")

    with open_lock("line-linux-session.lock") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return  # another bridge is already running
        bridge = ClipboardBridge(display.get_clipboard())
        tidy = None  # keep the directory monitor alive
        if args.downloads and os.path.isdir(args.downloads):
            tidy = DownloadTidy(args.downloads)
        loop = GLib.MainLoop()
        started = last_seen = time.monotonic()

        def check():
            nonlocal last_seen
            if line_running():
                last_seen = time.monotonic()
            elif (time.monotonic() - max(started + 60, last_seen) > 10
                  and not bridge.clipboard.is_local()):
                loop.quit()
            return True

        remove_old_captures()
        GLib.timeout_add_seconds(3600, remove_old_captures)
        GLib.timeout_add_seconds(5, check)
        loop.run()
        del tidy


if __name__ == "__main__":
    main()
