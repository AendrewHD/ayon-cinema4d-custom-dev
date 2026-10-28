"""AYON context per Cinema 4D document.

AYON keeps one context per process. With several documents open, the
context follows the active document: each document stores the folder/task it
belongs to, and switching documents switches the AYON context.
"""
import os
import logging

import c4d
import ayon_api

from ayon_core.pipeline import Anatomy, registered_host

log = logging.getLogger(__name__)

# Registered AYON plug-in id (context label command), used as the key of the
# sub-container in the document settings that stores the context.
DOC_CONTEXT_ID = 1064692
_KEYS = ("project_name", "folder_path", "task_name")

_anatomy_cache = {}
_warned_projects = set()


def get_document_path(doc):
    folder, name = doc.GetDocumentPath(), doc.GetDocumentName()
    return os.path.join(folder, name) if folder and name else ""


def get_document_context(doc):
    """Return the context stored in the document or None."""
    bc = doc.GetDataInstance().GetContainerInstance(DOC_CONTEXT_ID)
    if bc is None:
        return None
    context = {key: bc.GetString(i) for i, key in enumerate(_KEYS, 1)}
    if not context["project_name"] or not context["folder_path"]:
        return None
    return context


def set_document_context(doc, project_name, folder_path, task_name):
    """Store the context in the document (saved with the file)."""
    bc = c4d.BaseContainer()
    for i, value in enumerate((project_name, folder_path, task_name), 1):
        bc.SetString(i, value or "")
    doc.GetDataInstance().SetContainer(DOC_CONTEXT_ID, bc)


def get_rootless_path(project_name, path):
    anatomy = _anatomy_cache.get(project_name)
    if anatomy is None:
        anatomy = _anatomy_cache[project_name] = Anatomy(project_name)
    success, rootless = anatomy.find_root_template_from_path(path)
    if not success:
        return None
    return rootless.replace("\\", "/")


def get_workfile_entity(project_name, path, fields=None):
    """Workfile entity of an absolute workfile path, or None."""
    rootless = get_rootless_path(project_name, path)
    if not rootless:
        return None
    # 'get_workfile_entities' replaces 'get_workfiles_info' in newer ayon_api
    getter = getattr(ayon_api, "get_workfile_entities", None)
    if getter is None:
        getter = ayon_api.get_workfiles_info
    return next(
        iter(getter(project_name, paths=[rootless], fields=fields)), None
    )


def _context_from_path(project_name, path):
    """Context of a document that was not opened or saved through AYON."""
    workfile = get_workfile_entity(project_name, path, fields={"taskId"})
    if workfile:
        task = ayon_api.get_task_by_id(
            project_name, workfile["taskId"], fields={"name", "folderId"})
        folder = task and ayon_api.get_folder_by_id(
            project_name, task["folderId"], fields={"path"})
        if folder:
            return {
                "project_name": project_name,
                "folder_path": folder["path"],
                "task_name": task["name"],
            }

    # Saved into the current work area, e.g. the workfile AYON launched with
    workdir = os.environ.get("AYON_WORKDIR")
    if workdir:
        folder = os.path.normcase(os.path.normpath(os.path.dirname(path)))
        if folder == os.path.normcase(os.path.normpath(workdir)):
            context = registered_host().get_current_context()
            if context.get("folder_path") and context.get("task_name"):
                return dict(context)
    return None


def resolve_document_context(doc):
    """Context of the document: stored value, else from its file path."""
    context = get_document_context(doc)
    if context:
        return context

    path = get_document_path(doc)
    project_name = os.environ.get("AYON_PROJECT_NAME")
    if not path or not project_name:
        return None

    context = _context_from_path(project_name, path)
    if context:
        set_document_context(doc, **{key: context[key] for key in _KEYS})
    return context


def sync_context_to_document(doc):
    """Switch the AYON context to the document's context.

    Returns:
        bool: True if the context changed.
    """
    context = resolve_document_context(doc)
    if not context or not context["task_name"]:
        return False

    host = registered_host()
    current = host.get_current_context()
    project_name = context["project_name"]
    if project_name != current["project_name"]:
        if project_name not in _warned_projects:
            _warned_projects.add(project_name)
            log.warning(
                f"'{doc.GetDocumentName()}' belongs to project "
                f"'{project_name}', AYON can't switch projects in a running "
                f"session. Staying in '{current['project_name']}'."
            )
        return False

    if (
        context["folder_path"] == current["folder_path"]
        and context["task_name"] == current["task_name"]
    ):
        return False

    folder = ayon_api.get_folder_by_path(project_name, context["folder_path"])
    task = folder and ayon_api.get_task_by_name(
        project_name, folder["id"], context["task_name"])
    if not task:
        log.warning(
            f"Context of '{doc.GetDocumentName()}' no longer exists: "
            f"{context['folder_path']} / {context['task_name']}"
        )
        return False

    path = get_document_path(doc)
    if path:
        os.environ["AYON_WORKDIR"] = os.path.dirname(path)
    host.set_current_context(folder, task)
    log.info(f"AYON context: {folder['path']}, {task['name']}")
    return True
