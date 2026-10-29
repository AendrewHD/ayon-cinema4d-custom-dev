"""Workfile helpers for the native Workfiles window and the save commands.

The paths come from the project anatomy like in `ayon_core`'s
`save_next_version`, so the native window and the Qt tool agree.
"""
import os
import logging

import c4d
import ayon_api

from ayon_core.pipeline import Anatomy, registered_host
from ayon_core.pipeline.template_data import get_template_data
from ayon_core.pipeline.version_start import get_versioning_start
from ayon_core.pipeline.workfile import (
    get_workdir,
    get_workfile_template_key,
    save_next_version,
)
from ayon_core.settings import get_project_settings

from . import commands

log = logging.getLogger(__name__)

STARTUP_DEFAULTS = {
    "create_first_workfile": True,
    "reset_frame_range": True,
    "reset_resolution": True,
    "reset_colorspace": True,
    "reset_render_settings": True,
}


def list_workfiles(project_name, folder_entity, task_entity):
    """Workfiles of the task (files on disk + workfile entities)."""
    host = registered_host()
    return host.list_workfiles(project_name, folder_entity, task_entity)


def next_version(workfiles, project_name, task_entity):
    versions = [w.version for w in workfiles if w.version is not None]
    if versions:
        return max(versions) + 1
    return get_versioning_start(
        project_name, registered_host().name,
        task_name=task_entity["name"], task_type=task_entity["taskType"],
        product_base_type="workfile")


def build_workfile_path(
    project_name, folder_entity, task_entity, version, comment=None,
):
    """Workfile path of `version` in the task, from the anatomy."""
    host = registered_host()
    project_entity = ayon_api.get_project(project_name)
    project_settings = get_project_settings(project_name)
    anatomy = Anatomy(project_name, project_entity=project_entity)
    template_key = get_workfile_template_key(
        project_name, task_entity["taskType"], host.name,
        project_settings=project_settings)
    template = anatomy.get_template_item("work", template_key, "file")
    data = get_template_data(
        project_entity, folder_entity, task_entity, host.name,
        project_settings)
    data["version"] = version
    data["ext"] = host.get_workfile_extensions()[0].lstrip(".")
    if comment:
        data["comment"] = comment
    workdir = get_workdir(
        project_entity, folder_entity, task_entity, host.name,
        anatomy=anatomy, template_key=template_key,
        project_settings=project_settings)
    return os.path.join(workdir, template.format_strict(data))


def save_as(folder_entity, task_entity, version, comment=None):
    """Save the active document as workfile `version` of the task."""
    host = registered_host()
    project_name = host.get_current_context()["project_name"]
    path = build_workfile_path(
        project_name, folder_entity, task_entity, version, comment)
    if os.path.exists(path):
        raise FileExistsError(f"Workfile exists already: {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    host.save_workfile_with_context(
        path, folder_entity, task_entity, version=version, comment=comment)
    return path


def save_next():
    """Save the active document as the next workfile version."""
    save_next_version()
    return registered_host().get_current_workfile()


def open_workfile(path, folder_entity, task_entity):
    registered_host().open_workfile_with_context(
        path, folder_entity, task_entity)


# -- first workfile ----------------------------------------------------------
def get_startup_settings(project_name):
    settings = get_project_settings(project_name).get("cinema4d", {})
    return {**STARTUP_DEFAULTS, **settings.get("workfile_startup", {})}


def apply_task_settings(settings=None):
    """Frame range, resolution, colorspace and render settings of the task."""
    if settings is None:
        project_name = registered_host().get_current_context()["project_name"]
        settings = get_startup_settings(project_name)
    steps = [
        ("reset_frame_range", commands.reset_frame_range),
        ("reset_resolution", commands.reset_resolution),
        ("reset_colorspace", commands.reset_colorspace),
        ("reset_render_settings", commands.reset_render_settings),
    ]
    for key, func in steps:
        if not settings.get(key):
            continue
        try:
            func()
        except Exception:
            log.warning(f"First workfile: {key} failed", exc_info=True)


def is_empty_document(doc):
    """Untitled and unchanged (the default scene may contain objects)."""
    return not doc.GetDocumentPath() and not doc.GetChanged()


def start_task(folder_entity, task_entity, new_document=True):
    """Start a task: new scene with the task settings saved as v001.

    Args:
        new_document (bool): Start from a new document, else the active
            document is used.
    """
    host = registered_host()
    project_name = host.get_current_context()["project_name"]
    if new_document:
        # File > New, uses the user's default scene (new.c4d)
        c4d.CallCommand(12094)

    context = host.get_current_context()
    if (
        context["folder_path"] != folder_entity["path"]
        or context["task_name"] != task_entity["name"]
    ):
        host.set_current_context(folder_entity, task_entity)

    apply_task_settings(get_startup_settings(project_name))
    workfiles = list_workfiles(project_name, folder_entity, task_entity)
    version = next_version(workfiles, project_name, task_entity)
    path = save_as(folder_entity, task_entity, version)
    c4d.EventAdd()
    log.info(f"Started task {task_entity['name']} in {path}")
    return path


def on_startup():
    """Save a blank startup scene as first workfile of an empty task."""
    host = registered_host()
    context = host.get_current_context()
    project_name = context.get("project_name")
    if not (project_name and context.get("folder_path")
            and context.get("task_name")):
        return
    doc = c4d.documents.GetActiveDocument()
    if not is_empty_document(doc):
        return
    if not get_startup_settings(project_name)["create_first_workfile"]:
        return

    folder = ayon_api.get_folder_by_path(project_name, context["folder_path"])
    task = folder and ayon_api.get_task_by_name(
        project_name, folder["id"], context["task_name"])
    if not task:
        return
    if list_workfiles(project_name, folder, task):
        return
    start_task(folder, task, new_document=False)
