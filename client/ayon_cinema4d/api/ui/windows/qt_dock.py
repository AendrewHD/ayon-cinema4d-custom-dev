"""EXPERIMENTAL: AYON Qt tools in a dockable dialog (see `ui/qt_dock`)."""
import logging

import c4d

from ayon_cinema4d.api.ui import ids
from ayon_cinema4d.api.ui.dialog import AyonDialog
from ayon_cinema4d.api.ui.qt_dock import TOOLS, FOLLOW_INTERVAL, \
    Placeholder, QtHost
from ayon_cinema4d.api.ui.registry import Command

log = logging.getLogger(__name__)

ID_TOOL = 1000
ID_AREA = 1001


class QtDockDialog(AyonDialog):
    TITLE = "AYON Qt Dock (experimental)"
    DIALOG_ID = ids.QT_DOCK
    DEFAULT_SIZE = (900, 560)
    EVENT_KINDS = ()
    SHOW_STATUS = False

    def __init__(self):
        super().__init__()
        self.host = QtHost()
        self.placeholder = Placeholder()
        self._tool_index = 0
        self._last_rect = None

    def build(self):
        self.AddComboBox(ID_TOOL, c4d.BFH_LEFT, 200, 0)
        for index, (label, _) in enumerate(TOOLS):
            self.AddChild(ID_TOOL, index, label)
        self.AddUserArea(ID_AREA, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT)
        self.AttachUserArea(self.placeholder, ID_AREA)

    def InitValues(self):
        result = super().InitValues()
        self.SetInt32(ID_TOOL, self._tool_index)
        self.SetTimer(FOLLOW_INTERVAL)
        return result

    def refresh(self):
        self.host.set_tool(TOOLS[self._tool_index][1])
        self._last_rect = None

    def on_command(self, gadget_id, msg):
        if gadget_id == ID_TOOL:
            self._tool_index = self.GetInt32(ID_TOOL)
            self.refresh()

    def Timer(self, msg):
        # IsVisible: False while the dialog sits in an inactive tab
        if not self.IsVisible():
            if self._last_rect is not None:
                self.guard(self.host.follow, 0, 0, 0, 0)
                self._last_rect = None
            return
        rect = self.guard(self.placeholder.screen_rect)
        if rect and rect != self._last_rect:
            self._last_rect = rect
            self.guard(self.host.follow, *rect)

    def AskClose(self):
        self.host.release()
        return False

    def DestroyWindow(self):
        super().DestroyWindow()
        self.guard(self.host.release)


COMMANDS = [
    Command(
        ids.QT_DOCK, "Qt Dock (experimental)...", section="classic",
        order=90, dialog=QtDockDialog, separator_before=True,
        help="Show an AYON Qt tool inside a dockable Cinema 4D dialog",
    ),
]
