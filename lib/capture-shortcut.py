"""Bind or unbind a key combination to GNOME Shell's screenshot tool.

GNOME matches a letter shortcut against the character the key produces in
the active keyboard layout. With a non-Latin layout active (Thai, Russian,
...), the S key doesn't produce "s", so <Shift><Super>s does nothing. This
also binds the same physical key as it appears in every configured layout,
for example <Shift><Super>Thai_hohip.

  python3 capture-shortcut.py add '<Shift><Super>s'
  python3 capture-shortcut.py remove '<Shift><Super>s'
  python3 capture-shortcut.py show
"""
import ctypes
import ctypes.util
import re
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

SCHEMA, KEY = "org.gnome.shell.keybindings", "show-screenshot-ui"

xkb = ctypes.CDLL(ctypes.util.find_library("xkbcommon") or "libxkbcommon.so.0")


class RuleNames(ctypes.Structure):
    _fields_ = [(n, ctypes.c_char_p) for n in ("rules", "model", "layout", "variant", "options")]


xkb.xkb_context_new.restype = ctypes.c_void_p
xkb.xkb_keymap_new_from_names.restype = ctypes.c_void_p
xkb.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(RuleNames), ctypes.c_int]
xkb.xkb_keymap_unref.argtypes = [ctypes.c_void_p]
xkb.xkb_keymap_key_get_syms_by_level.argtypes = [
    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
    ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32))]
xkb.xkb_keysym_get_name.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
CONTEXT = xkb.xkb_context_new(0)


def base_keysyms(layout):
    """Map keycode -> name of the keysym on its first level, for one layout."""
    name, _, variant = layout.partition("+")
    names = RuleNames(None, None, name.encode(), variant.encode() or None, None)
    keymap = xkb.xkb_keymap_new_from_names(CONTEXT, ctypes.byref(names), 0)
    if not keymap:
        return {}
    result, buf = {}, ctypes.create_string_buffer(64)
    for keycode in range(8, 256):
        syms = ctypes.POINTER(ctypes.c_uint32)()
        if xkb.xkb_keymap_key_get_syms_by_level(keymap, keycode, 0, 0, ctypes.byref(syms)) > 0:
            xkb.xkb_keysym_get_name(syms[0], buf, len(buf))
            result[keycode] = buf.value.decode()
    xkb.xkb_keymap_unref(keymap)
    return result


def configured_layouts():
    sources = Gio.Settings.new("org.gnome.desktop.input-sources").get_value("sources").unpack()
    return [layout for kind, layout in sources if kind == "xkb"]


def variants(accel):
    """The accelerator plus the same physical key in every configured layout."""
    match = re.fullmatch(r"((?:<[^>]+>)*)(\w+)", accel)
    if not match:
        return [accel]
    mods, key = match.groups()
    us = base_keysyms("us")
    keycodes = [code for code, sym in us.items() if sym == key]
    result = [accel]
    for layout in configured_layouts():
        syms = base_keysyms(layout)
        for code in keycodes:
            sym = syms.get(code)
            if sym and mods + sym not in result:
                result.append(mods + sym)
    return result


def main():
    settings = Gio.Settings.new(SCHEMA)
    current = list(settings.get_strv(KEY))
    action = sys.argv[1] if len(sys.argv) > 1 else "show"
    if action == "show":
        print(", ".join(current) or "none")
        return
    if action not in ("add", "remove") or len(sys.argv) != 3:
        sys.exit(__doc__)
    wanted = variants(sys.argv[2])
    if action == "add":
        updated = current + [a for a in wanted if a not in current]
    else:
        updated = [a for a in current if a not in wanted]
    if updated != current:
        settings.set_strv(KEY, updated)
        Gio.Settings.sync()
    print(", ".join(updated) or "none")


if __name__ == "__main__":
    main()
