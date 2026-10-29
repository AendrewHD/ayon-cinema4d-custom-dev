"""AYON container tag, marks the root object of a loaded product.

The container data (representation, loader, ...) is user data on the tag,
written by `pipeline.imprint_container`. The icon shows the version state
(`tag_status`), the buttons update the product or open Manage.
Scenes stay usable where the addon isn't installed (data is kept).
"""
import c4d

from . import lib
from .ui import ids

TAG_ID = ids.CONTAINER_TAG
DESCRIPTION = "Tayoncontainer"  # startup/res/description/tayoncontainer.res

# Button ids, see startup/res/description/tayoncontainer.h
AYON_UPDATE_LATEST = 1000
AYON_OPEN_MANAGE = 1001

COLORS = {
    None: (0, 220, 170),         # not checked yet: AYON
    "latest": (80, 200, 90),
    "outdated": (240, 150, 40),
    "hero": (70, 140, 240),
    "missing": (220, 60, 60),
}
_icons = {}


class ContainerTag(c4d.plugins.TagData):

    def Message(self, node, type, data):
        if type == c4d.MSG_GETCUSTOMICON:
            self._set_icon(node, data)
        elif type == c4d.MSG_DESCRIPTION_COMMAND:
            self._button(node, data["id"][0].id)
        return True

    @staticmethod
    def _set_icon(node, data):
        from . import tag_status

        repre_id = lib.get_object_user_data_by_name(node, "representation")
        icon = _icons.get(tag_status.state(repre_id)) or _icons.get(None)
        if icon is None:
            return
        data["bmp"] = icon
        data["w"] = icon.GetBw()
        data["h"] = icon.GetBh()
        data["filled"] = True

    @staticmethod
    def _button(node, button_id):
        from . import tag_status

        if button_id == AYON_UPDATE_LATEST:
            tag_status.queue_update(node)
        elif button_id == AYON_OPEN_MANAGE:
            c4d.CallCommand(ids.MANAGE)


def _draw_icon(color):
    """Colored ring, None if drawing isn't available."""
    try:
        clip = c4d.bitmaps.GeClipMap()
        clip.Init(32, 32, 32)
        clip.BeginDraw()
        clip.SetColor(0, 0, 0, 0)
        clip.FillRect(0, 0, 31, 31)
        clip.SetColor(*color, 255)
        clip.FillEllipse(2, 2, 29, 29)
        clip.SetColor(32, 34, 40, 255)
        clip.FillEllipse(10, 10, 21, 21)
        clip.EndDraw()
        # The clip map owns its bitmap, keep a copy
        return clip.GetBitmap().GetClone()
    except Exception:
        return None


def register(res):
    """Register the tag, `res` is the `__res__` of the startup .pyp."""
    for state, color in COLORS.items():
        _icons[state] = _draw_icon(color)
    return c4d.plugins.RegisterTagPlugin(
        id=TAG_ID,
        str="AYON",
        info=c4d.TAG_VISIBLE,
        g=ContainerTag,
        description=DESCRIPTION,
        icon=_icons[None],
        res=res,
    )
