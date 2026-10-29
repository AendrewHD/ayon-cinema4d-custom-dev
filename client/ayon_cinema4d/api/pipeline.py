import os
import logging
import contextlib

import c4d
import pyblish.api

from ayon_core.lib import (
    register_event_callback,
    is_headless_mode_enabled
)
from ayon_core.host import HostBase, IWorkfileHost, ILoadHost, IPublishHost
from ayon_core.pipeline import (
    get_current_folder_path,
    get_current_task_name,
    register_loader_plugin_path,
    register_creator_plugin_path,
    AYON_CONTAINER_ID,
)
from .workio import (
    open_file,
    save_file,
    file_extensions,
    has_unsaved_changes,
    current_file
)
import ayon_cinema4d

from . import lib, plugin, doc_context, container_tag

log = logging.getLogger("ayon_cinema4d")

HOST_DIR = os.path.dirname(os.path.abspath(ayon_cinema4d.__file__))
PLUGINS_DIR = os.path.join(HOST_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "create")
INVENTORY_PATH = os.path.join(PLUGINS_DIR, "inventory")

AYON_CONTAINERS = lib.AYON_CONTAINERS
AYON_CONTEXT_CREATOR_IDENTIFIER = "io.ayon.create.context"


class Cinema4DHost(HostBase, IWorkfileHost, ILoadHost, IPublishHost):
    name = "cinema4d"

    def install(self):
        # process path mapping
        # dirmap_processor = Cinema4DDirmap("cinema4d", project_settings)
        # dirmap_processor.process_dirmap()

        pyblish.api.register_plugin_path(PUBLISH_PATH)
        pyblish.api.register_host("cinema4d")

        register_loader_plugin_path(LOAD_PATH)
        register_creator_plugin_path(CREATE_PATH)
        # TODO: Register only when any inventory actions are created
        # register_inventory_action_path(INVENTORY_PATH)
        self.log.info(PUBLISH_PATH)

        register_event_callback("taskChanged", on_task_changed)

    def open_workfile(self, filepath):
        return open_file(filepath)

    def save_workfile(self, filepath=None):
        return save_file(filepath)

    def get_current_workfile(self):
        return current_file()

    def workfile_has_unsaved_changes(self):
        return has_unsaved_changes()

    def get_workfile_extensions(self):
        return file_extensions()

    def get_containers(self):
        return iter_containers()

    # Remember the task each document belongs to (see `doc_context`)
    def _after_workfile_open(self, open_workfile_context):
        super()._after_workfile_open(open_workfile_context)
        _store_document_context(open_workfile_context)

    def _after_workfile_save(self, save_workfile_context):
        super()._after_workfile_save(save_workfile_context)
        _store_document_context(save_workfile_context)

    @contextlib.contextmanager
    def maintained_selection(self):
        with lib.maintained_selection():
            yield

    def _get_context_node(self, create_if_not_exists=False):
        doc = lib.active_document()
        context_node = None
        for creator_id, obj in plugin.iter_instance_objects(doc):
            if creator_id == AYON_CONTEXT_CREATOR_IDENTIFIER:
                context_node = obj

        if context_node is None and create_if_not_exists:
            context_node = plugin.create_selection([], name="AYON_context")
            plugin.parent_to_ayon_null(context_node)

        return context_node

    def update_context_data(self, data, changes):
        if not data:
            return

        context_node = self._get_context_node(create_if_not_exists=True)
        data["id"] = plugin.AYON_INSTANCE_ID
        data["creator_identifier"] = AYON_CONTEXT_CREATOR_IDENTIFIER
        lib.imprint(context_node, data)

    def get_context_data(self):
        context_node = self._get_context_node()
        if context_node is None:
            return {}

        data = lib.read(context_node)

        # Pop our custom data that we use to find the node again
        data.pop("id", None)
        data.pop("creator_identifier", None)

        return data


def get_container_tag(obj):
    """Return the AYON container tag of `obj`, None if it has none."""
    return obj.GetTag(container_tag.TAG_ID) if obj else None


def get_container_objects(node):
    """Return the objects of a container node.

    The tagged object for an AYON tag, the members of a legacy selection
    object, or the legacy object imprinted with the container data itself.
    """
    if isinstance(node, c4d.BaseTag):
        obj = node.GetObject()
        return [obj] if obj else []
    if node.CheckType(c4d.Oselection):
        return list(lib.get_objects_from_container(node))
    return [node]


def parse_container(node):
    """Return the full container data of a container node.

    Args:
        node (c4d.BaseList2D): AYON tag or legacy container object.

    Returns:
        dict[str, Any]: The container schema data for this container node.

    """
    data = lib.read(node)

    # Backwards compatibility pre-schemas for containers
    data["schema"] = data.get("schema", "ayon:container-3.0")

    # Append transient data
    owner = node.GetObject() if isinstance(node, c4d.BaseTag) else node
    data["objectName"] = owner.GetName() if owner else node.GetName()
    data["node"] = node

    return data


def iter_containers(doc=None):
    """Yield the containers of the document.

    AYON tags, plus the legacy selection objects / imprinted objects. A tag
    below another AYON tag came with that product (e.g. a merged model
    built from loaded assets) and is part of it, so it is skipped.
    """
    doc = doc or c4d.documents.GetActiveDocument()
    stack = [(obj, False) for obj in reversed(doc.GetObjects())]
    while stack:
        obj, nested = stack.pop()
        tag = get_container_tag(obj)
        if tag is not None:
            if not nested:
                yield parse_container(tag)
            nested = True
        elif not nested and lib.get_object_user_data_by_name(
                obj, "id") == AYON_CONTAINER_ID:
            yield parse_container(obj)
        stack.extend((child, nested) for child in reversed(obj.GetChildren()))


def containerise(name,
                 namespace,
                 nodes,
                 context,
                 loader):
    """Tag the root of the loaded `nodes` as AYON container.

    Several roots are grouped under a null first: one tag = one container.

    Arguments:
        name (str): Name of resulting assembly
        namespace (str): Namespace under which to host container
        nodes (list[c4d.BaseObject]): Loaded root objects
        context (dict): Asset information
        loader (str): Name of loader used to produce this container.

    Returns:
        c4d.BaseTag: The AYON container tag.

    """
    doc = nodes[0].GetDocument() or lib.active_document()
    with lib.undo_chunk():
        root = nodes[0]
        if len(nodes) > 1:
            root = lib.group_objects(doc, nodes, f"{namespace}_{name}")
        tag = imprint_container(root, name, namespace, context, loader)
    c4d.EventAdd()
    return tag


def imprint_container(
    node,
    name,
    namespace,
    context,
    loader
):
    """Imprint the container data on the AYON tag of `node`.

    Arguments:
        node (c4d.BaseObject | c4d.BaseTag): Object to tag, or its tag.
        name (str): Name of resulting assembly
        namespace (str): Namespace under which to host container
        context (dict): Asset information
        loader (str): Name of loader used to produce this container.

    Returns:
        c4d.BaseTag: The AYON container tag.
    """
    tag = node
    if not isinstance(node, c4d.BaseTag):
        tag = get_container_tag(node)
        if tag is None:
            tag = node.MakeTag(container_tag.TAG_ID)
            doc = node.GetDocument()
            if doc:
                doc.AddUndo(c4d.UNDOTYPE_NEW, tag)

    data = {
        "schema": "ayon:container-3.0",
        "id": AYON_CONTAINER_ID,
        "name": name,
        "namespace": namespace,
        "loader": str(loader),
        "representation": str(context["representation"]["id"]),
        # Library projects: update / manage need the source project
        "project_name": str(context["project"]["name"]),
    }
    data.update(_display_data(context))
    lib.imprint(tag, data, group="AYON")
    _name_tag(tag, context)
    return tag


def update_container(container, context):
    """Store the new representation of `container` after an update."""
    node = container["node"]
    data = {"representation": str(context["representation"]["id"])}
    data.update(_display_data(context))
    lib.imprint(node, data, group="AYON")
    _name_tag(node, context)


def remove_container(container):
    """Remove the container node and its objects."""
    node = container["node"]
    objects = get_container_objects(node)
    for obj in objects:
        obj.Remove()
    # A tag goes with its object
    if not isinstance(node, c4d.BaseTag) and node not in objects:
        node.Remove()
    c4d.EventAdd()


def _version_label(context):
    version = context["version"]["version"]
    return "hero" if version < 0 else f"v{version:03d}"


def _display_data(context):
    """Readable info for the Attribute Manager, not used by the pipeline."""
    return {
        "folder_path": str(context["folder"]["path"]),
        "product_name": str(context["product"]["name"]),
        "version_name": _version_label(context),
    }


def _name_tag(node, context):
    """Tag name shows product and version in the Object Manager tooltip."""
    if isinstance(node, c4d.BaseTag):
        node.SetName(
            f"AYON {context['product']['name']} {_version_label(context)}")


def _store_document_context(workfile_context):
    doc_context.set_document_context(
        lib.active_document(),
        workfile_context.project_name,
        workfile_context.folder_entity["path"],
        workfile_context.task_entity["name"],
    )


def _reset_visible_publisher():
    """Publisher shows the old context until it is reset."""
    from ayon_core.tools.utils import host_tools

    helper = host_tools._SingletonPoint.helper
    window = getattr(helper, "_publisher_tool", None)
    if window is not None and window.isVisible():
        window.reset()


def on_task_changed():

    if not is_headless_mode_enabled():
        # Get AYON Context menu command plugin (menu item) by its unique id.
        ayon_context = c4d.plugins.FindPlugin(1064692)
        # Update its value with the new context.
        ayon_context.SetName(
            "{}, {}".format(get_current_folder_path(), get_current_task_name())
        )
        c4d.gui.UpdateMenus()
        _reset_visible_publisher()
        from .ui import events
        events.notify(events.CONTEXT)
