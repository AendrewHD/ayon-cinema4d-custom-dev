"""Publish: native panel for the publish instances of the active document.

Lists the instances (toggle active, select, remove), edits the variant and
the creator / publish attributes of the selected instance, creates new ones
with default options and publishes through the AYON Publisher (Qt), which
starts publishing by itself.
"""
import inspect
import logging

import c4d
import ayon_api
from qtpy import QtCore

from ayon_core.pipeline import registered_host
from ayon_core.tools.utils import host_tools
from ayon_core.pipeline.create import CreateContext

from ayon_cinema4d.api import lib, plugin
from ayon_cinema4d.api.lib import get_main_window
from ayon_cinema4d.api.ui import events, ids, widgets
from ayon_cinema4d.api.ui.attributes import AttributeEditor
from ayon_cinema4d.api.ui.dialog import AyonDialog
from ayon_cinema4d.api.ui.registry import Command
from ayon_cinema4d.api.ui.tree import Column, Item, TreeModel

from .classic import center_on_first_show

log = logging.getLogger(__name__)

ID_TREE = 1000
ID_PUBLISH = 1001
ID_CREATE = 1002
ID_CREATE_QT = 1003
ID_REFRESH = 1004
ID_SUMMARY = 1005
ID_SAVE = 1006
ID_OPEN_PUBLISHER = 1007
ID_ATTRS_SCROLL = 1008
ID_ATTRS = 1009
ID_VARIANT = 1010
ID_VARIANT_PRESETS = 1011
ID_VARIANT_SET = 1012
ID_ATTR_FIRST = 5000

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


def _product_name(create_context, instance, variant):
    """Product name of `instance` with a new variant (like the Publisher)."""
    creator = create_context.creators[instance.creator_identifier]
    project_name = create_context.get_current_project_name()
    folder = create_context.get_folder_entity(instance["folderPath"])
    if folder is None:
        raise ValueError(f"Folder not found: {instance['folderPath']}")
    task = None
    if instance.get("task"):
        task = create_context.get_task_entity(
            instance["folderPath"], instance["task"])
    kwargs = {
        "host_name": create_context.host_name,
        "instance": instance,
        "project_entity": ayon_api.get_project(project_name),
        "product_type": instance.get("productType"),
    }
    # Older creators don't take all keyword arguments
    params = inspect.signature(creator.get_product_name).parameters
    if not any(p.kind == p.VAR_KEYWORD for p in params.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in params}
    return creator.get_product_name(
        project_name, folder, task, variant, **kwargs)


def _start_publish_when_ready(window):
    """Press the Publisher's publish button after its next reset."""
    window._ayon_c4d_autopublish = True
    if getattr(window, "_ayon_c4d_autopublish_hooked", False):
        return
    window._ayon_c4d_autopublish_hooked = True

    def on_reset(*_args):
        if getattr(window, "_ayon_c4d_autopublish", False):
            window._ayon_c4d_autopublish = False
            QtCore.QTimer.singleShot(0, window._on_publish_clicked)

    window._controller.register_event_callback(
        "controller.reset.finished", on_reset)


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
        self._attrs_dirty = False
        self._full_reset = True
        self._attr_instance_id = None
        self.attributes = None
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
        self.model.on_select = lambda items: self._build_attributes()
        self.model.on_double_click = lambda item: self.select_nodes([item])
        self.model.context_menu = self._context_menu
        self.model.on_delete = self.remove

    # -- layout ----------------------------------------------------------
    def build(self):
        self.add_tree(ID_TREE, self.model, min_size=(300, 120))
        self.ScrollGroupBegin(
            ID_ATTRS_SCROLL, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
            c4d.SCROLLGROUP_VERT | c4d.SCROLLGROUP_AUTOVERT, inith=160)
        self.GroupBegin(ID_ATTRS, c4d.BFH_SCALEFIT | c4d.BFV_TOP, cols=1)
        self.GroupEnd()
        self.GroupEnd()
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4):
            self.AddButton(ID_CREATE, c4d.BFH_LEFT, name="Create...")
            self.AddButton(ID_CREATE_QT, c4d.BFH_LEFT, name="Create (Qt)...")
            self.AddButton(ID_REFRESH, c4d.BFH_LEFT, name="Refresh")
            self.AddStaticText(ID_SUMMARY, c4d.BFH_SCALEFIT, name="")
        self.GroupEnd()
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=3):
            self.AddButton(ID_SAVE, c4d.BFH_LEFT, name="Save")
            self.AddButton(ID_OPEN_PUBLISHER, c4d.BFH_SCALEFIT,
                           name="Open Publisher")
            self.AddButton(ID_PUBLISH, c4d.BFH_SCALEFIT, name="Publish")
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
        if self.create_context is None:
            self.create_context = CreateContext(host, reset=False)
        if self._full_reset:
            # Publish plug-ins only for the publish attributes, the scene
            # watching below re-collects instances only
            self._full_reset = False
            self.create_context.reset(discover_publish_plugins=True)
        else:
            self._reload_instances()
        context = host.get_current_context()
        self.set_context_text(
            f"  {context['folder_path']}  /  {context['task_name']}")
        self._fill()

    def _reload_instances(self):
        """Re-collect instances, keep the discovered plug-ins."""
        ctx = self.create_context
        required = (
            "reset_preparation", "reset_current_context",
            "reset_context_data", "bulk_add_instances", "reset_instances",
            "find_convertor_items", "execute_autocreators",
            "reset_finalization",
        )
        if not all(hasattr(ctx, name) for name in required):
            ctx.reset(discover_publish_plugins=True)  # other ayon-core
            return
        ctx.reset_preparation()  # also clears the event callbacks
        # Re-register what reset_plugins() would register
        for creator in ctx.creators.values():
            creator.register_callbacks()
        for plugin in getattr(ctx, "plugins_with_defs", []):
            plugin.register_create_context_callbacks(ctx)
        ctx.reset_current_context()
        ctx.reset_context_data()
        with ctx.bulk_add_instances():
            ctx.reset_instances()
            ctx.find_convertor_items()
            ctx.execute_autocreators()
        ctx.reset_finalization()

    def on_events(self, kinds):
        if events.CONTEXT in kinds:
            self._full_reset = True
        self.refresh()

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
        self._build_attributes()

    # -- attributes ------------------------------------------------------
    def _selected_instance(self):
        items = self.model.selected_items()
        return items[0].data if len(items) == 1 else None

    def _build_attributes(self):
        instance = self._selected_instance()
        self.LayoutFlushGroup(ID_ATTRS)
        self.attributes = AttributeEditor(self, ID_ATTR_FIRST)
        self.attributes.on_change = self._on_attribute_change
        self._attr_instance_id = instance.id if instance else None
        if instance is None:
            self.AddStaticText(
                0, c4d.BFH_SCALEFIT,
                name="Select one instance to edit its settings.")
            self.LayoutChanged(ID_ATTRS)
            return

        creator = self.create_context.creators.get(
            instance.creator_identifier)
        if creator is not None and "variant" in instance:
            self.AddStaticText(
                0, c4d.BFH_SCALEFIT, name="Product",
                borderstyle=c4d.BORDER_WITH_TITLE_BOLD)
            if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4):
                self.GroupBorderSpace(8, 0, 0, 4)
                self.AddStaticText(0, c4d.BFH_LEFT, name="Variant")
                self.AddEditText(ID_VARIANT, c4d.BFH_SCALEFIT, 160, 0)
                self.AddButton(ID_VARIANT_PRESETS, c4d.BFH_RIGHT, 30, 0,
                               name="...")
                self.AddButton(ID_VARIANT_SET, c4d.BFH_RIGHT, name="Set")
            self.GroupEnd()
            self.SetString(ID_VARIANT, instance.get("variant") or "")

        self.attributes.add_section(
            getattr(creator, "label", "Creator"),
            instance.creator_attributes)
        for plugin_name, values in instance.publish_attributes.items():
            if getattr(values, "attr_defs", None):
                self.attributes.add_section(plugin_name, values)
        self.LayoutChanged(ID_ATTRS)

    def _on_attribute_change(self, values, key, value):
        self._attrs_dirty = True  # saved by the Timer, not per keystroke

    def _variant_presets(self):
        instance = self._selected_instance()
        creator = instance and self.create_context.creators.get(
            instance.creator_identifier)
        variants = list(getattr(creator, "default_variants", None) or [])
        if not variants:
            widgets.popup([("No default variants", None)])
            return

        def pick(variant):
            self.SetString(ID_VARIANT, variant)
            self.set_variant(variant)

        widgets.popup([(v, lambda v=v: pick(v)) for v in variants])

    def set_variant(self, variant=None):
        instance = self._selected_instance()
        if instance is None:
            return
        variant = (variant or self.GetString(ID_VARIANT)).strip()
        if not variant or variant == instance.get("variant"):
            return
        product_name = _product_name(self.create_context, instance, variant)
        instance["variant"] = variant
        instance["productName"] = product_name
        self._save_changes()
        self._fill()
        self.set_status(f"Product renamed to {product_name}")

    def on_document_change(self):
        self._scene_dirty = True

    def AskClose(self):
        if self._attrs_dirty:
            self._attrs_dirty = False
            self.guard(self._save_changes)
        return False

    def Timer(self, msg):
        if self._attrs_dirty:
            self._attrs_dirty = False
            self.guard(self._save_changes)
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
        self.open_publisher(tab="create", start=False)

    def open_publisher(self, tab="publish", start=False):
        """Show the Publisher with the saved state, optionally publish.

        The Publisher resets when it is shown the first time (or after it
        was closed); an open one is reset here. Publishing starts after the
        reset, a missing comment or failed validation stays visible there.
        """
        self._attrs_dirty = False
        self._save_changes()
        window = host_tools.get_tool_by_name(
            "publisher", parent=get_main_window())
        if start and hasattr(window, "show_and_publish"):
            # Public Publisher API: show, reset, press Publish
            window.set_current_tab(tab)
            window.show_and_publish()
            center_on_first_show(window)
            return
        was_visible = window is not None and window.isVisible()
        if start and window is not None and hasattr(window, "_controller"):
            _start_publish_when_ready(window)  # older ayon-core
        window = host_tools.show_publisher(
            tab=tab, parent=get_main_window()) or window
        center_on_first_show(window)
        if was_visible and window is not None:
            window.reset()

    def publish(self):
        self.open_publisher(tab="publish", start=True)

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
            ("Open Publisher...", self.open_publisher),
        ]

    def on_command(self, gadget_id, msg):
        if self.attributes is not None and self.attributes.command(gadget_id):
            return
        if gadget_id == ID_PUBLISH:
            self.publish()
        elif gadget_id == ID_OPEN_PUBLISHER:
            self.open_publisher()
        elif gadget_id == ID_VARIANT_SET:
            self.set_variant()
        elif gadget_id == ID_VARIANT_PRESETS:
            self._variant_presets()
        elif gadget_id == ID_CREATE:
            self.show_create_menu()
        elif gadget_id == ID_CREATE_QT:
            self.show_create_qt()
        elif gadget_id == ID_REFRESH:
            self._full_reset = True
            self.refresh()
        elif gadget_id == ID_SAVE:
            c4d.CallCommand(12098)  # Save
            self._fill()


COMMANDS = [
    Command(
        ids.PUBLISH, "Publish...", order=20, dialog=PublishDialog,
        help="Publish instances of the document",
    ),
]
