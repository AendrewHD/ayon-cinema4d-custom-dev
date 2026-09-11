import inspect
import os

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_cinema4d.api import lib, lib_renderproducts

import c4d

OUTPUT_LABELS = {
    c4d.RDATA_PATH: "Regular Image",
    c4d.RDATA_MULTIPASS_FILENAME: "Multi-Pass Image",
}


class ValidateRenderOutputPaths(pyblish.api.InstancePlugin):
    """Validate the output paths of the rendered take's render settings.

    Paths must be the pipeline paths from `cinema4d/render_settings`: absolute
    (the farm renders a published copy of the workfile), unique per workfile
    and take, and frames named `Name.0000.ext`.
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
        expected = lib_renderproducts.get_render_output_paths(
            instance.context.data["doc"],
            render_data,
            instance.context.data["project_settings"],
        )

        saved = []
        if render_data[c4d.RDATA_SAVEIMAGE]:
            saved.append(c4d.RDATA_PATH)
        if render_data[c4d.RDATA_MULTIPASS_SAVEIMAGE]:
            saved.append(c4d.RDATA_MULTIPASS_FILENAME)

        invalid = []
        for param_id in saved:
            path = render_data[param_id] or ""
            if _normalize(path) != _normalize(expected[param_id]):
                invalid.append(
                    "{} path is '{}', expected '{}'.".format(
                        OUTPUT_LABELS[param_id], path, expected[param_id]
                    )
                )

        if (
            saved
            and render_data[c4d.RDATA_NAMEFORMAT]
            != lib_renderproducts.RENDER_NAME_FORMAT
        ):
            invalid.append("File name format is not 'Name.0000.ext'.")
        return invalid

    @classmethod
    def repair(cls, instance):
        _take, render_data = cls.get_render_data(instance)
        paths = lib_renderproducts.get_render_output_paths(
            instance.context.data["doc"],
            render_data,
            instance.context.data["project_settings"],
        )
        for param_id, path in paths.items():
            render_data[param_id] = path
        render_data[c4d.RDATA_NAMEFORMAT] = (
            lib_renderproducts.RENDER_NAME_FORMAT
        )
        c4d.EventAdd()
        cls.log.info(f"Set output paths on: {render_data.GetName()}")


def _normalize(path):
    return os.path.normcase(os.path.normpath(path)) if path else ""
