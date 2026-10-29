import pyblish.api


class NotifyNativeWindows(pyblish.api.ContextPlugin):
    """Let the open AYON windows (Publish Status...) show the new publish."""

    label = "Update AYON Windows"
    order = pyblish.api.IntegratorOrder + 0.499
    hosts = ["cinema4d"]

    def process(self, context):
        try:
            from ayon_cinema4d.api.ui import events
        except Exception:  # no Cinema 4D GUI (farm publish job)
            return
        events.notify(events.PUBLISH)
