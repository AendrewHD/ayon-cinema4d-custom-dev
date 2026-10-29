"""Plug-in ids of the AYON commands and native windows.

All ids live here so new windows don't collide. A dialog uses the id of
the command that opens it, Cinema 4D stores docked dialogs in layouts by it.
"""

# Registered at Maxon (ynput)
WORKFILES = 1064310
LOAD = 1064311  # legacy "Load...", kept registered for layouts/shortcuts
CREATE = 1064312
PUBLISH = 1064313
LIBRARY = 1064314
MANAGE = 1064315
RESET_RENDER_SETTINGS = 1064316
RESET_FRAME_RANGE = 1064317
RESET_RESOLUTION = 1064318
EXPERIMENTAL_TOOLS = 1064319
RESET_COLORSPACE = 1064320
CONTEXT_LABEL = 1064692

# TODO: replace with ids registered at https://developers.maxon.net/forum/pid
# 1000001-1000010 are Maxon's ids for plug-ins in development.
DOCUMENT_WATCHER = 1000001  # also the core message id of `events`
PUBLISH_STATUS = 1000002
SAVE_NEXT_VERSION = 1000003
SAVE_AS = 1000004
CLASSIC_LIBRARY = 1000005
CLASSIC_MANAGE = 1000006
CLASSIC_WORKFILES = 1000007
CLASSIC_PUBLISHER = 1000008
QT_DOCK = 1000009
CONTAINER_TAG = 1000010  # AYON tag on loaded products, see `container_tag`

# Core message posted by `events.notify` (SpecialEventAdd)
EVENTS_MESSAGE = DOCUMENT_WATCHER
