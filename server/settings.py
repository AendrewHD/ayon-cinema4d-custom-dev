from ayon_server.settings import BaseSettingsModel, SettingsField

from .imageio import DEFAULT_IMAGEIO_SETTINGS, Cinema4DImageIOModel
from .create import DEFAULT_CREATE_SETTINGS, CreatePluginsModel
from .publish import DEFAULT_PUBLISH_SETTINGS, PublishPluginsModel

DEFAULT_VALUES = {
    "imageio": DEFAULT_IMAGEIO_SETTINGS,
    "create": DEFAULT_CREATE_SETTINGS,
    "publish": DEFAULT_PUBLISH_SETTINGS,
}


class RenderSettingsModel(BaseSettingsModel):
    render_folder: str = SettingsField(
        "renders/cinema4d",
        title="Render folder",
        description="Relative to the workfile folder.",
    )
    image_prefix: str = SettingsField(
        "$prj/$take/$take",
        title="Regular image prefix",
        description="Cinema 4D tokens, keep $take unique per take.",
    )
    multipass_prefix: str = SettingsField(
        "$prj/$take/$pass/$take_$pass",
        title="Multi-Pass prefix",
        description="Separate file per pass, needs $pass or $userpass.",
    )
    multilayer_prefix: str = SettingsField(
        "$prj/$take/$take_multipass",
        title="Multi-Layer file prefix",
        description="One file with all passes, without $pass.",
    )


class Cinema4DSettings(BaseSettingsModel):
    imageio: Cinema4DImageIOModel = SettingsField(
        default_factory=Cinema4DImageIOModel,
        title="Color Management (ImageIO)"
    )
    render_settings: RenderSettingsModel = SettingsField(
        default_factory=RenderSettingsModel,
        title="Render Settings",
    )
    create: CreatePluginsModel = SettingsField(
        default_factory=CreatePluginsModel,
        title="Create plugins",
    )
    publish: PublishPluginsModel = SettingsField(
        default_factory=PublishPluginsModel,
        title="Publish plugins",
    )
