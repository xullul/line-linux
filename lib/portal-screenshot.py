"""Take an interactive screenshot through the XDG desktop portal.

Prints the path of a private copy of the PNG (the caller deletes it) and
exits 0, or exits 1 if the user cancels or the portal doesn't answer within
two minutes. The portal's own file is left where it saved it. Works on Wayland, where X11 tools such as Wine can't see
other apps' windows.
"""
import os
import shutil
import sys
import tempfile
import urllib.parse

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

bus = Gio.bus_get_sync(Gio.BusType.SESSION)
token = f"line_linux_{os.getpid()}"
sender = bus.get_unique_name()[1:].replace(".", "_")
handle = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
loop = GLib.MainLoop()
result = {}


def on_response(_conn, _sender, _path, _iface, _signal, params):
    code, results = params.unpack()
    result["code"] = code
    result["uri"] = results.get("uri")
    loop.quit()


bus.signal_subscribe(
    "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
    handle, None, Gio.DBusSignalFlags.NONE, on_response,
)
bus.call_sync(
    "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
    "org.freedesktop.portal.Screenshot", "Screenshot",
    GLib.Variant("(sa{sv})", ("", {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", True),
    })),
    None, Gio.DBusCallFlags.NONE, 10000, None,
)
GLib.timeout_add_seconds(120, loop.quit)
loop.run()

if result.get("code") != 0 or not result.get("uri"):
    sys.exit(1)

uri = urllib.parse.urlparse(result["uri"])
if uri.scheme != "file":
    sys.exit(1)
src = urllib.parse.unquote(uri.path)
if not os.path.isfile(src):
    sys.exit(1)
fd, dst = tempfile.mkstemp(prefix="line-capture-", suffix=".png")
os.close(fd)
shutil.copyfile(src, dst)
print(dst)
