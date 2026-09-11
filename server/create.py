from ayon_server.settings import BaseSettingsModel, SettingsField


class ProductTypeItemModel(BaseSettingsModel):
    _layout = "compact"
    product_type: str = SettingsField(
        title="Product type",
        description="Product type name"
    )
    label: str = SettingsField(
        "",
        title="Label",
        description="Label to show in UI for the product type"
    )


class BaseCreatePluginModel(BaseSettingsModel):
    enabled: bool = SettingsField(
        default=True,
        title="Enabled"
    )
    product_type_items: list[ProductTypeItemModel] = SettingsField(
        default_factory=list,
        title="Product type items",
        description=(
            "Optional list of product types this plugin can create. "
        ),
    )


class RenderQualityModel(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(
        "",
        title="Name",
        regex="^[A-Za-z0-9_-]+$",
        description="Version tag, must exist in the project anatomy tags",
    )
    label: str = SettingsField("", title="Label")


class CreateRenderModel(BaseCreatePluginModel):
    render_qualities: list[RenderQualityModel] = SettingsField(
        default_factory=list,
        title="Render qualities",
        description="First item is the default.",
    )


class CreatePluginsModel(BaseSettingsModel):
    RenderlayerCreator: CreateRenderModel = SettingsField(
        title="Create Render",
        default_factory=CreateRenderModel,
    )
    CreateCamera: BaseCreatePluginModel = SettingsField(
        title="Create Camera",
        default_factory=BaseCreatePluginModel,
    )
    CreatePointcache: BaseCreatePluginModel = SettingsField(
        title="Create Pointcache",
        default_factory=BaseCreatePluginModel,
    )
    CreateRedshiftProxy: BaseCreatePluginModel = SettingsField(
        title="Create Redshift Proxy",
        default_factory=BaseCreatePluginModel,
    )
    CreateReview: BaseCreatePluginModel = SettingsField(
        title="Create Review",
        default_factory=BaseCreatePluginModel,
    )


DEFAULT_CREATE_SETTINGS = {
    "RenderlayerCreator": {
        "enabled": True,
        "product_type_items": [],
        "render_qualities": [
            {"name": "preview", "label": "Preview"},
            {"name": "final", "label": "Final"},
        ],
    },
}
