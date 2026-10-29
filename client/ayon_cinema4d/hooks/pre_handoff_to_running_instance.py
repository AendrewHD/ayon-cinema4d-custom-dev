"""Hand a launch over to an already running Cinema 4D.

Cinema 4D runs one instance per executable (Maxon removed '-parallel' in
R21); a second start only forwards its file argument, AYON's context is
lost. Running AYON sessions write a heartbeat (see `api/handoff.py`). If
one of the same executable is alive, this hook writes a request with the
launch context, which the running Cinema 4D picks up: it opens the
workfile or starts the task. The second process is still started (it only
brings Cinema 4D to front), without the workfile argument.

Set AYON_C4D_NO_HANDOFF=1 to disable.
"""
import os
import sys
import json
import time
import uuid
import tempfile

from ayon_applications import PreLaunchHook, LaunchTypes

# Keep in sync with api/handoff.py (the hook can't import c4d modules)
HANDOFF_DIR = os.path.join(tempfile.gettempdir(), "ayon_cinema4d_handoff")
HEARTBEAT_TIMEOUT = 15  # seconds


def _norm(path):
    return os.path.normcase(os.path.normpath(str(path)))


def find_running_instance(executable):
    """Heartbeat data of a live AYON session of `executable`, or None."""
    folder = os.path.join(HANDOFF_DIR, "instances")
    if not os.path.isdir(folder):
        return None
    now = time.time()
    found = None
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            continue
        if now - data.get("time", 0) > HEARTBEAT_TIMEOUT:
            continue
        if _norm(data.get("executable", "")) != _norm(executable):
            continue
        if found is None or data.get("time", 0) > found.get("time", 0):
            found = data  # the most recently active session
    return found


class HandOffToRunningInstance(PreLaunchHook):
    app_groups = {"cinema4d"}
    order = 100  # after the workfile hooks filled the data
    launch_types = {LaunchTypes.local}

    def execute(self):
        if os.getenv("AYON_C4D_NO_HANDOFF"):
            return
        executable = str(self.launch_context.executable)
        instance = find_running_instance(executable)
        if not instance:
            return

        workfile = self.data.get("workfile_path")
        if not workfile and self.data.get("start_last_workfile"):
            workfile = self.data.get("last_workfile_path")
        if workfile and not os.path.exists(workfile):
            workfile = None

        request = {
            "time": time.time(),
            "pid": instance.get("pid"),
            "project_name": self.data.get("project_name"),
            "folder_path": self.data.get("folder_path"),
            "task_name": self.data.get("task_name"),
            "workfile": workfile,
        }
        folder = os.path.join(HANDOFF_DIR, "requests")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{uuid.uuid4().hex}.json")
        with open(path + ".tmp", "w", encoding="utf-8") as stream:
            json.dump(request, stream)
        os.replace(path + ".tmp", path)  # never read half written
        self.log.info(
            f"Cinema 4D is running (pid {instance.get('pid')}), handed "
            f"{request['folder_path']} / {request['task_name']} over to it.")

        # The second process would forward the file as plain document
        if workfile:
            self.launch_context.launch_args = [
                arg for arg in self.launch_context.launch_args
                if _norm(arg) != _norm(workfile)
            ]
        # Let the running Cinema 4D come to the front
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass
