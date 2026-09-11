import pyblish.api

from ayon_cinema4d.api import plugin


class CollectReviewFarm(pyblish.api.InstancePlugin):
    """Collect whether the review is rendered on the farm.

    Farm reviews are rendered and published by Deadline jobs, see
    `Cinema4DSubmitReviewDeadline`.
    """

    label = "Collect Review Render Target"
    # Before `CollectReviewTakes` so take instances inherit the result
    order = pyblish.api.CollectorOrder - 0.49
    hosts = ["cinema4d"]
    families = ["review"]

    def process(self, instance):
        creator_attributes = instance.data.get("creator_attributes", {})
        farm = creator_attributes.get("render_target") == "farm"
        instance.data["farm"] = farm

        families = instance.data.setdefault("families", [])
        if farm and plugin.FARM_FAMILY not in families:
            families.append(plugin.FARM_FAMILY)
        elif not farm and plugin.FARM_FAMILY in families:
            families.remove(plugin.FARM_FAMILY)

        self.log.debug(
            "Review renders on the farm." if farm
            else "Review renders on the local machine."
        )
