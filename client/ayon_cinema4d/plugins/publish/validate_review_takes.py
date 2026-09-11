import inspect

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_cinema4d.api import lib


class ValidateMarkedTakes(pyblish.api.InstancePlugin):
    """Validate takes are marked when marked takes are published.

    Without a marked take there is nothing to publish per take, and silently
    publishing the current take instead would not be what the artist asked
    for.
    """

    label = "Validate Marked Takes"
    order = ValidateContentsOrder
    hosts = ["cinema4d"]
    families = ["review", "render"]

    def process(self, instance):
        if not instance.data.get("publishTakes") or "take" in instance.data:
            return

        if any(lib.iter_marked_takes(instance.context.data["doc"])):
            return

        option = "Publish Marked Takes"
        if instance.data.get("productBaseType") == "render":
            option = "Render Marked Takes"
        raise PublishValidationError(
            f"'{option}' is enabled but no take is marked.",
            title="No marked takes",
            description=inspect.cleandoc(
                f"""### No marked takes

                **{option}** is enabled, but no take is marked in the
                Take Manager.

                Mark the takes to publish (checkbox next to the take name)
                and refresh the publisher, or disable **{option}** to
                publish the current take.
                """
            ),
        )
