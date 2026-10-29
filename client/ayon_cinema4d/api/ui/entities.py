"""Folder / task items for the native windows (Library, Workfiles)."""
import ayon_api

from . import widgets
from .tree import Item

FOLDER_FIELDS = {"id", "name", "label", "path", "parentId", "folderType"}
TASK_FIELDS = {"id", "name", "label", "taskType", "folderId", "assignees"}


def get_folders(project_name):
    return list(ayon_api.get_folders(project_name, fields=FOLDER_FIELDS))


def folder_items(folders, text_filter=""):
    """Folder hierarchy as tree items, filtered by name/path substring.

    A folder matches when its path contains the filter, its parents are
    kept so the match stays reachable.
    """
    text_filter = text_filter.strip().lower()
    by_id = {folder["id"]: folder for folder in folders}
    keep = set(by_id)
    if text_filter:
        keep = set()
        for folder in folders:
            if text_filter in folder["path"].lower():
                folder_id = folder["id"]
                while folder_id and folder_id not in keep:
                    keep.add(folder_id)
                    folder_id = by_id.get(folder_id, {}).get("parentId")

    items = {}
    for folder_id in keep:
        folder = by_id[folder_id]
        items[folder_id] = Item(
            folder_id,
            {"name": folder.get("label") or folder["name"],
             "type": folder.get("folderType") or ""},
            data=folder,
            swatch=widgets.color_for(folder.get("folderType")),
            tooltip=folder["path"],
        )

    roots = []
    for folder_id, item in items.items():
        parent = items.get(item.data.get("parentId"))
        (parent.children if parent else roots).append(item)
    for item in items.values():
        item.children.sort(key=lambda i: i.text("name").lower())
    roots.sort(key=lambda i: i.text("name").lower())
    return roots, set(items) if text_filter else set()


def task_items(project_name, folder_id, user_name=None):
    tasks = ayon_api.get_tasks(
        project_name, folder_ids=[folder_id], fields=TASK_FIELDS)
    items = []
    for task in sorted(tasks, key=lambda t: t["name"].lower()):
        mine = bool(user_name and user_name in (task.get("assignees") or []))
        items.append(Item(
            task["id"],
            {"name": task.get("label") or task["name"],
             "type": task["taskType"]},
            data=task,
            swatch=widgets.color_for(task["taskType"]),
            bold=mine,
            tooltip="Assigned to you" if mine else None,
        ))
    return items
