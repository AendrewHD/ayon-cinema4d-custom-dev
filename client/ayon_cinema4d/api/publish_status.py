"""Publish status of the active document (see `ui/windows/publish_status`).

What was published from this workfile, the task's latest workfile publish
and the state of the loaded containers.
"""
import os
import logging

import ayon_api

from ayon_core.pipeline import registered_host

from . import doc_context

log = logging.getLogger(__name__)

VERSION_FIELDS = {
    "id", "version", "productId", "createdAt", "author", "attrib.source",
    "attrib.comment", "status",
}


def _same_path(a, b):
    return bool(a and b) and a.replace("\\", "/").lower() == b.lower()


def _version_row(version, products):
    product = products.get(version["productId"], {})
    attrib = version.get("attrib") or {}
    return {
        "id": version["id"],
        "product": product.get("name", "?"),
        "product_type": product.get("productType", ""),
        "version": version["version"],
        "created": version.get("createdAt"),
        "author": version.get("author") or "",
        "comment": attrib.get("comment") or "",
        "status": version.get("status") or "",
        "source": os.path.basename(attrib.get("source") or ""),
    }


def get_status_data(doc):
    """Publish status of `doc`.

    Returns:
        dict: context, workfile, saved, unsaved, own (versions published
            from this file), latest_workfile (latest workfile publish of
            the task if not this file), loaded, outdated (container rows),
            message (why nothing could be checked).
    """
    host = registered_host()
    context = (
        doc_context.get_document_context(doc) or host.get_current_context())
    project_name = context["project_name"]
    path = doc_context.get_document_path(doc)
    data = {
        "context": f"{context['folder_path']}  /  {context['task_name']}",
        "workfile": os.path.basename(path) if path else doc.GetDocumentName(),
        "saved": bool(path),
        "unsaved": bool(doc.GetChanged()),
        "own": [],
        "latest_workfile": None,
        "loaded": 0,
        "outdated": [],
        "message": "",
    }
    data.update(_container_status(project_name, host))
    if not path:
        data["message"] = "Document is not saved."
        return data

    folder = ayon_api.get_folder_by_path(
        project_name, context["folder_path"], fields={"id"})
    task = folder and ayon_api.get_task_by_name(
        project_name, folder["id"], context["task_name"], fields={"id"})
    if not task:
        data["message"] = "Task not found on the server."
        return data

    rootless = doc_context.get_rootless_path(project_name, path)
    versions = list(ayon_api.get_versions(
        project_name, task_ids=[task["id"]], fields=VERSION_FIELDS))
    products = {
        product["id"]: product
        for product in ayon_api.get_products(
            project_name,
            product_ids={v["productId"] for v in versions},
            fields={"id", "name", "productType"},
        )
    } if versions else {}

    own = [
        v for v in versions
        if _same_path((v.get("attrib") or {}).get("source"), rootless)
    ]
    data["own"] = [
        _version_row(v, products)
        for v in sorted(own, key=lambda v: v["createdAt"], reverse=True)
    ]

    workfiles = sorted(
        (
            v for v in versions
            if products.get(v["productId"], {}).get("productType")
            == "workfile"
        ),
        key=lambda v: v["createdAt"],
    )
    if workfiles and workfiles[-1] not in own:
        data["latest_workfile"] = _version_row(workfiles[-1], products)
    return data


def _container_status(project_name, host):
    containers = [
        c for c in host.get_containers()
        if c.get("project_name", project_name) == project_name
    ]
    repre_ids = {c.get("representation") for c in containers}
    repre_ids.discard(None)
    if not repre_ids:
        return {"loaded": len(containers)}

    repres = {
        r["id"]: r for r in ayon_api.get_representations(
            project_name, representation_ids=repre_ids,
            fields={"id", "versionId"})
    }
    versions = {
        v["id"]: v for v in ayon_api.get_versions(
            project_name,
            version_ids={r["versionId"] for r in repres.values()},
            fields={"id", "version", "productId"})
    }
    products = {
        p["id"]: p for p in ayon_api.get_products(
            project_name,
            product_ids={v["productId"] for v in versions.values()},
            fields={"id", "name", "productType"})
    } if versions else {}
    last = ayon_api.get_last_versions(
        project_name, set(products), fields={"version", "productId"}
    ) if products else {}

    outdated = []
    for container in containers:
        repre = repres.get(container.get("representation"))
        version = repre and versions.get(repre["versionId"])
        latest = version and last.get(version["productId"])
        if not latest or version["version"] < 0:
            continue
        if version["version"] < latest["version"]:
            product = products.get(version["productId"], {})
            outdated.append({
                "name": container.get("namespace") or container.get("name"),
                "product": product.get("name", "?"),
                "product_type": product.get("productType", ""),
                "version": version["version"],
                "latest": latest["version"],
            })
    return {"loaded": len(containers), "outdated": outdated}
