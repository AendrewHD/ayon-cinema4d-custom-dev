import os

import pyblish.api

from ayon_core.pipeline import publish


class ExtractWorkfileThumbnail(
    publish.Extractor, publish.OptionalPyblishPluginMixin
):
    """Viewport snapshot as workfile thumbnail, published as reviewable.

    A thumbnail set by the artist in the Publisher wins over the snapshot.
    Either one is added as `preview` representation tagged `webreview`, so
    it shows as reviewable on the server.
    """

    label = "Workfile Thumbnail"
    # after core 'ExtractThumbnailFromSource' (artist thumbnail)
    order = pyblish.api.ExtractorOrder + 0.1
    hosts = ["cinema4d"]
    families = ["workfile"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        thumbnail = (
            instance.data.get("thumbnailPath")
            or instance.context.data.get("thumbnailPath")
        )
        if not thumbnail or not os.path.isfile(thumbnail):
            from ayon_cinema4d.api.screenshot import capture_active_view

            path = os.path.join(self.staging_dir(instance), "viewport.jpg")
            try:
                thumbnail = capture_active_view(path)
            except Exception:
                self.log.warning("Viewport snapshot failed", exc_info=True)
                return
            if not thumbnail:
                self.log.warning("No active view to take a snapshot of.")
                return
            instance.data["thumbnailPath"] = thumbnail
            self.log.debug(f"Viewport snapshot: {thumbnail}")

        folder, filename = os.path.split(thumbnail)
        instance.data.setdefault("representations", []).append({
            "name": "preview",
            "ext": os.path.splitext(filename)[1].lstrip("."),
            "files": filename,
            "stagingDir": folder,
            "tags": ["webreview"],
        })
