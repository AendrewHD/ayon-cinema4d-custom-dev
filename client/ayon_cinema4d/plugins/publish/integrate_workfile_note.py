from datetime import datetime

import pyblish.api

from ayon_core.pipeline.workfile import save_workfile_info

NOTE_PREFIX = "★ Published:"


class IntegrateWorkfilePublishedNote(pyblish.api.InstancePlugin):
    """Mark the source workfile as published in its artist note.

    Adds 'Published: <product> v<NNN>' as first line of the workfile
    description, shown in the Workfiles tool. Older publish lines are
    replaced, the artist's own note is kept.
    """

    label = "Mark Workfile Published"
    order = pyblish.api.IntegratorOrder + 0.25
    hosts = ["cinema4d"]
    families = ["workfile"]

    def process(self, instance):
        version = instance.data.get("versionEntity")
        task = instance.data.get("taskEntity")
        if not version or not task:
            return

        from ayon_cinema4d.api.doc_context import (
            get_rootless_path,
            get_workfile_entity,
        )

        context = instance.context
        project_name = context.data["projectName"]
        path = context.data["currentFile"]
        rootless = get_rootless_path(project_name, path)
        if not rootless:
            self.log.warning(f"Workfile is outside the project roots: {path}")
            return

        workfile = get_workfile_entity(project_name, path) or {}
        description = (workfile.get("attrib") or {}).get("description") or ""
        lines = [
            line for line in description.splitlines()
            if not line.startswith(NOTE_PREFIX)
        ]
        note = (
            f"{NOTE_PREFIX} {instance.data['productName']} "
            f"v{version['version']:03d} "
            f"({datetime.now():%Y-%m-%d %H:%M})"
        )
        save_workfile_info(
            project_name,
            task["id"],
            rootless,
            "cinema4d",
            description="\n".join([note] + lines),
            data={"publishedVersionId": version["id"]},
        )
        self.log.debug(note)
