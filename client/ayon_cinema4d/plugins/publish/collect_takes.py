import pyblish.api

from ayon_cinema4d.api import lib


class CollectMarkedTakes(pyblish.api.InstancePlugin):
    """Split a review or render into one instance per marked take.

    With 'Publish/Render Marked Takes' enabled, every take marked in the Take
    Manager is published as its own product with the take name appended to
    the variant, e.g. `reviewMain_Hero`. The source instance is not published.

    Without it the current take is published; unless it is the Main take its
    name is appended the same way.
    """

    label = "Collect Marked Takes"
    # After `CollectInstances`, before core collects product versions
    order = pyblish.api.CollectorOrder - 0.39
    hosts = ["cinema4d"]
    families = ["review", "render"]

    def process(self, instance):
        if "take" in instance.data:
            return

        doc = instance.context.data["doc"]
        if not instance.data.get("publishTakes"):
            self.collect_current_take(instance, doc)
            return

        takes = list(lib.iter_marked_takes(doc))
        if not takes:
            # Reported by `ValidateMarkedTakes`
            return

        for take in takes:
            take_instance = self.create_take_instance(instance, take)
            self.log.debug(
                f"Collected take '{take.GetName()}' as: {take_instance}"
            )

        # Only the take products are published
        instance.data["publish"] = False

    def collect_current_take(self, instance, doc):
        """Name the instance after the current take, unless it is Main."""
        take_data = doc.GetTakeData()
        take = take_data.GetCurrentTake() if take_data else None
        if take is None or take.IsMain():
            return

        source_name = instance.data["productName"]
        instance.data.update(self.get_take_data(instance, take))
        instance.data["productGroup"] = source_name
        self.log.debug(
            f"Collected current take '{take.GetName()}' as: {instance}"
        )

    def get_take_data(self, instance, take):
        """Return the instance data that names a product after `take`."""
        take_variant = lib.get_take_variant(take)
        variant = "{}_{}".format(instance.data["variant"], take_variant)
        product_name = (
            self.get_product_name(instance, variant)
            # Default product name template `{productType}{Variant}`
            or "{}_{}".format(instance.data["productName"], take_variant)
        )

        label = "{} ({})".format(product_name, instance.data["folderPath"])
        if "frameStartHandle" in instance.data:
            label += "  [{}-{}]".format(
                int(instance.data["frameStartHandle"]),
                int(instance.data["frameEndHandle"]),
            )

        return {
            "name": product_name,
            "label": label,
            "variant": variant,
            "productName": product_name,
            "take": take,
            # The ayon-deadline Cinema4D submitter reads the take from here
            "transientData": dict(instance.data.get("transientData", {}),
                                  take=take),
        }

    def create_take_instance(self, instance, take):
        take_data = self.get_take_data(instance, take)
        product_name = take_data["productName"]

        take_instance = instance.context.create_instance(product_name)
        take_instance[:] = instance[:]

        # Copy containers so the take instance can change them freely
        for key, value in instance.data.items():
            if isinstance(value, (dict, list)):
                value = value.copy()
            take_instance.data[key] = value

        take_instance.data.update(take_data)
        take_instance.data.update({
            # Group the take products under the source product
            "productGroup": instance.data["productName"],
            "instance_id": take_instance.id,
        })
        return take_instance

    def get_product_name(self, instance, variant):
        """Return the product name from the instance's creator.

        Uses the creator so studio product name templates apply. Returns
        None when the create context or creator is not available.
        """
        create_context = instance.context.data.get("create_context")
        if create_context is None:
            return None
        creator = create_context.creators.get(
            instance.data.get("creator_identifier")
        )
        if creator is None:
            return None

        folder_path = instance.data["folderPath"]
        return creator.get_product_name(
            create_context.get_current_project_name(),
            create_context.get_folder_entity(folder_path),
            create_context.get_task_entity(
                folder_path, instance.data.get("task")
            ),
            variant,
            create_context.host_name,
            product_type=instance.data["productType"],
        )
