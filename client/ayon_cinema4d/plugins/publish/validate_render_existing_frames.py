import inspect
import os

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)


def get_missing_files(instance):
    """Return the expected render files that don't exist."""
    return [
        path
        for aov_files in instance.data.get("expectedFiles", [{}])[0].values()
        for path in aov_files
        if not os.path.exists(path)
    ]


class ValidateRenderExistingFrames(pyblish.api.InstancePlugin):
    """Validate all frames exist when publishing existing frames."""

    label = "Validate Existing Frames"
    order = ValidateContentsOrder
    hosts = ["cinema4d"]
    families = ["render"]

    def process(self, instance):
        if instance.data.get("renderTarget") != "local_no_render":
            return

        missing = get_missing_files(instance)
        if not missing:
            return

        report = "\n".join(f"- {path}" for path in missing[:20])
        if len(missing) > 20:
            report += f"\n- ... {len(missing) - 20} more"
        raise PublishValidationError(
            f"{len(missing)} expected frame(s) are missing.",
            title="Missing frames",
            description=inspect.cleandoc(
                """### Missing frames

                *Use existing frames* publishes frames already rendered to
                the output paths of the render settings. These are missing:

                {}

                Render them first or choose another render target.
                """
            ).format(report),
        )
