"""Commands of the AYON menu, collected from `api/ui/windows/*.py`.

Every module in `windows` defines `COMMANDS`, a list of `Command`s. New
windows only need a new module, the menu and plug-in registration pick it
up. Menu order is (section order, command order).
"""
import importlib
import logging
import pkgutil

import c4d

log = logging.getLogger(__name__)

# (key, submenu title or None, order)
SECTIONS = [
    ("context", None, 0),
    ("main", None, 10),
    ("workfiles", None, 20),
    ("tools", "Tools", 30),
    ("classic", "Classic Windows", 40),
]


class Command:
    """A command plug-in of the AYON menu.

    Args:
        plugin_id (int): Plug-in id, see `ids`.
        label (str): Menu / command name.
        execute (callable): Called without arguments.
        icon (c4d.bitmaps.BaseBitmap): Command icon.
        section (str): Menu section key, None = registered but not in menu.
        order (int): Order within the section.
        dialog (type): `AyonDialog` subclass, enables layout restore.
        help (str): Status bar help.
        separator_before (bool): Menu separator before this command.
    """

    def __init__(
        self, plugin_id, label, execute=None, icon=None, section="main",
        order=50, dialog=None, help=None, separator_before=False,
    ):
        self.plugin_id = plugin_id
        self.label = label
        self.execute = execute or (dialog.open if dialog else None)
        self.icon = icon
        self.section = section
        self.order = order
        self.dialog = dialog
        self.help = help
        self.separator_before = separator_before


class _CommandData(c4d.plugins.CommandData):
    def __init__(self, command):
        super().__init__()
        self.command = command

    def Execute(self, doc):
        try:
            result = self.command.execute()
        except Exception:
            log.error(f"{self.command.label} failed", exc_info=True)
            return False
        return result is not False

    def RestoreLayout(self, sec_ref):
        if self.command.dialog is None:
            return False
        return self.command.dialog.restore(sec_ref)


def discover():
    """All `Command`s of the modules in `api/ui/windows`."""
    from . import windows

    commands = []
    for module_info in sorted(
        pkgutil.iter_modules(windows.__path__), key=lambda m: m.name
    ):
        name = f"{windows.__name__}.{module_info.name}"
        try:
            module = importlib.import_module(name)
        except Exception:
            log.error(f"Failed to import {name}", exc_info=True)
            continue
        commands.extend(getattr(module, "COMMANDS", []))

    by_id = {}
    for command in commands:
        if command.plugin_id in by_id:
            log.error(
                f"Duplicate plug-in id {command.plugin_id}: "
                f"'{command.label}' and '{by_id[command.plugin_id].label}'")
            continue
        by_id[command.plugin_id] = command
    return list(by_id.values())


def register(commands):
    for command in commands:
        c4d.plugins.RegisterCommandPlugin(
            id=command.plugin_id,
            str=command.label,
            info=c4d.PLUGINFLAG_HIDEPLUGINMENU,
            icon=command.icon,
            help=command.help or "",
            dat=_CommandData(command),
        )


def build_menu(commands):
    """Menu container with sections, separators and submenus."""
    separator = 2  # MENURESOURCE_SEPERATOR / _SEPARATOR, renamed by Maxon

    menu = c4d.BaseContainer()
    menu.InsData(c4d.MENURESOURCE_SUBTITLE, "AYON")
    first = True
    for key, title, _ in sorted(SECTIONS, key=lambda s: s[2]):
        section = sorted(
            (c for c in commands if c.section == key), key=lambda c: c.order)
        if not section:
            continue
        if not first:
            menu.InsData(separator, True)
        first = False

        target = menu
        if title:
            target = c4d.BaseContainer()
            target.InsData(c4d.MENURESOURCE_SUBTITLE, title)
        for index, command in enumerate(section):
            if command.separator_before and index:
                target.InsData(separator, True)
            target.InsData(
                c4d.MENURESOURCE_COMMAND, f"PLUGIN_CMD_{command.plugin_id}")
        if title:
            menu.InsData(c4d.MENURESOURCE_SUBMENU, target)
    return menu
