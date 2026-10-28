from __future__ import annotations

import webbrowser
import urllib.parse
from typing import Any, Optional

import ayon_api

from ayon_core.pipeline.actions import (
    LoaderActionResult,
    LoaderActionSelection,
    LoaderSimpleActionPlugin,
)


class OpenInAYONWeb(LoaderSimpleActionPlugin):
    """Open the selected version in the AYON web interface."""

    identifier = "cinema4d.open_in_ayon_web"
    label = "Open in AYON"
    order = 100
    icon = {"type": "material-symbols", "name": "open_in_new", "color": "#5bb8f5"}

    def is_compatible(self, selection: LoaderActionSelection) -> bool:
        return bool(selection.selected_ids) and selection.selected_type in {
            "version", "representation"
        }

    def execute_simple_action(
        self,
        selection: LoaderActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        if selection.versions_selected():
            version_ids = selection.selected_ids
        else:
            version_ids = {
                repre["versionId"]
                for repre in selection.get_selected_representation_entities()
            }

        project_name = selection.project_name
        base_url = ayon_api.get_base_url().rstrip("/")
        # several selected: open the first, the web page has its own list
        version_id = sorted(version_ids)[0]
        query = urllib.parse.urlencode(
            {"project": project_name, "type": "version", "id": version_id})
        url = f"{base_url}/projects/{project_name}/products?{query}"
        webbrowser.open_new_tab(url)
        return LoaderActionResult(f"Opened {url}")
