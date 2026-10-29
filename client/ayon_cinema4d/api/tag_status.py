"""Version state of the AYON tags in the active document.

The document watcher calls `tick` every second: when the tags or the
server changed, a thread asks the server for the version states and the
tags redraw with the matching icon color. Manage feeds its results in
with `store`. Tag buttons queue their update here (`queue_update`), it
runs outside the tag's own message call (`run_pending`).
"""
import logging
import threading

import c4d

from . import inventory, pipeline
from .ui import events, ids, widgets

log = logging.getLogger(__name__)

_lock = threading.Lock()
_states = {}  # representation id -> inventory state
_dirty = True
_redraw = False
_signature = None
_server_revision = None
_worker = None
_pending = []  # tags waiting for "Update to Latest"


class _Subscriber:
    """Keeps the server event polling running while tags exist."""
    project_name = None


_subscriber = _Subscriber()
_subscribed = False


def state(representation_id):
    with _lock:
        return _states.get(representation_id)


def store(rows):
    """Remember the states of `inventory.collect_inventory` rows."""
    global _redraw
    with _lock:
        for row in rows:
            repre_id = row["container"].get("representation")
            if repre_id:
                _states[repre_id] = row["state"]
        _redraw = True


def mark_dirty():
    """The document changed, check the tags at the next tick."""
    global _dirty
    _dirty = True


def tick():
    """Main thread, called by the document watcher timer."""
    global _dirty, _redraw, _signature, _server_revision, _worker
    if _redraw:
        _redraw = False
        c4d.EventAdd()  # tags redraw their icons

    server_revision = events.snapshot().get(events.SERVER)
    if not _dirty and server_revision == _server_revision:
        return
    if (_worker is not None and _worker.is_alive()) or widgets.is_playing():
        return
    _dirty = False

    doc = c4d.documents.GetActiveDocument()
    containers = [
        {"representation": c.get("representation"),
         "project_name": c.get("project_name")}
        for c in pipeline.iter_containers(doc)
        if isinstance(c["node"], c4d.BaseTag)
    ]
    _subscribe(bool(containers))
    signature = frozenset(
        (c["project_name"], c["representation"]) for c in containers)
    if signature == _signature and server_revision == _server_revision:
        return
    _signature, _server_revision = signature, server_revision
    if containers:
        _worker = threading.Thread(
            target=_check, args=(containers,),
            name="AYON tag status", daemon=True)
        _worker.start()


def _check(containers):
    try:
        store(inventory.collect_inventory(containers))
    except Exception:
        log.debug("Checking the AYON tag versions failed", exc_info=True)


def _subscribe(active):
    global _subscribed
    if active and not _subscribed:
        events.subscribe(_subscriber)
    elif not active and _subscribed:
        events.unsubscribe(_subscriber)
    _subscribed = active


def queue_update(tag):
    """Update `tag` to the latest version once its message call is done."""
    _pending.append(tag)
    c4d.SpecialEventAdd(ids.EVENTS_MESSAGE)


def run_pending():
    """Main thread: run the queued "Update to Latest" requests."""
    if not _pending:
        return
    from ayon_core.pipeline.load import update_container

    errors = []
    while _pending:
        tag = _pending.pop(0)
        if not tag.IsAlive() or tag.GetObject() is None:
            continue
        container = pipeline.parse_container(tag)
        try:
            update_container(container, -1)
        except Exception as error:
            log.warning("AYON update failed", exc_info=True)
            errors.append(f"{container.get('objectName')}: {error}")
    mark_dirty()
    c4d.EventAdd()
    if errors:
        c4d.gui.MessageDialog("AYON update failed:\n" + "\n".join(errors))
