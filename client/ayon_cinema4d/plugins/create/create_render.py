import inspect

from ayon_core.lib import BoolDef, EnumDef, NumberDef, UILabelDef
from ayon_cinema4d.api import lib, lib_renderproducts, plugin


class RenderlayerCreator(plugin.Cinema4DCreator):
    """Render the current take or the marked takes with their render settings.

    Nothing is added to the scene besides the instance node. Frame range,
    frame step, frame rate, resolution and output paths of this product are
    applied to each rendered take's render settings before rendering.
    """

    identifier = "io.ayon.creators.cinema4d.render"
    label = "Render"
    description = "Render the current or marked takes."
    detailed_description = inspect.cleandoc(__doc__)
    product_base_type = "render"
    product_type = product_base_type
    icon = "eye"

    render_target = "farm"
    default_chunk_size = 10
    # Overridden by settings: cinema4d/create/RenderlayerCreator
    render_qualities = lib_renderproducts.DEFAULT_RENDER_QUALITIES

    def get_instance_attr_defs(self):
        doc = lib.active_document()
        defs = lib.collect_animation_defs(self.create_context, fps=True)
        defs.append(NumberDef(
            "frameStep", label="Frame Step", default=1, minimum=1,
            decimals=0, tooltip="Render every n-th frame."))
        defs.extend(lib.collect_resolution_defs(self.create_context))

        qualities = {
            item["name"]: item["label"] or item["name"]
            for item in self.render_qualities
        }
        if qualities:
            defs.append(EnumDef(
                "render_quality",
                label="Render Quality",
                items=qualities,
                default=next(iter(qualities)),
                tooltip="Added to the published version as tag.",
            ))

        _take, render_data = lib.get_take_render_data(doc)
        defs.extend([
            EnumDef(
                "render_target",
                label="Render Target",
                items={
                    "farm": "Farm rendering",
                    "local": "Local machine rendering",
                    "local_no_render": "Use existing frames (local)",
                },
                tooltip=(
                    "Local rendering blocks Cinema 4D until the render is"
                    " done. Existing frames publishes the frames already"
                    " rendered to the output paths."
                ),
                default=self.render_target),
            BoolDef(
                "publishTakes",
                label="Render Marked Takes",
                tooltip=(
                    "Render a separate product per take marked in the Take"
                    " Manager, with the take name appended to the variant,"
                    " e.g. 'renderMain_Hero'. Each take uses its own render"
                    " settings."
                ),
                default=False),
            UILabelDef(
                lib.get_marked_takes_label(doc),
                tooltip="Refresh the publisher after changing take marks."),
            UILabelDef(
                "Current render settings: {}".format(render_data.GetName()),
                tooltip="Render settings of the current take."),
        ])
        return defs

    def get_pre_create_attr_defs(self):
        return []
