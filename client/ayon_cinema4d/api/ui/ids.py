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

# Registered at Maxon (Styleframe, AYON_C4D_SF_01-10)
DOCUMENT_WATCHER = 1072601  # also the core message id of `events`
PUBLISH_STATUS = 1072602
SAVE_NEXT_VERSION = 1072603
SAVE_AS = 1072604
CLASSIC_LIBRARY = 1072605
CLASSIC_MANAGE = 1072606
CLASSIC_WORKFILES = 1072607
CLASSIC_PUBLISHER = 1072608
QT_DOCK = 1072609
CONTAINER_TAG = 1072610  # AYON tag on loaded products, saved in scenes

# Core message posted by `events.notify` (SpecialEventAdd)
EVENTS_MESSAGE = DOCUMENT_WATCHER
