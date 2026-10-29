"""Change notifications for the native windows.

Kinds:
    server: entities changed on the AYON server (polled, see `_Watcher`)
    context: the AYON context (folder/task) changed
    publish: a publish finished or instances changed

`notify` bumps a revision per kind and posts a core message; every open
`AyonDialog` compares the revisions with the ones it has seen.
The server is only polled while a dialog that needs it is open.
"""
import os
import logging
import threading
from datetime import datetime, timedelta, timezone

import c4d
import ayon_api

from . import ids

log = logging.getLogger(__name__)

SERVER = "server"
CONTEXT = "context"
PUBLISH = "publish"

# Entity changes the windows care about
SERVER_TOPICS = (
    "entity.folder.created",
    "entity.folder.deleted",
    "entity.folder.renamed",
    "entity.task.created",
    "entity.task.deleted",
    "entity.product.created",
    "entity.product.deleted",
    "entity.version.created",
    "entity.version.deleted",
    "entity.version.status_changed",
    "entity.version.tags_changed",
    "entity.representation.created",
    "entity.workfile.created",
)
POLL_INTERVAL = float(os.getenv("AYON_C4D_EVENT_POLL_SECONDS", "5"))
OVERLAP = timedelta(seconds=30)  # tolerate clock offsets to the server

_lock = threading.Lock()
_revisions = {SERVER: 0, CONTEXT: 0, PUBLISH: 0}
_recent = []  # latest server events, newest last
_subscribers = set()
_watcher = None


def notify(kind):
    """Mark `kind` as changed and wake the open windows (any thread)."""
    with _lock:
        _revisions[kind] = _revisions.get(kind, 0) + 1
    c4d.SpecialEventAdd(ids.EVENTS_MESSAGE)


def snapshot():
    with _lock:
        return dict(_revisions)


def changed_kinds(seen):
    with _lock:
        return {k for k, v in _revisions.items() if seen.get(k) != v}


def recent_events():
    """Latest server events (dicts with 'topic', 'summary', 'project')."""
    with _lock:
        return list(_recent)


def subscribe(dialog):
    """Poll the server while at least one subscriber is open."""
    global _watcher
    _subscribers.add(dialog)
    if _watcher is None or not _watcher.is_alive():
        _watcher = _Watcher()
        _watcher.start()


def unsubscribe(dialog):
    global _watcher
    _subscribers.discard(dialog)
    if not _subscribers and _watcher is not None:
        _watcher.stop()
        _watcher = None


def _current_project():
    return os.getenv("AYON_PROJECT_NAME")


class _Watcher(threading.Thread):
    def __init__(self):
        super().__init__(name="AYON C4D event watcher", daemon=True)
        self._stop_event = threading.Event()
        self._since = datetime.now(timezone.utc)
        self._seen_ids = []

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.wait(POLL_INTERVAL):
            try:
                if self._poll():
                    notify(SERVER)
            except Exception:
                log.debug("Polling AYON events failed", exc_info=True)

    def _poll(self):
        project_name = _current_project()
        if not project_name:
            return False

        newer_than = (self._since - OVERLAP).isoformat()
        events = list(ayon_api.get_events(
            topics=SERVER_TOPICS,
            project_names=[project_name],
            newer_than=newer_than,
            fields={"id", "topic", "createdAt", "summary", "project"},
        ))
        new_events = [e for e in events if e["id"] not in self._seen_ids]
        if not new_events:
            return False

        for event in new_events:
            self._seen_ids.append(event["id"])
            created = _parse_time(event.get("createdAt"))
            if created and created > self._since:
                self._since = created
        del self._seen_ids[:-500]

        with _lock:
            _recent.extend(new_events)
            del _recent[:-100]
        return True


def _parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
