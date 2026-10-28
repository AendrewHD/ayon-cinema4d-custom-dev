import c4d

from ayon_cinema4d.api import lib, pipeline, plugin


def _uid(node):
    """Hashable unique id of a node (stable while the document is open)."""
    return bytes(node.FindUniqueID(c4d.MAXON_CREATOR_ID) or b"")


def _iter_material_users(doc):
    for obj in lib.iter_objects(doc.GetFirstObject()):
        for tag in obj.GetTags():
            if tag.CheckType(c4d.Ttexture) and tag.GetMaterial():
                yield tag.GetMaterial()


class MergeLoader(plugin.Cinema4DLoader):
    """Merge the file into the scene, grouped under a null.

    Unlike an XRef the objects become part of the scene. Updating re-merges
    the new version: transforms of the group null are kept, changes inside
    the group are lost.
    """

    label = "Merge"
    product_base_types = {"*"}
    product_types = product_base_types
    representations = {
        "c4d", "fbx", "obj", "abc", "usd", "usda", "usdc", "usdz",
        "gltf", "glb", "stl", "ply", "3ds", "dae",
    }
    icon = "compress"
    color = "orange"
    order = -9

    def _merge(self, doc, filepath, group):
        """Merge `filepath` into `doc` and move new top objects under `group`.
        """
        old_objects = {_uid(obj) for obj in doc.GetObjects()}
        old_materials = {_uid(mat) for mat in doc.GetMaterials()}

        if not c4d.documents.MergeDocument(
            doc, filepath,
            c4d.SCENEFILTER_OBJECTS
            | c4d.SCENEFILTER_MATERIALS
            | c4d.SCENEFILTER_MERGESCENE,
        ):
            raise RuntimeError(f"Merging failed: {filepath}")

        new_objects = [
            obj for obj in doc.GetObjects()
            if _uid(obj) not in old_objects and obj != group
        ]
        for obj in reversed(new_objects):
            mg = obj.GetMg()
            obj.Remove()
            obj.InsertUnder(group)
            obj.SetMg(mg)

        return [
            mat for mat in doc.GetMaterials()
            if _uid(mat) not in old_materials
        ]

    def load(self, context, name=None, namespace=None, options=None):
        filepath = self.filepath_from_context(context)
        doc = lib.active_document()
        name, namespace = self.get_name_and_namespace(
            context, name, namespace, doc)

        with lib.undo_chunk():
            group = c4d.BaseObject(c4d.Onull)
            group.SetName(f"{namespace}_{name}")
            doc.InsertObject(group)
            doc.AddUndo(c4d.UNDOTYPE_NEW, group)
            self._merge(doc, filepath, group)

        container = pipeline.containerise(
            name=str(name),
            namespace=str(namespace),
            nodes=[group],
            context=context,
            loader=str(self.__class__.__name__),
        )
        c4d.EventAdd()
        return container

    def update(self, container, context):
        filepath = self.filepath_from_context(context)
        container_node = container["node"]
        doc = container_node.GetDocument()

        with lib.undo_chunk():
            for group in lib.get_objects_from_container(container_node):
                self._clear_group(doc, group)
                self._merge(doc, filepath, group)

        for i, base_container in container_node.GetUserDataContainer():
            if base_container[c4d.DESC_NAME] == "representation":
                container_node[i] = context["representation"]["id"]
                break
        c4d.EventAdd()

    def remove(self, container):
        container_node = container["node"]
        doc = container_node.GetDocument()
        for group in lib.get_objects_from_container(container_node):
            self._clear_group(doc, group)
            group.Remove()
        container_node.Remove()
        c4d.EventAdd()

    @staticmethod
    def _clear_group(doc, group):
        """Remove the merged objects and materials only they used."""
        children = list(lib.get_all_children(group))
        materials = {
            _uid(mat): mat for mat in lib.get_materials_from_objects(children)
        }
        for child in group.GetChildren():
            child.Remove()

        still_used = {_uid(mat) for mat in _iter_material_users(doc)}
        for uid, mat in materials.items():
            if uid not in still_used:
                mat.Remove()
