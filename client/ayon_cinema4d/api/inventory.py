"""Version state of loaded containers on the AYON server.

Shared by the Manage window and the AYON tag icons (`tag_status`).
"""
import ayon_api

from ayon_core.pipeline import get_current_project_name

STATE_LATEST = "latest"
STATE_OUTDATED = "outdated"
STATE_HERO = "hero"
STATE_MISSING = "missing"


def collect_inventory(containers):
    """Server info per container.

    Returns:
        list[dict]: One row per container: container, project_name,
            folder, product, version, last_version, repre, state.
    """
    by_project = {}
    for container in containers:
        project_name = (
            container.get("project_name") or get_current_project_name())
        by_project.setdefault(project_name, []).append(container)

    rows = []
    for project_name, project_containers in by_project.items():
        repre_ids = {c.get("representation") for c in project_containers}
        repre_ids.discard(None)
        repres = {
            r["id"]: r for r in ayon_api.get_representations(
                project_name, representation_ids=repre_ids,
                fields={"id", "name", "versionId"})
        } if repre_ids else {}
        versions = {
            v["id"]: v for v in ayon_api.get_versions(
                project_name,
                version_ids={r["versionId"] for r in repres.values()},
                fields={"id", "version", "productId", "status"})
        } if repres else {}
        product_ids = {v["productId"] for v in versions.values()}
        products = {
            p["id"]: p for p in ayon_api.get_products(
                project_name, product_ids=product_ids,
                fields={"id", "name", "productType", "folderId"})
        } if product_ids else {}
        folders = {
            f["id"]: f for f in ayon_api.get_folders(
                project_name,
                folder_ids={p["folderId"] for p in products.values()},
                fields={"id", "path"})
        } if products else {}
        last_versions = ayon_api.get_last_versions(
            project_name, product_ids, fields={"id", "version", "productId"}
        ) if product_ids else {}

        for container in project_containers:
            repre = repres.get(container.get("representation"))
            version = repre and versions.get(repre["versionId"])
            product = version and products.get(version["productId"])
            folder = product and folders.get(product["folderId"])
            last = product and last_versions.get(product["id"])
            if not version:
                state = STATE_MISSING
            elif version["version"] < 0:
                state = STATE_HERO
            elif last and version["version"] < last["version"]:
                state = STATE_OUTDATED
            else:
                state = STATE_LATEST
            rows.append({
                "container": container,
                "project_name": project_name,
                "folder": folder,
                "product": product,
                "version": version,
                "last_version": last,
                "repre": repre,
                "state": state,
            })
    return rows
