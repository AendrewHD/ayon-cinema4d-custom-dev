"""Snapshot of the active viewport.

Python can't read the viewport pixels (`BaseDraw::GetViewportImage` is C++
only), so the current frame is rendered with the Viewport Renderer, which
Maxon recommends for this. It uses the active view's camera and the view's
pixel size, so the image matches the whole viewport at any resolution.
Grid, HUD, handles and other helpers are left out (playblast filters).
"""
import os
import logging

import c4d

from . import exporters

log = logging.getLogger(__name__)


def get_view_size(doc):
    """Pixel size (width, height) of the active view."""
    bd = doc.GetActiveBaseDraw()
    if bd is None:
        return None
    frame = bd.GetFrame()
    width = frame["cr"] - frame["cl"] + 1  # right / bottom are inclusive
    height = frame["cb"] - frame["ct"] + 1
    if width <= 1 or height <= 1:
        return None
    return width, height


def capture_active_view(filepath, doc=None):
    """Render the active view for the current frame. Returns path or None."""
    doc = doc or c4d.documents.GetActiveDocument()
    size = get_view_size(doc)
    if size is None:
        return None

    frame = doc.GetTime().GetFrame(doc.GetFps())
    base = os.path.splitext(filepath)[0]
    files = exporters.render_playblast(
        base,
        frame_start=frame,
        frame_end=frame,
        width=size[0],
        height=size[1],
        geometry_only=False,
        show_splines=True,
        show_nulls=True,
        doc=doc,
    )
    rendered = os.path.join(os.path.dirname(base), files[0])
    if os.path.normcase(rendered) != os.path.normcase(filepath):
        os.replace(rendered, filepath)
    return filepath
