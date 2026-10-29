"""Base class of the native (dockable) AYON windows.

A window is a `GeDialog` opened with the id of its command, so Cinema 4D
can dock it, tab it and restore it with the layout. Subclasses implement:

    build()              add the gadgets (called in CreateLayout)
    refresh()            reload the content
    on_events(kinds)     react to `events` kinds (default: refresh)
    on_document_change() active document or its content changed
    on_command(id, msg)  gadget commands

Errors in these hooks are logged and shown in the status line instead of
breaking the dialog.
"""
import logging
import traceback

import c4d

from . import events, tree

log = logging.getLogger(__name__)

ID_STATUS = 9000
ID_CONTEXT = 9001


class AyonDialog(c4d.gui.GeDialog):
    TITLE = "AYON"
    DIALOG_ID = 0
    DEFAULT_SIZE = (480, 420)
    # `events` kinds that trigger `on_events`, SERVER starts polling
    EVENT_KINDS = (events.CONTEXT,)
    SHOW_STATUS = True
    SHOW_CONTEXT = False

    _instances = {}

    # -- opening ---------------------------------------------------------
    @classmethod
    def instance(cls):
        dialog = AyonDialog._instances.get(cls)
        if dialog is None:
            dialog = AyonDialog._instances[cls] = cls()
        return dialog

    @classmethod
    def open(cls):
        dialog = cls.instance()
        if dialog.IsOpen():
            dialog.guard(dialog.refresh)
            return True
        width, height = cls.DEFAULT_SIZE
        return dialog.Open(
            c4d.DLG_TYPE_ASYNC, pluginid=cls.DIALOG_ID,
            defaultw=width, defaulth=height)

    @classmethod
    def restore(cls, sec_ref):
        return cls.instance().Restore(pluginid=cls.DIALOG_ID, secret=sec_ref)

    @classmethod
    def refresh_if_open(cls):
        dialog = AyonDialog._instances.get(cls)
        if dialog is not None and dialog.IsOpen():
            dialog.guard(dialog.refresh)

    # -- hooks -----------------------------------------------------------
    def build(self):
        pass

    def refresh(self):
        pass

    def on_events(self, kinds):
        self.refresh()

    def on_document_change(self):
        pass

    def on_command(self, gadget_id, msg):
        pass

    # -- helpers ---------------------------------------------------------
    def guard(self, func, *args, **kwargs):
        """Run `func`, show errors in the status line."""
        try:
            return func(*args, **kwargs)
        except Exception as error:
            log.warning(
                f"{self.TITLE}: {func.__name__} failed\n"
                f"{traceback.format_exc()}"
            )
            self.set_status(f"Error: {error}", error=True)
            return None

    def set_status(self, text, error=False):
        if not self.SHOW_STATUS or not self.IsOpen():
            return
        self.SetString(ID_STATUS, text or "")

    def set_context_text(self, text):
        if self.SHOW_CONTEXT:
            self.SetString(ID_CONTEXT, text)

    def add_tree(self, gadget_id, model, min_size=(200, 120), header=True):
        """TreeView for `model`, attached in InitValues."""
        tree.add_tree(self, gadget_id, model, min_size, header)
        self._trees.append((gadget_id, model))

    def add_context_header(self):
        """Bold context line (folder / task) above the content."""
        self.AddStaticText(
            ID_CONTEXT, c4d.BFH_SCALEFIT, name="",
            borderstyle=c4d.BORDER_WITH_TITLE_BOLD)

    # -- GeDialog --------------------------------------------------------
    def __init__(self):
        super().__init__()
        self._seen = events.snapshot()
        self._subscribed = False
        self._trees = []

    def CreateLayout(self):
        self._trees = []
        self.SetTitle(self.TITLE)
        self.GroupBorderSpace(4, 4, 4, 4)
        if self.SHOW_CONTEXT:
            self.add_context_header()
        self.guard(self.build)
        if self.SHOW_STATUS:
            self.AddStaticText(ID_STATUS, c4d.BFH_SCALEFIT, name="")
        return True

    def InitValues(self):
        for gadget_id, model in self._trees:
            model.attach(self.FindCustomGui(gadget_id, c4d.CUSTOMGUI_TREEVIEW))
        self._seen = events.snapshot()
        if events.SERVER in self.EVENT_KINDS and not self._subscribed:
            events.subscribe(self)
            self._subscribed = True
        self.guard(self.refresh)
        return True

    def DestroyWindow(self):
        if self._subscribed:
            events.unsubscribe(self)
            self._subscribed = False

    def Command(self, gadget_id, msg):
        self.guard(self.on_command, gadget_id, msg)
        return True

    def CoreMessage(self, message_id, msg):
        if message_id == events.ids.EVENTS_MESSAGE:
            kinds = events.changed_kinds(self._seen) & set(self.EVENT_KINDS)
            self._seen = events.snapshot()
            if kinds and self.IsOpen():
                self.guard(self.on_events, kinds)
        elif message_id == c4d.EVMSG_CHANGE and self.IsOpen():
            self.guard(self.on_document_change)
        return c4d.gui.GeDialog.CoreMessage(self, message_id, msg)
