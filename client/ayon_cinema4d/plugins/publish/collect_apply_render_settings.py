import pyblish.api

from ayon_cinema4d.api import lib, lib_renderproducts

import c4d


class CollectApplyRenderSettings(pyblish.api.InstancePlugin):
    """Apply the render product to the render settings before rendering.

    Frame range (handles included), frame step, frame rate, resolution and
    output paths of each rendered take's render settings are set from the
    product, and a missing render quality tag is added to the project. The
    workfile is saved before a farm submission (`SaveCurrentScene`), so the
    farm renders the same settings.
    """

    label = "Apply Render Product Settings"
    # After `CollectMarkedTakes`, before `CollectCinema4DRender`
    order = pyblish.api.CollectorOrder + 0.09
    hosts = ["cinema4d"]
    families = ["render"]

    def process(self, instance):
        # Source of marked takes, the takes are applied on their instances
        if instance.data.get("publish") is False:
            return

        doc = instance.context.data["doc"]
        attrs = instance.data["creator_attributes"]
        _take, render_data = lib.get_take_render_data(
            doc, instance.data.get("take")
        )
        self.apply_render_settings(instance, doc, render_data, attrs)
        self.ensure_quality_tag(instance, attrs.get("render_quality"))

    def apply_render_settings(self, instance, doc, render_data, attrs):
        product = lib.get_render_product(attrs)
        project_settings = instance.context.data["project_settings"]
        changes = lib.apply_render_product(
            doc, render_data, product, dry_run=True
        )
        changes += lib_renderproducts.apply_render_output_paths(
            doc, render_data, project_settings, dry_run=True
        )
        if not changes:
            return

        with lib.undo_chunk():
            doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, render_data)
            lib.apply_render_product(doc, render_data, product)
            lib_renderproducts.apply_render_output_paths(
                doc, render_data, project_settings
            )
        c4d.EventAdd()
        self.log.info(
            "Applied to render settings '{}':\n{}".format(
                render_data.GetName(),
                "\n".join(f"- {change}" for change in changes),
            )
        )

    def ensure_quality_tag(self, instance, quality):
        """Add the render quality tag to the project when it's missing.

        Needs project manager rights, `ValidateRenderQuality` reports a
        failure.
        """
        if not quality or not lib.core_supports_version_tags():
            return

        context = instance.context
        tags = context.data["projectEntity"].setdefault("tags", [])
        if quality in {tag["name"] for tag in tags}:
            return
        try:
            lib.add_project_tag(context.data["projectName"], quality)
        except Exception as exc:
            self.log.warning(f"Could not add tag '{quality}': {exc}")
            return
        tags.append({"name": quality})
        self.log.info(f"Added tag '{quality}' to the project.")
