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
    review: bool = SettingsField(
        True,
        title="Review the rendered sequence",
        description="Create a movie from the rendered frames in AYON.",
    )
    jpeg_sequence: bool = SettingsField(
        True,
        title="Publish a JPEG sequence",
        description="Converted from the rendered frames, display referred.",
    )
    contact_sheet: bool = SettingsField(
        True,
        title="Publish a Multi-Pass contact sheet",
        description=(
            "One labelled grid of all passes per frame, needs a Multi-Layer"
            " file. Published as JPEG sequence with a movie."
        ),
    )
    contact_sheet_columns: int = SettingsField(
        0,
        title="Contact sheet columns",
        ge=0,
        le=16,
        description="0 fits the grid to the number of passes.",
    )
    contact_sheet_tile_width: int = SettingsField(
        640,
        title="Contact sheet tile width",
        ge=64,
        le=4096,
        description="Width of a single pass in the contact sheet.",
    )


class WorkfileStartupModel(BaseSettingsModel):
    create_first_workfile: bool = SettingsField(
        True,
        title="Start a task without workfiles in v001",
        description=(
            "When Cinema 4D starts in a task without workfiles, or a task"
            " is started from the Workfiles window, save the empty scene"
            " as the first workfile version."
        ),
    )
    reset_frame_range: bool = SettingsField(
        True, title="Set the frame range and fps of the task")
    reset_resolution: bool = SettingsField(
        True, title="Set the resolution of the task")
    reset_colorspace: bool = SettingsField(
        True, title="Set the colorspace (OCIO)")
    reset_render_settings: bool = SettingsField(
        True, title="Set the render settings (Redshift, output paths)")


class Cinema4DSettings(BaseSettingsModel):
    workfile_startup: WorkfileStartupModel = SettingsField(
        default_factory=WorkfileStartupModel,
        title="First Workfile",
    )
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
