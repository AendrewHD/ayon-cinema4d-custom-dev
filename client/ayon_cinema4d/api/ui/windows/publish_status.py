"""Publish Status window: what this workfile published, what is outdated."""
import c4d

from ayon_cinema4d.api import publish_status
from ayon_cinema4d.api.ui import events, ids, widgets
from ayon_cinema4d.api.ui.dialog import AyonDialog
from ayon_cinema4d.api.ui.registry import Command
from ayon_cinema4d.api.ui.tree import Column, Item, TreeModel

ID_HEADER = 1000
ID_TREE = 1001
ID_REFRESH = 1002
ID_MANAGE = 1003
ID_PUBLISH = 1004
ID_SAVE = 1005
ID_SAVE_NEXT = 1006
ID_SAVE_AS = 1007

SAVE_COMMAND = 12098  # File > Save


def _version(number):
    return "hero" if number < 0 else f"v{number:03d}"


class StatusHeader(c4d.gui.GeUserArea):
    """Workfile name, context and colored state badges."""

    HEIGHT = 58

    def __init__(self):
        super().__init__()
        self.data = None

    def GetMinSize(self):
        return 200, self.HEIGHT

    def _badges(self):
        data = self.data
        badges = []
        if not data["saved"]:
            badges.append(("not saved", widgets.RED))
        elif data["unsaved"]:
            badges.append(("unsaved changes", widgets.ORANGE))
        if data["own"]:
            latest = data["own"][0]
            badges.append((
                f"published {latest['product']} "
                f"{_version(latest['version'])}", widgets.GREEN))
        elif data["saved"]:
            badges.append(("not published", widgets.GRAY))
        if data["latest_workfile"]:
            badges.append(("newer workfile publish", widgets.ORANGE))
        if data["loaded"]:
            badges.append((f"{data['loaded']} loaded", widgets.BLUE))
        if data["outdated"]:
            badges.append(
                (f"{len(data['outdated'])} outdated", widgets.ORANGE))
        return badges

    def DrawMsg(self, x1, y1, x2, y2, msg):
        self.OffScreenOn()
        self.DrawSetPen(c4d.COLOR_BG)
        self.DrawRectangle(x1, y1, x2, y2)
        if not self.data:
            return
        width = self.GetWidth()
        font_h = self.DrawGetFontHeight()

        self.DrawSetFont(c4d.FONT_BOLD)
        self.DrawSetTextCol(widgets.TEXT, c4d.COLOR_TRANS)
        self.DrawText(
            widgets.elide(self, self.data["workfile"] or "Untitled",
                          width - 12), 6, 2)
        self.DrawSetFont(c4d.FONT_DEFAULT)
        self.DrawSetTextCol(widgets.TEXT_DIM, c4d.COLOR_TRANS)
        self.DrawText(
            widgets.elide(self, self.data["context"], width - 12),
            6, 4 + font_h)

        x, y = 6, 10 + font_h * 2
        for text, color in self._badges():
            badge_w = self.DrawGetTextWidth(text) + 12
            if x + badge_w > width and x > 6:
                break
            self.DrawSetPen(color)
            self.DrawRectangle(x, y, x + badge_w, y + font_h + 3)
            self.DrawSetTextCol(widgets.contrast_text(color), c4d.COLOR_TRANS)
            self.DrawText(text, x + 6, y + 1)
            x += badge_w + 5


def _section(key, title, children, empty=None):
    """Bold parent line, `empty` is shown as dimmed child when empty."""
    if children:
        title = f"{title}  ({len(children)})"
    elif empty:
        children = [Item(f"{key}:empty", {"name": empty}, dim=True)]
    return Item(key, {"name": title}, bold=True, children=children)


def _version_item(row, prefix):
    created = widgets.format_time(row["created"])
    return Item(
        f"{prefix}:{row['id']}",
        {
            "name": row["product"],
            "version": _version(row["version"]),
            "info": "  ".join(filter(None, [created, row["author"]])),
        },
        swatch=widgets.color_for(row["product_type"]),
        colors={"version": widgets.GREEN if prefix == "own"
                else widgets.ORANGE},
        tooltip=row["comment"] or row["source"] or None,
    )


class PublishStatusDialog(AyonDialog):
    TITLE = "AYON Publish Status"
    DIALOG_ID = ids.PUBLISH_STATUS
    DEFAULT_SIZE = (440, 260)
    EVENT_KINDS = (events.CONTEXT, events.PUBLISH, events.SERVER)

    def __init__(self):
        super().__init__()
        self.header = StatusHeader()
        self.model = TreeModel(
            [
                Column("name", "Product"),
                Column("version", "Version", width=70, pill=True),
                Column("info", "Published"),
            ],
            empty_text="",
        )
        self.model.on_double_click = self._open_item

    def build(self):
        self.AddUserArea(ID_HEADER, c4d.BFH_SCALEFIT, 0, StatusHeader.HEIGHT)
        self.AttachUserArea(self.header, ID_HEADER)
        self.add_tree(ID_TREE, self.model, min_size=(240, 100))
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=3):
            self.AddButton(ID_SAVE, c4d.BFH_SCALEFIT, name="Save")
            self.AddButton(ID_SAVE_NEXT, c4d.BFH_SCALEFIT,
                           name="Save Next Version")
            self.AddButton(ID_SAVE_AS, c4d.BFH_SCALEFIT, name="Save As...")
        self.GroupEnd()
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=3):
            self.AddButton(ID_REFRESH, c4d.BFH_LEFT, name="Refresh")
            self.AddButton(ID_MANAGE, c4d.BFH_RIGHT | c4d.BFH_SCALE,
                           name="Manage...")
            self.AddButton(ID_PUBLISH, c4d.BFH_RIGHT, name="Publish...")
        self.GroupEnd()

    def refresh(self):
        doc = c4d.documents.GetActiveDocument()
        data = publish_status.get_status_data(doc)
        self.header.data = data
        self.header.Redraw()

        sections = [
            _section(
                "own", "Published from this file",
                [_version_item(r, "own") for r in data["own"]],
                empty=data["message"] or "Nothing published from this file."),
        ]
        if data["latest_workfile"]:
            row = data["latest_workfile"]
            item = _version_item(row, "latest")
            item.values["info"] = f"from {row['source']}"
            sections.append(_section(
                "latest", "Newer workfile publish of the task", [item]))
        if data["outdated"]:
            sections.append(_section("outdated", "Outdated", [
                Item(
                    f"outdated:{i}",
                    {"name": row["name"] or row["product"],
                     "version": _version(row["version"]),
                     "info": f"latest {_version(row['latest'])}"},
                    swatch=widgets.color_for(row["product_type"]),
                    colors={"version": widgets.ORANGE},
                    tooltip=row["product"],
                )
                for i, row in enumerate(data["outdated"])
            ]))
        self.model.set_items(sections, open_all=True)
        self.set_status("")

    def on_document_change(self):
        # Only the saved state can change without an event, redraw cheaply
        data = self.header.data
        if data is not None:
            unsaved = bool(c4d.documents.GetActiveDocument().GetChanged())
            if unsaved != data["unsaved"]:
                data["unsaved"] = unsaved
                self.header.Redraw()

    def _open_item(self, item):
        if item.key.startswith("outdated:"):
            c4d.CallCommand(ids.MANAGE)

    def on_command(self, gadget_id, msg):
        save_commands = {
            ID_SAVE: SAVE_COMMAND,
            ID_SAVE_NEXT: ids.SAVE_NEXT_VERSION,
            ID_SAVE_AS: ids.SAVE_AS,
        }
        if gadget_id in save_commands:
            c4d.CallCommand(save_commands[gadget_id])
            self.refresh()
        elif gadget_id == ID_REFRESH:
            self.refresh()
        elif gadget_id == ID_MANAGE:
            c4d.CallCommand(ids.MANAGE)
        elif gadget_id == ID_PUBLISH:
            c4d.CallCommand(ids.PUBLISH)


COMMANDS = [
    Command(
        ids.PUBLISH_STATUS, "Publish Status...",
        icon=widgets.ayon_icon("circle_green"), order=50,
        dialog=PublishStatusDialog,
    ),
]
