import inspect

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_cinema4d.api import lib

import c4d

FRAME_MODE_LABELS = {
    c4d.RDATA_FRAMESEQUENCE_MANUAL: "Manual",
    c4d.RDATA_FRAMESEQUENCE_CURRENTFRAME: "Current Frame",
    c4d.RDATA_FRAMESEQUENCE_ALLFRAMES: "All Frames",
    c4d.RDATA_FRAMESEQUENCE_PREVIEWRANGE: "Preview Range",
}

class ValidateRenderSettings(pyblish.api.InstancePlugin):
    """Validate the render settings of each rendered take against the product.

    Checks frame range (handles included), frame step, frame rate and
    resolution of the take's effective render settings. Final renders must
    match exactly. Previews may render a part of the product range, use frame
    steps or a scaled resolution with the same aspect ratio (warnings only).
    """

    label = "Validate Render Settings"
    order = ValidateContentsOrder
    hosts = ["cinema4d"]
    families = ["render"]
    actions = [RepairAction]

    def process(self, instance):
        errors, warnings = self.get_invalid(instance)
        for message in warnings:
            self.log.warning(message)
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
                resolution to these render settings. Output paths are
                repaired by *Validate Render Output Paths*.
                """
            ).format(render_data.GetName(), take.GetName(), report),
        )

    @staticmethod
    def get_render_data(instance):
        doc = instance.context.data["doc"]
        take = instance.data["transientData"]["take"]
        return lib.get_take_render_data(doc, take)

    @staticmethod
    def get_product_values(instance):
        """Return the product settings the render settings must match."""
        attrs = instance.data["creator_attributes"]
        return {
            "frame_start": int(attrs["frameStart"] - attrs["handleStart"]),
            "frame_end": int(attrs["frameEnd"] + attrs["handleEnd"]),
            "fps": float(attrs["fps"]),
            "width": int(attrs["resolutionWidth"]),
            "height": int(attrs["resolutionHeight"]),
            "pixel_aspect": float(attrs["pixelAspect"]),
        }

    @classmethod
    def get_invalid(cls, instance):
        """Return error and warning messages."""
        doc = instance.context.data["doc"]
        _take, render_data = cls.get_render_data(instance)
        product = cls.get_product_values(instance)
        strict = instance.data.get("renderQualityStrict", True)
        errors, warnings = [], []
        # Allowed deviations of previews are warnings
        relaxed = errors if strict else warnings

        # Frame range, handles included
        start, end = product["frame_start"], product["frame_end"]
        render_range = lib.get_render_frame_range(doc, render_data)
        if render_range is None:
            errors.append(
                "Frame range 'Custom' is not supported, use Manual,"
                " All Frames or Preview Range."
            )
        elif render_range != (start, end):
            mode = FRAME_MODE_LABELS.get(
                render_data[c4d.RDATA_FRAMESEQUENCE], ""
            )
            message = "Frame range {}-{} ({}) doesn't match {}-{}.".format(
                *render_range, mode, start, end
            )
            inside = start <= render_range[0] <= render_range[1] <= end
            (relaxed if inside else errors).append(message)

        step = int(render_data[c4d.RDATA_FRAMESTEP])
        if step != 1:
            relaxed.append(f"Frame step is {step}, not 1.")

        # Frame rate of the render settings and the document
        fps = product["fps"]
        render_fps = float(render_data[c4d.RDATA_FRAMERATE])
        if abs(render_fps - fps) > 0.001:
            errors.append(f"Frame rate {render_fps:g} doesn't match {fps:g}.")
        doc_fps = lib.get_document_fps(fps)
        if doc.GetFps() != doc_fps:
            errors.append(
                f"Project frame rate {doc.GetFps()} doesn't match {doc_fps}."
            )

        # Resolution
        width = int(round(render_data[c4d.RDATA_XRES]))
        height = int(round(render_data[c4d.RDATA_YRES]))
        if (width, height) != (product["width"], product["height"]):
            message = "Resolution {}x{} doesn't match {}x{}.".format(
                width, height, product["width"], product["height"]
            )
            same_aspect = abs(
                width / height - product["width"] / product["height"]
            ) < 0.01
            (relaxed if same_aspect else errors).append(message)

        pixel_aspect = float(render_data[c4d.RDATA_PIXELASPECT])
        if abs(pixel_aspect - product["pixel_aspect"]) > 0.001:
            errors.append("Pixel aspect {:g} doesn't match {:g}.".format(
                pixel_aspect, product["pixel_aspect"]
            ))
        if render_data[c4d.RDATA_RENDERREGION]:
            errors.append("Render Region is enabled.")

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

        return errors, warnings

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
        doc = instance.context.data["doc"]
        _take, render_data = cls.get_render_data(instance)
        product = cls.get_product_values(instance)

        doc.SetFps(lib.get_document_fps(product["fps"]))
        lib.set_render_frame_range(render_data,
                                   product["frame_start"],
                                   product["frame_end"],
                                   product["fps"])
        render_data[c4d.RDATA_FRAMESTEP] = 1
        lib.set_render_resolution(render_data,
                                  product["width"],
                                  product["height"],
                                  product["pixel_aspect"])
        render_data[c4d.RDATA_RENDERREGION] = False
        c4d.EventAdd()
        cls.log.info(f"Applied product settings to: {render_data.GetName()}")
