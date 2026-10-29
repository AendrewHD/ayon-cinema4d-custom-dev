"""Manage: native scene inventory of the loaded AYON containers.

Lists the containers of the active document with their version state,
updates / switches versions, selects and removes them. Refreshes when
containers change in the document and when new versions are published.
"""
import logging

import c4d
import ayon_api

from ayon_core.pipeline import get_current_project_name, registered_host
from ayon_core.pipeline.load import (
    HeroVersionType,
    remove_container,
    update_container,
)

from ayon_cinema4d.api import lib
from ayon_cinema4d.api.ui import events, ids, widgets
from ayon_cinema4d.api.ui.dialog import AyonDialog
from ayon_cinema4d.api.ui.registry import Command
from ayon_cinema4d.api.ui.tree import Column, Item, TreeModel

from .classic import show_scene_inventory

log = logging.getLogger(__name__)

ID_TREE = 1000
ID_REFRESH = 1001
ID_UPDATE = 1002
ID_UPDATE_ALL = 1003
ID_SELECT = 1004
ID_REMOVE = 1005
ID_OUTDATED_ONLY = 1006
ID_FILTER = 1007
ID_SUMMARY = 1008
ID_QT = 1009

CHECK_INTERVAL = 1000  # ms, scene changes are checked at most this often

STATE_LATEST = "latest"
STATE_OUTDATED = "outdated"
STATE_HERO = "hero"
STATE_MISSING = "missing"
STATE_COLORS = {
    STATE_LATEST: widgets.GREEN,
    STATE_OUTDATED: widgets.ORANGE,
    STATE_HERO: widgets.BLUE,
    STATE_MISSING: widgets.RED,
}


def _version_label(version):
    if version is None:
        return "?"
    if version["version"] < 0:
        return "hero"
    return f"v{version['version']:03d}"


def collect_inventory(containers):
    """Server info per container.

    Returns:
        list[dict]: One row per container: container, project_name,
            folder, product, version, last_version, repre, state.
    """
    by_project = {}
    for container in containers:
        project_name = (
            container.get("project_name") or get_current_project_name())
        by_project.setdefault(project_name, []).append(container)

    rows = []
    for project_name, project_containers in by_project.items():
        repre_ids = {c.get("representation") for c in project_containers}
        repre_ids.discard(None)
        repres = {
            r["id"]: r for r in ayon_api.get_representations(
                project_name, representation_ids=repre_ids,
                fields={"id", "name", "versionId"})
        } if repre_ids else {}
        versions = {
            v["id"]: v for v in ayon_api.get_versions(
                project_name,
                version_ids={r["versionId"] for r in repres.values()},
                fields={"id", "version", "productId", "status"})
        } if repres else {}
        product_ids = {v["productId"] for v in versions.values()}
        products = {
            p["id"]: p for p in ayon_api.get_products(
                project_name, product_ids=product_ids,
                fields={"id", "name", "productType", "folderId"})
        } if product_ids else {}
        folders = {
            f["id"]: f for f in ayon_api.get_folders(
                project_name,
                folder_ids={p["folderId"] for p in products.values()},
                fields={"id", "path"})
        } if products else {}
        last_versions = ayon_api.get_last_versions(
            project_name, product_ids, fields={"id", "version", "productId"}
        ) if product_ids else {}

        for container in project_containers:
            repre = repres.get(container.get("representation"))
            version = repre and versions.get(repre["versionId"])
            product = version and products.get(version["productId"])
            folder = product and folders.get(product["folderId"])
            last = product and last_versions.get(product["id"])
            if not version:
                state = STATE_MISSING
            elif version["version"] < 0:
                state = STATE_HERO
            elif last and version["version"] < last["version"]:
                state = STATE_OUTDATED
            else:
                state = STATE_LATEST
            rows.append({
                "container": container,
                "project_name": project_name,
                "folder": folder,
                "product": product,
                "version": version,
                "last_version": last,
                "repre": repre,
                "state": state,
            })
    return rows


def _row_item(row):
    container = row["container"]
    product = row["product"] or {}
    product_type = product.get("productType", "")
    state = row["state"]
    node = container.get("node")
    key = container.get("objectName") or str(id(container))
    if node is not None and node.IsAlive():
        key = str(node.GetGUID())  # names are not guaranteed unique
    return Item(
        key,
        {
            "name": (
                container.get("namespace") or container.get("name")
                or container.get("objectName", "")),
            "product": product.get("name", container.get("name", "")),
            "version": _version_label(row["version"]),
            "latest": _version_label(row["last_version"]),
            "repre": (row["repre"] or {}).get("name", ""),
            "loader": container.get("loader", ""),
            "folder": (row["folder"] or {}).get("path", ""),
        },
        data=row,
        swatch=widgets.color_for(product_type),
        colors={"version": STATE_COLORS[state]},
        dim=node is not None and not node.IsAlive(),
        tooltip=f"{product_type}  -  {container.get('objectName', '')}",
    )


STATE_ORDER = [STATE_LATEST, STATE_HERO, STATE_OUTDATED, STATE_MISSING]


def _group_items(rows_items):
    """One parent per product (like the Qt inventory), containers below."""
    groups = {}
    for row, item in rows_items:
        product = row["product"] or {}
        key = product.get("id") or f"missing:{item.key}"
        groups.setdefault(key, []).append((row, item))

    parents = []
    for key, members in groups.items():
        rows = [row for row, _ in members]
        children = [item for _, item in members]
        first = children[0]
        state = max((r["state"] for r in rows), key=STATE_ORDER.index)
        versions = {first_v["id"] for first_v in
                    (r["version"] for r in rows) if first_v}
        values = dict(first.values)
        label = values["product"] or values["name"]
        values["name"] = f"{label}  ({len(children)})"
        values["product"] = (rows[0]["product"] or {}).get("productType", "")
        if len(versions) > 1:
            values["version"] = "mixed"
        for child in children:
            child.values["product"] = ""
            child.values["folder"] = ""
        parents.append(Item(
            f"group:{key}", values,
            data={"group": True, "state": state, "rows": rows},
            swatch=first.swatch, bold=True,
            colors={"version": STATE_COLORS[state]},
            children=children,
        ))
    parents.sort(key=lambda i: i.text("name").lower())
    return parents


def _scene_signature(doc):
    """Cheap fingerprint of the containers in the document."""
    return (
        id(doc),
        tuple(
            (c.get("objectName"), c.get("representation"))
            for c in registered_host().get_containers()
        ),
    )


class ManageDialog(AyonDialog):
    TITLE = "AYON Manage"
    DIALOG_ID = ids.MANAGE
    DEFAULT_SIZE = (720, 360)
    EVENT_KINDS = (events.CONTEXT, events.SERVER)

    def __init__(self):
        super().__init__()
        self._rows = []
        self._signature = None
        self._scene_dirty = False
        self._known_groups = set()
        self.model = TreeModel(
            [
                Column("name", "Name"),
                Column("product", "Type"),
                Column("version", "Version", width=70, pill=True),
                Column("latest", "Latest", width=60),
                Column("repre", "Repre", width=60),
                Column("loader", "Loader"),
                Column("folder", "Folder"),
            ],
            empty_text="Nothing loaded from AYON in this document.",
        )
        self.model.on_double_click = lambda item: self.select_in_scene(
            self._containers([item]))
        self.model.context_menu = self._context_menu
        self.model.on_select = lambda items: self._update_buttons()
        self.model.on_delete = lambda items: self.remove(
            self._containers(items))

    @staticmethod
    def _containers(items):
        """Container items of the selection (groups -> their children)."""
        result, seen = [], set()
        for item in items:
            for child in (item.children if item.data.get("group") else [item]):
                if child.key not in seen:
                    seen.add(child.key)
                    result.append(child)
        return result

    # -- layout ----------------------------------------------------------
    def build(self):
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=9):
            self.AddButton(ID_REFRESH, c4d.BFH_LEFT, name="Refresh")
            self.AddButton(ID_UPDATE, c4d.BFH_LEFT, name="Update to Latest")
            self.AddButton(ID_UPDATE_ALL, c4d.BFH_LEFT, name="Update All")
            self.AddButton(ID_SELECT, c4d.BFH_LEFT, name="Select")
            self.AddButton(ID_REMOVE, c4d.BFH_LEFT, name="Remove")
            self.AddCheckbox(
                ID_OUTDATED_ONLY, c4d.BFH_LEFT, 0, 0, name="Outdated only")
            self.AddEditText(ID_FILTER, c4d.BFH_SCALEFIT, 120, 0)
            self.AddStaticText(ID_SUMMARY, c4d.BFH_RIGHT, 160, 0, name="")
            self.AddButton(ID_QT, c4d.BFH_RIGHT, name="Qt...")
        self.GroupEnd()
        self.add_tree(ID_TREE, self.model, min_size=(400, 150))

    def InitValues(self):
        result = super().InitValues()
        self.SetTimer(CHECK_INTERVAL)
        return result

    # -- data ------------------------------------------------------------
    def refresh(self):
        doc = c4d.documents.GetActiveDocument()
        self._signature = _scene_signature(doc)
        self._scene_dirty = False
        containers = list(registered_host().get_containers())
        self._rows = collect_inventory(containers)
        self._fill()

    def _fill(self):
        text_filter = self.GetString(ID_FILTER).strip().lower()
        outdated_only = self.GetBool(ID_OUTDATED_ONLY)
        rows_items = []
        for row in self._rows:
            if outdated_only and row["state"] != STATE_OUTDATED:
                continue
            item = _row_item(row)
            if text_filter and not any(
                text_filter in str(v).lower() for v in item.values.values()
            ):
                continue
            rows_items.append((row, item))
        groups = _group_items(rows_items)
        # New groups open, collapsed ones stay collapsed
        known = self._known_groups
        self.model.open_keys(g.key for g in groups if g.key not in known)
        known.update(g.key for g in groups)
        self.model.set_items(groups)

        outdated = sum(1 for r in self._rows if r["state"] == STATE_OUTDATED)
        missing = sum(1 for r in self._rows if r["state"] == STATE_MISSING)
        summary = f"{len(self._rows)} loaded"
        if outdated:
            summary += f", {outdated} outdated"
        if missing:
            summary += f", {missing} missing"
        self.SetString(ID_SUMMARY, summary)
        self.SetString(ID_UPDATE_ALL, f"Update All ({outdated})")
        self.Enable(ID_UPDATE_ALL, bool(outdated))
        self._update_buttons()
        self.set_status("")

    def _update_buttons(self):
        selected = bool(self.model.selected_items())
        for gadget_id in (ID_UPDATE, ID_SELECT, ID_REMOVE):
            self.Enable(gadget_id, selected)

    def on_document_change(self):
        self._scene_dirty = True

    def Timer(self, msg):
        if not self._scene_dirty or widgets.is_playing():
            return
        self._scene_dirty = False
        doc = c4d.documents.GetActiveDocument()
        if self.guard(_scene_signature, doc) != self._signature:
            self.guard(self.refresh)

    # -- actions ---------------------------------------------------------
    def on_command(self, gadget_id, msg):
        if gadget_id == ID_REFRESH:
            self.refresh()
        elif gadget_id == ID_UPDATE:
            self.set_version(
                self._containers(self.model.selected_items()), -1)
        elif gadget_id == ID_UPDATE_ALL:
            self.set_version(
                [i for i in self.model.all_items()
                 if not i.data.get("group")
                 and i.data["state"] == STATE_OUTDATED], -1)
        elif gadget_id == ID_SELECT:
            self.select_in_scene(
                self._containers(self.model.selected_items()))
        elif gadget_id == ID_REMOVE:
            self.remove(self._containers(self.model.selected_items()))
        elif gadget_id in (ID_OUTDATED_ONLY, ID_FILTER):
            self._fill()
        elif gadget_id == ID_QT:
            show_scene_inventory()

    def set_version(self, items, version):
        """Update containers, `version`: -1 latest, int or HeroVersionType."""
        if not items:
            return
        errors = []
        for item in items:
            container = item.data["container"]
            try:
                update_container(container, version)
            except Exception as error:
                log.warning(
                    f"Update of {container.get('objectName')} failed",
                    exc_info=True)
                errors.append(f"{container.get('objectName')}: {error}")
        c4d.EventAdd()
        self.refresh()
        if errors:
            c4d.gui.MessageDialog("Update failed:\n" + "\n".join(errors))
        else:
            self.set_status(f"Updated {len(items)} container(s).")

    def select_in_scene(self, items):
        doc = c4d.documents.GetActiveDocument()
        nodes = []
        for item in items:
            node = item.data["container"].get("node")
            if node is not None and node.IsAlive():
                nodes.extend(lib.get_objects_from_container(node))
        lib.set_selection(doc, nodes)
        c4d.EventAdd()

    def select_containers(self, items):
        doc = c4d.documents.GetActiveDocument()
        nodes = [item.data["container"].get("node") for item in items]
        lib.set_selection(doc, [n for n in nodes if n and n.IsAlive()])
        c4d.EventAdd()

    def remove(self, items):
        if not items:
            return
        names = ", ".join(i.text("name") for i in items[:5])
        if len(items) > 5:
            names += ", ..."
        if not widgets.confirm(f"Remove {len(items)} container(s)?\n{names}"):
            return
        for item in items:
            try:
                remove_container(item.data["container"])
            except Exception:
                log.warning("Remove failed", exc_info=True)
        c4d.EventAdd()
        self.refresh()

    def _version_entries(self, items):
        """'Set Version' submenu when all items share one product."""
        product_ids = {
            (i.data["product"] or {}).get("id") for i in items}
        if len(product_ids) != 1 or None in product_ids:
            return [("Set Version (one product only)", None)]
        project_name = items[0].data["project_name"]
        versions = sorted(
            ayon_api.get_versions(
                project_name, product_ids=product_ids,
                fields={"id", "version"}),
            key=lambda v: v["version"], reverse=True)
        current = {
            (i.data["version"] or {}).get("version") for i in items}

        entries = []
        for version in versions:
            label = _version_label(version)
            if version["version"] in current:
                label = "*" + label
            value = (
                HeroVersionType(version["version"])
                if version["version"] < 0 else version["version"])
            entries.append(
                (label, lambda v=value: self.set_version(items, v)))
        return [("Set Version", entries)]

    def _context_menu(self, items):
        items = self._containers(items)
        if not items:
            return [("Refresh", self.refresh)]
        return [
            ("Update to Latest", lambda: self.set_version(items, -1)),
            *self._version_entries(items),
            None,
            ("Select Objects", lambda: self.select_in_scene(items)),
            ("Select Container", lambda: self.select_containers(items)),
            None,
            ("Remove...", lambda: self.remove(items)),
        ]


COMMANDS = [
    Command(
        ids.MANAGE, "Manage...", icon=widgets.ayon_icon("inventory"),
        order=30, dialog=ManageDialog,
    ),
]
