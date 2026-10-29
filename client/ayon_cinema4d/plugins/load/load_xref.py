import c4d

from ayon_cinema4d.api import lib, pipeline, plugin


class XRefLoader(plugin.Cinema4DLoader):
    """Load a file as XRef."""

    label = "Load XRef"

    product_base_types = {"*"}
    product_types = product_base_types
    representations = {"c4d", "abc", "fbx"}
    icon = "code-fork"
    color = "orange"
    order = -8

    def load(self, context, name=None, namespace=None, options=None):
        """Load the asset as XRef, namespaced by where it comes from.

        Todo:
            - Find out how to set the path to non-relative.
        """
        filepath = self.filepath_from_context(context)
        doc = lib.active_document()
        name = name or context["product"]["name"]
        namespace = namespace or lib.get_xref_namespace(context, doc)

        xref = c4d.BaseList2D(c4d.Oxref)
        xref.SetName(f"{namespace}{lib.XREF_SEPARATOR}{name}")
        lib.insert_object(doc, xref)
        xref.SetParameter(
            c4d.ID_CA_XREF_FILE,
            filepath,
            c4d.DESCFLAGS_SET_USERINTERACTION
        )
        xref.SetParameter(
            c4d.ID_CA_XREF_NAMESPACE,
            str(namespace),
            c4d.DESCFLAGS_SET_USERINTERACTION
        )
        c4d.EventAdd()
        # c4d.ID_CA_XREF_FILE       # filepath
        # c4d.ID_CA_XREF_NAMESPACE  # namespace
        # c4d.ID_CA_XREF_LOADED     # loaded checkbox
        # c4d.ID_CA_XREF_RELATIVE   # Relative to project

        container = pipeline.containerise(
            name=str(name),
            namespace=str(namespace),
            nodes=[xref],
            context=context,
            loader=str(self.__class__.__name__),
        )

        return container

    def update(self, container, context):
        filepath = self.filepath_from_context(context)
        # There should be only 1 xref node
        for xref in pipeline.get_container_objects(container["node"]):
            if xref.GetTypeName() == "XRef":
                # This requires `c4d.DESCFLAGS_SET_USERINTERACTION`
                # which will unfortunately prompt the user to confirm it.
                # There is no other way, see:
                # https://developers.maxon.net/forum/topic/15728/update-xref-filepath-without-user-interaction  # noqa: E402
                xref.SetParameter(
                    c4d.ID_CA_XREF_FILE,
                    filepath,
                    c4d.DESCFLAGS_SET_USERINTERACTION,
                )

        pipeline.update_container(container, context)
        c4d.EventAdd()
