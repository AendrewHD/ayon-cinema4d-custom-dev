"""Library: native AYON loader.

Folders on the left, products of the selected folders on the right as list
or thumbnail grid. Products load with the AYON loaders (containerised,
placed by Preferences > Interface > Insert Objects at) or are dragged into
the Object Manager / viewport / Node Editor as files (not tracked).
Refreshes itself when the AYON server reports new products or versions.
"""
import os
import logging
import tempfile
import threading
import webbrowser
import urllib.parse

import c4d
import ayon_api

from ayon_core.pipeline import (
    Anatomy,
    get_current_project_name,
    registered_host,
)
from ayon_core.pipeline.load import (
    discover_loader_plugins,
    get_representation_contexts,
    get_representation_path_with_anatomy,
    load_with_repre_context,
    loaders_from_repre_context,
)

from ayon_cinema4d.api.browser_drag import EXTENSION_PRIORITY, SKIP_NAMES
from ayon_cinema4d.api.ui import entities, events, ids, widgets
from ayon_cinema4d.api.ui.dialog import AyonDialog
from ayon_cinema4d.api.ui.registry import Command
from ayon_cinema4d.api.ui.tree import TreeModel, Column

from .classic import show_browser

log = logging.getLogger(__name__)

ID_PROJECT = 1000
ID_FOLDER_FILTER = 1001
ID_PRODUCT_FILTER = 1002
ID_VIEW_MODE = 1003
ID_REFRESH = 1004
ID_QT = 1005
ID_SPLIT = 1006
ID_FOLDERS = 1007
ID_SUBFOLDERS = 1008
ID_PRODUCTS = 1009
ID_PRODUCTS_SCROLL = 1010
ID_VERSION = 1011
ID_LOAD_MENU = 1012
ID_MERGE = 1013
ID_ALEMBIC = 1014
ID_XREF = 1015
ID_INFO = 1016

MODE_LIST = 0
MODE_GRID = 1

# Quick load buttons: loader class name -> button
QUICK_LOADERS = {
    ID_MERGE: "MergeLoader",
    ID_ALEMBIC: "AlembicLoader",
    ID_XREF: "XRefLoader",
}
# Double click: first loader of this list that fits
DEFAULT_LOADERS = ["MergeLoader", "AlembicLoader", "CameraLoader"]

SCENE_EXTENSIONS = {
    "c4d", "fbx", "abc", "obj", "usd", "usda", "usdc", "usdz", "gltf",
    "glb", "stl", "ply", "3ds", "dae",
}
IMAGE_EXTENSIONS = {
    "exr", "tx", "tif", "tiff", "png", "jpg", "jpeg", "hdr", "tga", "psd",
}

VERSION_FIELDS = {
    "id", "version", "productId", "createdAt", "author", "thumbnailId",
    "status", "taskId", "attrib.comment",
}
THUMB_DIR = os.path.join(tempfile.gettempdir(), "ayon_c4d_thumbnails")


def _repre_ext(repre):
    ext = (repre.get("context") or {}).get("ext") or repre["name"]
    return ext.lower().lstrip(".")


def _best_repre(repres):
    """Representation used for drag and double click."""
    best = None
    for repre in repres:
        ext = _repre_ext(repre)
        if repre["name"] in SKIP_NAMES or ext not in EXTENSION_PRIORITY:
            continue
        rank = EXTENSION_PRIORITY.index(ext)
        if best is None or rank < best[0]:
            best = (rank, repre)
    return best[1] if best else None


def _version_label(version):
    if version["version"] < 0:
        return "hero"
    return f"v{version['version']:03d}"


class ProductEntry:
    """A product with its versions, the shown version and its files."""

    def __init__(self, product, folder_path, versions):
        self.product = product
        self.folder_path = folder_path
        self.versions = sorted(
            versions, key=lambda v: (v["version"] >= 0, abs(v["version"])),
            reverse=True)
        standard = [v for v in self.versions if v["version"] >= 0]
        self.version = standard[0] if standard else (
            self.versions[0] if self.versions else None)
        self.repres = []
        self.path = None
        self.thumbnail = None  # local file path once downloaded

    @property
    def id(self):
        return self.product["id"]

    @property
    def name(self):
        return self.product["name"]

    @property
    def product_type(self):
        return self.product.get("productType") or ""


class ThumbnailLoader:
    """Downloads version thumbnails in a thread, redraws the area."""

    def __init__(self, area):
        self._area = area
        self._queue = []
        self._lock = threading.Lock()
        self._thread = None

    def request(self, project_name, entries):
        with self._lock:
            self._queue = [
                (project_name, entry) for entry in entries
                if entry.version and entry.version.get("thumbnailId")
                and entry.thumbnail is None
            ]
        if self._queue and (self._thread is None
                            or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self):
        while True:
            with self._lock:
                if not self._queue:
                    return
                project_name, entry = self._queue.pop(0)
            version = entry.version
            try:
                path = _thumbnail_path(project_name, version)
                # The shown version may have changed while downloading
                if path and entry.version is version:
                    entry.thumbnail = path
                    self._area.Redraw(True)
            except Exception:
                log.debug("Thumbnail download failed", exc_info=True)


def _thumbnail_path(project_name, version):
    """Cached thumbnail file of a version, downloaded if needed."""
    thumbnail_id = version["thumbnailId"]
    base = os.path.join(THUMB_DIR, project_name, thumbnail_id)
    for ext in (".jpg", ".png"):
        if os.path.exists(base + ext):
            return base + ext
    getter = getattr(ayon_api, "get_thumbnail_by_id", None)
    if getter is not None:
        thumbnail = getter(project_name, thumbnail_id)
    else:  # older ayon_api
        thumbnail = ayon_api.get_thumbnail(
            project_name, "version", version["id"], thumbnail_id)
    if not thumbnail or not thumbnail.content:
        return None
    path = base + (".png" if "png" in (thumbnail.content_type or "")
                   else ".jpg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as stream:
        stream.write(thumbnail.content)
    return path


class ProductArea(c4d.gui.GeUserArea):
    """Product list / grid with selection, double click, menu and drag."""

    LIST_HEIGHT = 44
    GRID_WIDTH = 168
    GRID_HEIGHT = 150
    GAP = 6

    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.entries = []
        self.selected = set()
        self.anchor = None
        self.mode = MODE_LIST
        self.thumbnails = ThumbnailLoader(self)
        self._width = 400

    # -- layout ----------------------------------------------------------
    def set_entries(self, entries):
        self.entries = entries
        ids_ = {e.id for e in entries}
        self.selected &= ids_
        self.LayoutChanged()
        self.Redraw()

    def selected_entries(self):
        return [e for e in self.entries if e.id in self.selected]

    def _columns(self):
        if self.mode == MODE_LIST:
            return 1
        return max(1, (self._width - self.GAP) // (self.GRID_WIDTH + self.GAP))

    def _cell(self, index):
        """(x1, y1, x2, y2) of entry `index`."""
        if self.mode == MODE_LIST:
            y = index * self.LIST_HEIGHT
            return 0, y, self._width, y + self.LIST_HEIGHT
        cols = self._columns()
        col, row = index % cols, index // cols
        x = self.GAP + col * (self.GRID_WIDTH + self.GAP)
        y = self.GAP + row * (self.GRID_HEIGHT + self.GAP)
        return x, y, x + self.GRID_WIDTH, y + self.GRID_HEIGHT

    def _content_height(self):
        if not self.entries:
            return 40
        return self._cell(len(self.entries) - 1)[3] + self.GAP

    def GetMinSize(self):
        return 100, self._content_height()

    def Sized(self, w, h):
        if w != self._width:
            self._width = w
            self.LayoutChanged()

    def _index_at(self, x, y):
        for index in range(len(self.entries)):
            x1, y1, x2, y2 = self._cell(index)
            if x1 <= x < x2 and y1 <= y < y2:
                return index
        return None

    # -- drawing ---------------------------------------------------------
    def DrawMsg(self, x1, y1, x2, y2, msg):
        self.OffScreenOn(x1, y1, x2 - x1 + 1, y2 - y1 + 1)
        self.SetClippingRegion(x1, y1, x2 - x1 + 1, y2 - y1 + 1)
        self.DrawSetPen(c4d.COLOR_BG)
        self.DrawRectangle(x1, y1, x2, y2)
        if not self.entries:
            self.DrawSetTextCol(widgets.TEXT_DIM, c4d.COLOR_TRANS)
            self.DrawText(self.dialog.empty_text(), 8, 12)
            return
        for index, entry in enumerate(self.entries):
            cell = self._cell(index)
            if cell[3] < y1 or cell[1] > y2:
                continue
            if self.mode == MODE_LIST:
                self._draw_row(entry, *cell)
            else:
                self._draw_card(entry, *cell)

    def _draw_thumbnail(self, entry, x1, y1, x2, y2):
        self.DrawSetPen(c4d.Vector(0.16))
        self.DrawRectangle(x1, y1, x2, y2)
        bmp = widgets.bitmap(entry.thumbnail) if entry.thumbnail else None
        if bmp is None:
            color = widgets.color_for(entry.product_type)
            self.DrawSetTextCol(color, c4d.COLOR_TRANS)
            self.DrawSetFont(c4d.FONT_BOLD)
            letter = (entry.product_type[:1] or "?").upper()
            self.DrawText(
                letter,
                (x1 + x2 - self.DrawGetTextWidth(letter)) // 2,
                (y1 + y2 - self.DrawGetFontHeight()) // 2)
            return
        # fit the image into the box, keep aspect
        bw, bh = bmp.GetBw(), bmp.GetBh()
        box_w, box_h = x2 - x1, y2 - y1
        scale = min(box_w / max(bw, 1), box_h / max(bh, 1))
        w, h = int(bw * scale), int(bh * scale)
        x = x1 + (box_w - w) // 2
        y = y1 + (box_h - h) // 2
        self.DrawBitmap(
            bmp, x, y, w, h, 0, 0, bw, bh,
            c4d.BMP_NORMALSCALED | c4d.BMP_ALLOWALPHA)

    def _text(self, text, x, y, width, color=widgets.TEXT,
              font=c4d.FONT_DEFAULT):
        self.DrawSetFont(font)
        self.DrawSetTextCol(color, c4d.COLOR_TRANS)
        self.DrawText(widgets.elide(self, text, width), x, y)

    def _pill(self, text, x, y, color):
        width = self.DrawGetTextWidth(text) + 10
        height = self.DrawGetFontHeight() + 2
        self.DrawSetPen(color)
        self.DrawRectangle(x, y, x + width, y + height)
        self.DrawSetTextCol(widgets.contrast_text(color), c4d.COLOR_TRANS)
        self.DrawText(text, x + 5, y + 1)
        return width

    def _background(self, entry, x1, y1, x2, y2):
        if entry.id in self.selected:
            self.DrawSetPen(widgets.SELECTION)
            self.DrawRectangle(x1, y1, x2, y2)

    def _version_text(self, entry):
        if not entry.version:
            return "no versions"
        text = _version_label(entry.version)
        if len(entry.versions) > 1:
            text += f" / {len(entry.versions)}"
        return text

    def _draw_row(self, entry, x1, y1, x2, y2):
        self._background(entry, x1, y1, x2, y2)
        thumb_w = 64
        self._draw_thumbnail(entry, x1 + 4, y1 + 4, x1 + 4 + thumb_w, y2 - 4)
        x = x1 + thumb_w + 12
        font_h = self.DrawGetFontHeight()
        self._text(entry.name, x, y1 + 5, x2 - x - 150, font=c4d.FONT_BOLD)
        self.DrawSetFont(c4d.FONT_DEFAULT)
        pill_x = x
        pill_x += self._pill(
            entry.product_type, pill_x, y1 + 8 + font_h,
            widgets.color_for(entry.product_type)) + 6
        version = entry.version or {}
        details = "  ".join(filter(None, [
            entry.folder_path if self.dialog.show_folder_path() else "",
            widgets.format_time(version.get("createdAt")),
            version.get("author") or "",
        ]))
        self._text(
            details, pill_x, y1 + 9 + font_h, x2 - pill_x - 90,
            color=widgets.TEXT_DIM)
        version_text = self._version_text(entry)
        self.DrawSetFont(c4d.FONT_BOLD)
        self._text(
            version_text, x2 - 12 - self.DrawGetTextWidth(version_text),
            y1 + 5, 120, font=c4d.FONT_BOLD)
        self.DrawSetPen(widgets.LINE)
        self.DrawLine(x1, y2 - 1, x2, y2 - 1)

    def _draw_card(self, entry, x1, y1, x2, y2):
        self.DrawSetPen(widgets.CARD)
        self.DrawRectangle(x1, y1, x2, y2)
        self._background(entry, x1, y1, x2, y2)
        thumb_h = (x2 - x1 - 8) * 9 // 16
        self._draw_thumbnail(entry, x1 + 4, y1 + 4, x2 - 4, y1 + 4 + thumb_h)
        y = y1 + thumb_h + 8
        font_h = self.DrawGetFontHeight()
        self._text(entry.name, x1 + 6, y, x2 - x1 - 12, font=c4d.FONT_BOLD)
        self.DrawSetFont(c4d.FONT_DEFAULT)
        y += font_h + 4
        width = self._pill(
            entry.product_type, x1 + 6, y,
            widgets.color_for(entry.product_type))
        self._text(
            self._version_text(entry), x1 + 14 + width, y + 1,
            x2 - x1 - width - 20)

    # -- input -----------------------------------------------------------
    def InputEvent(self, msg):
        if msg[c4d.BFM_INPUT_DEVICE] != c4d.BFM_INPUT_MOUSE:
            return False
        channel = msg[c4d.BFM_INPUT_CHANNEL]
        if channel not in (c4d.BFM_INPUT_MOUSELEFT, c4d.BFM_INPUT_MOUSERIGHT):
            return False

        offset = self.Local2Global()
        x = msg[c4d.BFM_INPUT_X] - offset["x"]
        y = msg[c4d.BFM_INPUT_Y] - offset["y"]
        index = self._index_at(x, y)
        entry = self.entries[index] if index is not None else None
        qualifier = msg[c4d.BFM_INPUT_QUALIFIER]

        if channel == c4d.BFM_INPUT_MOUSERIGHT:
            if entry is not None and entry.id not in self.selected:
                self._select(index, 0)
            self.dialog.guard(self.dialog.show_menu)
            return True

        if entry is None:
            self.selected = set()
            self.Redraw()
            self.dialog.guard(self.dialog.on_product_selection)
            return True

        if msg[c4d.BFM_INPUT_DOUBLECLICK]:
            self._select(index, 0)
            self.dialog.guard(self.dialog.load_default, [entry])
            return True

        if entry.id not in self.selected or qualifier:
            self._select(index, qualifier)
        # Dragging a product drops its file (not tracked as container)
        if not qualifier and entry.path and self.HandleMouseDrag(
            msg, _drag_type(entry.path), entry.path, 0
        ):
            return True
        if not qualifier and len(self.selected) > 1:
            self._select(index, 0)  # plain click in a multi selection
        return True

    def _select(self, index, qualifier):
        entry = self.entries[index]
        if qualifier & c4d.QSHIFT and self.anchor is not None:
            low, high = sorted((self.anchor, index))
            self.selected |= {e.id for e in self.entries[low:high + 1]}
        elif qualifier & c4d.QCTRL:
            self.selected ^= {entry.id}
            self.anchor = index
        else:
            self.selected = {entry.id}
            self.anchor = index
        self.Redraw()
        self.dialog.guard(self.dialog.on_product_selection)


def _drag_type(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in SCENE_EXTENSIONS:
        return c4d.DRAGTYPE_FILENAME_SCENE
    if ext in IMAGE_EXTENSIONS:
        return c4d.DRAGTYPE_FILENAME_IMAGE
    return c4d.DRAGTYPE_FILENAME_OTHER


class LibraryDialog(AyonDialog):
    TITLE = "AYON Library"
    DIALOG_ID = ids.LIBRARY
    DEFAULT_SIZE = (900, 520)
    EVENT_KINDS = (events.CONTEXT, events.SERVER)

    def __init__(self):
        super().__init__()
        self.project_name = None
        self._projects = []
        self._folders = []
        self._folder_paths = {}
        self._loaders = None
        self._anatomy = None
        self._seen_event_ids = set()
        self._all_entries = []
        self._pending_folder = None
        self._loader_cache = {}  # version id -> loader names
        self.products = ProductArea(self)
        self.folders = TreeModel(
            [Column("name", "Folder")], empty_text="No folders")
        self.folders.on_select = lambda items: self.load_products()

    # -- layout ----------------------------------------------------------
    def build(self):
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=7):
            self.AddComboBox(ID_PROJECT, c4d.BFH_LEFT, 180, 0)
            self.AddEditText(ID_FOLDER_FILTER, c4d.BFH_LEFT, 160, 0)
            self.AddEditText(ID_PRODUCT_FILTER, c4d.BFH_SCALEFIT, 160, 0)
            self.AddComboBox(ID_VIEW_MODE, c4d.BFH_RIGHT, 80, 0)
            self.AddChild(ID_VIEW_MODE, MODE_LIST, "List")
            self.AddChild(ID_VIEW_MODE, MODE_GRID, "Grid")
            self.AddCheckbox(ID_SUBFOLDERS, c4d.BFH_RIGHT, 0, 0,
                             name="Subfolders")
            self.AddButton(ID_REFRESH, c4d.BFH_RIGHT, name="Refresh")
            self.AddButton(ID_QT, c4d.BFH_RIGHT, name="Qt...")
        self.GroupEnd()

        if self.GroupBegin(
            ID_SPLIT, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=2,
            groupflags=c4d.BFV_GRIDGROUP_ALLOW_WEIGHTS,
        ):
            self.add_tree(ID_FOLDERS, self.folders, min_size=(180, 200),
                          header=False)
            self.ScrollGroupBegin(
                ID_PRODUCTS_SCROLL, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                c4d.SCROLLGROUP_VERT | c4d.SCROLLGROUP_AUTOVERT,
                initw=300, inith=200)
            self.AddUserArea(
                ID_PRODUCTS, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT)
            self.AttachUserArea(self.products, ID_PRODUCTS)
            self.GroupEnd()
        self.GroupEnd()
        weights = c4d.BaseContainer()
        weights.SetInt32(c4d.GROUPWEIGHTS_PERCENT_W_CNT, 2)
        weights.SetFloat(c4d.GROUPWEIGHTS_PERCENT_W_VAL + 0, 25.0)
        weights.SetFloat(c4d.GROUPWEIGHTS_PERCENT_W_VAL + 1, 75.0)
        self.GroupWeightsLoad(ID_SPLIT, weights)

        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=6):
            self.AddComboBox(ID_VERSION, c4d.BFH_LEFT, 110, 0)
            self.AddButton(ID_LOAD_MENU, c4d.BFH_LEFT, name="Load...")
            self.AddButton(ID_MERGE, c4d.BFH_LEFT, name="Merge")
            self.AddButton(ID_ALEMBIC, c4d.BFH_LEFT, name="Alembic")
            self.AddButton(ID_XREF, c4d.BFH_LEFT, name="XRef")
            self.AddStaticText(ID_INFO, c4d.BFH_SCALEFIT, name="")
        self.GroupEnd()

    def InitValues(self):
        self.SetString(
            ID_FOLDER_FILTER, "Filter folders", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(
            ID_PRODUCT_FILTER, "Filter products",
            flags=c4d.EDITTEXT_HELPTEXT)
        self.SetInt32(ID_VIEW_MODE, self.products.mode)
        return super().InitValues()

    def empty_text(self):
        if not self.folders.selected_items():
            return "Select a folder."
        return "No products."

    def show_folder_path(self):
        return (
            self.GetBool(ID_SUBFOLDERS)
            or len(self.folders.selected_items()) > 1)

    # -- data ------------------------------------------------------------
    def refresh(self):
        self._fill_projects()
        if not self.folders.selected_items():
            self._select_context_folder()
        self.load_folders()

    def _select_context_folder(self):
        """Start in the folder of the current context."""
        if self.project_name != get_current_project_name():
            return
        folder_path = registered_host().get_current_context().get(
            "folder_path")
        folder = folder_path and ayon_api.get_folder_by_path(
            self.project_name, folder_path, fields={"id"})
        if folder:
            self._pending_folder = folder["id"]

    def _fill_projects(self):
        current = get_current_project_name()
        projects = [current]
        try:
            projects += sorted(
                p["name"] for p in ayon_api.get_projects(
                    fields={"name", "library"})
                if p.get("library") and p["name"] != current)
        except Exception:
            log.debug("Library projects not available", exc_info=True)
        self._projects = projects
        if self.project_name not in projects:
            self._reset_project(current)
        self.FreeChildren(ID_PROJECT)
        for index, name in enumerate(projects):
            label = name if index == 0 else f"{name}  (library)"
            self.AddChild(ID_PROJECT, index, label)
        self.SetInt32(ID_PROJECT, projects.index(self.project_name))

    def _reset_project(self, project_name):
        self.project_name = project_name
        self._loaders = None
        self._anatomy = None
        self._loader_cache = {}
        self.folders.select_keys([])

    def _set_project(self, project_name):
        if project_name == self.project_name:
            return
        self._reset_project(project_name)
        self.load_folders()

    def load_folders(self):
        self._folders = entities.get_folders(self.project_name)
        self._folder_paths = {f["id"]: f["path"] for f in self._folders}
        self._fill_folders()
        self.load_products()

    def _fill_folders(self):
        roots, matches = entities.folder_items(
            self._folders, self.GetString(ID_FOLDER_FILTER))
        self.folders.set_items(roots)
        if matches:
            self.folders.open_keys(matches)
            self.folders.refresh()
        pending, self._pending_folder = self._pending_folder, None
        if pending and self.folders.get(pending):
            self.folders.select_keys([pending])
            self.folders.show(pending)

    def _selected_folder_ids(self):
        folder_ids = {item.key for item in self.folders.selected_items()}
        if folder_ids and self.GetBool(ID_SUBFOLDERS):
            children = {}
            for folder in self._folders:
                children.setdefault(folder["parentId"], []).append(
                    folder["id"])
            stack = list(folder_ids)
            while stack:
                for child in children.get(stack.pop(), []):
                    if child not in folder_ids:
                        folder_ids.add(child)
                        stack.append(child)
        return folder_ids

    def load_products(self, keep_versions=False):
        folder_ids = self._selected_folder_ids()
        if not folder_ids:
            self.products.set_entries([])
            self.on_product_selection()
            return

        previous = {e.id: e for e in self.products.entries}
        project_name = self.project_name
        products = list(ayon_api.get_products(
            project_name, folder_ids=folder_ids,
            fields={"id", "name", "productType", "folderId"}))
        versions_by_product = {}
        if products:
            for version in ayon_api.get_versions(
                project_name, product_ids={p["id"] for p in products},
                fields=VERSION_FIELDS,
            ):
                versions_by_product.setdefault(
                    version["productId"], []).append(version)

        entries = []
        for product in sorted(products, key=lambda p: p["name"].lower()):
            entry = ProductEntry(
                product, self._folder_paths.get(product["folderId"], ""),
                versions_by_product.get(product["id"], []))
            old = previous.get(entry.id)
            if keep_versions and old and old.version:
                entry.version = next(
                    (v for v in entry.versions
                     if v["id"] == old.version["id"]), entry.version)
            if old and old.version and entry.version \
                    and old.version["id"] == entry.version["id"]:
                entry.thumbnail = old.thumbnail
            entries.append(entry)

        self._all_entries = entries
        self._fetch_repres(entries)
        self._apply_product_filter()
        self.products.thumbnails.request(project_name, entries)

    def _apply_product_filter(self):
        text = self.GetString(ID_PRODUCT_FILTER).strip().lower()
        entries = getattr(self, "_all_entries", [])
        if text:
            entries = [
                e for e in entries
                if text in e.name.lower() or text in e.product_type.lower()
            ]
        self.products.set_entries(entries)
        self.on_product_selection()
        self.set_status(f"{len(entries)} products")

    def _fetch_repres(self, entries):
        """Representations and drag path of the shown versions."""
        by_version = {e.version["id"]: e for e in entries if e.version}
        if not by_version:
            return
        for entry in entries:
            entry.repres = []
        for repre in ayon_api.get_representations(
            self.project_name, version_ids=set(by_version)
        ):
            by_version[repre["versionId"]].repres.append(repre)
        if self._anatomy is None:
            self._anatomy = Anatomy(self.project_name)
        for entry in by_version.values():
            entry.path = None
            repre = _best_repre(entry.repres)
            if repre is None:
                continue
            try:
                entry.path = str(get_representation_path_with_anatomy(
                    repre, self._anatomy))
            except Exception:
                log.debug("No path for %s", repre["id"], exc_info=True)

    def on_events(self, kinds):
        if events.CONTEXT in kinds and self._projects and \
                self._projects[0] != get_current_project_name():
            self.refresh()  # the session project changed
            return
        if events.SERVER not in kinds:
            return
        new = [
            e for e in events.recent_events()
            if e["id"] not in self._seen_event_ids
            and e.get("project") == self.project_name
        ]
        self._seen_event_ids.update(e["id"] for e in new)
        topics = {e["topic"] for e in new}
        if any(t.startswith("entity.folder.") for t in topics):
            self.load_folders()
        elif topics:
            self.load_products(keep_versions=True)

    # -- selection / version ---------------------------------------------
    def on_product_selection(self):
        selected = self.products.selected_entries()
        self.FreeChildren(ID_VERSION)
        single = selected[0] if len(selected) == 1 else None
        if single:
            for index, version in enumerate(single.versions):
                self.AddChild(ID_VERSION, index, _version_label(version))
            if single.version in single.versions:
                self.SetInt32(
                    ID_VERSION, single.versions.index(single.version))
        self.Enable(ID_VERSION, single is not None)

        available = self._loader_names(selected)
        self.Enable(ID_LOAD_MENU, bool(selected))
        for gadget_id, loader_name in QUICK_LOADERS.items():
            self.Enable(gadget_id, loader_name in available)

        info = ""
        if single and single.version:
            comment = (single.version.get("attrib") or {}).get("comment")
            info = ", ".join(filter(None, [
                single.folder_path, comment,
                ", ".join(sorted({_repre_ext(r) for r in single.repres})),
            ]))
        elif selected:
            info = f"{len(selected)} products selected"
        self.SetString(ID_INFO, info)

    def _set_version(self, index):
        selected = self.products.selected_entries()
        if len(selected) != 1 or not 0 <= index < len(selected[0].versions):
            return
        entry = selected[0]
        entry.version = entry.versions[index]
        entry.thumbnail = None
        self._fetch_repres([entry])
        self.products.thumbnails.request(self.project_name, [entry])
        self.products.Redraw()
        self.on_product_selection()

    # -- loading ---------------------------------------------------------
    def _get_loaders(self):
        if self._loaders is None:
            self._loaders = discover_loader_plugins(self.project_name)
        return self._loaders

    def _contexts(self, entries):
        repres = [r for e in entries for r in e.repres]
        if not repres:
            return {}
        return get_representation_contexts(self.project_name, repres)

    def _loader_names(self, entries):
        """Names of the loaders compatible with any of the entries.

        Same check as AYON (`loaders_from_repre_context`), cached per
        shown version.
        """
        names = set()
        missing = [
            e for e in entries
            if e.version and e.version["id"] not in self._loader_cache]
        if missing:
            contexts = self._contexts(missing)
            loaders = self._get_loaders()
            for entry in missing:
                self._loader_cache[entry.version["id"]] = {
                    loader.__name__
                    for repre in entry.repres
                    if contexts.get(repre["id"])
                    for loader in loaders_from_repre_context(
                        loaders, contexts[repre["id"]])
                }
        for entry in entries:
            if entry.version:
                names |= self._loader_cache.get(entry.version["id"], set())
        return names

    def load(self, entries, loader_name=None, loader=None, repre_id=None):
        """Load entries with a loader (by class name or class)."""
        contexts = self._contexts(entries)
        loaded, errors = 0, []
        for entry in entries:
            repres = [r for r in entry.repres
                      if repre_id is None or r["id"] == repre_id]
            # Preferred representation first
            best = _best_repre(repres)
            repres.sort(key=lambda r: r is not best)
            done = False
            for repre in repres:
                context = contexts.get(repre["id"])
                if not context:
                    continue
                candidates = loaders_from_repre_context(
                    self._get_loaders(), context)
                for candidate in candidates:
                    if loader is not None and candidate is not loader:
                        continue
                    if loader_name and candidate.__name__ != loader_name:
                        continue
                    try:
                        load_with_repre_context(candidate, context)
                        loaded += 1
                    except Exception as error:
                        log.warning("Loading failed", exc_info=True)
                        errors.append(f"{entry.name}: {error}")
                    done = True
                    break
                if done:
                    break
            if not done:
                errors.append(f"{entry.name}: no matching loader")
        c4d.EventAdd()
        if errors:
            c4d.gui.MessageDialog("Loading failed:\n" + "\n".join(errors))
        if loaded:
            self.set_status(f"Loaded {loaded} product(s).")
        return loaded

    def load_default(self, entries):
        """First loader of DEFAULT_LOADERS that fits, per product."""
        for entry in entries:
            names = self._loader_names([entry])
            loader_name = next(
                (n for n in DEFAULT_LOADERS if n in names), None)
            if loader_name:
                self.load([entry], loader_name)
            elif len(entries) == 1:
                self.show_menu()

    def show_menu(self):
        entries = self.products.selected_entries()
        if not entries:
            return
        menu = []
        if len(entries) == 1:
            menu.extend(self._repre_menu(entries[0]))
        else:
            for loader in sorted(self._get_loaders(), key=lambda l: l.order):
                if loader.__name__ in self._loader_names(entries):
                    menu.append((
                        loader.label or loader.__name__,
                        lambda l=loader: self.load(entries, loader=l)))
        menu.append(None)
        entry = entries[0]
        if len(entries) == 1 and len(entry.versions) > 1:
            menu.append(("Version", [
                ("*" + _version_label(v) if v is entry.version
                 else _version_label(v),
                 lambda i=i: self._select_version(i))
                for i, v in enumerate(entry.versions)
            ]))
        if entry.path:
            menu.append(("Show in Explorer",
                         lambda: widgets.open_in_explorer(entry.path)))
            menu.append(("Copy Path", lambda: c4d.CopyStringToClipboard(
                entry.path)))
        if entry.version:
            menu.append(("Open in AYON", lambda: self.open_in_ayon(entry)))
        widgets.popup(menu)

    def _select_version(self, index):
        self.SetInt32(ID_VERSION, index)
        self._set_version(index)

    def _repre_menu(self, entry):
        contexts = self._contexts([entry])
        loaders = self._get_loaders()
        menu = []
        for repre in sorted(entry.repres, key=lambda r: r["name"]):
            context = contexts.get(repre["id"])
            if not context:
                continue
            candidates = sorted(
                loaders_from_repre_context(loaders, context),
                key=lambda l: l.order)
            if not candidates:
                continue
            menu.append((repre["name"], [
                (loader.label or loader.__name__,
                 lambda l=loader, r=repre["id"]: self.load(
                     [entry], loader=l, repre_id=r))
                for loader in candidates
            ]))
        return menu or [("No loader for these files", None)]

    def open_in_ayon(self, entry):
        base_url = ayon_api.get_base_url().rstrip("/")
        query = urllib.parse.urlencode({
            "project": self.project_name, "type": "version",
            "id": entry.version["id"]})
        webbrowser.open_new_tab(
            f"{base_url}/projects/{self.project_name}/products?{query}")

    # -- commands --------------------------------------------------------
    def on_command(self, gadget_id, msg):
        if gadget_id == ID_PROJECT:
            index = self.GetInt32(ID_PROJECT)
            if 0 <= index < len(self._projects):
                self._set_project(self._projects[index])
        elif gadget_id == ID_FOLDER_FILTER:
            self._fill_folders()
        elif gadget_id == ID_PRODUCT_FILTER:
            self._apply_product_filter()
        elif gadget_id == ID_SUBFOLDERS:
            self.load_products()
        elif gadget_id == ID_VIEW_MODE:
            self.products.mode = self.GetInt32(ID_VIEW_MODE)
            self.products.LayoutChanged()
            self.products.Redraw()
        elif gadget_id == ID_REFRESH:
            self._loaders = None
            self._loader_cache = {}
            self.refresh()
        elif gadget_id == ID_QT:
            show_browser()
        elif gadget_id == ID_VERSION:
            self._set_version(self.GetInt32(ID_VERSION))
        elif gadget_id == ID_LOAD_MENU:
            self.show_menu()
        elif gadget_id in QUICK_LOADERS:
            self.load(self.products.selected_entries(),
                      QUICK_LOADERS[gadget_id])


COMMANDS = [
    Command(
        ids.LIBRARY, "Library...", icon=widgets.ayon_icon("folder-favorite"),
        order=40, dialog=LibraryDialog,
    ),
    # Legacy "Load..." opens the same window, not in the menu
    Command(
        ids.LOAD, "Load...", LibraryDialog.open,
        icon=widgets.ayon_icon("loader"), section=None,
    ),
]
