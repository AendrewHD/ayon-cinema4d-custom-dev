import inspect

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_cinema4d.api import lib


class AddProjectTagAction(RepairAction):
    label = "Add Tag to Project"
    icon = "tag"


class ValidateRenderQuality(pyblish.api.InstancePlugin):
    """Validate the render quality exists as tag in the project anatomy.

    The render quality is added to the published version as tag, AYON only
    accepts tags defined in the project anatomy. `CollectApplyRenderSettings`
    adds a missing tag automatically when the user has the rights.
    """

    label = "Validate Render Quality"
    order = ValidateContentsOrder
    hosts = ["cinema4d"]
    families = ["render"]
    actions = [AddProjectTagAction]

    def process(self, instance):
        quality = instance.data.get("renderQuality")
        if not quality:
            return

        if not lib.core_supports_version_tags():
            self.log.warning(
                "ayon-core doesn't write version tags, the render quality"
                f" '{quality}' is not added to the version."
            )
            return

        project_entity = instance.context.data["projectEntity"]
        tags = {tag["name"] for tag in project_entity.get("tags", [])}
        if quality in tags:
            return

        raise PublishValidationError(
            f"Render quality '{quality}' is not a tag of the project.",
            title="Render quality tag missing",
            description=inspect.cleandoc(
                f"""### Render quality tag missing

                The render quality **{quality}** is added to the version as
                tag, but the project has no tag with that name and it could
                not be added (project manager rights needed).

                Add it in *Project Settings > Anatomy > Tags* or ask a
                project manager. The qualities are set in
                *cinema4d/create/RenderlayerCreator*.
                """
            ),
        )

    @classmethod
    def repair(cls, instance):
        quality = instance.data["renderQuality"]
        if lib.add_project_tag(instance.context.data["projectName"], quality):
            cls.log.info(f"Added tag '{quality}' to the project.")
