"""Launches handed over from AYON to this running Cinema 4D.

The launch hook `hooks/pre_handoff_to_running_instance.py` writes requests
when a heartbeat of this session is fresh. `tick()` (DocumentWatcher timer)
writes the heartbeat and handles the requests: switch to the task and open
its workfile, or start the task in a new document.
"""
import os
import sys
import json
import time
import logging
import tempfile

import c4d
import ayon_api

from ayon_core.pipeline import registered_host

from . import workfiles

log = logging.getLogger(__name__)

# Keep in sync with the launch hook
HANDOFF_DIR = os.path.join(tempfile.gettempdir(), "ayon_cinema4d_handoff")
HEARTBEAT_INTERVAL = 5  # seconds, the hook accepts 15
REQUEST_TIMEOUT = 120  # older requests are dropped

_last_heartbeat = 0.0


def _heartbeat_path():
    return os.path.join(HANDOFF_DIR, "instances", f"{os.getpid()}.json")


def _write_heartbeat():
    path = _heartbeat_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "pid": os.getpid(),
        "time": time.time(),
        "executable": c4d.storage.GeGetStartupApplication(),
    }
    with open(path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(data, stream)
    os.replace(path + ".tmp", path)


def remove_heartbeat():
    try:
        os.remove(_heartbeat_path())
    except OSError:
        pass


def _take_requests():
    folder = os.path.join(HANDOFF_DIR, "requests")
    if not os.path.isdir(folder):
        return []
    requests = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as stream:
                request = json.load(stream)
        except (OSError, ValueError):
            continue
        expired = time.time() - request.get("time", 0) > REQUEST_TIMEOUT
        if not expired and request.get("pid") not in (None, os.getpid()):
            continue  # for another Cinema 4D session
        try:
            os.remove(path)
        except OSError:
            continue  # taken by another session
        if not expired:
            requests.append(request)
    return requests


def tick():
    """Heartbeat + pending requests, called about once per second."""
    global _last_heartbeat
    now = time.time()
    if now - _last_heartbeat > HEARTBEAT_INTERVAL:
        _last_heartbeat = now
        try:
            _write_heartbeat()
        except OSError:
            log.debug("AYON heartbeat failed", exc_info=True)
    for request in _take_requests():
        try:
            handle(request)
        except Exception as error:
            log.warning("AYON launch handoff failed", exc_info=True)
            c4d.gui.MessageDialog(f"AYON could not open the task:\n{error}")


def _find_open_document(path):
    target = os.path.normcase(os.path.normpath(path))
    doc = c4d.documents.GetFirstDocument()
    while doc is not None:
        folder, name = doc.GetDocumentPath(), doc.GetDocumentName()
        if folder and name and os.path.normcase(
            os.path.normpath(os.path.join(folder, name))
        ) == target:
            return doc
        doc = doc.GetNext()
    return None


def handle(request):
    host = registered_host()
    project_name = host.get_current_context()["project_name"]
    if request.get("project_name") != project_name:
        c4d.gui.MessageDialog(
            f"AYON: Cinema 4D runs in project '{project_name}', it can't "
            f"switch to '{request.get('project_name')}'.\n"
            "Close Cinema 4D and launch again.")
        return

    folder = ayon_api.get_folder_by_path(project_name, request["folder_path"])
    task = folder and ayon_api.get_task_by_name(
        project_name, folder["id"], request["task_name"])
    if not task:
        raise RuntimeError(
            f"{request['folder_path']} / {request['task_name']} not found")

    path = request.get("workfile")
    if not path:
        existing = [
            w for w in workfiles.list_workfiles(project_name, folder, task)
            if w.available and w.version is not None
        ]
        if existing:
            path = max(existing, key=lambda w: w.version).filepath

    if path:
        doc = _find_open_document(path)
        if doc is not None:
            c4d.documents.SetActiveDocument(doc)
        else:
            workfiles.open_workfile(path, folder, task)
        log.info(f"AYON launch: opened {path}")
    else:
        workfiles.start_task(folder, task, new_document=True)
    c4d.EventAdd()
    _bring_to_front()


def _bring_to_front():
    """Raise the Cinema 4D main window (Windows, best effort)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pid = os.getpid()
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd) \
                    and not user32.GetWindow(hwnd, 4):  # GW_OWNER
                found.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        for hwnd in found[:1]:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE, keeps maximized
            user32.SetForegroundWindow(hwnd)
    except Exception:
        log.debug("Bringing Cinema 4D to front failed", exc_info=True)
