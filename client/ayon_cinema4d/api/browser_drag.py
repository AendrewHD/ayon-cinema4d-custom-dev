"""Drag versions from the AYON Browser into Cinema 4D.

The Browser has no drag support of its own. This adds it from the host side:
dragging selected rows starts a file drag (like Explorer), and Cinema 4D
handles the drop natively - merge in the viewport / Object Manager, image
nodes in the Node Editor, texture on objects. Dropped files are not tracked
as AYON containers, use Merge / Load XRef for that.
"""
import logging

import ayon_api
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.load import get_representation_path_with_anatomy

log = logging.getLogger(__name__)

# First match wins per version (scene / model formats before images)
EXTENSION_PRIORITY = [
    "c4d", "fbx", "abc", "obj", "usd", "usdc", "usda", "usdz", "gltf", "glb",
    "exr", "tx", "tif", "tiff", "png", "jpg", "jpeg", "hdr", "tga", "psd",
    "mov", "mp4", "wav",
]
SKIP_NAMES = {"thumbnail", "preview"}


def _repre_ext(repre):
    ext = (repre.get("context") or {}).get("ext") or repre["name"]
    return ext.lower().lstrip(".")


def get_drag_paths(project_name, version_ids):
    """Best representation file per version."""
    anatomy = Anatomy(project_name)
    by_version = {}
    for repre in ayon_api.get_representations(
        project_name, version_ids=version_ids
    ):
        ext = _repre_ext(repre)
        if repre["name"] in SKIP_NAMES or ext not in EXTENSION_PRIORITY:
            continue
        current = by_version.get(repre["versionId"])
        rank = EXTENSION_PRIORITY.index(ext)
        if current is None or rank < current[0]:
            by_version[repre["versionId"]] = (rank, repre)

    paths = []
    for _, repre in by_version.values():
        try:
            paths.append(get_representation_path_with_anatomy(repre, anatomy))
        except Exception:
            log.warning(f"No path for representation {repre['id']}",
                        exc_info=True)
    return [str(path) for path in paths]


class _DragFilter(QtCore.QObject):
    """Starts a file drag when selected rows are dragged."""

    def __init__(self, browser_widget, view):
        super().__init__(view)
        self._browser = browser_widget
        self._view = view
        self._start = None

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type == QtCore.QEvent.MouseButtonPress:
            self._start = None
            if event.button() == QtCore.Qt.LeftButton:
                self._start = event.pos()
        elif event_type == QtCore.QEvent.MouseButtonRelease:
            self._start = None
        elif (
            event_type == QtCore.QEvent.MouseMove
            and self._start is not None
            and event.buttons() & QtCore.Qt.LeftButton
        ):
            distance = (event.pos() - self._start).manhattanLength()
            if distance < QtWidgets.QApplication.startDragDistance():
                return False
            index = self._view.indexAt(self._start)
            self._start = None
            selection = self._view.selectionModel()
            if index.isValid() and selection.isRowSelected(
                index.row(), index.parent()
            ):
                self._start_drag()
                return True
        return False

    def _start_drag(self):
        project_name = self._browser._controller.current_project
        version_ids = self._browser._get_selected_version_ids()
        if not project_name or not version_ids:
            return
        paths = get_drag_paths(project_name, version_ids)
        if not paths:
            log.info("Nothing to drag: no supported representation.")
            return

        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(path) for path in paths])
        drag = QtGui.QDrag(self._view)
        drag.setMimeData(mime)
        drag.exec_(QtCore.Qt.CopyAction)


def install(window):
    """Add drag support to a Browser window (no-op for the legacy Loader)."""
    browser = getattr(window, "browser_widget", None)
    table = getattr(browser, "_table", None)
    if table is None or not hasattr(browser, "_get_selected_version_ids"):
        log.debug("Loader window has no Browser views, drag not added.")
        return
    if getattr(browser, "_ayon_c4d_drag_filters", None):
        return

    filters = []
    for view in (table.table, table.card_view):
        drag_filter = _DragFilter(browser, view)
        view.viewport().installEventFilter(drag_filter)
        filters.append(drag_filter)
    browser._ayon_c4d_drag_filters = filters
