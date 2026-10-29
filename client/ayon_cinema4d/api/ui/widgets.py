"""Drawing and popup helpers shared by the native windows."""
import os
import hashlib

import c4d

# Colors (0..1) in the AYON palette
GREEN = c4d.Vector(0.30, 0.69, 0.38)
ORANGE = c4d.Vector(0.93, 0.58, 0.20)
RED = c4d.Vector(0.86, 0.30, 0.30)
BLUE = c4d.Vector(0.36, 0.72, 0.96)
GRAY = c4d.Vector(0.45, 0.45, 0.47)

_PALETTE = [
    c4d.Vector(0.36, 0.72, 0.96), c4d.Vector(0.55, 0.80, 0.39),
    c4d.Vector(0.96, 0.69, 0.30), c4d.Vector(0.80, 0.49, 0.93),
    c4d.Vector(0.94, 0.47, 0.55), c4d.Vector(0.40, 0.84, 0.78),
    c4d.Vector(0.85, 0.80, 0.38), c4d.Vector(0.62, 0.62, 0.93),
]

_bitmaps = {}


def ui_color(name, fallback):
    """Cinema 4D interface color id by name, `fallback` Vector if missing."""
    return getattr(c4d, name, None) or fallback


TEXT = ui_color("COLOR_TEXT", c4d.Vector(0.85))
TEXT_DIM = ui_color("COLOR_TEXT_DISABLED", c4d.Vector(0.5))
TEXT_SELECTED = ui_color("COLOR_TEXT_SELECTED", c4d.Vector(1.0))
SELECTION = c4d.Vector(0.22, 0.40, 0.58)
CARD = c4d.Vector(0.20)
LINE = c4d.Vector(0.14)


def color_for(name):
    """Stable palette color for a name (product type, folder type...)."""
    digest = hashlib.md5((name or "").encode("utf-8")).digest()
    return _PALETTE[digest[0] % len(_PALETTE)]


def mix(a, b, t):
    """Blend color `a` towards `b` by `t` (0..1)."""
    return a + (b - a) * t


def tint(name, amount=0.18, base=None):
    """Product-type color toned down into the background."""
    base = base if base is not None else c4d.Vector(0.19)
    return mix(base, color_for(name), amount)


def contrast_text(color):
    luminance = color.x * 0.299 + color.y * 0.587 + color.z * 0.114
    return c4d.Vector(0.08) if luminance > 0.55 else c4d.Vector(1.0)


def elide(area, text, width):
    """Shorten `text` with '...' to fit `width` pixels of `area`."""
    if width <= 0:
        return ""
    if area.DrawGetTextWidth(text) <= width:
        return text
    while text and area.DrawGetTextWidth(text + "...") > width:
        text = text[:-1]
    return text + "..." if text else ""


def bitmap(path):
    """Cached bitmap from a file, None if missing."""
    if path in _bitmaps:
        return _bitmaps[path]
    bmp = None
    if path and os.path.exists(path):
        bmp = c4d.bitmaps.BaseBitmap()
        result = bmp.InitWith(path)  # (result, ismovie)
        if isinstance(result, tuple):
            result = result[0]
        if result != c4d.IMAGERESULT_OK:
            bmp = None
    _bitmaps[path] = bmp
    return bmp


def ayon_icon(name):
    """Icon from the ayon-core resources ('circle_green', 'loader'...)."""
    from ayon_core.resources import get_resource
    return bitmap(get_resource("icons", f"{name}.png"))


def popup(entries):
    """Show a popup menu at the mouse and run the chosen callback.

    Args:
        entries (list): (label, callback) tuples, (label, [entries]) for a
            submenu, (label, None) for a disabled entry, None for a separator.
            A label starting with '*' is shown checked.
    """
    callbacks = {}
    next_id = [c4d.FIRST_POPUP_ID]

    def fill(menu, items):
        for entry in items:
            if entry is None:
                menu.InsData(0, "")
                continue
            label, target = entry
            flags = ""
            if label.startswith("*"):
                label, flags = label[1:], "&c&"
            if isinstance(target, list):
                sub = c4d.BaseContainer()
                sub.InsData(1, label)
                fill(sub, target)
                menu.SetContainer(next_id[0], sub)
                next_id[0] += 1
                continue
            if target is None:
                flags += "&d&"
            menu.InsData(next_id[0], label + flags)
            callbacks[next_id[0]] = target
            next_id[0] += 1

    menu = c4d.BaseContainer()
    fill(menu, entries)
    result = c4d.gui.ShowPopupDialog(
        cd=None, bc=menu, x=c4d.MOUSEPOS, y=c4d.MOUSEPOS)
    callback = callbacks.get(result)
    if callback:
        callback()
    return result


def is_playing():
    """Animation playback runs (skip scene scans then)."""
    return c4d.CheckIsRunning(c4d.CHECKISRUNNING_ANIMATIONRUNNING)


def confirm(text):
    return c4d.gui.QuestionDialog(text)


def open_in_explorer(path):
    """Show a file or folder in the OS file browser."""
    if not path:
        return
    if os.path.isfile(path):
        c4d.storage.ShowInFinder(path, False)
    elif os.path.isdir(path):
        c4d.storage.ShowInFinder(path, True)


def format_time(value):
    """Server timestamp or epoch -> local 'YYYY-MM-DD HH:MM'."""
    from datetime import datetime
    try:
        if isinstance(value, (int, float)):
            stamp = datetime.fromtimestamp(value)
        else:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            stamp = stamp.astimezone()
        return stamp.strftime("%Y-%m-%d %H:%M")
    except (AttributeError, ValueError, TypeError, OSError):
        return value or ""
