import os

from ayon_core.pipeline import publish
from ayon_cinema4d.api import exporters


class Cinema4DExtractReview(publish.Extractor):
    """Render the review as a jpg sequence.

    The reviewable movie is created from the sequence by ayon-core's
    `ExtractReview`, so both the frames and the movie are published.

    Farm reviews are not rendered here: a render-ready copy of the scene is
    saved for `Cinema4DSubmitReviewDeadline` instead.
    """

    label = "Render Review"
    hosts = ["cinema4d"]
    families = ["review"]

    def process(self, instance):
        options = self.get_render_options(instance)
        if instance.data.get("farm"):
            self.extract_farm_scene(instance, options)
        else:
            self.render(instance, options)

    def get_render_options(self, instance):
        """Return the `exporters.render_playblast` options of the review."""
        # Resolution and fps from the instance, falling back to the folder
        attrib = instance.data.get("folderEntity", {}).get("attrib", {})
        width = instance.data.get("resolutionWidth",
                                  attrib.get("resolutionWidth", 1920))
        height = instance.data.get("resolutionHeight",
                                   attrib.get("resolutionHeight", 1080))

        # Viewport content. Splines and nulls can only render with
        # 'Geometry Only' disabled, so enabling either implies it.
        show_splines = instance.data.get("showSplines", False)
        show_nulls = instance.data.get("showNulls", False)
        geometry_only = instance.data.get("geometryOnly", True)
        if show_splines or show_nulls:
            geometry_only = False

        # TODO: Allow using members for isolate view
        return {
            # Frame range including handles
            "frame_start": instance.data["frameStartHandle"],
            "frame_end": instance.data["frameEndHandle"],
            "fps": instance.data.get("fps", attrib.get("fps")),
            "width": int(width),
            "height": int(height),
            "geometry_only": geometry_only,
            "show_splines": show_splines,
            "show_nulls": show_nulls,
            # Set by `CollectReviewTakes` when publishing marked takes
            "take": instance.data.get("take"),
            "doc": instance.context.data["doc"],
        }

    def render(self, instance, options):
        # Define extract output file path, frames get `.<frame>.jpg` appended
        dir_path = self.staging_dir(instance)
        path = os.path.join(dir_path, instance.name)

        files = exporters.render_playblast(path, **options)

        # Middle frame as the version thumbnail. `thumbnailPath` is uploaded
        # by core `IntegrateThumbnailsAYON`; `thumbnailSource` would be too
        # late, `ExtractThumbnailFromSource` runs before this extractor.
        instance.data["thumbnailPath"] = os.path.join(
            dir_path, files[len(files) // 2]
        )

        representation = {
            "name": exporters.PLAYBLAST_EXTENSION,
            "ext": exporters.PLAYBLAST_EXTENSION,
            # A single frame must not be published as a sequence
            "files": files if len(files) > 1 else files[0],
            "stagingDir": dir_path,
            "frameStart": options["frame_start"],
            "frameEnd": options["frame_end"],
            "fps": options["fps"],
            "tags": ["review"],
        }
        instance.data.setdefault("representations", []).append(representation)

        self.log.info(
            f"Extracted instance '{instance.name}' to: {dir_path}"
            f" ({len(files)} frames)"
        )

    def extract_farm_scene(self, instance, options):
        """Save the review scene the farm renders."""
        output_dir = self.get_farm_output_dir(instance)
        path = os.path.join(output_dir, instance.name)
        scene_path = path + ".c4d"

        take_name = exporters.save_playblast_scene(scene_path, path, **options)

        # Used by `Cinema4DSubmitReviewDeadline`
        instance.data.update({
            "outputDir": output_dir,
            "expectedFiles": exporters.get_playblast_files(
                path, options["frame_start"], options["frame_end"]
            ),
            "reviewScenePath": scene_path,
            "reviewTake": take_name,
            "resolutionWidth": options["width"],
            "resolutionHeight": options["height"],
        })

        self.log.info(
            f"Saved review scene of '{instance.name}' for the farm:"
            f" {scene_path} (take: {take_name})"
        )

    def get_farm_output_dir(self, instance):
        """Return the directory the farm renders the review to.

        The default staging dir is a local temp folder the farm can't reach,
        so without a custom staging dir the review renders next to the
        workfile: `renders/review/<workfile name>/<product name>`.
        """
        if instance.data.get("stagingDir_is_custom"):
            return instance.data["stagingDir"]

        workdir, filename = os.path.split(instance.context.data["currentFile"])
        return os.path.join(
            workdir,
            "renders",
            "review",
            os.path.splitext(filename)[0],
            instance.name,
        )
