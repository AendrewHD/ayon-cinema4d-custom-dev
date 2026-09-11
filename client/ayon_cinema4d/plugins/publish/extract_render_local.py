import os

import pyblish.api

from ayon_core.pipeline import publish
from ayon_cinema4d.api import exporters


class ExtractRenderLocal(publish.Extractor):
    """Render locally or use the existing frames of a render.

    The frames are published by the AOV instances of `CollectRenderLocal`.
    The render instance itself is done afterwards, the ayon-deadline Cinema4D
    submitter must not process it.
    """

    label = "Render Local"
    # Before core `ExtractReview` / `ExtractBurnin`
    order = pyblish.api.ExtractorOrder - 0.1
    hosts = ["cinema4d"]
    families = ["render"]

    def process(self, instance):
        if instance.data.get("farm"):
            return

        files = [
            path
            for aov_files in instance.data["expectedFiles"][0].values()
            for path in aov_files
        ]
        if instance.data.get("renderTarget") == "local":
            for directory in {os.path.dirname(path) for path in files}:
                os.makedirs(directory, exist_ok=True)

            take = instance.data["transientData"]["take"]
            self.log.info(f"Rendering take '{take.GetName()}' ...")
            render_data = exporters.render_take(
                instance.context.data["doc"], take
            )
            self.log.info(f"Rendered '{render_data.GetName()}'.")

        missing = [path for path in files if not os.path.exists(path)]
        if missing:
            raise publish.PublishError(
                "{} of {} expected frame(s) were not rendered, e.g. {}".format(
                    len(missing), len(files), missing[0]
                )
            )

        # Done: skip integration and the ayon-deadline Cinema4D submitter
        instance.data["publish"] = False
