import inspect

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_cinema4d.api import lib, lib_renderproducts

import c4d


class ValidateRenderOutputPaths(pyblish.api.InstancePlugin):
    """Validate the output paths of the rendered take's render settings.

    Paths must be the pipeline paths from `cinema4d/render_settings`: absolute
    (the farm renders a published copy of the workfile), unique per workfile
    and take, and frames named `Name.0000.ext`. They are applied by
    `CollectApplyRenderSettings` before.
    """

    label = "Validate Render Output Paths"
    # Before `ValidateRenderSettings` checks the collected output files
    order = ValidateContentsOrder - 0.01
    hosts = ["cinema4d"]
    families = ["render"]
    actions = [RepairAction]

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if not invalid:
            return

        for message in invalid:
            self.log.error(message)
        _take, render_data = self.get_render_data(instance)
        report = "\n".join(f"- {message}" for message in invalid)
        raise PublishValidationError(
            "Output paths of render settings '{}' are not the pipeline"
            " paths.".format(render_data.GetName()),
            title="Render output paths",
            description=inspect.cleandoc(
                """### Render output paths

                Render settings **{}**:

                {}

                *Repair* sets the pipeline output paths and the frame name
                format `Name.0000.ext` on these render settings.
                """
            ).format(render_data.GetName(), report),
        )

    @staticmethod
    def get_render_data(instance):
        doc = instance.context.data["doc"]
        take = instance.data["transientData"]["take"]
        return lib.get_take_render_data(doc, take)

    @classmethod
    def get_invalid(cls, instance):
        """Return error messages for wrong output paths."""
        _take, render_data = cls.get_render_data(instance)
        return lib_renderproducts.apply_render_output_paths(
            instance.context.data["doc"],
            render_data,
            instance.context.data["project_settings"],
            dry_run=True,
        )

    @classmethod
    def repair(cls, instance):
        _take, render_data = cls.get_render_data(instance)
        lib_renderproducts.apply_render_output_paths(
            instance.context.data["doc"],
            render_data,
            instance.context.data["project_settings"],
        )
        c4d.EventAdd()
        cls.log.info(f"Set output paths on: {render_data.GetName()}")
