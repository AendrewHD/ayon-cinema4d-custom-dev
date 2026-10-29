import os
import sys
import logging

# For whatever reason Cinema4D does not add `PYTHONPATH` to `sys.path`
# It also seems that e.g. `C4DPYTHONPATH310` does not do that either?
for path in os.getenv("PYTHONPATH", "").split(os.pathsep):
    if path and path not in sys.path:
        sys.path.append(path)

# C4D doesn't ship with python3.dll which PySide is built against on Windows.
# Note: The python3.dll must match with the correct Python 3.x.y version
# Hence we need to force it to be an available .dll for Qt.
# C4D Hosts root
import ayon_cinema4d  # noqa: E402
AYON_C4D_ROOT = os.path.dirname(ayon_cinema4d.__file__)


def add_dll_directory(_path):
    # Python3.8+ uses os.add_dll_directory to load dlls
    # Previous version just add to the PATH env var
    try:
        os.add_dll_directory(_path)
    except AttributeError:
        norm_path = os.path.normpath(_path)
        os.environ["PATH"] = norm_path + os.pathsep + os.environ["PATH"]


if "win" in sys.platform:
    dll_dir = os.path.join(
        AYON_C4D_ROOT, "resource", "windows", "bin",
        "py{0.major}.{0.minor}".format(sys.version_info)
    )
    print("Adding DLL directory: {}".format(dll_dir))
    add_dll_directory(dll_dir)


import c4d  # noqa: E402

from ayon_core.pipeline import install_host  # noqa: E402
from ayon_core.lib import is_headless_mode_enabled  # noqa: E402
from ayon_cinema4d.api import Cinema4DHost  # noqa: E402
from ayon_cinema4d.api import doc_context  # noqa: E402
from ayon_cinema4d.api.ui import events, ids, registry  # noqa: E402

log = logging.getLogger("ayon_cinema4d")

# Menu commands and windows, see `api/ui/windows`
COMMANDS = []


class DocumentWatcher(c4d.plugins.MessageData):
    """Switch the AYON context when another document becomes active."""

    def __init__(self):
        self._doc = None
        self._path = None

    def CoreMessage(self, id, bc):
        if id != c4d.EVMSG_CHANGE:
            return True

        doc = c4d.documents.GetActiveDocument()
        path = doc_context.get_document_path(doc)
        try:
            same_doc = doc == self._doc
        except ReferenceError:  # previous document was closed
            same_doc = False
        if same_doc and path == self._path:
            return True

        self._doc, self._path = doc, path
        try:
            doc_context.sync_context_to_document(doc)
        except Exception:
            log.warning("Switching the AYON context failed", exc_info=True)
        # Windows showing per-document data (publish status...) update
        events.notify(events.CONTEXT)
        return True


def is_commandline():
    """Commandline / Team Render client, no interactive documents."""
    no_gui = {
        getattr(c4d, name, None)
        for name in ("VERSIONTYPE_COMMANDLINE",
                     "VERSIONTYPE_TEAMRENDER_CLIENT",
                     "VERSIONTYPE_TEAMRENDER_SERVER")
    }
    no_gui.discard(None)
    return c4d.GeGetVersionType() in no_gui


def install_menu():
    """Add the AYON menu after the Extensions (plug-ins) menu."""
    main_menu = c4d.gui.GetMenuResource("M_EDITOR")
    plugins_menu = c4d.gui.SearchPluginMenuResource()
    menu = registry.build_menu(COMMANDS)
    if plugins_menu:
        main_menu.InsDataAfter(c4d.MENURESOURCE_STRING, menu, plugins_menu)
    else:
        main_menu.InsData(c4d.MENURESOURCE_STRING, menu)
    c4d.gui.UpdateMenus()


def PluginMessage(id, data):
    """Entry point to add menu items to Cinema4D"""
    if id == c4d.C4DPL_BUILDMENU:
        install_menu()
    return False


if __name__ == '__main__':
    install_host(Cinema4DHost())

    # Ensure a running QApplication instance without calling `.exec()` on it
    # because this way the Qt UIs run as intended inside Cinema4D.
    from qtpy import QtWidgets  # noqa: E402
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication([])

    # Do not close app if we close last open Qt window
    app.setQuitOnLastWindowClosed(False)

    COMMANDS.extend(registry.discover())
    registry.register(COMMANDS)

    # No context switching for command line / farm renders
    if not is_headless_mode_enabled() and not is_commandline():
        c4d.plugins.RegisterMessagePlugin(
            id=ids.DOCUMENT_WATCHER,
            str="AYON Document Watcher",
            info=0,
            dat=DocumentWatcher()
        )
