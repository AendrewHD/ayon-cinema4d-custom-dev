"""Publish Status window."""
import c4d

from ayon_cinema4d.api import publish_status
from ayon_cinema4d.api.ui import events, ids, widgets
from ayon_cinema4d.api.ui.dialog import AyonDialog
from ayon_cinema4d.api.ui.registry import Command

ID_REFRESH = 1000
ID_HEADER = 1001
ID_ROWS = 1002


class PublishStatusDialog(AyonDialog):
    TITLE = "AYON Publish Status"
    DIALOG_ID = ids.PUBLISH_STATUS
    DEFAULT_SIZE = (420, 180)
    EVENT_KINDS = (events.CONTEXT, events.PUBLISH, events.SERVER)
    SHOW_STATUS = False

    def build(self):
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2):
            self.AddStaticText(ID_HEADER, c4d.BFH_SCALEFIT, name="")
            self.AddButton(ID_REFRESH, c4d.BFH_RIGHT, name="Refresh")
        self.GroupEnd()
        self.AddSeparatorH(0)
        self.ScrollGroupBegin(
            0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
            c4d.SCROLLGROUP_VERT | c4d.SCROLLGROUP_AUTOVERT)
        self.GroupBegin(ID_ROWS, c4d.BFH_SCALEFIT | c4d.BFV_TOP, cols=1)
        self.GroupEnd()
        self.GroupEnd()

    def on_command(self, gadget_id, msg):
        if gadget_id == ID_REFRESH:
            self.refresh()

    def refresh(self):
        try:
            header, rows = publish_status.get_status(
                c4d.documents.GetActiveDocument())
        except Exception as error:
            header, rows = "", [f"Error: {error}"]

        self.SetString(ID_HEADER, header)
        self.LayoutFlushGroup(ID_ROWS)
        for i, row in enumerate(rows):
            self.AddStaticText(ID_ROWS + 1 + i, c4d.BFH_SCALEFIT, name=row)
        self.LayoutChanged(ID_ROWS)


COMMANDS = [
    Command(
        ids.PUBLISH_STATUS, "Publish Status...",
        icon=widgets.ayon_icon("circle_green"), order=50,
        dialog=PublishStatusDialog,
    ),
]
