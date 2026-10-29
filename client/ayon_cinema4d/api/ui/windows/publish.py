"""Publish, opens the Qt Publisher until the native window."""
from ayon_cinema4d.api.ui import ids
from ayon_cinema4d.api.ui.registry import Command

from .classic import show_publisher

COMMANDS = [
    Command(ids.PUBLISH, "Publish...", show_publisher, order=20),
]
