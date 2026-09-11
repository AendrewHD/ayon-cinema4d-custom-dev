import inspect
import re

import ayon_api
import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_core.version import __version__ as core_version

# First ayon-core version integrating `versionTags`
VERSION_TAGS_CORE_VERSION = (1, 9, 8)
TAG_COLOR = "#5bb8f5"


class AddProjectTagAction(RepairAction):
    label = "Add Tag to Project"
    icon = "tag"


class ValidateRenderQuality(pyblish.api.InstancePlugin):
    """Validate the render quality exists as tag in the project anatomy.

    The render quality is added to the published version as tag, AYON only
    accepts tags defined in the project anatomy.
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

        core = tuple(int(n) for n in re.findall(r"\d+", core_version)[:3])
        if core < VERSION_TAGS_CORE_VERSION:
            self.log.warning(
                f"ayon-core {core_version} doesn't write version tags, the"
                f" render quality '{quality}' is not added to the version."
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
                tag, but the project has no tag with that name.

                *Add Tag to Project* adds it to the project anatomy (needs
                project manager rights), or add it in *Project Settings >
                Anatomy > Tags*. The qualities are set in
                *cinema4d/create/RenderlayerCreator*.
                """
            ),
        )

    @classmethod
    def repair(cls, instance):
        quality = instance.data["renderQuality"]
        project_name = instance.context.data["projectName"]
        tags = ayon_api.get_project(project_name).get("tags") or []
        if quality in {tag["name"] for tag in tags}:
            return
        ayon_api.update_project(
            project_name, tags=tags + [{"name": quality, "color": TAG_COLOR}]
        )
        cls.log.info(f"Added tag '{quality}' to project '{project_name}'.")
