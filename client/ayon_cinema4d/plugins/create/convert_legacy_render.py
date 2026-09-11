from ayon_core.pipeline.create.creator_plugins import ProductConvertorPlugin
from ayon_cinema4d.api import lib

import c4d

RENDER_CREATOR_ID = "io.ayon.creators.cinema4d.render"


class Cinema4DLegacyRenderConvertor(ProductConvertorPlugin):
    """Convert render instances stored on takes to one render instance.

    The previous Render creator turned every take into a render instance.
    Marked takes were rendered, which the new instance reproduces with
    'Render Marked Takes' enabled.
    """

    identifier = "io.ayon.convertors.cinema4d.render_takes"

    def find_instances(self):
        if self._iter_legacy_takes(lib.active_document()):
            self.add_convertor_item("Found render instances on takes.")

    def convert(self):
        doc = lib.active_document()
        takes = self._iter_legacy_takes(doc)
        if not takes:
            self.remove_convertor_item()
            return

        # Take names are appended to the variant, e.g. `renderMain_Hero`
        instance = self.create_context.create(RENDER_CREATOR_ID, "Main")
        if instance is not None:
            instance.creator_attributes["publishTakes"] = True
            creator = self.create_context.creators[RENDER_CREATOR_ID]
            creator.update_instances([(instance, None)])

        # Only after the new instance exists
        for take in takes:
            self._remove_instance_user_data(take)
        c4d.EventAdd()
        self.log.info(f"Converted {len(takes)} take render instance(s).")
        self.remove_convertor_item()

    @staticmethod
    def _iter_legacy_takes(doc):
        take_data = doc.GetTakeData()
        if take_data is None:
            return []
        return [
            take for take in lib.iter_takes(take_data.GetMainTake())
            if lib.read(take).get("creator_identifier") == RENDER_CREATOR_ID
        ]

    @staticmethod
    def _remove_instance_user_data(take):
        """Remove the imprinted "AYON" user data group and its entries."""
        user_data = take.GetUserDataContainer()
        groups = [
            description_id for description_id, base_container in user_data
            if base_container[c4d.DESC_NAME] == "AYON"
            and description_id[1].dtype == c4d.DTYPE_GROUP
        ]
        for description_id, base_container in reversed(user_data):
            if base_container[c4d.DESC_PARENTGROUP] in groups:
                take.RemoveUserData(description_id)
        for description_id in groups:
            take.RemoveUserData(description_id)
