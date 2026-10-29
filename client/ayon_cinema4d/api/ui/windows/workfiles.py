"""Workfiles: native window plus the key-bindable save commands.

Folder tree and tasks on the left, the task's workfiles (or published
workfiles) on the right. "Save Next Version" and "Save As..." are
separate commands, so they can get shortcuts in Customize Commands.
"""
import os
import logging

import c4d
import ayon_api

from ayon_core.host.interfaces import CopyWorkfileOptionalData
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.workfile import copy_workfile_to_context
from ayon_core.lib import get_ayon_username

from ayon_cinema4d.api import workfiles
from ayon_cinema4d.api.ui import entities, events, ids, widgets
from ayon_cinema4d.api.ui.dialog import AyonDialog
from ayon_cinema4d.api.ui.registry import Command
from ayon_cinema4d.api.ui.tree import Column, Item, TreeModel

from .classic import show_workfiles

log = logging.getLogger(__name__)

ID_FOLDER_FILTER = 1000
ID_SPLIT = 1001
ID_FOLDERS = 1002
ID_TASKS = 1003
ID_FILES = 1004
ID_PUBLISHED = 1005
ID_OPEN = 1006
ID_SAVE_AS = 1007
ID_SAVE_NEXT = 1008
ID_START = 1009
ID_EXPLORER = 1010
ID_REFRESH = 1011
ID_QT = 1012
ID_CURRENT = 1013

# Save As dialog
ID_SA_CONTEXT = 2000
ID_SA_VERSION = 2001
ID_SA_COMMENT = 2002
ID_SA_PREVIEW = 2003
ID_SA_OK = 2004
ID_SA_CANCEL = 2005


def _current_entities():
    """(folder, task) entities of the current context."""
    context = registered_host().get_current_context()
    project_name = context["project_name"]
    folder = ayon_api.get_folder_by_path(project_name, context["folder_path"])
    task = folder and ayon_api.get_task_by_name(
        project_name, folder["id"], context["task_name"])
    return folder, task


class SaveAsDialog(c4d.gui.GeDialog):
    """Modal: version and comment of the new workfile, path preview."""

    def __init__(self, folder_entity, task_entity, version):
        super().__init__()
        self.folder = folder_entity
        self.task = task_entity
        self.version = version
        self.comment = ""
        self.result = None
        self._project_name = (
            registered_host().get_current_context()["project_name"])

    def CreateLayout(self):
        self.SetTitle("AYON Save As")
        self.GroupBorderSpace(10, 10, 10, 10)
        self.AddStaticText(
            ID_SA_CONTEXT, c4d.BFH_SCALEFIT, name="",
            borderstyle=c4d.BORDER_WITH_TITLE_BOLD)
        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2):
            self.AddStaticText(0, c4d.BFH_LEFT, name="Version")
            self.AddEditNumberArrows(ID_SA_VERSION, c4d.BFH_LEFT, 80, 0)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Comment")
            self.AddEditText(ID_SA_COMMENT, c4d.BFH_SCALEFIT, 260, 0)
        self.GroupEnd()
        self.AddStaticText(ID_SA_PREVIEW, c4d.BFH_SCALEFIT, 420, 0, name="")
        if self.GroupBegin(0, c4d.BFH_RIGHT, cols=2):
            self.AddButton(ID_SA_OK, c4d.BFH_RIGHT, 90, 0, name="Save")
            self.AddButton(ID_SA_CANCEL, c4d.BFH_RIGHT, 90, 0, name="Cancel")
        self.GroupEnd()
        return True

    def InitValues(self):
        self.SetString(
            ID_SA_CONTEXT, f"{self.folder['path']}  /  {self.task['name']}")
        self.SetInt32(ID_SA_VERSION, self.version, min=1, max=9999)
        self._update_preview()
        return True

    def _update_preview(self):
        try:
            path = workfiles.build_workfile_path(
                self._project_name, self.folder, self.task,
                self.GetInt32(ID_SA_VERSION),
                self.GetString(ID_SA_COMMENT).strip() or None)
            text = os.path.basename(path)
            if os.path.exists(path):
                text += "   (exists)"
        except Exception as error:
            text = f"Error: {error}"
        self.SetString(ID_SA_PREVIEW, text)

    def Command(self, gadget_id, msg):
        if gadget_id in (ID_SA_VERSION, ID_SA_COMMENT):
            self._update_preview()
        elif gadget_id == ID_SA_OK:
            self.result = (
                self.GetInt32(ID_SA_VERSION),
                self.GetString(ID_SA_COMMENT).strip() or None)
            self.Close()
        elif gadget_id == ID_SA_CANCEL:
            self.Close()
        return True


def save_as(folder_entity=None, task_entity=None):
    """Ask for version / comment and save the active document."""
    if folder_entity is None or task_entity is None:
        folder_entity, task_entity = _current_entities()
    if not task_entity:
        c4d.gui.MessageDialog("No AYON task in the current context.")
        return False
    project_name = registered_host().get_current_context()["project_name"]
    existing = workfiles.list_workfiles(
        project_name, folder_entity, task_entity)
    dialog = SaveAsDialog(
        folder_entity, task_entity,
        workfiles.next_version(existing, project_name, task_entity))
    dialog.Open(c4d.DLG_TYPE_MODAL_RESIZEABLE, defaultw=460, defaulth=0)
    if not dialog.result:
        return False
    version, comment = dialog.result
    try:
        path = workfiles.save_as(folder_entity, task_entity, version, comment)
    except Exception as error:
        log.warning("Save As failed", exc_info=True)
        c4d.gui.MessageDialog(f"Save As failed:\n{error}")
        return False
    c4d.StatusSetText(f"AYON: saved {os.path.basename(path)}")
    WorkfilesDialog.refresh_if_open()
    return True


def save_next_version():
    try:
        path = workfiles.save_next()
    except Exception as error:
        log.warning("Save Next Version failed", exc_info=True)
        c4d.gui.MessageDialog(f"Save Next Version failed:\n{error}")
        return False
    c4d.StatusSetText(f"AYON: saved {os.path.basename(path or '')}")
    WorkfilesDialog.refresh_if_open()
    return True


class WorkfilesDialog(AyonDialog):
    TITLE = "AYON Workfiles"
    DIALOG_ID = ids.WORKFILES
    DEFAULT_SIZE = (820, 460)
    EVENT_KINDS = (events.CONTEXT, events.SERVER)

    def __init__(self):
        super().__init__()
        self._folders = []
        self._user = None
        self._pending = None  # (folder id, task id) to select
        self._seen_event_ids = set()
        self.folders = TreeModel([Column("name", "Folder")])
        self.folders.on_select = lambda items: self._load_tasks()
        self.tasks = TreeModel(
            [Column("name", "Task"), Column("type", "Type")],
            empty_text="Select a folder", flat=True)
        self.tasks.on_select = lambda items: self._load_files()
        self.files = TreeModel(
            [
                Column("name", "Workfile"),
                Column("version", "Version", width=60),
                Column("comment", "Comment"),
                Column("modified", "Modified", width=120),
                Column("author", "Author"),
            ],
            empty_text="No workfiles yet, use Start Task.",
            flat=True,
        )
        self.files.on_double_click = lambda item: self.open_file(item)
        self.files.on_select = lambda items: self._update_buttons()
        self.files.context_menu = self._file_menu

    # -- layout ----------------------------------------------------------
    def build(self):
        if self.GroupBegin(
            ID_SPLIT, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=2,
            groupflags=c4d.BFV_GRIDGROUP_ALLOW_WEIGHTS,
        ):
            if self.GroupBegin(
                0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1
            ):
                if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2):
                    self.AddEditText(ID_FOLDER_FILTER, c4d.BFH_SCALEFIT, 120)
                    self.AddButton(ID_CURRENT, c4d.BFH_RIGHT, name="Current")
                self.GroupEnd()
                self.add_tree(ID_FOLDERS, self.folders, min_size=(200, 160),
                              header=False)
                self.add_tree(ID_TASKS, self.tasks, min_size=(200, 100))
            self.GroupEnd()
            if self.GroupBegin(
                0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1
            ):
                self.AddCheckbox(ID_PUBLISHED, c4d.BFH_LEFT, 0, 0,
                                 name="Published")
                self.add_tree(ID_FILES, self.files, min_size=(360, 200))
            self.GroupEnd()
        self.GroupEnd()
        weights = c4d.BaseContainer()
        weights.SetInt32(c4d.GROUPWEIGHTS_PERCENT_W_CNT, 2)
        weights.SetFloat(c4d.GROUPWEIGHTS_PERCENT_W_VAL + 0, 32.0)
        weights.SetFloat(c4d.GROUPWEIGHTS_PERCENT_W_VAL + 1, 68.0)
        self.GroupWeightsLoad(ID_SPLIT, weights)

        if self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=7):
            self.AddButton(ID_OPEN, c4d.BFH_LEFT, name="Open")
            self.AddButton(ID_START, c4d.BFH_LEFT, name="Start Task")
            self.AddButton(ID_EXPLORER, c4d.BFH_LEFT, name="Explorer")
            self.AddButton(ID_REFRESH, c4d.BFH_LEFT | c4d.BFH_SCALE,
                           name="Refresh")
            self.AddButton(ID_QT, c4d.BFH_RIGHT, name="Qt...")
            self.AddButton(ID_SAVE_AS, c4d.BFH_RIGHT, name="Save As...")
            self.AddButton(ID_SAVE_NEXT, c4d.BFH_RIGHT,
                           name="Save Next Version")
        self.GroupEnd()

    def InitValues(self):
        self.SetString(
            ID_FOLDER_FILTER, "Filter folders", flags=c4d.EDITTEXT_HELPTEXT)
        return super().InitValues()

    # -- data ------------------------------------------------------------
    @property
    def project_name(self):
        return registered_host().get_current_context()["project_name"]

    def refresh(self):
        if self._user is None:
            try:
                self._user = get_ayon_username()
            except Exception:
                self._user = ""
        if not self.folders.selected_items():
            self.select_current()
            return
        self._folders = entities.get_folders(self.project_name)
        self._fill_folders()
        self._load_tasks()

    def select_current(self):
        context = registered_host().get_current_context()
        folder = ayon_api.get_folder_by_path(
            self.project_name, context["folder_path"], fields={"id"})
        task = folder and ayon_api.get_task_by_name(
            self.project_name, folder["id"], context["task_name"],
            fields={"id"})
        self._pending = (
            folder["id"] if folder else None, task["id"] if task else None)
        self._folders = entities.get_folders(self.project_name)
        self._fill_folders()
        self._load_tasks()

    def _fill_folders(self):
        roots, matches = entities.folder_items(
            self._folders, self.GetString(ID_FOLDER_FILTER))
        self.folders.set_items(roots)
        if matches:
            self.folders.open_keys(matches)
            self.folders.refresh()
        if self._pending and self._pending[0]:
            self.folders.select_keys([self._pending[0]])
            self.folders.show(self._pending[0])

    def _selected_folder(self):
        items = self.folders.selected_items()
        return items[0].data if len(items) == 1 else None

    def _selected_task(self):
        items = self.tasks.selected_items()
        return items[0].data if len(items) == 1 else None

    def _load_tasks(self):
        folder = self._selected_folder()
        if folder is None:
            self.tasks.set_items([])
        else:
            self.tasks.set_items(entities.task_items(
                self.project_name, folder["id"], self._user))
        pending, self._pending = self._pending, None
        if pending and pending[1]:
            self.tasks.select_keys([pending[1]])
        self._load_files()

    def _load_files(self):
        folder, task = self._selected_folder(), self._selected_task()
        if folder is None or task is None:
            self.files.empty_text = "Select a task."
            self.files.set_items([])
            self._update_buttons()
            return

        folder = ayon_api.get_folder_by_id(self.project_name, folder["id"])
        task = ayon_api.get_task_by_id(self.project_name, task["id"])
        current = os.path.normcase(
            registered_host().get_current_workfile() or "")
        items = []
        if self.GetBool(ID_PUBLISHED):
            self.files.empty_text = "No published workfiles."
            host = registered_host()
            for info in host.list_published_workfiles(
                self.project_name, folder["id"]
            ):
                if info.task_id and info.task_id != task["id"]:
                    continue
                items.append(Item(
                    info.representation_id,
                    {
                        "name": os.path.basename(info.filepath),
                        "modified": widgets.format_time(info.created_at),
                        "author": info.author or "",
                    },
                    data=("published", info, folder, task),
                    dim=not info.available,
                    tooltip=info.filepath,
                ))
        else:
            self.files.empty_text = "No workfiles yet, use Start Task."
            for info in workfiles.list_workfiles(
                self.project_name, folder, task
            ):
                is_current = os.path.normcase(info.filepath) == current
                items.append(Item(
                    info.filepath,
                    {
                        "name": os.path.basename(info.filepath),
                        "version": info.version or 0,
                        "comment": info.comment or "",
                        "modified": widgets.format_time(info.file_modified),
                        "author": "",
                    },
                    data=("workfile", info, folder, task),
                    bold=is_current,
                    dim=not info.available,
                    swatch=widgets.GREEN if is_current else None,
                    tooltip=info.filepath,
                ))
            items.sort(key=lambda i: i.values["version"], reverse=True)
            for item in items:
                item.values["version"] = f"v{item.values['version']:03d}"
        self.files.set_items(items)
        self._update_buttons()

    def _update_buttons(self):
        task = self._selected_task()
        selected = self.files.selected_items()
        self.Enable(ID_OPEN, len(selected) == 1)
        self.Enable(ID_SAVE_AS, task is not None)
        self.Enable(ID_START, task is not None)
        self.Enable(ID_EXPLORER, task is not None)
        published = self.GetBool(ID_PUBLISHED)
        self.SetString(ID_OPEN, "Copy & Open" if published else "Open")

    # -- actions ---------------------------------------------------------
    def open_file(self, item=None):
        if item is None:
            selected = self.files.selected_items()
            if len(selected) != 1:
                return
            item = selected[0]
        kind, info, folder, task = item.data
        if kind == "published":
            if not info.available:
                c4d.gui.MessageDialog("The file is not available locally.")
                return
            # core reads prepared_data without None check (1.10.4)
            existing = workfiles.list_workfiles(
                self.project_name, folder, task)
            copy_workfile_to_context(
                info.filepath, folder, task,
                version=workfiles.next_version(
                    existing, self.project_name, task),
                prepared_data=CopyWorkfileOptionalData())
        else:
            workfiles.open_workfile(info.filepath, folder, task)
        self.set_status(f"Opened {os.path.basename(info.filepath)}")
        self.refresh()

    def _task_entities(self):
        folder, task = self._selected_folder(), self._selected_task()
        if folder is None or task is None:
            return None, None
        return (
            ayon_api.get_folder_by_id(self.project_name, folder["id"]),
            ayon_api.get_task_by_id(self.project_name, task["id"]),
        )

    def start_task(self):
        folder, task = self._task_entities()
        if task is None:
            return
        existing = workfiles.list_workfiles(self.project_name, folder, task)
        if existing and not widgets.confirm(
            f"{task['name']} has {len(existing)} workfile(s) already.\n"
            "Start a new scene with the task settings anyway?"
        ):
            return
        path = workfiles.start_task(folder, task, new_document=True)
        self.set_status(f"Started {os.path.basename(path)}")
        self.refresh()

    def show_in_explorer(self):
        selected = self.files.selected_items()
        if selected:
            widgets.open_in_explorer(selected[0].data[1].filepath)
            return
        folder, task = self._task_entities()
        if task is None:
            return
        path = workfiles.build_workfile_path(
            self.project_name, folder, task, 1)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        widgets.open_in_explorer(os.path.dirname(path))

    def _file_menu(self, items):
        if len(items) != 1:
            return []
        item = items[0]
        path = item.data[1].filepath
        return [
            ("Open", lambda: self.open_file(item)),
            ("Show in Explorer", lambda: widgets.open_in_explorer(path)),
            ("Copy Path", lambda: c4d.CopyStringToClipboard(path)),
        ]

    def on_command(self, gadget_id, msg):
        if gadget_id == ID_FOLDER_FILTER:
            self._fill_folders()
        elif gadget_id == ID_CURRENT:
            self.select_current()
        elif gadget_id == ID_PUBLISHED:
            self._load_files()
        elif gadget_id == ID_OPEN:
            self.open_file()
        elif gadget_id == ID_START:
            self.start_task()
        elif gadget_id == ID_SAVE_AS:
            folder, task = self._task_entities()
            if save_as(folder, task):
                self.refresh()
        elif gadget_id == ID_SAVE_NEXT:
            save_next_version()
        elif gadget_id == ID_EXPLORER:
            self.show_in_explorer()
        elif gadget_id == ID_REFRESH:
            self.refresh()
        elif gadget_id == ID_QT:
            show_workfiles()

    def on_events(self, kinds):
        if events.CONTEXT in kinds:
            # Keep the browsed task, update the current workfile mark
            self._load_files()
        elif events.SERVER in kinds:
            new = [
                e for e in events.recent_events()
                if e["id"] not in self._seen_event_ids
            ]
            self._seen_event_ids.update(e["id"] for e in new)
            topics = {e["topic"] for e in new}
            if any(t.startswith(("entity.folder.", "entity.task."))
                   for t in topics):
                self.refresh()
            else:
                self._load_files()


COMMANDS = [
    Command(
        ids.WORKFILES, "Workfiles...", icon=widgets.ayon_icon("workfiles"),
        section="workfiles", order=10, dialog=WorkfilesDialog,
    ),
    Command(
        ids.SAVE_NEXT_VERSION, "Save Next Version", save_next_version,
        icon=c4d.bitmaps.InitResourceBitmap(12098), section="workfiles",
        order=20, help="Save the scene as next AYON workfile version",
    ),
    Command(
        ids.SAVE_AS, "Save As...", save_as,
        icon=c4d.bitmaps.InitResourceBitmap(12218), section="workfiles",
        order=30, help="Save the scene as AYON workfile with a comment",
    ),
]
