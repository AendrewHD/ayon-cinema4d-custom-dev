import json
import os

import c4d
import pyblish.api

from ayon_core.pipeline.farm.pyblish_functions import (
    create_metadata_path,
    create_skeleton_instance,
)

try:
    from ayon_deadline import abstract_submit_deadline
    from ayon_deadline.lib import (
        DeadlineJobInfo,
        JobType,
        get_instance_job_envs,
    )
    # Private name, pyblish would discover the abstract class as a plug-in
    _SubmitDeadline = abstract_submit_deadline.AbstractSubmitDeadline
except ImportError:
    # Deadline addon is not in the bundle, the plug-in is not discovered
    _SubmitDeadline = object


class Cinema4DSubmitReviewDeadline(_SubmitDeadline):
    """Render the review on Deadline and publish it in a dependent job.

    The Deadline Cinema4D plug-in renders the review scene saved by
    `Cinema4DExtractReview`. The dependent AYON publish job integrates the
    frames and creates the reviewable with core `ExtractReview` on the farm.
    The generic Deadline publish job isn't used, it publishes every product
    as `render`.
    """

    label = "Submit Review to Deadline"
    order = pyblish.api.IntegratorOrder + 0.1
    hosts = ["cinema4d"]
    families = ["review"]
    targets = ["local"]

    def process(self, instance):
        if not instance.data.get("farm"):
            self.log.debug("Review renders locally, skipping.")
            return

        super().process(instance)
        self.submit_publish_job(instance)

    def _set_scene_path(self, *args, **kwargs):
        # Render the saved review scene, never the (published) workfile
        self.scene_path = self._instance.data["reviewScenePath"]
        self.log.info(f"Using {self.scene_path} for render.")

    def get_job_info(self, job_info=None, **kwargs):
        instance = self._instance
        job_info.Plugin = "Cinema4D"

        if job_info.Frames:
            self.log.warning(
                "Custom frames are not supported for reviews,"
                " rendering the full frame range."
            )
        job_info.Frames = "{}-{}".format(
            int(instance.data["frameStartHandle"]),
            int(instance.data["frameEndHandle"]),
        )
        return job_info

    def get_plugin_info(self, **kwargs):
        return {
            "SceneFile": self.scene_path,
            # Major version, e.g. 2026
            "Version": c4d.GetC4DVersion() // 1000,
            "Take": self._instance.data["reviewTake"],
        }

    def submit_publish_job(self, instance):
        """Write the publish metadata and submit the AYON publish job."""
        context = instance.context
        anatomy = context.data["anatomy"]
        render_job = instance.data["deadlineSubmissionJob"]

        publish_instance = self.get_publish_instance_data(instance)
        publish_job = {
            "folderPath": publish_instance["folderPath"],
            "frameStart": publish_instance["frameStart"],
            "frameEnd": publish_instance["frameEnd"],
            "fps": publish_instance["fps"],
            "source": publish_instance["source"],
            "user": context.data["user"],
            "intent": context.data.get("intent"),
            "comment": context.data.get("comment"),
            "job": render_job,
            "instances": [publish_instance],
            # Required key, integrate picks the version
            "version": context.data.get("version"),
        }

        # Written before submitting, the publish job reads it
        metadata_path, rootless_metadata_path = create_metadata_path(
            instance, anatomy
        )
        self.log.debug(f"Writing publish metadata to: {metadata_path}")
        with open(metadata_path, "w") as stream:
            json.dump(publish_job, stream, indent=4, sort_keys=True)

        job_info = self.get_publish_job_info(instance, render_job)
        args = [
            "--headless",
            "publish",
            rootless_metadata_path,
            "--targets", "deadline",
            "--targets", "farm",
        ]
        deadline_addon = context.data["ayonAddonsManager"]["deadline"]
        payload = deadline_addon.submit_ayon_plugin_job(
            instance.data["deadline"]["serverName"], args, job_info
        )
        self.log.info(
            f"Submitted publish job to Deadline: {payload['response']['_id']}"
        )

    def get_publish_job_info(self, instance, render_job):
        """Return the publish job info, using the Deadline publish job
        settings (`ProcessSubmittedJobOnFarm`) like other farm publishes."""
        context = instance.context
        render_job_info = instance.data["deadline"]["job_info"]
        settings = (
            context.data["project_settings"]["deadline"]["publish"]
            .get("ProcessSubmittedJobOnFarm", {})
        )

        job_info = DeadlineJobInfo(
            Name="Publish - {}".format(instance.data["productName"]),
            BatchName=render_job["Props"]["Batch"],
            UserName=render_job["Props"]["User"],
            Comment=context.data.get("comment"),
            Department=(
                render_job_info.Department
                or settings.get("deadline_department")
                or None
            ),
            Priority=(
                settings.get("deadline_priority")
                or render_job_info.Priority
            ),
            Group=settings.get("deadline_group") or None,
            Pool=settings.get("deadline_pool") or None,
            InitialStatus=render_job_info.publish_job_state or "Active",
            JobDependencies=[render_job["_id"]],
        )
        job_info.EnvironmentKeyValue.update(get_instance_job_envs(instance))
        job_info.EnvironmentKeyValue.update(JobType.PUBLISH.get_job_env())
        return job_info

    def get_publish_instance_data(self, instance):
        """Return the instance data the farm publish creates the review from.

        Based on the core farm skeleton, which is made for renders: the
        product type, families and representations are the review's.
        """
        anatomy = instance.context.data["anatomy"]
        data = create_skeleton_instance(instance)

        product_base_type = (
            instance.data.get("productBaseType")
            or instance.data["productType"]
        )
        data.update({
            "productType": instance.data["productType"],
            "productBaseType": product_base_type,
            "family": product_base_type,
            "families": [product_base_type],
        })
        # Marked takes are grouped under the review product
        if instance.data.get("productGroup"):
            data["productGroup"] = instance.data["productGroup"]

        output_dir = instance.data["outputDir"]
        success, staging_dir = anatomy.find_root_template_from_path(
            output_dir
        )
        if not success:
            self.log.warning(
                f"Could not find root path for remapping '{output_dir}'."
                " This may cause issues on farm."
            )
            staging_dir = output_dir

        files = [
            os.path.basename(path) for path in instance.data["expectedFiles"]
        ]
        ext = os.path.splitext(files[0])[1].lstrip(".")
        data["representations"] = [
            {
                "name": ext,
                "ext": ext,
                # A single frame must not be published as a sequence
                "files": files if len(files) > 1 else files[0],
                "stagingDir": staging_dir,
                "frameStart": instance.data["frameStartHandle"],
                "frameEnd": instance.data["frameEndHandle"],
                "fps": instance.data["fps"],
                "tags": ["review"],
            },
            # Middle frame as the version thumbnail
            {
                "name": "thumbnail",
                "ext": ext,
                "files": files[len(files) // 2],
                "stagingDir": staging_dir,
                "outputName": "thumbnail",
                "tags": ["thumbnail"],
            },
        ]
        return data
