import c4d

from ayon_cinema4d.api import lib, pipeline, plugin


class CameraLoader(plugin.Cinema4DLoader):
    """Load the camera."""

    color = "orange"
    product_base_types = {"camera"}
    product_types = product_base_types
    representations = {"abc"}
    icon = "file-video-o"
    label = "Load Camera"
    order = -11

    def _merge_camera(self, filepath, doc=None):
        """Merge a camera from a file.

        Arguments:
            filepath (str): The full path to the file that contains the camera.
            doc (optional c4d.documents.BaseDocument): The document to put the
                camera in. By default this will be the active document.

        Returns:
            c4d.BaseList2D: The merge camera object
        """

        doc = doc or lib.active_document()
        camera_doc = c4d.documents.LoadDocument(
            filepath,
            c4d.SCENEFILTER_OBJECTS
            # | c4d.SCENEFILTER_MERGESCENE
            | c4d.SCENEFILTER_NOUNDO
            | c4d.SCENEFILTER_IGNOREXREFS
            | c4d.SCENEFILTER_DONTCORRECTOUTPUTFORMAT,
        )

        # TODO: We should include the parent hierarchy of the loaded camera
        #  to ensure the full correct transformations? As such, maybe we should
        #  merge the full camera - and only make editable the camera objects
        for obj in lib.iter_objects(camera_doc.GetFirstObject()):
            # Get internal camera data from the Alembic Generator
            data = {"res": None}
            if not obj.Message(c4d.MSG_GETREALCAMERADATA, data):
                continue

            if data["res"] is not None:
                camera_alembic = obj
                break
        else:
            raise RuntimeError(f"No camera found in {filepath}")

        # The camera should be the only object in the file
        result = c4d.utils.SendModelingCommand(
            command=c4d.MCOMMAND_MAKEEDITABLE,
            list=[camera_alembic],
            doc=doc,
        )
        assert result, "Making the camera editable failed."
        camera = result[0]
        assert camera.GetTypeName() == "Camera", "No camera found in: {}".format(
            filepath
        )

        self.log.info("Loaded camera '%s' from %s", camera.GetName(), filepath)

        return camera

    def _protect_camera(self, camera):
        """Add a protection tag to the camera.

        Arguments:
            camera (c4d.CameraObject): The camera to protect.
        """

        if camera.GetTag(c4d.Tprotection):  # kept from the previous version
            return
        protection_tag = c4d.BaseTag(c4d.Tprotection)
        camera.InsertTag(protection_tag)
        self.log.debug("Added a protection tag to camera '%s'", camera.GetName())

    def load(self, context, name=None, namespace=None, options=None):
        """Load the camera."""

        doc = lib.active_document()
        name, namespace = self.get_name_and_namespace(
            context, name, namespace, doc)
        basename = f"{namespace}_{name}"

        filepath = self.filepath_from_context(context)
        camera = self._merge_camera(filepath, doc)

        lib.insert_object(doc, camera)
        camera.SetName(str(basename))

        # Set the camera as the active camera
        for basedraw in (doc.GetActiveBaseDraw(), doc.GetRenderBaseDraw()):
            basedraw.SetSceneCamera(camera)

        self._protect_camera(camera)

        container = pipeline.containerise(
            name=str(name),
            namespace=str(namespace),
            nodes=[camera],
            context=context,
            loader=str(self.__class__.__name__),
        )

        c4d.EventAdd()

        return container

    def update(self, container, context):
        doc = lib.active_document()
        node = container["node"]
        filepath = self.filepath_from_context(context)

        # The new camera takes the place, name and tags (incl. the AYON tag)
        # of the old one. There should be only 1 camera.
        old = pipeline.get_container_objects(node)
        camera = self._merge_camera(filepath, doc=doc)
        if old:
            camera.InsertBefore(old[0])
            camera.SetName(old[0].GetName())
            for tag in old[0].GetTags():
                tag.Remove()
                camera.InsertTag(tag, camera.GetLastTag())
        else:
            doc.InsertObject(camera)
        for obj in old:
            obj.Remove()

        # Set the camera as the active camera
        for basedraw in (doc.GetActiveBaseDraw(), doc.GetRenderBaseDraw()):
            basedraw.SetSceneCamera(camera)

        self._protect_camera(camera)

        if not isinstance(node, c4d.BaseTag):  # legacy selection object
            lib.add_objects_to_container(node, [camera])
        pipeline.update_container(container, context)
        c4d.EventAdd()
