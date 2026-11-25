"""Make LINE's drop-shadow windows invisible while LINE runs under Wine.

LINE draws the shadow around each of its windows with eight thin, untitled
ARGB popup windows. Wine maps most of them as override-redirect X windows,
which GNOME keeps above every normal window, and some as separate dialogs, so
after switching apps the shadows stay on screen as a dark or transparent
frame over the other app. The same windows are LINE's resize handles: LINE
shows the resize cursor over them and resizes the window when they are
dragged.

A shadow window is recognized by where it is: an untitled 32-bit LINE window,
at most MAX_THICKNESS thick, lying along the outside edge of a titled LINE
window without overlapping it. Tooltips and menus don't match. This watcher
sets each one's opacity to 0, so it is never drawn. While its LINE window is
the active window, a shadow keeps its normal shape so it can be dragged to
resize. Otherwise it gets an empty X shape, so clicks pass through to
whatever app is underneath. The watcher re-applies this when the active
window changes or Wine changes the opacity or shape. The windows still exist,
so Wine and LINE are unaffected.

On Wayland the watcher can also replace LINE's blank screenshot overlay
with the desktop picker. It only redirects LINE's borderless, always-on-top,
fullscreen capture window, not ordinary LINE windows.

  python3 hide-shadows.py          watch until LINE exits
  python3 hide-shadows.py --once   hide current shadows and exit
"""
import argparse
import ctypes
import ctypes.util
import fcntl
import os
import select
import subprocess
import sys
import time

MAX_THICKNESS = 40          # main windows use 11 px shadows, dialogs 20 px
MAX_FRAME_DEPTH = 3         # levels below the root to look for reparented windows

x = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
xext = ctypes.CDLL(ctypes.util.find_library("Xext") or "libXext.so.6")

Display = ctypes.c_void_p
Window = ctypes.c_ulong


class XWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int), ("y", ctypes.c_int),
        ("width", ctypes.c_int), ("height", ctypes.c_int),
        ("border_width", ctypes.c_int), ("depth", ctypes.c_int),
        ("visual", ctypes.c_void_p), ("root", Window),
        ("class_", ctypes.c_int), ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong), ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int), ("colormap", ctypes.c_ulong),
        ("map_installed", ctypes.c_int), ("map_state", ctypes.c_int),
        ("all_event_masks", ctypes.c_long), ("your_event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p),
    ]


class XClassHint(ctypes.Structure):
    _fields_ = [("res_name", ctypes.c_void_p), ("res_class", ctypes.c_void_p)]


class XMapEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int), ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int), ("display", Display),
        ("event", Window), ("window", Window), ("override_redirect", ctypes.c_int),
    ]


class XPropertyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int), ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int), ("display", Display),
        ("window", Window), ("atom", ctypes.c_ulong),
        ("time", ctypes.c_ulong), ("state", ctypes.c_int),
    ]


class XKeyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int), ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int), ("display", Display),
        ("window", Window), ("root", Window), ("subwindow", Window),
        ("time", ctypes.c_ulong),
        ("x", ctypes.c_int), ("y", ctypes.c_int),
        ("x_root", ctypes.c_int), ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint), ("keycode", ctypes.c_uint),
        ("same_screen", ctypes.c_int),
    ]


class XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("xmap", XMapEvent), ("xproperty", XPropertyEvent),
                ("xkey", XKeyEvent), ("pad", ctypes.c_long * 24)]


ErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, Display, ctypes.c_void_p)
x.XOpenDisplay.restype = Display
x.XDefaultRootWindow.restype = Window
x.XDefaultRootWindow.argtypes = [Display]
x.XGetWindowAttributes.argtypes = [Display, Window, ctypes.POINTER(XWindowAttributes)]
x.XGetClassHint.argtypes = [Display, Window, ctypes.POINTER(XClassHint)]
x.XQueryTree.argtypes = [Display, Window, ctypes.POINTER(Window), ctypes.POINTER(Window),
                         ctypes.POINTER(ctypes.POINTER(Window)), ctypes.POINTER(ctypes.c_uint)]
x.XSelectInput.argtypes = [Display, Window, ctypes.c_long]
x.XNextEvent.argtypes = [Display, ctypes.POINTER(XEvent)]
x.XPending.argtypes = [Display]
x.XKeysymToKeycode.argtypes = [Display, ctypes.c_ulong]
x.XKeysymToKeycode.restype = ctypes.c_ubyte
x.XSendEvent.argtypes = [Display, Window, ctypes.c_int, ctypes.c_long, ctypes.POINTER(XEvent)]
x.XConnectionNumber.argtypes = [Display]
x.XFlush.argtypes = [Display]
x.XFree.argtypes = [ctypes.c_void_p]
x.XSetErrorHandler.argtypes = [ErrorHandler]
xext.XShapeCombineRectangles.argtypes = [Display, Window, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
xext.XShapeCombineMask.argtypes = [Display, Window, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_ulong, ctypes.c_int]

SHAPE_BOUNDING, SHAPE_INPUT, SHAPE_SET = 0, 2, 0
SHAPE_NOTIFY_MASK = 1
STRUCTURE_NOTIFY = 1 << 17
SUBSTRUCTURE_NOTIFY = 1 << 19
PROPERTY_CHANGE = 1 << 22
UNMAP_NOTIFY = 18
MAP_NOTIFY = 19
CONFIGURE_NOTIFY = 22
PROPERTY_NOTIFY = 28
KEY_PRESS, KEY_RELEASE = 2, 3
KEY_PRESS_MASK, KEY_RELEASE_MASK = 1, 2
CONTROL_MASK = 4
XK_ESCAPE, XK_RETURN, XK_CONTROL_L = 0xFF1B, 0xFF0D, 0xFFE3
ANY_PROPERTY_TYPE = 0
XA_ATOM = 4
XA_CARDINAL = 6
XA_STRING = 31
XA_WINDOW = 33
XA_WM_NAME = 39

x.XInternAtom.restype = ctypes.c_ulong
x.XInternAtom.argtypes = [Display, ctypes.c_char_p, ctypes.c_int]
x.XChangeProperty.argtypes = [Display, Window, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int,
                              ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
x.XGetWindowProperty.argtypes = [Display, Window, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
                                 ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                 ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
                                 ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p)]
xext.XShapeQueryExtension.argtypes = [Display, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
xext.XShapeSelectInput.argtypes = [Display, Window, ctypes.c_ulong]
# (display, window, bounding_shaped, x, y, w, h, clip_shaped, x, y, w, h)
xext.XShapeQueryExtents.argtypes = [Display, Window] + ([ctypes.POINTER(ctypes.c_int)] * 3
                                                       + [ctypes.POINTER(ctypes.c_uint)] * 2) * 2

# Windows can vanish between the event and our query; ignore those errors.
_ignore_errors = ErrorHandler(lambda d, e: 0)
x.XSetErrorHandler(_ignore_errors)


x.XTranslateCoordinates.argtypes = [Display, Window, Window, ctypes.c_int, ctypes.c_int,
                                    ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                    ctypes.POINTER(Window)]
IS_VIEWABLE = 2


def line_window(dpy, root, win):
    """Return (titled, depth, (x, y, w, h)) for a viewable LINE window, else None."""
    attrs = XWindowAttributes()
    if not x.XGetWindowAttributes(dpy, win, ctypes.byref(attrs)) or attrs.map_state != IS_VIEWABLE:
        return None
    hint = XClassHint()
    if not x.XGetClassHint(dpy, win, ctypes.byref(hint)):
        return None
    cls = ctypes.string_at(hint.res_class).lower() if hint.res_class else b""
    for ptr in (hint.res_name, hint.res_class):
        if ptr:
            x.XFree(ptr)
    if cls != b"line.exe":
        return None
    # Not XFetchName: it only reads STRING titles, and Wine stores a title
    # outside Latin-1, such as a Thai chat name, as COMPOUND_TEXT.
    titled = get_property(dpy, win, XA_WM_NAME, ANY_PROPERTY_TYPE)[0] > 0
    rx, ry, child = ctypes.c_int(), ctypes.c_int(), Window()
    x.XTranslateCoordinates(dpy, win, root, 0, 0, ctypes.byref(rx), ctypes.byref(ry), ctypes.byref(child))
    return titled, attrs.depth, (rx.value, ry.value, attrs.width, attrs.height)


def children(dpy, win):
    root_ret, parent = Window(), Window()
    kids, count = ctypes.POINTER(Window)(), ctypes.c_uint()
    if not x.XQueryTree(dpy, win, ctypes.byref(root_ret), ctypes.byref(parent),
                        ctypes.byref(kids), ctypes.byref(count)):
        return []
    result = [kids[i] for i in range(count.value)]
    if kids:
        x.XFree(kids)
    return result


def hugs(shadow, window):
    """True if `shadow` lies along the outside edge of `window`."""
    sx, sy, sw, sh = shadow
    wx, wy, ww, wh = window
    t = min(sw, sh)
    inside_band = wx - t <= sx and sx + sw <= wx + ww + t and wy - t <= sy and sy + sh <= wy + wh + t
    overlaps = sx < wx + ww and wx < sx + sw and sy < wy + wh and wy < sy + sh
    return inside_band and not overlaps


def get_property(dpy, win, atom, kind):
    """(item count, first item if 32-bit else None) of a window property.
    Reads at most one 32-bit unit, so an 8-bit property's count is capped
    at 4. The count is 0 if the property isn't set or has another type."""
    actual, fmt = ctypes.c_ulong(), ctypes.c_int()
    count, after, data = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
    x.XGetWindowProperty(dpy, win, atom, 0, 1, False, kind, ctypes.byref(actual),
                         ctypes.byref(fmt), ctypes.byref(count), ctypes.byref(after), ctypes.byref(data))
    value = None
    if data.value and count.value and fmt.value == 32:
        value = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[0]
    if data.value:
        x.XFree(data)
    return count.value, value


def prop32(dpy, win, atom, kind=XA_CARDINAL):
    """First value of a 32-bit property, or None if it isn't set."""
    return get_property(dpy, win, atom, kind)[1]


def active_window(dpy, root):
    return prop32(dpy, root, x.XInternAtom(dpy, b"_NET_ACTIVE_WINDOW", False), XA_WINDOW)


def shape_state(dpy, win):
    """'default' (no shape), 'empty', or 'other'."""
    shaped, bx, by, cx, cy = (ctypes.c_int() for _ in range(5))
    bw, bh, cw, ch = (ctypes.c_uint() for _ in range(4))
    cshaped = ctypes.c_int()
    xext.XShapeQueryExtents(dpy, win, ctypes.byref(shaped), ctypes.byref(bx), ctypes.byref(by),
                            ctypes.byref(bw), ctypes.byref(bh), ctypes.byref(cshaped),
                            ctypes.byref(cx), ctypes.byref(cy), ctypes.byref(cw), ctypes.byref(ch))
    if not shaped.value:
        return "default"
    return "empty" if bw.value == 0 and bh.value == 0 else "other"


def hide(dpy, win, clickable):
    """Make a shadow window invisible, and click-through unless `clickable`.
    Only writes what differs, so the change events it causes don't trigger
    it again."""
    atom = x.XInternAtom(dpy, b"_NET_WM_WINDOW_OPACITY", False)
    if prop32(dpy, win, atom) != 0:
        zero = ctypes.c_ulong(0)
        x.XChangeProperty(dpy, win, atom, XA_CARDINAL, 32, 0, ctypes.byref(zero), 1)
    # Both shapes change together; X clips the input shape to the bounding
    # one, so a clickable shadow needs both back to the full window.
    state = shape_state(dpy, win)
    for kind in (SHAPE_BOUNDING, SHAPE_INPUT):
        if clickable and state != "default":
            xext.XShapeCombineMask(dpy, win, kind, 0, 0, 0, SHAPE_SET)  # 0 = None: remove the shape
        elif not clickable and state != "empty":
            xext.XShapeCombineRectangles(dpy, win, kind, 0, 0, None, 0, SHAPE_SET, 0)
    # Hear about it if Wine changes the opacity or shape later.
    x.XSelectInput(dpy, win, PROPERTY_CHANGE)
    xext.XShapeSelectInput(dpy, win, SHAPE_NOTIFY_MASK)


class CaptureRedirect:
    """Wait for LINE to cancel its overlay before the portal takes a screenshot."""
    def __init__(self, dpy, root, command):
        self.dpy, self.root, self.command = dpy, root, command
        self.state_atom = x.XInternAtom(dpy, b"_NET_WM_STATE", False)
        self.dialog_states = {
            x.XInternAtom(dpy, b"_NET_WM_STATE_" + name, False)
            for name in (b"SKIP_TASKBAR", b"SKIP_PAGER")
        }
        self.capture_states = self.dialog_states | {
            x.XInternAtom(dpy, b"_NET_WM_STATE_" + name, False)
            for name in (b"ABOVE", b"FULLSCREEN")
        }
        self.window_type = x.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE", False)
        self.normal_type = x.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE_NORMAL", False)
        self.dialog_type = x.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE_DIALOG", False)
        self.transient = x.XInternAtom(dpy, b"WM_TRANSIENT_FOR", False)
        self.pid = x.XInternAtom(dpy, b"_NET_WM_PID", False)
        self.overlays = set()
        self.last_chat = self.origin = None
        self.dismissed_at = self.picker = self.deadline = None
        self.uri = b""
        self.waiting_for_prompt = False

    def read_property(self, win, atom, kind):
        actual, fmt = ctypes.c_ulong(), ctypes.c_int()
        count, after, data = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        x.XGetWindowProperty(self.dpy, win, atom, 0, 32, False, kind,
                             ctypes.byref(actual), ctypes.byref(fmt), ctypes.byref(count),
                             ctypes.byref(after), ctypes.byref(data))
        try:
            if not data.value or after.value:
                return ()
            if fmt.value == 32:
                return tuple(ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[:count.value])
            if fmt.value == 8:
                return ctypes.string_at(data, count.value)
            return ()
        finally:
            if data.value:
                x.XFree(data)

    def is_overlay(self, win):
        # Wine may set the fullscreen state after mapping the window.
        x.XSelectInput(self.dpy, win, PROPERTY_CHANGE | STRUCTURE_NOTIFY)
        states = self.read_property(win, self.state_atom, XA_ATOM)
        return (self.capture_states.issubset(states)
                and self.read_property(win, XA_WM_NAME, XA_STRING) == b"LINE")

    def is_chat(self, win):
        return (prop32(self.dpy, win, self.window_type, XA_ATOM) == self.normal_type
                and not self.dialog_states.intersection(self.read_property(win, self.state_atom, XA_ATOM)))

    def is_paste_prompt(self, win, origin, pid):
        if (win == origin or prop32(self.dpy, win, self.transient, XA_WINDOW) != origin
                or prop32(self.dpy, win, self.pid) != pid
                or prop32(self.dpy, win, self.window_type, XA_ATOM) != self.dialog_type):
            return False
        info = line_window(self.dpy, self.root, win)
        if not info:
            return False
        _, _, (_, _, width, height) = info
        # The Image/Text prompt is a 280 x 128 dialog before display scaling.
        # If a LINE update changes it, leave the choice to the user.
        return (abs(width / height - 280 / 128) < 0.05
                and self.dialog_states.issubset(self.read_property(win, self.state_atom, XA_ATOM))
                and self.read_property(win, XA_WM_NAME, XA_STRING) == b"LINE")

    def key(self, win, symbol, *, state=0, pressed=None):
        code = x.XKeysymToKeycode(self.dpy, symbol)
        if not code:
            return
        event = XEvent()
        event.xkey = XKeyEvent(display=self.dpy, window=win, root=self.root,
                               keycode=code, state=state, same_screen=True)
        if pressed is not False:
            event.xkey.type = KEY_PRESS
            x.XSendEvent(self.dpy, win, False, KEY_PRESS_MASK, ctypes.byref(event))
        if pressed is not True:
            event.xkey.type = KEY_RELEASE
            x.XSendEvent(self.dpy, win, False, KEY_RELEASE_MASK, ctypes.byref(event))
        x.XFlush(self.dpy)

    def update(self, overlays, chat):
        now = time.monotonic()
        if overlays and not self.overlays and not self.busy:
            win = chat or self.last_chat
            self.origin = (win, prop32(self.dpy, win, self.pid)) if win else None
            self.dismissed_at = now
        for win in overlays - self.overlays:
            # Escape goes to the capture window, never to the desktop.
            self.key(win, XK_ESCAPE)
        self.overlays = overlays
        if not overlays:
            self.last_chat = chat
            if self.dismissed_at is not None:
                if now - self.dismissed_at < 2:
                    self.picker = subprocess.Popen([self.command, "capture", "--for-chat"],
                                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
                self.dismissed_at = None

    @property
    def busy(self):
        return self.dismissed_at is not None or self.picker is not None or self.deadline is not None

    def paste_if_ready(self):
        now = time.monotonic()
        if self.dismissed_at is not None and now - self.dismissed_at >= 2:
            self.dismissed_at = None
        if self.picker is not None:
            status = self.picker.poll()
            if status is None:
                return
            self.uri = self.picker.communicate()[0].strip()
            self.picker = None
            if status == 0 and self.uri and self.origin and self.origin[1]:
                self.deadline = now + 2
                self.waiting_for_prompt = False
        if self.deadline is None:
            return
        if now >= self.deadline:
            self.deadline = None
            return

        origin, pid = self.origin
        win = active_window(self.dpy, self.root)
        if not win:
            return
        if self.waiting_for_prompt:
            # Enter in this specific dialog chooses Image. Never send Enter
            # to the composer: that would send the draft to the chat.
            if self.is_paste_prompt(win, origin, pid):
                self.key(win, XK_RETURN)
                self.deadline = None
        elif win == origin and prop32(self.dpy, win, self.pid) == pid:
            try:
                uri = subprocess.check_output(
                    ["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"],
                    stderr=subprocess.DEVNULL, timeout=0.2).strip()
            except (subprocess.SubprocessError, OSError):
                return
            if uri != self.uri or active_window(self.dpy, self.root) != origin:
                return
            self.key(win, XK_CONTROL_L, pressed=True)
            self.key(win, ord('v'), state=CONTROL_MASK)
            self.key(win, XK_CONTROL_L, state=CONTROL_MASK, pressed=False)
            self.waiting_for_prompt = True
            self.deadline = now + 1


def scan(dpy, root, *, shadows=True, capture=None):
    """Hide LINE shadows and find newly mapped capture overlays."""
    # Top-level windows, plus a few levels down: window managers reparent
    # titled windows into frames, GNOME's one level deep and KWin's two
    # (frame, then wrapper, then the client).
    windows, level = [], children(dpy, root)
    for _ in range(MAX_FRAME_DEPTH + 1):
        windows.extend(level)
        level = [kid for win in level for kid in children(dpy, win)]
    titled, candidates = [], []
    overlays = set()
    chat = None
    active = active_window(dpy, root) if shadows or capture else None
    for win in windows:
        info = line_window(dpy, root, win)
        if info is None:
            continue
        is_titled, depth, rect = info
        if is_titled:
            if shadows:
                titled.append((rect, win == active))
            if capture:
                if depth == 32 and capture.is_overlay(win):
                    overlays.add(win)
                elif win == active and capture.is_chat(win):
                    chat = win
        elif shadows and depth == 32 and min(rect[2], rect[3]) <= MAX_THICKNESS:
            candidates.append((win, rect))
    if capture:
        capture.update(overlays, chat)
    hidden = 0
    for win, rect in candidates:
        owners = [is_active for owner, is_active in titled if hugs(rect, owner)]
        if owners:
            # Resizable only while its window is active: an inactive LINE
            # window can be covered by other apps, and its shadows, which
            # stay on top, would then catch their clicks.
            hide(dpy, win, clickable=any(owners))
            hidden += 1
    x.XFlush(dpy)
    return hidden


def open_lock(name):
    """Open a lock file in a private per-user folder, never through a symlink."""
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "line-linux")
    os.makedirs(base, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(base, name), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    return os.fdopen(fd, "r+")


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="hide current shadows and exit")
    parser.add_argument("--keep-shadows", action="store_true", help="do not hide shadows")
    parser.add_argument("--capture-command", help="path to line-linux for opening the desktop picker")
    args = parser.parse_args()
    dpy = x.XOpenDisplay(None)
    if not dpy:
        sys.exit("cannot open X display")
    root = x.XDefaultRootWindow(dpy)
    if args.once:
        print(f"hid {scan(dpy, root)} shadow windows")
        return

    with open_lock("line-linux-shadows.lock") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return  # another watcher is already running
        capture = CaptureRedirect(dpy, root, args.capture_command) if args.capture_command else None
        watch(dpy, root, shadows=not args.keep_shadows, capture=capture)


def watch(dpy, root, *, shadows, capture):
    shape_event, shape_error = ctypes.c_int(), ctypes.c_int()
    xext.XShapeQueryExtension(dpy, ctypes.byref(shape_event), ctypes.byref(shape_error))
    x.XSelectInput(dpy, root, SUBSTRUCTURE_NOTIFY | PROPERTY_CHANGE)
    active_atom = x.XInternAtom(dpy, b"_NET_ACTIVE_WINDOW", False)
    scan(dpy, root, shadows=shadows, capture=capture)
    fd = x.XConnectionNumber(dpy)
    started = last_seen = time.monotonic()
    next_check = started + 5
    event = XEvent()
    while True:
        select.select([fd], [], [], 0.1 if capture and capture.busy else 5)
        changed = False
        while x.XPending(dpy):
            x.XNextEvent(dpy, ctypes.byref(event))
            if event.type == PROPERTY_NOTIFY and event.xproperty.window == root:
                # The root has many busy properties; only focus matters.
                changed |= event.xproperty.atom == active_atom
            else:
                changed |= event.type in (MAP_NOTIFY, CONFIGURE_NOTIFY, PROPERTY_NOTIFY, shape_event.value)
                changed |= capture is not None and event.type == UNMAP_NOTIFY
        if changed:
            # A shadow can appear before its window, so rescan once per batch.
            scan(dpy, root, shadows=shadows, capture=capture)
        if capture and capture.busy:
            capture.paste_if_ready()
        now = time.monotonic()
        if now >= next_check:
            # Allow time for LineLauncher to start LINE.exe, then exit with it.
            next_check = now + 5
            if line_running():
                last_seen = now
            elif now - max(started + 60, last_seen) > 10:
                return

if __name__ == "__main__":
    main()
