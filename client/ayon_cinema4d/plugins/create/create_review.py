from ayon_core.lib import BoolDef, EnumDef, UILabelDef
from ayon_cinema4d.api import (
    lib,
    plugin
)


class CreateReview(plugin.Cinema4DCreator):
    """Viewport render reviewable"""

    identifier = "io.ayon.creators.cinema4d.review"
    label = "Review"
    description = __doc__
    product_base_type = "review"
    product_type = product_base_type
    icon = "video-camera"

    render_target = "local"
    default_chunk_size = 10

    def get_publish_families(self):
        # Shows the Deadline job options on the instance. Removed again by
        # `CollectReviewFarm` when the review renders locally.
        return [plugin.FARM_FAMILY]

    def get_instance_attr_defs(self):
        # `fps` is required by ayon-core ExtractReview
        defs = lib.collect_animation_defs(self.create_context, fps=True)
        defs.extend([
            EnumDef(
                "render_target",
                label="Render Target",
                items={
                    "local": "Local machine rendering",
                    "farm": "Farm rendering",
                },
                tooltip=(
                    "Farm rendering renders the review with Deadline and"
                    " publishes it in a dependent Deadline job. The farm"
                    " workers need a GPU for the Viewport Renderer."
                ),
                default=self.render_target),
            BoolDef(
                "geometryOnly",
                label="Geometry Only",
                tooltip=(
                    "Render geometry only. Splines, nulls, grid and other"
                    " viewport helpers are excluded from the review."
                ),
                default=True),
            BoolDef(
                "showSplines",
                label="Show Splines",
                tooltip=(
                    "Include splines in the review. Disables 'Geometry"
                    " Only'; grid, handles and other helpers stay"
                    " excluded."
                ),
                default=False),
            BoolDef(
                "showNulls",
                label="Show Nulls",
                tooltip=(
                    "Include nulls in the review. Disables 'Geometry"
                    " Only'; grid, handles and other helpers stay"
                    " excluded."
                ),
                default=False),
            BoolDef(
                "publishTakes",
                label="Publish Marked Takes",
                tooltip=(
                    "Publish a separate review per take marked in the Take"
                    " Manager, with the take name appended to the variant,"
                    " e.g. 'reviewMain_Hero'. The review itself is not"
                    " published."
                ),
                default=False),
            UILabelDef(
                lib.get_marked_takes_label(lib.active_document()),
                tooltip="Refresh the publisher after changing take marks."),
        ])
        return defs
