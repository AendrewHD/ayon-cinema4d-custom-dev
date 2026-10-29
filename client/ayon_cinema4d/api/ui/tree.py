"""Small item model for the Cinema 4D TreeView.

    model = TreeModel([Column("name", "Name"), Column("version", "Version")])
    dialog.add_tree(ID_TREE, model)  # AyonDialog attaches it in InitValues
    model.set_items([Item("a", {"name": "Hero", "version": "v003"})])

Callbacks (all optional) receive the clicked / selected `Item`s:
    on_select(items), on_double_click(item), on_check(item, checked),
    context_menu(items) -> popup entries (see `widgets.popup`),
    on_delete(items)
"""
import c4d

from . import widgets

PADDING = 6
ICON_SIZE = 16
SWATCH_SIZE = 10


class Column:
    """Column definition.

    Args:
        key (str): Key in `Item.values`.
        title (str): Header text.
        width (int): Fixed width, None fits the content.
        checkbox (bool): Checkbox column, uses `Item.checked`.
        pill (bool): Draw the value as colored pill (`Item.colors[key]`).
    """

    def __init__(self, key, title, width=None, checkbox=False, pill=False):
        self.key = key
        self.title = title
        self.width = width
        self.checkbox = checkbox
        self.pill = pill


class Item:
    """One line in the tree.

    Args:
        key (str): Unique key, keeps selection / open state over reloads.
        values (dict): Text per column key.
        data (Any): Payload for the callbacks.
        swatch (c4d.Vector): Colored square before the first column text.
        icon (c4d.bitmaps.BaseBitmap): Icon before the first column text.
        colors (dict): Text / pill color per column key (c4d.Vector).
        checked (bool): State of checkbox columns.
        bold (bool): Bold text.
        dim (bool): Grayed out text.
        tooltip (str): Bubble help.
    """

    def __init__(
        self, key, values=None, data=None, swatch=None, icon=None,
        colors=None, checked=False, bold=False, dim=False, tooltip=None,
        children=None,
    ):
        self.key = key
        self.values = values or {}
        self.data = data
        self.swatch = swatch
        self.icon = icon
        self.colors = colors or {}
        self.checked = checked
        self.bold = bold
        self.dim = dim
        self.tooltip = tooltip
        self.children = children or []
        self.parent = None
        self.next = None
        self.pred = None

    def text(self, key):
        value = self.values.get(key, "")
        return "" if value is None else str(value)


def _link(items, parent=None):
    pred = None
    for item in items:
        item.parent = parent
        item.pred = pred
        item.next = None
        if pred is not None:
            pred.next = item
        pred = item
        _link(item.children, item)


def iter_items(items):
    for item in items:
        yield item
        yield from iter_items(item.children)


class TreeModel(c4d.gui.TreeViewFunctions):

    def __init__(self, columns, empty_text="", flat=False):
        super().__init__()
        self.columns = columns
        self.empty_text = empty_text
        self.flat = flat
        self.items = []
        self.gui = None
        self._by_key = {}
        self._selected = set()
        self._opened = set()
        self._sort = None  # (column key, ascending)
        self.on_select = None
        self.on_double_click = None
        self.on_check = None
        self.on_delete = None
        self.context_menu = None

    # -- model -----------------------------------------------------------
    def attach(self, gui):
        self.gui = gui
        if gui is None:
            return
        layout = c4d.BaseContainer()
        for column_id, column in enumerate(self.columns, 1):
            if column.checkbox:
                kind = c4d.LV_CHECKBOX
            elif column_id == 1 and not self.flat:
                kind = c4d.LV_USERTREE
            else:
                kind = c4d.LV_USER
            layout.SetInt32(column_id, kind)
        gui.SetLayout(len(self.columns), layout)
        for column_id, column in enumerate(self.columns, 1):
            gui.SetHeaderText(column_id, column.title)
        gui.SetRoot(self, self, None)
        gui.Refresh()

    def set_items(self, items, open_all=False):
        """Replace the items, keep selection and open state by key."""
        self.items = list(items)
        self._apply_sort()
        _link(self.items)
        self._by_key = {item.key: item for item in iter_items(self.items)}
        self._selected &= set(self._by_key)
        if open_all:
            self._opened = {
                item.key for item in self._by_key.values() if item.children
            }
        self.refresh()

    def refresh(self):
        if self.gui is not None:
            self.gui.Refresh()

    def get(self, key):
        return self._by_key.get(key)

    def all_items(self):
        return list(iter_items(self.items))

    def selected_items(self):
        return [i for i in iter_items(self.items) if i.key in self._selected]

    def select_keys(self, keys, notify=False):
        self._selected = set(keys) & set(self._by_key)
        self.refresh()
        if notify and self.on_select:
            self.on_select(self.selected_items())

    def open_keys(self, keys):
        self._opened |= set(keys)

    def show(self, key):
        item = self._by_key.get(key)
        if item is None:
            return
        parent = item.parent
        while parent is not None:
            self._opened.add(parent.key)
            parent = parent.parent
        if self.gui is not None:
            self.gui.Refresh()
            self.gui.MakeVisible(item)

    def _apply_sort(self):
        if not self._sort:
            return
        key, ascending = self._sort

        def sort(items):
            items.sort(
                key=lambda i: _sort_value(i.values.get(key)),
                reverse=not ascending)
            for item in items:
                sort(item.children)

        sort(self.items)

    # -- TreeViewFunctions: structure -------------------------------------
    def GetFirst(self, root, userdata):
        return self.items[0] if self.items else None

    def GetDown(self, root, userdata, obj):
        return obj.children[0] if obj.children else None

    def GetNext(self, root, userdata, obj):
        return obj.next

    def GetPred(self, root, userdata, obj):
        return obj.pred

    def GetId(self, root, userdata, obj):
        return hash(obj.key) & 0x7FFFFFFF

    def IsOpened(self, root, userdata, obj):
        return obj.key in self._opened

    def Open(self, root, userdata, obj, onoff):
        if onoff:
            self._opened.add(obj.key)
        else:
            self._opened.discard(obj.key)

    def IsSelected(self, root, userdata, obj):
        return obj.key in self._selected

    def Select(self, root, userdata, obj, mode):
        if mode == c4d.SELECTION_NEW:
            self._selected = {obj.key}
        elif mode == c4d.SELECTION_ADD:
            self._selected.add(obj.key)
        elif mode == c4d.SELECTION_SUB:
            self._selected.discard(obj.key)

    def SelectionChanged(self, root, userdata):
        if self.on_select:
            self.on_select(self.selected_items())

    def GetName(self, root, userdata, obj):
        return obj.text(self.columns[0].key)

    def EmptyText(self, root, userdata):
        return self.empty_text

    def GetBubbleHelp(self, root, userdata, obj, col, info):
        return obj.tooltip or ""

    def GetDragType(self, root, userdata, obj):
        return c4d.NOTOK

    # -- TreeViewFunctions: drawing ---------------------------------------
    def _column(self, col):
        if 1 <= col <= len(self.columns):
            return self.columns[col - 1]
        return None

    def _lead_width(self, obj, col):
        if col != 1:
            return 0
        width = 0
        if obj.swatch is not None:
            width += SWATCH_SIZE + 4
        if obj.icon is not None:
            width += ICON_SIZE + 4
        return width

    def GetColumnWidth(self, root, userdata, obj, col, area):
        column = self._column(col)
        if column is None:
            return 40
        if column.width:
            return column.width
        text_width = area.DrawGetTextWidth(obj.text(column.key))
        return text_width + self._lead_width(obj, col) + PADDING * 3

    def GetHeaderColumnWidth(self, root, userdata, col, area):
        column = self._column(col)
        if column is not None and column.width:
            return column.width
        return -1

    def GetLineHeight(self, root, userdata, obj, col, area):
        return max(area.DrawGetFontHeight() + 6, ICON_SIZE + 4)

    def DrawCell(self, root, userdata, obj, col, drawinfo, bgColor):
        column = self._column(col)
        if column is None:
            return
        area = drawinfo["frame"]
        x, y = drawinfo["xpos"], drawinfo["ypos"]
        width, height = drawinfo["width"], drawinfo["height"]
        selected = obj.key in self._selected

        if col == 1:
            if obj.swatch is not None:
                top = y + (height - SWATCH_SIZE) // 2
                area.DrawSetPen(obj.swatch)
                area.DrawRectangle(
                    x + 2, top, x + 2 + SWATCH_SIZE, top + SWATCH_SIZE)
                x += SWATCH_SIZE + 4
                width -= SWATCH_SIZE + 4
            if obj.icon is not None:
                bmp = obj.icon
                area.DrawBitmap(
                    bmp, x + 2, y + (height - ICON_SIZE) // 2,
                    ICON_SIZE, ICON_SIZE, 0, 0, bmp.GetBw(), bmp.GetBh(),
                    c4d.BMP_ALLOWALPHA | c4d.BMP_NORMALSCALED)
                x += ICON_SIZE + 4
                width -= ICON_SIZE + 4

        text = obj.text(column.key)
        if not text:
            return
        area.DrawSetFont(c4d.FONT_BOLD if obj.bold else c4d.FONT_DEFAULT)
        color = obj.colors.get(column.key)
        font_height = area.DrawGetFontHeight()
        text_y = y + (height - font_height) // 2

        if column.pill and color is not None:
            text = widgets.elide(area, text, width - PADDING * 3)
            pill_width = area.DrawGetTextWidth(text) + PADDING * 2
            area.DrawSetPen(color)
            area.DrawRectangle(
                x + 2, y + 2, x + 2 + pill_width, y + height - 3)
            area.DrawSetTextCol(widgets.contrast_text(color), c4d.COLOR_TRANS)
            area.DrawText(text, x + 2 + PADDING, text_y)
            return

        if selected:
            text_color = c4d.COLOR_TEXT_SELECTED
        elif color is not None:
            text_color = color
        elif obj.dim:
            text_color = c4d.COLOR_TEXT_DISABLED
        else:
            text_color = c4d.COLOR_TEXT
        area.DrawSetTextCol(text_color, c4d.COLOR_TRANS)
        area.DrawText(
            widgets.elide(area, text, width - PADDING), x + PADDING // 2,
            text_y)

    # -- TreeViewFunctions: checkbox ---------------------------------------
    def IsChecked(self, root, userdata, obj, lColumn):
        column = self._column(lColumn)
        if column is None or not column.checkbox:
            return c4d.NOTOK
        state = c4d.LV_CHECKBOX_ENABLED
        if obj.checked:
            state |= c4d.LV_CHECKBOX_CHECKED
        return state

    def SetCheck(self, root, userdata, obj, lColumn, bCheck, bcMsg):
        obj.checked = bool(bCheck)
        if self.on_check:
            self.on_check(obj, obj.checked)

    # -- TreeViewFunctions: input ------------------------------------------
    def DoubleClick(self, root, userdata, obj, col, mouseinfo):
        if self.on_double_click and obj is not None:
            self.on_double_click(obj)
            return True
        return False

    def MouseDown(self, root, userdata, obj, col, mouseinfo, rightButton):
        if not rightButton or not self.context_menu:
            return False
        if obj is not None and obj.key not in self._selected:
            self._selected = {obj.key}
            self.refresh()
            if self.on_select:
                self.on_select(self.selected_items())
        entries = self.context_menu(self.selected_items())
        if entries:
            widgets.popup(entries)
        return True

    def DeletePressed(self, root, userdata):
        if self.on_delete:
            self.on_delete(self.selected_items())

    def HeaderClick(self, root, userdata, lColID, lChannel, bDblClk,
                    mouseX, mouseY, ua):
        column = self._column(lColID)
        if column is None or column.checkbox:
            return False
        if self._sort and self._sort[0] == column.key:
            self._sort = (column.key, not self._sort[1])
        else:
            self._sort = (column.key, True)
        self._apply_sort()
        _link(self.items)
        return True

    def GetHeaderSortArrow(self, root, userdata, lColID):
        column = self._column(lColID)
        if column is None or not self._sort or self._sort[0] != column.key:
            return 0
        return 1 if self._sort[1] else -1


def _sort_value(value):
    if isinstance(value, (int, float)):
        return (0, value, "")
    text = "" if value is None else str(value)
    digits = text.lstrip("v")
    if digits.isdigit():
        return (0, int(digits), text)
    return (1, 0, text.lower())


def add_tree(dialog, gadget_id, model, min_size=(200, 120), header=True):
    """Add a TreeView gadget for `model` (attach it in InitValues)."""
    bc = c4d.BaseContainer()
    bc.SetInt32(c4d.TREEVIEW_BORDER, c4d.BORDER_THIN_IN)
    bc.SetBool(c4d.TREEVIEW_HAS_HEADER, header)
    bc.SetBool(c4d.TREEVIEW_HIDE_LINES, model.flat)
    bc.SetBool(c4d.TREEVIEW_RESIZE_HEADER, True)
    bc.SetBool(c4d.TREEVIEW_MOVE_COLUMN, False)
    bc.SetBool(c4d.TREEVIEW_ALTERNATE_BG, True)
    bc.SetBool(c4d.TREEVIEW_CURSORKEYS, True)
    bc.SetBool(c4d.TREEVIEW_NOENTERRENAME, True)
    bc.SetBool(c4d.TREEVIEW_FIXED_LAYOUT, True)
    gui = dialog.AddCustomGui(
        gadget_id, c4d.CUSTOMGUI_TREEVIEW, "",
        c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
        min_size[0], min_size[1], bc)
    return gui
