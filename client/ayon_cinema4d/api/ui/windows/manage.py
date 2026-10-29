"""Manage (scene inventory), opens the Qt tool until the native window."""
from ayon_cinema4d.api.ui import ids, widgets
from ayon_cinema4d.api.ui.registry import Command

from .classic import show_scene_inventory

COMMANDS = [
    Command(
        ids.MANAGE, "Manage...", show_scene_inventory,
        icon=widgets.ayon_icon("inventory"), order=30,
    ),
]
