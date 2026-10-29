"""Publish: native panel for the publish instances of the active document.

Lists the instances (toggle active, select, remove), creates new ones with
default options and opens the AYON Publisher for validation and publishing,
which stays a Qt window.
"""
import logging

import c4d

from ayon_core.pipeline import registered_host
from ayon_core.pipeline.create import CreateContext

from ayon_cinema4d.api import lib, plugin
from ayon_cinema4d.api.ui import events, ids, widgets
from ayon_cinema4d.api.ui.dialog import AyonDialog
from ayon_cinema4d.api.ui.registry import Command
from ayon_cinema4d.api.ui.tree import Column, Item, TreeModel

from .classic import show_publisher

log = logging.getLogger(__name__)

ID_TREE = 1000
ID_PUBLISH = 1001
ID_CREATE = 1002
ID_CREATE_QT = 1003
ID_REFRESH = 1004
ID_SUMMARY = 1005
ID_SAVE = 1006

CHECK_INTERVAL = 1000  # ms


def _default_pre_create_data(creator):
    data = {}
    for attr_def in creator.get_pre_create_attr_defs() or []:
        key = getattr(attr_def, "key", None)
        if key:
            data[key] = getattr(attr_def, "default", None)
    return data


def _default_variant(creator):
    variant = getattr(creator, "default_variant", None)
    if variant:
        return variant
    variants = getattr(creator, "default_variants", None) or ["Main"]
    return variants[0]


def _scene_signature(doc):
    return (id(doc), tuple(
        (creator_id, obj.GetName())
        for creator_id, obj in plugin.iter_instance_objects(doc)
    ))


class PublishDialog(AyonDialog):
    TITLE = "AYON Publish"
    DIALOG_ID = ids.PUBLISH
    DEFAULT_SIZE = (520, 320)
    EVENT_KINDS = (events.CONTEXT, events.PUBLISH)
    SHOW_CONTEXT = True

    def __init__(self):
        super().__init__()
        self.create_context = None
        self._signature = None
        self._scene_dirty = False
        self.model = TreeModel(
            [
                Column("active", "", width=24, checkbox=True),
                Column("product", "Product"),
                Column("type", "Type"),
                Column("variant", "Variant"),
                Column("context", "Context"),
            ],
            empty_text="Nothing to publish. Create an instance first.",
            flat=True,
        )
        self.model.lead_column = 2  # swatch on the product, not the checkbox
        self.model.on_check = self._on_check
        self.model.on_double_click = lambda item: self.select_nodes([item])
        self.model.context_menu = self._context_menu
        self.model.on_delete = self.remove

    # -- layout ----------------------------------------------------------
    def build(self):
        self.add_tree(ID_TREE, self.model, min_size=(300, 120))
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=6):
            self.AddButton(ID_CREATE, c4d.BFH_LEFT, name="Create...")
            self.AddButton(ID_CREATE_QT, c4d.BFH_LEFT, name="Create (Qt)...")
            self.AddButton(ID_REFRESH, c4d.BFH_LEFT, name="Refresh")
            self.AddStaticText(ID_SUMMARY, c4d.BFH_SCALEFIT, name="")
            self.AddButton(ID_SAVE, c4d.BFH_RIGHT, name="Save")
            self.AddButton(ID_PUBLISH, c4d.BFH_RIGHT, 120, 0,
                           name="Publish...")
        self.GroupEnd()

    def InitValues(self):
        result = super().InitValues()
        self.SetTimer(CHECK_INTERVAL)
        return result

    # -- data ------------------------------------------------------------
    def refresh(self):
        doc = c4d.documents.GetActiveDocument()
        self._signature = _scene_signature(doc)
        self._scene_dirty = False
        host = registered_host()
        # Publish plug-ins are discovered by the Publisher, not needed here
        if self.create_context is None:
            self.create_context = CreateContext(host, reset=False)
        self.create_context.reset(discover_publish_plugins=False)
        context = host.get_current_context()
        self.set_context_text(
            f"  {context['folder_path']}  /  {context['task_name']}")
        self._fill()

    def _fill(self):
        context = registered_host().get_current_context()
        creators = self.create_context.creators
        items = []
        for instance in self.create_context.instances:
            creator = creators.get(instance.creator_identifier)
            product_type = instance.get("productType") or ""
            folder_path = instance.get("folderPath") or ""
            task_name = instance.get("task") or ""
            other_context = (
                folder_path and folder_path != context["folder_path"]
            ) or (task_name and task_name != context["task_name"])
            items.append(Item(
                instance.id,
                {
                    "product": instance.get("productName") or "",
                    "type": product_type,
                    "variant": instance.get("variant") or "",
                    "context": f"{folder_path} / {task_name}"
                    if other_context else "",
                    "creator": getattr(creator, "label", ""),
                },
                data=instance,
                swatch=widgets.color_for(product_type),
                checked=bool(instance.get("active", True)),
                dim=not instance.get("active", True),
                colors={"context": widgets.ORANGE},
                tooltip=getattr(creator, "label", None),
            ))
        items.sort(key=lambda i: (i.text("type"), i.text("product")))
        self.model.set_items(items)

        active = sum(1 for i in items if i.checked)
        doc = c4d.documents.GetActiveDocument()
        summary = f"{active} of {len(items)} active"
        if doc.GetChanged():
            summary += "  -  unsaved changes"
        self.SetString(ID_SUMMARY, summary)
        self.Enable(ID_PUBLISH, active > 0)

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
    def _save_changes(self):
        self.create_context.save_changes()
        self._signature = _scene_signature(
            c4d.documents.GetActiveDocument())
        self.notify(events.PUBLISH)  # other windows, not this one
        c4d.EventAdd()

    def _on_check(self, item, checked):
        self.guard(self.set_active, [item], checked)

    def set_active(self, items, active):
        for item in items:
            item.data["active"] = active
        self._save_changes()
        self._fill()

    def select_nodes(self, items):
        nodes = [
            item.data.transient_data.get("instance_node") for item in items]
        nodes = [n for n in nodes if n is not None and n.IsAlive()]
        if nodes:
            lib.set_selection(c4d.documents.GetActiveDocument(), nodes)
            c4d.EventAdd()

    def remove(self, items):
        items = [i for i in items if i.data.creator_identifier]
        if not items or not widgets.confirm(
            f"Remove {len(items)} instance(s)?"
        ):
            return
        self.create_context.remove_instances([i.data for i in items])
        self._save_changes()
        self.refresh()

    def create(self, creator):
        pre_create_data = _default_pre_create_data(creator)
        self.create_context.create(
            creator.identifier, _default_variant(creator),
            pre_create_data=pre_create_data)
        self._save_changes()
        self.refresh()
        self.set_status(f"Created {creator.label}.")

    def show_create_menu(self):
        creators = sorted(
            self.create_context.manual_creators.values(),
            key=lambda c: c.label or c.identifier)
        entries = [
            (f"{creator.label}  ({_default_variant(creator)})",
             lambda c=creator: self.guard(self.create, c))
            for creator in creators
        ]
        entries += [None, ("More options (Qt)...", self.show_create_qt)]
        widgets.popup(entries)

    def show_create_qt(self):
        show_publisher(tab="create")

    def publish(self):
        self._save_changes()
        show_publisher(tab="publish")
        # An open Publisher shows the old state until it is reset
        from ayon_cinema4d.api.pipeline import _reset_visible_publisher
        _reset_visible_publisher()

    def _context_menu(self, items):
        if not items:
            return [("Refresh", self.refresh)]
        any_active = any(i.checked for i in items)
        return [
            ("Disable" if any_active else "Enable",
             lambda: self.set_active(items, not any_active)),
            ("Select Node", lambda: self.select_nodes(items)),
            None,
            ("Remove...", lambda: self.remove(items)),
            None,
            ("Open Publisher...", self.publish),
        ]

    def on_command(self, gadget_id, msg):
        if gadget_id == ID_PUBLISH:
            self.publish()
        elif gadget_id == ID_CREATE:
            self.show_create_menu()
        elif gadget_id == ID_CREATE_QT:
            self.show_create_qt()
        elif gadget_id == ID_REFRESH:
            self.refresh()
        elif gadget_id == ID_SAVE:
            c4d.CallCommand(12098)  # Save
            self._fill()


COMMANDS = [
    Command(
        ids.PUBLISH, "Publish...", order=20, dialog=PublishDialog,
        help="Publish instances of the document, opens the Publisher",
    ),
]
