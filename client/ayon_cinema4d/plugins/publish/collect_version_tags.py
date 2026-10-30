import pyblish.api

from ayon_cinema4d.api import lib


class CollectVersionTags(pyblish.api.InstancePlugin):
    """Add the `version_tags` of the instance's creator to the version.

    Set in the creator settings, e.g. cinema4d/create/CreateReview. The tags
    don't have to exist in the project anatomy; AYON shows tags that aren't
    there without a colour.
    """

    label = "Collect Version Tags"
    # After `CollectMarkedTakes` and `CollectCinema4DRender`, before
    # `CollectCinema4DRenderLocal` copies `versionTags` to the AOV instances
    order = pyblish.api.CollectorOrder + 0.12
    hosts = ["cinema4d"]

    def process(self, instance):
        create_context = instance.context.data.get("create_context")
        creator = create_context and create_context.creators.get(
            instance.data.get("creator_identifier")
        )
        tags = list(instance.data.get("versionTags") or [])
        for tag in getattr(creator, "version_tags", None) or []:
            if tag and tag not in tags:
                tags.append(tag)
        if not tags:
            return

        instance.data["versionTags"] = tags
        if not lib.core_supports_version_tags():
            self.log.warning(
                "ayon-core < 1.9.8 doesn't write version tags, not added:"
                f" {', '.join(tags)}"
            )
            return
        self.log.debug(f"Version tags: {tags}")
