import inspect

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_cinema4d.api import lib

import c4d


class ValidateRenderSettings(pyblish.api.InstancePlugin):
    """Validate the render settings of each rendered take against the product.

    `CollectApplyRenderSettings` applies the product before, this catches
    what couldn't be applied: frame range (handles included), frame step,
    frame rate, resolution, disabled saving and missing or shared outputs.
    """

    label = "Validate Render Settings"
    order = ValidateContentsOrder
    hosts = ["cinema4d"]
    families = ["render"]
    actions = [RepairAction]

    def process(self, instance):
        errors = self.get_invalid(instance)
        if not errors:
            return

        for message in errors:
            self.log.error(message)
        take, render_data = self.get_render_data(instance)
        report = "\n".join(f"- {message}" for message in errors)
        raise PublishValidationError(
            "Render settings '{}' of take '{}' don't match the render"
            " product.".format(render_data.GetName(), take.GetName()),
            title="Render settings mismatch",
            description=inspect.cleandoc(
                """### Render settings mismatch

                Render settings **{}** of take **{}**:

                {}

                *Repair* applies the product frame range, frame rate and
                resolution to these render settings.
                """
            ).format(render_data.GetName(), take.GetName(), report),
        )

    @staticmethod
    def get_render_data(instance):
        doc = instance.context.data["doc"]
        take = instance.data["transientData"]["take"]
        return lib.get_take_render_data(doc, take)

    @classmethod
    def get_invalid(cls, instance):
        """Return error messages."""
        _take, render_data = cls.get_render_data(instance)
        errors = lib.apply_render_product(
            instance.context.data["doc"],
            render_data,
            lib.get_render_product(instance.data["creator_attributes"]),
            dry_run=True,
        )

        # Nothing would be written to disk
        saves = (
            render_data[c4d.RDATA_SAVEIMAGE]
            or render_data[c4d.RDATA_MULTIPASS_SAVEIMAGE]
        )
        if not render_data[c4d.RDATA_GLOBALSAVE] or not saves:
            errors.append(
                "Saving is disabled, enable Save for the regular or"
                " Multi-Pass image."
            )
        errors.extend(cls.get_invalid_outputs(instance))
        return errors

    @staticmethod
    def get_invalid_outputs(instance):
        """Return errors for missing or shared output files."""
        files = {
            path
            for aov_files in instance.data.get("expectedFiles", [{}])[0]
            .values()
            for path in aov_files
        }
        if not files:
            return ["No output files found, the output settings or the"
                    " renderer are not supported."]

        # Marked takes writing to the same files overwrite each other
        errors = []
        for other in instance.context:
            if (
                other is instance
                or other.data.get("publish") is False
                or other.data.get("productBaseType") != "render"
                or not other.data.get("expectedFiles")
            ):
                continue
            other_files = {
                path
                for aov_files in other.data["expectedFiles"][0].values()
                for path in aov_files
            }
            if files & other_files:
                errors.append(
                    "Output files are shared with '{}', add the $take"
                    " token to the output paths.".format(
                        other.data["productName"]
                    )
                )
        return errors

    @classmethod
    def repair(cls, instance):
        _take, render_data = cls.get_render_data(instance)
        lib.apply_render_product(
            instance.context.data["doc"],
            render_data,
            lib.get_render_product(instance.data["creator_attributes"]),
        )
        c4d.EventAdd()
        cls.log.info(f"Applied product settings to: {render_data.GetName()}")
