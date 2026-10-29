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
    """Starts a file drag when selected items are dragged.

    Installed on the application: the grid view shows every item as a card
    widget on top of the viewport, so the mouse events go to the cards (and
    their child widgets), not to the viewport. Events are matched to a view
    by widget ancestry and global position.
    """

    def __init__(self, browser_widget, views):
        super().__init__(browser_widget)
        self._browser = browser_widget
        self._views = views
        self._start = None  # (view, global pos)

    def _view_of(self, widget):
        if not isinstance(widget, QtWidgets.QWidget):
            return None
        for view in self._views:
            viewport = view.viewport()
            if widget is viewport or viewport.isAncestorOf(widget):
                return view
        return None

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type not in (
            QtCore.QEvent.MouseButtonPress,
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QEvent.MouseMove,
        ):
            return False

        if event_type == QtCore.QEvent.MouseButtonRelease:
            self._start = None
            return False

        view = self._view_of(obj)
        if view is None or not view.isVisible():
            return False

        global_pos = _global_pos(event)
        if event_type == QtCore.QEvent.MouseButtonPress:
            self._start = None
            if event.button() == QtCore.Qt.LeftButton:
                self._start = (view, global_pos)
            return False

        if self._start is None or not event.buttons() & QtCore.Qt.LeftButton:
            return False
        start_view, start_pos = self._start
        if start_view is not view:
            return False
        distance = (global_pos - start_pos).manhattanLength()
        if distance < QtWidgets.QApplication.startDragDistance():
            return False

        self._start = None
        index = view.indexAt(view.viewport().mapFromGlobal(start_pos))
        if not index.isValid():
            return False
        # The grid selects column 0 only, `isRowSelected` needs all columns
        index = index.sibling(index.row(), 0)
        selection = view.selectionModel()
        if not selection.isSelected(index):
            # Card child widgets may swallow the click that selects
            selection.select(
                index,
                QtCore.QItemSelectionModel.ClearAndSelect
                | QtCore.QItemSelectionModel.Rows,
            )
        self._start_drag(view)
        return True

    def _start_drag(self, view):
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
        drag = QtGui.QDrag(view)
        drag.setMimeData(mime)
        exec_ = getattr(drag, "exec", None) or drag.exec_
        exec_(QtCore.Qt.CopyAction)


def _global_pos(event):
    """Global mouse position as QPoint (Qt5 and Qt6)."""
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def install(window):
    """Add drag support to a Browser window (no-op for the legacy Loader)."""
    browser = getattr(window, "browser_widget", None)
    table = getattr(browser, "_table", None)
    if table is None or not hasattr(browser, "_get_selected_version_ids"):
        log.debug("Loader window has no Browser views, drag not added.")
        return
    if getattr(browser, "_ayon_c4d_drag_filter", None):
        return

    views = [
        view for view in (
            getattr(table, "table", None), getattr(table, "card_view", None)
        )
        if view is not None
    ]
    drag_filter = _DragFilter(browser, views)
    QtWidgets.QApplication.instance().installEventFilter(drag_filter)
    browser._ayon_c4d_drag_filter = drag_filter
