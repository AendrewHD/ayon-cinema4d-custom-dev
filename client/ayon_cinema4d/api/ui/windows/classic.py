"""The AYON Qt tools, for features the native windows don't cover."""
from ayon_core.tools.utils import host_tools

from ayon_cinema4d.api import browser_drag
from ayon_cinema4d.api.lib import get_main_window
from ayon_cinema4d.api.ui import ids, widgets
from ayon_cinema4d.api.ui.registry import Command


def show_browser():
    # ayon-core >= 1.9.8: the library loader is the regular Loader/Browser
    # with library projects in its project dropdown.
    window = host_tools.show_tool_by_name(
        "libraryloader", parent=get_main_window())
    browser_drag.install(window)


def show_scene_inventory():
    host_tools.show_scene_inventory(parent=get_main_window())


def show_workfiles():
    host_tools.show_workfiles(parent=get_main_window())


def show_publisher(tab="publish"):
    host_tools.show_publisher(tab=tab, parent=get_main_window())


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
