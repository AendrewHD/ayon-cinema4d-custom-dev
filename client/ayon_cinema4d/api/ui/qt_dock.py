"""EXPERIMENTAL: show an AYON Qt tool inside a dockable Cinema 4D dialog.

Cinema 4D can only dock its own dialogs and the Python API exposes no
native handle of a dialog (Redshift's RenderView does this in C++). So the
dialog holds an empty user area as placeholder and the Qt window is laid
over it, following its position and size:

- Windows: the Qt window becomes a native child window (Win32 SetParent)
  of the Cinema 4D window under the placeholder. It moves with Cinema 4D
  and stays below floating Cinema 4D windows.
- Elsewhere, or if that fails: a frameless Qt tool window on top.

The tools are AYON's cached singletons: while docked, the Classic Windows
commands show the same (docked) window.

Known limits: a few frames of lag while resizing / dragging the layout,
the tool is hidden while its tab is not active (IsVisible), Qt popups and keyboard
focus may behave differently than in a normal window.
"""
import sys
import ctypes
import logging

import c4d
from qtpy import QtCore, QtWidgets

from ayon_core.tools.utils import host_tools

log = logging.getLogger(__name__)

TOOLS = [
    ("Browser", "libraryloader"),
    ("Scene Inventory", "sceneinventory"),
    ("Workfiles", "workfiles"),
    ("Publisher", "publisher"),
]
FOLLOW_INTERVAL = 60  # ms

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _GWL_STYLE = -16
    _WS_CHILD = 0x40000000
    _WS_POPUP = 0x80000000
    _WS_CAPTION = 0x00C00000
    _WS_THICKFRAME = 0x00040000
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020
    _GA_ROOT = 2

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    _user32.WindowFromPoint.argtypes = [_POINT]
    _user32.WindowFromPoint.restype = ctypes.c_void_p
    _user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    _user32.GetAncestor.restype = ctypes.c_void_p
    _user32.SetParent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _user32.SetParent.restype = ctypes.c_void_p
    _user32.ScreenToClient.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_POINT)]
    _user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _get_style = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _set_style = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _get_style.restype = ctypes.c_ssize_t
    _set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    _set_style.restype = ctypes.c_ssize_t


class QtHost:
    """Keeps a Qt window on top of a rectangle given in screen pixels."""

    def __init__(self):
        self.window = None
        self.tool_name = None
        self.native_parent = None
        self._visible = False

    def set_tool(self, tool_name):
        if tool_name == self.tool_name and self.window is not None:
            return
        self.release()
        window = host_tools.get_tool_by_name(tool_name)
        if window is None:
            raise RuntimeError(f"No AYON tool '{tool_name}'")
        self.tool_name = tool_name
        self.window = window
        window.setWindowFlags(
            QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        # get_tool_by_name doesn't refresh like the show_* functions do
        refresh = getattr(window, "refresh", None)
        if callable(refresh):
            refresh()

    def release(self):
        """Give the tool back as a normal window."""
        window, self.window = self.window, None
        if window is None:
            return
        if self.native_parent and sys.platform == "win32":
            hwnd = int(window.winId())
            _user32.SetParent(hwnd, None)
            style = _get_style(hwnd, _GWL_STYLE)
            _set_style(hwnd, _GWL_STYLE, (style & ~_WS_CHILD) | _WS_POPUP)
        self.native_parent = None
        window.setWindowFlags(QtCore.Qt.Window)
        window.hide()
        self._visible = False

    def follow(self, x, y, width, height):
        """Place the window at the screen rect, hide it for an empty rect."""
        window = self.window
        if window is None:
            return
        if width <= 4 or height <= 4:
            if self._visible:
                window.hide()
                self._visible = False
            return
        if not self._visible:
            # Find the Cinema 4D window under the placeholder before the
            # Qt window covers it
            if sys.platform == "win32" and self.native_parent is None:
                self._embed(x + width // 2, y + height // 2)
            window.show()
            self._visible = True

        if self.native_parent:
            point = _POINT(x, y)
            _user32.ScreenToClient(self.native_parent, ctypes.byref(point))
            _user32.SetWindowPos(
                int(window.winId()), None, point.x, point.y, width, height,
                _SWP_NOZORDER | _SWP_NOACTIVATE)
        else:
            ratio = window.devicePixelRatioF() or 1.0
            window.setGeometry(
                int(x / ratio), int(y / ratio),
                int(width / ratio), int(height / ratio))

    def _embed(self, center_x, center_y):
        """Make the Qt window a child of the Cinema 4D window at the point."""
        try:
            target = _user32.WindowFromPoint(_POINT(center_x, center_y))
            hwnd = int(self.window.winId())
            if not target or _user32.GetAncestor(target, _GA_ROOT) == \
                    _user32.GetAncestor(hwnd, _GA_ROOT):
                return
            style = _get_style(hwnd, _GWL_STYLE)
            style = (style | _WS_CHILD) & ~(
                _WS_POPUP | _WS_CAPTION | _WS_THICKFRAME)
            _set_style(hwnd, _GWL_STYLE, style)
            _user32.SetParent(hwnd, target)
            _user32.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED)
            self.native_parent = target
            log.info(f"AYON Qt dock: embedded into window {target:#x}")
        except Exception:
            log.warning("AYON Qt dock: native embedding failed, "
                        "using a floating window", exc_info=True)
            self.native_parent = None


class Placeholder(c4d.gui.GeUserArea):
    def DrawMsg(self, x1, y1, x2, y2, msg):
        self.DrawSetPen(c4d.COLOR_BG)
        self.DrawRectangle(x1, y1, x2, y2)

    def screen_rect(self):
        """(x, y, w, h) in screen pixels, empty while not mapped."""
        origin = self.Local2Screen()
        if not origin:
            return 0, 0, 0, 0
        return origin["x"], origin["y"], self.GetWidth(), self.GetHeight()
