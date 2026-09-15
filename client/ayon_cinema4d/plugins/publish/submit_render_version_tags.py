import json
import os

import pyblish.api

from ayon_core.pipeline.farm.pyblish_functions import create_metadata_path


class SubmitRenderVersionTags(pyblish.api.InstancePlugin):
    """Add the version tags of a farm render to its publish job metadata.

    The ayon-deadline publish job (`ProcessSubmittedJobOnFarm`) creates the
    farm instances with core `create_skeleton_instance`, which doesn't pass
    `versionTags` on. The publish job depends on the render job, so the
    metadata is updated before it's read.
    """

    label = "Add Version Tags to Farm Publish"
    # After `ProcessSubmittedJobOnFarm` wrote the metadata
    order = pyblish.api.IntegratorOrder + 0.21
    hosts = ["cinema4d"]
    families = ["render"]
    targets = ["local"]

    def process(self, instance):
        tags = instance.data.get("versionTags")
        if not instance.data.get("farm") or not tags:
            return

        metadata_path, _ = create_metadata_path(
            instance, instance.context.data["anatomy"]
        )
        if not os.path.exists(metadata_path):
            self.log.warning(
                f"No publish metadata at '{metadata_path}', version tags"
                f" {tags} are not added."
            )
            return

        with open(metadata_path, "r") as stream:
            metadata = json.load(stream)
        for publish_instance in metadata.get("instances", []):
            instance_tags = list(publish_instance.get("versionTags") or [])
            instance_tags.extend(t for t in tags if t not in instance_tags)
            publish_instance["versionTags"] = instance_tags
        with open(metadata_path, "w") as stream:
            json.dump(metadata, stream, indent=4, sort_keys=True)

        self.log.debug(f"Added version tags {tags} to: {metadata_path}")
