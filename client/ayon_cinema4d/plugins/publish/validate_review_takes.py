import inspect

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_cinema4d.api import lib


class ValidateReviewTakes(pyblish.api.InstancePlugin):
    """Validate takes are marked when 'Publish Marked Takes' is enabled.

    Without a marked take there is nothing to publish per take, and silently
    publishing the review instead would not be what the artist asked for.
    """

    label = "Validate Marked Takes"
    order = ValidateContentsOrder
    hosts = ["cinema4d"]
    families = ["review"]

    def process(self, instance):
        if not instance.data.get("publishTakes") or "take" in instance.data:
            return

        if any(lib.iter_marked_takes(instance.context.data["doc"])):
            return

        raise PublishValidationError(
            "'Publish Marked Takes' is enabled but no take is marked.",
            title="No marked takes",
            description=inspect.cleandoc(
                """### No marked takes

                The review has **Publish Marked Takes** enabled, but no take
                is marked in the Take Manager.

                Mark the takes to publish (checkbox next to the take name)
                and refresh the publisher, or disable **Publish Marked Takes**
                to publish the review from the current take.
                """
            ),
        )
