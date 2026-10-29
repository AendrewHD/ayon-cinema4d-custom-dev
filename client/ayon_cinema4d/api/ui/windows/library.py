"""Library, opens the Qt Browser until the native window."""
from ayon_cinema4d.api.ui import ids, widgets
from ayon_cinema4d.api.ui.registry import Command

from .classic import show_browser

COMMANDS = [
    Command(
        ids.LIBRARY, "Library...", show_browser,
        icon=widgets.ayon_icon("folder-favorite"), order=40,
    ),
    # Legacy "Load..." (same window), not in the menu, kept for layouts
    Command(
        ids.LOAD, "Load...", show_browser,
        icon=widgets.ayon_icon("loader"), section=None,
    ),
]
