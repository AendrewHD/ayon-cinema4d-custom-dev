"""Dockable 'Publish Status' dialog.

Shows for the active document: what was published from this workfile, the
task's latest workfile publish and outdated loaded containers.
"""
import os
import logging
from datetime import datetime

import c4d
import ayon_api

from ayon_core.pipeline import registered_host

from . import doc_context

log = logging.getLogger(__name__)

ID_REFRESH = 1000
ID_HEADER = 1001
ID_ROWS = 1002


def _time(value):
    """Server timestamp -> local 'YYYY-MM-DD HH:MM'."""
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.astimezone().strftime("%Y-%m-%d %H:%M")
    except (AttributeError, ValueError):
        return value or ""


def _same_path(a, b):
    return bool(a and b) and a.replace("\\", "/").lower() == b.lower()


def get_status(doc):
    """Collect the status lines of the document.

    Returns:
        tuple[str, list[str]]: Header and rows.
    """
    host = registered_host()
    context = doc_context.get_document_context(doc) or host.get_current_context()
    project_name = context["project_name"]
    path = doc_context.get_document_path(doc)
    header = f"{context['folder_path']}  /  {context['task_name']}"
    if not path:
        return header, ["Document is not saved."]

    folder = ayon_api.get_folder_by_path(
        project_name, context["folder_path"], fields={"id"})
    task = folder and ayon_api.get_task_by_name(
        project_name, folder["id"], context["task_name"], fields={"id"})
    if not task:
        return header, ["Task not found on the server."]

    rootless = doc_context.get_rootless_path(project_name, path)
    versions = list(ayon_api.get_versions(
        project_name,
        task_ids=[task["id"]],
        fields={"id", "version", "productId", "createdAt", "author",
                "attrib.source"},
    ))
    products = {
        product["id"]: product
        for product in ayon_api.get_products(
            project_name,
            product_ids={v["productId"] for v in versions},
            fields={"id", "name", "productType"},
        )
    }

    def label(version):
        product = products.get(version["productId"], {})
        return (
            f"{product.get('name', '?')}  v{version['version']:03d}   "
            f"{_time(version['createdAt'])}  {version.get('author') or ''}"
        )

    rows = []
    own = [
        v for v in versions
        if _same_path(v["attrib"].get("source"), rootless)
    ]
    if own:
        rows.append("Published from this file:")
        rows.extend(f"    {label(v)}" for v in own)
    else:
        rows.append("This file is not published.")

    workfiles = sorted(
        (
            v for v in versions
            if products.get(v["productId"], {}).get("productType")
            == "workfile"
        ),
        key=lambda v: v["createdAt"],
    )
    if workfiles and workfiles[-1] not in own:
        latest = workfiles[-1]
        source = os.path.basename(latest["attrib"].get("source") or "")
        rows.append("Latest workfile publish of the task:")
        rows.append(f"    {label(latest)}")
        rows.append(f"    from {source}")

    rows.extend(_container_rows(project_name, host))
    return header, rows


def _container_rows(project_name, host):
    repre_ids = {c["representation"] for c in host.get_containers()}
    if not repre_ids:
        return []

    repres = ayon_api.get_representations(
        project_name, representation_ids=repre_ids, fields={"versionId"})
    version_ids = {r["versionId"] for r in repres}
    versions = list(ayon_api.get_versions(
        project_name, version_ids=version_ids,
        fields={"id", "version", "productId"}))
    last = ayon_api.get_last_versions(
        project_name, {v["productId"] for v in versions},
        fields={"version", "productId"})
    outdated = [
        v for v in versions
        if last.get(v["productId"])
        and v["version"] < last[v["productId"]]["version"]
    ]
    text = f"Loaded: {len(versions)} versions"
    if outdated:
        text += f", {len(outdated)} outdated (AYON > Manage...)"
    return [text]


class PublishStatusDialog(c4d.gui.GeDialog):

    def __init__(self):
        super().__init__()
        self._rows = []

    def CreateLayout(self):
        self.SetTitle("AYON Publish Status")
        self.GroupBorderSpace(6, 6, 6, 6)
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
        return True

    def InitValues(self):
        self.update()
        return True

    def Command(self, id, msg):
        if id == ID_REFRESH:
            self.update()
        return True

    def update(self):
        try:
            header, rows = get_status(c4d.documents.GetActiveDocument())
        except Exception as error:
            log.warning("Publish status failed", exc_info=True)
            header, rows = "", [f"Error: {error}"]

        self.SetString(ID_HEADER, header)
        self.LayoutFlushGroup(ID_ROWS)
        for i, row in enumerate(rows):
            self.AddStaticText(ID_ROWS + 1 + i, c4d.BFH_SCALEFIT, name=row)
        self.LayoutChanged(ID_ROWS)


_dialog = None


def _get_dialog():
    global _dialog
    if _dialog is None:
        _dialog = PublishStatusDialog()
    return _dialog


def open_dialog(plugin_id):
    dialog = _get_dialog()
    if dialog.IsOpen():
        dialog.update()
        return True
    return dialog.Open(
        c4d.DLG_TYPE_ASYNC, pluginid=plugin_id, defaultw=420, defaulth=180)


def restore_dialog(plugin_id, sec_ref):
    return _get_dialog().Restore(pluginid=plugin_id, secret=sec_ref)


def refresh():
    """Update the dialog if it is open."""
    if _dialog is not None and _dialog.IsOpen():
        _dialog.update()
