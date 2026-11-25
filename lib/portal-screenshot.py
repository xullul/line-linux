"""Take an interactive screenshot through the XDG desktop portal.

Prints the path of a private copy of the PNG, or exits 1 if the user
cancels. With --for-chat or --annotate, opens an editor before copying the
image. The caller deletes the copy unless --for-chat is set, in which case
the session helper ages it out of the capture cache. The portal's own file
stays put.
"""
import argparse
import hashlib
import io
import math
import os
import sys
import tempfile
import urllib.parse

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


def screenshot():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    token = f"line_linux_{os.getpid()}"
    sender = bus.get_unique_name()[1:].replace(".", "_")
    handle = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop = GLib.MainLoop()
    result = None

    def on_response(_conn, _sender, _path, _iface, _signal, params):
        nonlocal result
        result = params.unpack()
        loop.quit()

    subscription = bus.signal_subscribe(
        "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
        handle, None, Gio.DBusSignalFlags.NONE, on_response,
    )
    try:
        bus.call_sync(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot", "Screenshot",
            GLib.Variant("(sa{sv})", ("", {
                "handle_token": GLib.Variant("s", token),
                "interactive": GLib.Variant("b", True),
            })),
            None, Gio.DBusCallFlags.NONE, 10000, None,
        )
        timeout = GLib.timeout_add_seconds(120, loop.quit)
        loop.run()
        if result is not None:
            GLib.source_remove(timeout)
    finally:
        bus.signal_unsubscribe(subscription)
    if result is None or result[0] != 0 or not result[1].get("uri"):
        return None
    uri = urllib.parse.urlparse(result[1]["uri"])
    if uri.scheme != "file":
        return None
    with open(urllib.parse.unquote(uri.path), "rb") as image:
        return image.read()


def annotate(png):
    # Only the editor needs GTK and Pycairo. Drawing into a memory texture
    # avoids requiring the separate PyGObject-Cairo bridge.
    import cairo

    gi.require_version("Gdk", "4.0")
    gi.require_version("Graphene", "1.0")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, Graphene, Gtk

    image = cairo.ImageSurface.create_from_png(io.BytesIO(png))
    width, height = image.get_width(), image.get_height()
    colors = {"Red": (0.92, 0.14, 0.18), "Yellow": (1, 0.8, 0),
              "White": (1, 1, 1), "Black": (0.08, 0.08, 0.08)}
    tool_icons = {"Pen": "draw-freehand-symbolic", "Arrow": "draw-arrow-symbolic",
                  "Box": "draw-rectangle-symbolic"}
    marks, history = [], []
    full = crop = (0, 0, width, height)
    crop_mode = False
    result = None
    thickness = max(3, min(width, height) / 180)

    def paint(ctx):
        ctx.set_source_surface(image)
        ctx.paint()
        ctx.set_line_width(thickness)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        for tool, color, points in marks:
            ctx.set_source_rgb(*color)
            x, y = points[0]
            end_x, end_y = points[-1]
            if tool == "Box":
                ctx.rectangle(x, y, end_x - x, end_y - y)
            else:
                ctx.move_to(x, y)
                if tool == "Pen":
                    for point in points[1:] or [(x + 0.001, y)]:
                        ctx.line_to(*point)
                else:
                    ctx.line_to(end_x, end_y)
                    angle = math.atan2(end_y - y, end_x - x)
                    length = min(thickness * 5, math.hypot(end_x - x, end_y - y) / 2)
                    for offset in (-0.5, 0.5):
                        ctx.move_to(end_x, end_y)
                        ctx.line_to(end_x - length * math.cos(angle + offset),
                                    end_y - length * math.sin(angle + offset))
            ctx.stroke()

    def paint_crop(ctx, scale):
        if not crop_mode and crop == full:
            return
        left, top, right, bottom = crop
        ctx.save()
        ctx.rectangle(0, 0, width, height)
        ctx.rectangle(left, top, right - left, bottom - top)
        ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        ctx.set_source_rgba(0, 0, 0, 0.55)
        ctx.fill()
        ctx.set_source_rgb(0.21, 0.52, 0.89)
        ctx.set_line_width(2 / scale)
        ctx.rectangle(left, top, right - left, bottom - top)
        ctx.stroke()
        if crop_mode:
            size = min(8 / scale, width, height)
            for x in (left, (left + right) / 2, right):
                for y in (top, (top + bottom) / 2, bottom):
                    if x in (left, right) or y in (top, bottom):
                        ctx.rectangle(min(width - size, max(0, x - size / 2)),
                                      min(height - size, max(0, y - size / 2)), size, size)
            ctx.fill()
        ctx.restore()

    class Canvas(Gtk.Widget):
        __gtype_name__ = "LineCaptureCanvas"

        def geometry(self):
            w, h = self.get_width(), self.get_height()
            scale = min(w / width, h / height)
            return (w - width * scale) / 2, (h - height * scale) / 2, scale

        def do_snapshot(self, snapshot):
            x, y, scale = self.geometry()
            w, h = round(width * scale), round(height * scale)
            if w < 1 or h < 1:
                return
            preview = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            ctx = cairo.Context(preview)
            ctx.scale(w / width, h / height)
            paint(ctx)
            paint_crop(ctx, scale)
            preview.flush()
            pixel_format = (Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED if sys.byteorder == "little"
                            else Gdk.MemoryFormat.A8R8G8B8_PREMULTIPLIED)
            texture = Gdk.MemoryTexture.new(w, h, pixel_format, GLib.Bytes.new(preview.get_data()),
                                            preview.get_stride())
            snapshot.append_texture(texture, Graphene.Rect().init(x, y, w, h))

    def icon_label(icon, name):
        row = Gtk.Box(spacing=7)
        row.append(Gtk.Image.new_from_icon_name(icon))
        row.append(Gtk.Label(label=name, xalign=0))
        return row

    def palette_class(name):
        return f"capture-color-{name.lower()}"

    def selector_factory(icons=None):
        factory = Gtk.SignalListItemFactory()

        def setup(_factory, item):
            row = Gtk.Box(spacing=7)
            visual = (Gtk.Image() if icons is not None else
                      Gtk.Box(width_request=16, height_request=16, valign=Gtk.Align.CENTER))
            row.append(visual)
            row.append(Gtk.Label(xalign=0))
            item.set_child(row)

        def bind(_factory, item):
            name = item.get_item().get_string()
            row = item.get_child()
            visual = row.get_first_child()
            if icons is None:
                visual.set_css_classes(["capture-color-swatch", palette_class(name)])
            else:
                visual.set_from_icon_name(icons[name])
            row.get_last_child().set_text(name)

        factory.connect("setup", setup)
        factory.connect("bind", bind)
        return factory

    def style_color_selector(selector):
        styles = [".capture-color-swatch { border: 1px solid gray; border-radius: 3px; }"]
        for name, rgb in colors.items():
            bg = "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb)
            fg = "#ffffff" if name == "Black" else "#000000"
            css_class = palette_class(name)
            styles.append(
                f"dropdown.{css_class} > button {{ background-image: none; "
                f"background-color: {bg}; color: {fg}; text-shadow: none; }}"
                f".capture-color-swatch.{css_class} {{ background-color: {bg}; }}"
            )
        provider = Gtk.CssProvider()
        provider.load_from_data("\n".join(styles).encode())
        Gtk.StyleContext.add_provider_for_display(
            selector.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        def update(button, _property=None):
            for name in colors:
                button.remove_css_class(palette_class(name))
            button.add_css_class(palette_class(button.get_selected_item().get_string()))

        selector.connect("notify::selected", update)
        update(selector)

    def activate(app):
        window = Gtk.ApplicationWindow(application=app, title="Annotate LINE capture")
        window.set_default_size(900, 650)
        toolbar = Gtk.Box(spacing=8, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        tool = Gtk.DropDown.new_from_strings(list(tool_icons))
        tool.set_factory(selector_factory(tool_icons))
        tool.set_list_factory(selector_factory(tool_icons))
        tool.set_size_request(96, -1)
        tool.set_tooltip_text("Drawing tool")
        color = Gtk.DropDown.new_from_strings(list(colors))
        color.set_list_factory(selector_factory())
        color.set_size_request(86, -1)
        color.set_tooltip_text("Stroke color")
        style_color_selector(color)
        crop_button = Gtk.ToggleButton(child=icon_label("image-crop-symbolic", "Crop"))
        crop_button.update_property([Gtk.AccessibleProperty.LABEL], ["Crop"])
        crop_button.set_tooltip_text("Drag a new selection or resize it from an edge or corner")
        undo = Gtk.Button(label="Undo", sensitive=False)
        dimensions = Gtk.Label()
        spacer = Gtk.Box(hexpand=True)
        cancel = Gtk.Button(label="Cancel")
        accept = Gtk.Button(label="Use image")
        accept.add_css_class("suggested-action")
        for widget in (tool, color, crop_button, undo, dimensions, spacer, cancel, accept):
            toolbar.append(widget)
        canvas = Canvas(hexpand=True, vexpand=True)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        layout.append(toolbar)
        layout.append(canvas)
        window.set_child(layout)

        drag = Gtk.GestureDrag(button=1)
        canvas.add_controller(drag)
        active = False
        crop_drag = None

        def redraw():
            left, top, right, bottom = crop
            dimensions.set_text(f"{right - left} × {bottom - top}")
            undo.set_sensitive(bool(history))
            canvas.queue_draw()

        def toggle_crop(button):
            nonlocal crop_mode
            crop_mode = button.get_active()
            tool.set_sensitive(not crop_mode)
            color.set_sensitive(not crop_mode)
            redraw()

        def nearest_edge(point, lo, hi, tolerance):
            edge = -1 if abs(point - lo) <= abs(point - hi) else 1
            return edge if min(abs(point - lo), abs(point - hi)) <= tolerance else 0

        def begin(_drag, x, y):
            nonlocal active, crop_drag
            left, top, scale = canvas.geometry()
            if not scale or not (left <= x <= left + width * scale and top <= y <= top + height * scale):
                return
            start_x, start_y = (x - left) / scale, (y - top) / scale
            active = True
            if crop_mode:
                l, t, r, b = crop
                tolerance = 10 / scale
                ex = nearest_edge(start_x, l, r, tolerance) if t - tolerance <= start_y <= b + tolerance else 0
                ey = nearest_edge(start_y, t, b, tolerance) if l - tolerance <= start_x <= r + tolerance else 0
                crop_drag = (crop, ex, ey, start_x, start_y)
            else:
                name = tool.get_selected_item().get_string()
                rgb = colors[color.get_selected_item().get_string()]
                marks.append((name, rgb, [(start_x, start_y)]))
                history.append(("mark", None))
            redraw()

        def move(_drag, dx, dy):
            nonlocal crop
            if not active:
                return
            _, _, scale = canvas.geometry()
            if not scale:
                return
            dx, dy = dx / scale, dy / scale
            if crop_drag is not None:
                original, ex, ey, start_x, start_y = crop_drag
                l, t, r, b = original
                if ex or ey:
                    if ex < 0:
                        l = min(r - 1, max(0, round(l + dx)))
                    elif ex > 0:
                        r = max(l + 1, min(width, round(r + dx)))
                    if ey < 0:
                        t = min(b - 1, max(0, round(t + dy)))
                    elif ey > 0:
                        b = max(t + 1, min(height, round(b + dy)))
                else:
                    x, y = round(min(width, max(0, start_x + dx))), round(min(height, max(0, start_y + dy)))
                    l, r = sorted((round(start_x), x))
                    t, b = sorted((round(start_y), y))
                    if l == r or t == b:
                        return
                crop = (l, t, r, b)
            else:
                kind, _, points = marks[-1]
                start_x, start_y = points[0]
                point = (min(width, max(0, start_x + dx)), min(height, max(0, start_y + dy)))
                if kind == "Pen" or len(points) == 1:
                    points.append(point)
                else:
                    points[-1] = point
            redraw()

        def finish(gesture, dx, dy):
            nonlocal active, crop_drag
            move(gesture, dx, dy)
            if crop_drag is not None and crop != crop_drag[0]:
                history.append(("crop", crop_drag[0]))
            crop_drag = None
            active = False
            redraw()

        def undo_change(_button):
            nonlocal crop
            if history:
                kind, previous = history.pop()
                if kind == "crop":
                    crop = previous
                else:
                    marks.pop()
                redraw()

        def use_image(_button):
            nonlocal result
            if not marks and crop == full:
                result = png
            else:
                left, top, right, bottom = crop
                out = cairo.ImageSurface(cairo.FORMAT_ARGB32, right - left, bottom - top)
                ctx = cairo.Context(out)
                ctx.translate(-left, -top)
                paint(ctx)
                data = io.BytesIO()
                out.write_to_png(data)
                result = data.getvalue()
            window.close()

        drag.connect("drag-begin", begin)
        drag.connect("drag-update", move)
        drag.connect("drag-end", finish)
        crop_button.connect("toggled", toggle_crop)
        undo.connect("clicked", undo_change)
        cancel.connect("clicked", lambda _button: window.close())
        accept.connect("clicked", use_image)
        redraw()
        window.present()

    app = Gtk.Application(flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", activate)
    app.run([])
    return result


def save_copy(png, for_chat):
    cache = None
    if for_chat:
        cache = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                             "line-linux", "captures")
        os.makedirs(cache, mode=0o700, exist_ok=True)
        os.chmod(cache, 0o700)
    fd, path = tempfile.mkstemp(prefix="capture-", suffix=".png", dir=cache)
    with os.fdopen(fd, "wb") as out:
        out.write(png)
    if cache is not None:
        # GNOME also puts the PNG on the clipboard. Use the same destination
        # as the clipboard bridge so either writer can finish first.
        dst = os.path.join(cache, f"capture-{hashlib.sha256(png).hexdigest()}.png")
        os.replace(path, dst)
        path = dst
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--for-chat", action="store_true")
    parser.add_argument("--annotate", action="store_true")
    args = parser.parse_args()
    png = screenshot()
    if png is not None and (args.for_chat or args.annotate):
        png = annotate(png)
    if png is None:
        return 1
    print(save_copy(png, args.for_chat))
    return 0


if __name__ == "__main__":
    sys.exit(main())
