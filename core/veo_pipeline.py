"""Veo 3.1 rendering with real continuity controls.

Gemini Flash is used elsewhere in REVERIE to plan and critique a film.  It is
not the video renderer.  This module deliberately uses the documented
``client.models.generate_videos`` Veo API, because that API supports the
reference-image controls needed to keep a character recognisable across shots.

The implementation makes two product guarantees explicit:

* a character-lock shot is rendered at Veo's supported 8 second duration;
* every real render consumes an atomic daily budget reservation *before* a
  model call.  A failed attempt is still accounted for, rather than allowing a
  race to exceed the project's quota.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from google.api_core.exceptions import ResourceExhausted

from core.logger import get_logger, trace_span
from models.schema import SceneRecord
from repositories.scene import BudgetExceededError, SceneRepository

logger = get_logger(__name__)

# Veo 3 supports 4, 6, and 8 second clips.  Reference-image character locking
# is documented for the 8 second Veo 3.1 preview path, so the studio always
# uses 8 seconds for a continuity-enabled film.  Do not silently turn a user
# request for a 10 second clip into an 8 second one.
CHARACTER_LOCK_DURATION_SECONDS = 8
SUPPORTED_VEO_DURATIONS = frozenset({4, 6, 8})
MAX_REFERENCE_IMAGES = 3
DEFAULT_DAILY_CLIP_BUDGET = 24
DEFAULT_REFERENCE_MODEL_ID = "veo-3.1-generate-preview"
DEFAULT_TEXT_MODEL_ID = "veo-3.1-fast-generate-001"
INTER_CLIP_DELAY_SECONDS = 15

_DATA_IMAGE_RE = re.compile(
    r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE | re.DOTALL,
)
_PUBLIC_GCS_PREFIX = "https://storage.googleapis.com/"


@dataclass(frozen=True)
class ReferenceImage:
    """A Veo-compatible GCS image used as an asset/character anchor."""

    gcs_uri: str
    mime_type: str
    label: str = ""


class VeoPipeline:
    """Creates Veo clips and turns user reference images into Veo assets."""

    def __init__(self, scene_repo: SceneRepository):
        self.scene_repo = scene_repo
        self.bucket_name = os.getenv("GCS_RENDER_BUCKET", "reverio-render-bucket")
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        # The Google Gen AI SDK examples for Veo use global.  Do not inherit a
        # Cloud Run region such as us-east1 here: availability is model-specific.
        self.location = os.getenv("VEO_LOCATION", "global")
        self.reference_model_id = os.getenv(
            "VEO_REFERENCE_MODEL_ID", DEFAULT_REFERENCE_MODEL_ID
        )
        self.text_model_id = os.getenv("VEO_MODEL_ID", DEFAULT_TEXT_MODEL_ID)
        self.daily_clip_budget = max(
            1, int(os.getenv("VEO_DAILY_CLIP_BUDGET", str(DEFAULT_DAILY_CLIP_BUDGET)))
        )
        self._storage_client: Any = None
        self._genai_client: Any = None

    def _get_storage_client(self):
        if self._storage_client is None:
            from google.cloud import storage

            self._storage_client = storage.Client(project=self.project_id or None)
        return self._storage_client

    def _get_genai_client(self):
        if self._genai_client is None:
            from google import genai

            if not self.project_id:
                raise RuntimeError(
                    "GOOGLE_CLOUD_PROJECT is required for Veo rendering."
                )
            self._genai_client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
            )
        return self._genai_client

    @staticmethod
    def continuity_duration(requested_seconds: int, has_character_references: bool) -> int:
        """Return a valid Veo duration or raise a useful, honest error.

        Text-only Veo renders may use 4, 6, or 8 seconds.  A production that
        promises character consistency must use 8 seconds because that is the
        reference-image-supported path.
        """
        try:
            duration = int(requested_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("Clip duration must be an integer number of seconds.") from exc

        if has_character_references:
            if duration != CHARACTER_LOCK_DURATION_SECONDS:
                raise ValueError(
                    "Character Lock requires 8-second Veo 3.1 clips. "
                    "This is a Veo capability constraint, not a prompt setting."
                )
            return CHARACTER_LOCK_DURATION_SECONDS
        if duration not in SUPPORTED_VEO_DURATIONS:
            raise ValueError(
                f"Veo supports {sorted(SUPPORTED_VEO_DURATIONS)} second clips; got {duration}."
            )
        return duration

    @staticmethod
    def stable_seed(production_id: str, scene_index: int, attempt: int = 0) -> int:
        """Create a reproducible uint32 seed without pretending it is a lock."""
        raw = f"{production_id}:scene:{scene_index}:attempt:{attempt}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")

    def _count_reserved_clips_today(self) -> int:
        """Read the same Firestore counter used by the reservation transaction."""
        try:
            doc = self.scene_repo.db.collection("system_meta").document("veo_budget").get()
            if doc.exists:
                data = doc.to_dict() or {}
                if data.get("date") == datetime.utcnow().strftime("%Y-%m-%d"):
                    return int(data.get("count", 0))
        except Exception as exc:
            logger.warning("Could not read Veo budget counter: %s", exc)
        return 0

    async def remaining_budget(self) -> int:
        used = await asyncio.to_thread(self._count_reserved_clips_today)
        return max(0, self.daily_clip_budget - used)

    def _public_url(self, uri: str) -> str:
        if uri.startswith("gs://"):
            return f"{_PUBLIC_GCS_PREFIX}{uri[len('gs://') :]}"
        return uri

    @staticmethod
    def _gcs_uri_from_url(uri: str) -> Optional[str]:
        if uri.startswith("gs://"):
            return uri
        if uri.startswith(_PUBLIC_GCS_PREFIX):
            rest = uri[len(_PUBLIC_GCS_PREFIX) :]
            if "/" in rest:
                return f"gs://{rest}"
        return None

    def _upload_reference_data_uri(self, name: str, data_uri: str) -> ReferenceImage:
        """Persist a browser data URI to GCS so Veo can consume it safely."""
        match = _DATA_IMAGE_RE.match(data_uri.strip())
        if not match:
            raise ValueError("Character reference must be a PNG, JPEG, or WebP data URI.")

        mime_type = match.group(1).lower()
        raw = base64.b64decode(match.group(2), validate=False)
        if not raw or len(raw) > 10 * 1024 * 1024:
            raise ValueError("Character reference image must be between 1 byte and 10 MB.")

        digest = hashlib.sha256(raw).hexdigest()
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
        blob_name = f"continuity/references/{digest}.{extension}"
        bucket = self._get_storage_client().bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        # Content-addressing prevents every rerender from duplicating the same
        # anchor.  It is safe if two requests race: both write identical bytes.
        if not blob.exists():
            blob.upload_from_string(raw, content_type=mime_type)
        return ReferenceImage(f"gs://{self.bucket_name}/{blob_name}", mime_type, name)

    def _reference_from_asset(self, asset: Dict[str, Any], name: str) -> Optional[ReferenceImage]:
        if not isinstance(asset, dict):
            return None
        asset_type = str(asset.get("type") or asset.get("asset_type") or "").lower()
        mime_type = str(asset.get("mime_type") or "").lower()
        uri = str(asset.get("url") or asset.get("public_url") or "")
        if asset_type != "image" and not mime_type.startswith("image/"):
            return None
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            return None
        gcs_uri = self._gcs_uri_from_url(uri)
        if gcs_uri:
            return ReferenceImage(gcs_uri, mime_type, name)
        if uri.startswith("data:"):
            return self._upload_reference_data_uri(name, uri)
        return None

    async def prepare_character_references(
        self, characters: Iterable[Dict[str, Any]]
    ) -> Dict[str, ReferenceImage]:
        """Resolve one stable Veo asset reference for each named character.

        Per-character image uploads win.  A labelled uploaded image is a
        fallback.  Generic mood boards, videos, and audio are intentionally not
        treated as character anchors: silently claiming otherwise was one of the
        original continuity bugs.
        """
        resolved: Dict[str, ReferenceImage] = {}
        for character in characters:
            name = str(character.get("name") or "").strip()
            if not name:
                continue
            data_uri = str(character.get("reference_image_base64") or "").strip()
            if data_uri:
                resolved[name] = await asyncio.to_thread(
                    self._upload_reference_data_uri, name, data_uri
                )
                continue

            # An asset only becomes a character anchor when its label explicitly
            # matches the character.  This avoids applying a background moodboard
            # to a face simply because it happened to be uploaded in the same run.
            normalized_name = name.casefold()
            for asset in character.get("reference_asset_urls") or []:
                label = str(asset.get("label") or "").strip().casefold() if isinstance(asset, dict) else ""
                if label != normalized_name:
                    continue
                reference = await asyncio.to_thread(self._reference_from_asset, asset, name)
                if reference:
                    resolved[name] = reference
                    break
        return resolved

    async def reserve_veo_budget(
        self,
        scene_id: str,
        *,
        characters_involved: Optional[List[str]] = None,
        drama_score: float = 0.0,
        veo_prompt: str = "",
        duration_seconds: int = CHARACTER_LOCK_DURATION_SECONDS,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        seed: Optional[int] = None,
        anchor_image_uris: Optional[List[str]] = None,
    ) -> SceneRecord:
        """Atomically reserve budget before asking Veo to generate a clip."""
        characters_involved = list(characters_involved or [])
        if len(characters_involved) > MAX_REFERENCE_IMAGES:
            raise ValueError(
                f"A Veo shot can character-lock at most {MAX_REFERENCE_IMAGES} subjects; "
                f"got {len(characters_involved)}. Split the scene into coverage shots."
            )
        if aspect_ratio not in {"16:9", "9:16"}:
            raise ValueError("Veo aspect ratio must be 16:9 or 9:16.")
        if duration_seconds not in SUPPORTED_VEO_DURATIONS:
            raise ValueError("Veo duration must be 4, 6, or 8 seconds.")

        scene = SceneRecord(
            scene_id=scene_id,
            characters_involved=characters_involved,
            drama_score=max(0.0, min(1.0, float(drama_score))),
            veo_prompt=veo_prompt,
            video_uri="",
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            status="queued",
            seed=seed,
            anchor_image_uris=list(anchor_image_uris or []),
        )

        # The transaction increments the counter and writes the queued scene in
        # one operation, closing the check-then-spend race in the former Omni path.
        return await self.scene_repo.reserve_veo_budget(scene_id, scene)

    async def generate_clip(
        self,
        scene: SceneRecord,
        *,
        reference_images: Optional[List[ReferenceImage]] = None,
    ) -> str:
        """Render one reserved scene and keep it in ``rendering`` until review."""
        with trace_span("veo_generate_clip", {"scene_id": scene.scene_id}):
            references = list(reference_images or [])[:MAX_REFERENCE_IMAGES]
            scene.status = "rendering"
            self.scene_repo.save(scene.scene_id, scene)

            last_error: Optional[Exception] = None
            for attempt in range(3):
                try:
                    gcs_uri = await self._call_veo_api(scene, references)
                    public_url = self._public_url(gcs_uri)
                    scene.video_uri = public_url
                    # The director quality gate owns the terminal `critiqued`
                    # status.  Keep this rendering while it is being evaluated.
                    self.scene_repo.save(scene.scene_id, scene)
                    logger.info("[Veo] Clip ready for review: %s", public_url)
                    return public_url
                except ResourceExhausted as exc:
                    last_error = exc
                    if attempt == 2:
                        break
                    delay = 30 * (2**attempt)
                    logger.warning("[Veo] Rate-limited scene %s; retrying in %ss", scene.scene_id, delay)
                    await asyncio.sleep(delay)
                except Exception as exc:
                    last_error = exc
                    # Retrying a transient server/network failure is useful, but
                    # don't obscure configuration or safety errors with long waits.
                    if attempt == 2:
                        break
                    logger.warning("[Veo] Attempt %s failed for %s: %s", attempt + 1, scene.scene_id, exc)
                    await asyncio.sleep(10 * (attempt + 1))

            scene.status = "failed"
            scene.failure_reason = str(last_error or "Veo did not return a video")[:1000]
            self.scene_repo.save(scene.scene_id, scene)
            raise RuntimeError(f"Veo generation failed for {scene.scene_id}: {last_error}")

    async def _call_veo_api(self, scene: SceneRecord, references: List[ReferenceImage]) -> str:
        """Invoke documented Veo generation and return the resulting GCS URI."""
        from google.genai import types

        if references and scene.duration_seconds != CHARACTER_LOCK_DURATION_SECONDS:
            raise ValueError("Veo reference-image generation requires an 8-second scene.")

        client = self._get_genai_client()
        output_gcs_uri = f"gs://{self.bucket_name}/veo-raw/{scene.scene_id}/"
        model_id = self.reference_model_id if references else self.text_model_id
        prompt = scene.veo_prompt or scene.omni_prompt
        if not prompt:
            raise ValueError("Cannot render an empty Veo prompt.")

        config_kwargs: Dict[str, Any] = {
            "number_of_videos": 1,
            "duration_seconds": scene.duration_seconds,
            "aspect_ratio": scene.aspect_ratio,
            "resolution": scene.resolution,
            "generate_audio": True,
            "person_generation": "allow_adult",
            "output_gcs_uri": output_gcs_uri,
            "enhance_prompt": False,
            # A seed improves rerun reproducibility, but we still use a reference
            # image and visual ledger because seed alone does not guarantee identity.
            "seed": scene.seed,
        }
        if references:
            config_kwargs["reference_images"] = [
                types.VideoGenerationReferenceImage(
                    image=types.Image(gcs_uri=ref.gcs_uri, mime_type=ref.mime_type),
                    reference_type="asset",
                )
                for ref in references
            ]

        def _generate() -> str:
            logger.info(
                "[Veo] generate_videos scene=%s model=%s duration=%ss anchors=%s",
                scene.scene_id,
                model_id,
                scene.duration_seconds,
                len(references),
            )
            operation = client.models.generate_videos(
                model=model_id,
                prompt=prompt,
                config=types.GenerateVideosConfig(**config_kwargs),
            )
            while not operation.done:
                time.sleep(15)
                operation = client.operations.get(operation)

            result = getattr(operation, "response", None) or getattr(operation, "result", None)
            if callable(result):
                result = result()
            videos = getattr(result, "generated_videos", None) or []
            if not videos:
                raise RuntimeError(f"Veo completed without generated_videos for scene {scene.scene_id}")
            video = getattr(videos[0], "video", videos[0])
            uri = getattr(video, "uri", None)
            if uri:
                return str(uri)

            # Some SDK response shapes return inline bytes even with an output
            # prefix. Persist them so the rest of the pipeline has one URI type.
            raw = getattr(video, "video_bytes", None)
            if raw:
                blob_name = f"renders/{scene.scene_id}.mp4"
                blob = self._get_storage_client().bucket(self.bucket_name).blob(blob_name)
                blob.upload_from_string(raw, content_type="video/mp4")
                return f"gs://{self.bucket_name}/{blob_name}"
            raise RuntimeError(f"Veo returned neither a GCS URI nor bytes for scene {scene.scene_id}")

        return await asyncio.get_running_loop().run_in_executor(None, _generate)
