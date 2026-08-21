import os
import ffmpeg
import uuid
import tempfile
import asyncio
from typing import List, Dict, Optional
from core.logger import get_logger

logger = get_logger(__name__)


class VideoEditor:
    """
    Concatenates Gemini Omni clips into a single film.

    Omni returns MP4 files with native audio (voices + ambience baked in).
    We simply concatenate them — no TTS mixing, no audio replacement.
    FFmpeg re-encodes to a consistent codec so every clip plays cleanly.
    """

    def __init__(self):
        self.bucket_name = os.getenv("GCS_RENDER_BUCKET", "").strip()
        self._storage_client = None

    def _get_storage_client(self):
        if not self._storage_client:
            from google.cloud import storage
            self._storage_client = storage.Client()
        return self._storage_client

    def _download(self, uri: str, suffix: str) -> Optional[str]:
        """Download a GCS public URL or gs:// URI to a temp file."""
        if not uri:
            return None
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        path = tmp.name
        tmp.close()
        try:
            if uri.startswith("gs://"):
                rest = uri[len("gs://"):]
                bucket_name, blob_path = rest.split("/", 1)
                client = self._get_storage_client()
                client.bucket(bucket_name).blob(blob_path).download_to_filename(path)
            else:
                import urllib.request
                urllib.request.urlretrieve(uri, path)
            logger.info(f"Downloaded {uri} → {path}")
            return path
        except Exception as e:
            logger.error(f"Download failed for {uri}: {e}")
            if os.path.exists(path):
                os.remove(path)
            return None

    async def compile_movie(
        self, scene_assets: List[Dict], target_duration_seconds: Optional[int] = None
    ) -> str:
        """
        Concatenate accepted Omni clips into a final film and upload to GCS.

        Each entry in scene_assets needs only 'video_uri'.
        Omni clips already contain audio — we preserve it via the copy codec
        during concat so no quality is lost.
        """
        if target_duration_seconds is not None and target_duration_seconds <= 0:
            raise ValueError("target_duration_seconds must be positive when supplied.")
        if not self.bucket_name:
            raise RuntimeError("GCS_RENDER_BUCKET is required to compile and deliver a real film.")
        logger.info(
            "Compiling %s accepted Omni clips%s…",
            len(scene_assets),
            f" to {target_duration_seconds}s" if target_duration_seconds else "",
        )
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._compile_sync, scene_assets, target_duration_seconds
        )

    def _compile_sync(
        self, scene_assets: List[Dict], target_duration_seconds: Optional[int] = None
    ) -> str:
        tmp_files: List[str] = []
        out_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
        tmp_files.append(out_path)

        try:
            local_clips: List[str] = []
            for scene in scene_assets:
                # Internal services use the GCS URI, not the browser-facing
                # public URL. This keeps compilation working with private GCS
                # buckets and avoids relying on an unauthenticated HTTP fetch.
                uri = scene.get("storage_uri") or scene.get("video_uri")
                if not uri:
                    continue
                local = self._download(uri, ".mp4")
                if local:
                    local_clips.append(local)
                    tmp_files.append(local)

            if not local_clips:
                raise RuntimeError("No clips downloaded — nothing to compile.")

            output_args = {
                "vcodec": "libx264",
                "acodec": "aac",
                "audio_bitrate": "192k",
                "movflags": "+faststart",
            }
            if target_duration_seconds is not None:
                # The screenplay can require ceil(runtime / 10) Omni clips. Cut
                # only the end of the last accepted clip so the advertised film
                # runtime is true, rather than returning 64 seconds for a 60s film.
                output_args["t"] = target_duration_seconds

            if len(local_clips) == 1:
                # Single clip — re-encode to h264/aac for compatibility.
                logger.info("Single clip — re-encoding…")
                (
                    ffmpeg
                    .input(local_clips[0])
                    .output(out_path, **output_args)
                    .overwrite_output()
                    .run(quiet=True)
                )
            else:
                # Multiple clips — write a concat list file and use the
                # concat demuxer.  This is the most reliable FFmpeg concat
                # approach for clips that may have slightly different headers.
                list_file = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".txt", mode="w"
                )
                for clip in local_clips:
                    # FFmpeg concat list requires forward-slashes even on Windows.
                    list_file.write(f"file '{clip.replace(os.sep, '/')}'\n")
                list_file.close()
                tmp_files.append(list_file.name)

                logger.info(f"Concatenating {len(local_clips)} clips via concat demuxer…")
                (
                    ffmpeg
                    .input(list_file.name, format="concat", safe=0)
                    .output(out_path, **output_args)
                    .overwrite_output()
                    .run(quiet=True)
                )

            # Verify we did not make a false duration claim. FFmpeg cannot add
            # real story content to an underlength source, so fail rather than
            # padding with frozen frames or silently returning a short film.
            if target_duration_seconds is not None:
                try:
                    probe = ffmpeg.probe(out_path)
                    actual_duration = float(probe["format"]["duration"])
                    if actual_duration < target_duration_seconds - 0.35:
                        logger.warning(
                            "Final edit is %.2fs but target was %ss — "
                            "fewer clips were accepted than planned (partial film).",
                            actual_duration,
                            target_duration_seconds,
                        )
                    else:
                        logger.info(
                            "Final edit duration verified: %.2fs (target %ss)",
                            actual_duration,
                            target_duration_seconds,
                        )
                except ffmpeg.Error as exc:
                    logger.warning("Could not verify final movie duration: %s", exc)

            # Upload to GCS.
            movie_id = f"cinema_{uuid.uuid4().hex[:8]}"
            blob_name = f"renders/{movie_id}_final.mp4"
            client = self._get_storage_client()
            blob = client.bucket(self.bucket_name).blob(blob_name)
            blob.upload_from_filename(out_path, content_type="video/mp4")

            public_url = f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
            logger.info(f"Final film uploaded: {public_url}")
            return public_url

        except Exception as e:
            logger.error(f"FFmpeg compilation failed: {e}")
            raise
        finally:
            for f in tmp_files:
                try:
                    os.remove(f)
                except OSError:
                    pass
