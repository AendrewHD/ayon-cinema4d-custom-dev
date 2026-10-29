"""Context label, Create and the Tools submenu."""
import c4d

from ayon_core.pipeline import get_current_folder_path, get_current_task_name
from ayon_core.resources import get_ayon_icon_filepath
from ayon_core.tools.utils import host_tools

from ayon_cinema4d.api import commands
from ayon_cinema4d.api.lib import get_main_window
from ayon_cinema4d.api.ui import ids, widgets
from ayon_cinema4d.api.ui.registry import Command


def context_label():
    return f"{get_current_folder_path()}, {get_current_task_name()}"


def _show_create():
    host_tools.show_publisher(tab="create", parent=get_main_window())


def _show_experimental_tools():
    host_tools.show_experimental_tools_dialog(get_main_window())


def _open_workfiles():
    c4d.CallCommand(ids.WORKFILES)


COMMANDS = [
    Command(
        ids.CONTEXT_LABEL, context_label(), _open_workfiles,
        icon=widgets.bitmap(get_ayon_icon_filepath()), section="context",
        help="Current AYON context, opens Workfiles",
    ),
    Command(
        ids.CREATE, "Create...", _show_create,
        icon=c4d.bitmaps.InitResourceBitmap(1018791), order=10,
    ),
    Command(
        ids.RESET_FRAME_RANGE, "Reset Frame Range", commands.reset_frame_range,
        icon=c4d.bitmaps.InitResourceBitmap(1038339), section="tools",
        order=10,
    ),
    Command(
        ids.RESET_RESOLUTION, "Reset Scene Resolution",
        commands.reset_resolution,
        icon=c4d.bitmaps.InitResourceBitmap(1040962), section="tools",
        order=20,
    ),
    Command(
        ids.RESET_COLORSPACE, "Reset Colorspace", commands.reset_colorspace,
        icon=c4d.bitmaps.InitResourceBitmap(440000312), section="tools",
        order=30,
    ),
    Command(
        ids.RESET_RENDER_SETTINGS, "Reset Render Settings",
        commands.reset_render_settings,
        icon=c4d.bitmaps.InitResourceBitmap(1024542), section="tools",
        order=40,
    ),
    Command(
        ids.EXPERIMENTAL_TOOLS, "Experimental Tools",
        _show_experimental_tools,
        icon=c4d.bitmaps.InitResourceBitmap(18186), section="tools",
        order=90, separator_before=True,
    ),
]
