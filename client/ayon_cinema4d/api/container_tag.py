"""AYON container tag, marks the root object of a loaded product.

The container data (representation, loader, ...) is user data on the tag,
written by `pipeline.imprint_container`. The tag itself has no behaviour,
so scenes stay usable where the addon isn't installed (data is kept).
"""
import c4d

from .ui import ids

TAG_ID = ids.CONTAINER_TAG
DESCRIPTION = "Tayoncontainer"  # startup/res/description/tayoncontainer.res
COLOR = (0, 220, 170)


class ContainerTag(c4d.plugins.TagData):
    """Data only tag."""


def _icon():
    """AYON colored ring, None if drawing isn't available."""
    try:
        clip = c4d.bitmaps.GeClipMap()
        clip.Init(32, 32, 32)
        clip.BeginDraw()
        clip.SetColor(0, 0, 0, 0)
        clip.FillRect(0, 0, 31, 31)
        clip.SetColor(*COLOR, 255)
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
    return c4d.plugins.RegisterTagPlugin(
        id=TAG_ID,
        str="AYON",
        info=c4d.TAG_VISIBLE,
        g=ContainerTag,
        description=DESCRIPTION,
        icon=_icon(),
        res=res,
    )
