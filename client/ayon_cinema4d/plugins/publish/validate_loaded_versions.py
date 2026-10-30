"""Products loaded through AYON must be on their latest version."""
import c4d
import pyblish.api

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairContextAction,
)

from ayon_cinema4d.api import inventory, pipeline, tag_status

DESCRIPTION = """### Outdated loaded products

These products in the scene have a newer version on AYON:

{items}

**Fix:** run the *Update to Latest* action or update them in
**AYON > Manage**, then publish again.

**Publish anyway:** turn off *Validate Loaded Versions* in the Publisher
(select **Context**) or in the AYON Publish panel (no instance selected).
Outdated products are then only logged as a warning.
"""


class OpenManageAction(pyblish.api.Action):
    label = "Open Manage"
    icon = "briefcase"
    on = "failed"

    def process(self, context, plugin):
        from ayon_cinema4d.api.ui import ids

        c4d.CallCommand(ids.MANAGE)


class UpdateToLatestAction(RepairContextAction):
    label = "Update to Latest"
    icon = "refresh"


def _collect(context):
    rows = inventory.collect_inventory(
        pipeline.iter_containers(context.data.get("doc")))
    tag_status.store(rows)  # tag icons match the publish result
    return rows


def _describe(row):
    """`/folder / product v003 -> v005 (object)`, object only if missing."""
    container = row["container"]
    name = container.get("objectName") or container.get("name") or "?"
    if row["state"] != inventory.STATE_OUTDATED:
        return name
    folder = (row["folder"] or {}).get("path", "?")
    version = row["version"]["version"]
    last = row["last_version"]["version"]
    return (f"`{folder}` / `{row['product']['name']}`"
            f" v{version:03d} -> v{last:03d} ({name})")


class ValidateLoadedVersions(
    pyblish.api.ContextPlugin, OptionalPyblishPluginMixin
):
    """Products loaded in the scene are on their latest version.

    Hero versions count as latest. Products not found on the server only
    log a warning. Turned off by the artist, outdated products are logged
    as a warning instead of failing the publish.
    """

    label = "Validate Loaded Versions"
    order = pyblish.api.ValidatorOrder
    hosts = ["cinema4d"]
    optional = True
    optional_tooltip = (
        "Off: publish with outdated loaded products, only a warning is logged"
    )
    actions = [OpenManageAction, UpdateToLatestAction]

    settings_category = "cinema4d"

    def process(self, context):
        rows = _collect(context)
        for row in rows:
            if row["state"] == inventory.STATE_MISSING:
                self.log.warning(f"Not found on AYON: {_describe(row)}")

        outdated = [_describe(r) for r in rows
                    if r["state"] == inventory.STATE_OUTDATED]
        if not outdated:
            self.log.debug(f"{len(rows)} loaded product(s) checked.")
            return

        if not self.is_active(context.data):
            self.log.warning(
                "Check turned off, publishing with outdated products:\n"
                + "\n".join(outdated))
            return

        raise PublishValidationError(
            f"{len(outdated)} loaded product(s) not on the latest version:\n"
            + "\n".join(outdated),
            title="Outdated loaded products",
            description=DESCRIPTION.format(
                items="\n".join(f"- {line}" for line in outdated)),
        )

    @classmethod
    def repair(cls, context):
        from ayon_core.pipeline.load import update_container

        failed = []
        for row in _collect(context):
            if row["state"] != inventory.STATE_OUTDATED:
                continue
            try:
                update_container(row["container"], -1)
            except Exception as error:
                cls.log.warning(f"Update of {_describe(row)} failed",
                                exc_info=True)
                failed.append(f"{_describe(row)}: {error}")
        tag_status.mark_dirty()
        c4d.EventAdd()
        if failed:
            raise RuntimeError("Update failed:\n" + "\n".join(failed))
