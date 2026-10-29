"""Workfiles, opens the Qt tool until the native window."""
from ayon_cinema4d.api.ui import ids, widgets
from ayon_cinema4d.api.ui.registry import Command

from .classic import show_workfiles

COMMANDS = [
    Command(
        ids.WORKFILES, "Workfiles...", show_workfiles,
        icon=widgets.ayon_icon("workfiles"), section="workfiles", order=10,
    ),
]
