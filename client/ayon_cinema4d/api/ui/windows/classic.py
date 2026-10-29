"""The AYON Qt tools, for features the native windows don't cover."""
from qtpy import QtGui, QtWidgets

from ayon_core.tools.utils import host_tools

from ayon_cinema4d.api import browser_drag
from ayon_cinema4d.api.lib import get_main_window
from ayon_cinema4d.api.ui import ids, widgets
from ayon_cinema4d.api.ui.registry import Command


def center_on_first_show(window):
    """Center a tool on the screen under the mouse the first time.

    The tools have no Qt parent in Cinema 4D (`get_main_window` is None), so
    Qt would place them in the top left corner. Later opens keep the
    position the user left the window at.
    """
    if window is None or getattr(window, "_ayon_c4d_centered", False):
        return
    window._ayon_c4d_centered = True
    screen = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
    screen = screen or QtWidgets.QApplication.primaryScreen()
    if screen is None:
        return
    frame = window.frameGeometry()
    frame.moveCenter(screen.availableGeometry().center())
    window.move(frame.topLeft())


def _show(tool_name, **kwargs):
    """Show an AYON tool (singleton), centered on its first open."""
    window = host_tools.show_tool_by_name(
        tool_name, parent=get_main_window(), **kwargs)
    # Older ayon-core returns None from show_*
    window = window or host_tools.get_tool_by_name(tool_name)
    center_on_first_show(window)
    return window


def show_browser():
    # ayon-core >= 1.9.8: the Browser lists library projects itself
    window = _show("loader")
    browser_drag.install(window)
    return window


def show_scene_inventory():
    return _show("sceneinventory")


def show_workfiles():
    return _show("workfiles")


def show_publisher(tab="publish"):
    return _show("publisher", tab=tab)


COMMANDS = [
    Command(
        ids.CLASSIC_LIBRARY, "Browser (Qt)...", show_browser,
        icon=widgets.ayon_icon("folder-favorite"), section="classic",
        order=10,
    ),
    Command(
        ids.CLASSIC_MANAGE, "Scene Inventory (Qt)...", show_scene_inventory,
        icon=widgets.ayon_icon("inventory"), section="classic", order=20,
    ),
    Command(
        ids.CLASSIC_WORKFILES, "Workfiles (Qt)...", show_workfiles,
        icon=widgets.ayon_icon("workfiles"), section="classic", order=30,
    ),
    Command(
        ids.CLASSIC_PUBLISHER, "Publisher (Qt)...", show_publisher,
        section="classic", order=40,
    ),
]
