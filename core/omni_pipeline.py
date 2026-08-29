"""Gemini Omni Flash rendering and stateful continuity primitives.

Omni is the renderer for REVERIE.  Gemini Flash plans/criticises the film;
Gemini Omni Flash creates the video and its native audio.  The important part
of this module is not a longer prompt: it keeps the *accepted interaction ID*
between shots so Omni can retain the previous video state.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from google.api_core.exceptions import ResourceExhausted

from core.logger import get_logger, trace_span
from models.schema import SceneRecord
from repositories.scene import BudgetExceededError, SceneRepository

logger = get_logger(__name__)

OMNI_CLIP_DURATION_SECONDS = 10
# Omni does not expose a duration control. Accept any clip between 1s and 12s —
# Vertex Omni sometimes returns slightly shorter clips and we don't want to
# reject valid video on a minor timing difference.
MIN_ACCEPTED_CLIP_SECONDS = float(os.getenv("OMNI_MIN_CLIP_SECONDS", "1.0"))
MAX_ACCEPTED_CLIP_SECONDS = float(os.getenv("OMNI_MAX_CLIP_SECONDS", "12.0"))
DEFAULT_OMNI_MODEL_ID = "gemini-omni-1.1-flash-preview"
DEFAULT_DAILY_CLIP_BUDGET = 24
MAX_REFERENCE_IMAGES = 6
INTER_CLIP_DELAY_SECONDS = int(os.getenv("OMNI_INTER_CLIP_DELAY_SECONDS", "5"))

_DATA_IMAGE_RE = re.compile(
    r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE | re.DOTALL,
)
_PUBLIC_GCS_PREFIX = "https://storage.googleapis.com/"


@dataclass(frozen=True)
class OmniReferenceImage:
    """Browser/GCS image normalised to Omni's documented inline image input."""

    name: str
    mime_type: str
    data: str  # base64 only; no data URI prefix


class OmniPipeline:
    """Generate stateful Omni clips and persist them in GCS for the editor."""

    def __init__(self, scene_repo: SceneRepository):
        self.scene_repo = scene_repo
        self.bucket_name = os.getenv("GCS_RENDER_BUCKET", "").strip()
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip()
        self.omni_model_id = os.getenv("OMNI_MODEL_ID", DEFAULT_OMNI_MODEL_ID)
        self.daily_clip_budget = max(
            1, int(os.getenv("OMNI_DAILY_CLIP_BUDGET", str(DEFAULT_DAILY_CLIP_BUDGET)))
        )
        self._storage_client: Any = None
        self._genai_client: Any = None

    def validate_configuration(self) -> None:
        """Fail before a render rather than silently substituting a demo clip."""
        missing = []
        if not self.project_id:
            missing.append("GOOGLE_CLOUD_PROJECT")
        if not self.bucket_name:
            missing.append("GCS_RENDER_BUCKET")
        if missing:
            raise RuntimeError(
                "REVERIE cannot start the real Omni renderer; missing "
                + ", ".join(missing)
                + ". Configure the Cloud Run environment variables."
            )

    def _get_storage_client(self):
        if self._storage_client is None:
            from google.cloud import storage

            self._storage_client = storage.Client(project=self.project_id or None)
        return self._storage_client

    def _get_genai_client(self):
        """Create a Vertex AI genai client using the project's service account.

        Uses Vertex AI ADC (Application Default Credentials) — no API key needed.
        On Cloud Run the runtime service account provides credentials automatically.
        """
        if self._genai_client is None:
            from google import genai
            from google.genai import types as genai_types

            self._genai_client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
                http_options=genai_types.HttpOptions(
                    headers={"Api-Revision": "2026-05-20"}
                ),
            )
        return self._genai_client

    @staticmethod
    def stable_seed(production_id: str, scene_index: int, attempt: int = 0) -> int:
        """Stable metadata identifier; Omni does not expose a seed control today."""
        raw = f"{production_id}:scene:{scene_index}:attempt:{attempt}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")

    def _count_reserved_clips_today(self) -> int:
        try:
            doc = self.scene_repo.db.collection("system_meta").document("omni_budget").get()
            if doc.exists:
                data = doc.to_dict() or {}
                if data.get("date") == datetime.utcnow().strftime("%Y-%m-%d"):
                    return int(data.get("count", 0))
        except Exception as exc:
            logger.warning("Could not read Omni budget counter: %s", exc)
        return 0

    async def remaining_budget(self) -> int:
        used = await asyncio.to_thread(self._count_reserved_clips_today)
        return max(0, self.daily_clip_budget - used)

    @staticmethod
    def _parse_data_image(data_uri: str) -> OmniReferenceImage:
        match = _DATA_IMAGE_RE.match(data_uri.strip())
        if not match:
            raise ValueError("Character reference must be a PNG, JPEG, or WebP data URI.")
        mime_type = match.group(1).lower()
        encoded = "".join(match.group(2).split())
        raw = base64.b64decode(encoded, validate=False)
        if not raw or len(raw) > 10 * 1024 * 1024:
            raise ValueError("Character reference image must be between 1 byte and 10 MB.")
        return OmniReferenceImage(name="", mime_type=mime_type, data=encoded)

    @staticmethod
    def _gcs_parts(url: str) -> Optional[tuple[str, str]]:
        if url.startswith("gs://"):
            rest = url[len("gs://") :]
        elif url.startswith(_PUBLIC_GCS_PREFIX):
            rest = url[len(_PUBLIC_GCS_PREFIX) :]
        else:
            return None
        if "/" not in rest:
            return None
        return tuple(rest.split("/", 1))  # type: ignore[return-value]

    def _load_reference_asset(self, asset: Dict[str, Any], name: str) -> Optional[OmniReferenceImage]:
        """Use only a labelled image from our GCS bucket as a cast anchor.

        This deliberately refuses arbitrary remote URLs.  It avoids an SSRF
        surface and prevents the UI from claiming an audio/video moodboard is a
        character reference when Omni currently does not support audio references.
        """
        asset_type = str(asset.get("type") or asset.get("asset_type") or "").lower()
        mime_type = str(asset.get("mime_type") or "").lower()
        uri = str(asset.get("url") or asset.get("public_url") or "")
        if asset_type != "image" and not mime_type.startswith("image/"):
            return None
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            return None
        if uri.startswith("data:"):
            reference = self._parse_data_image(uri)
            return OmniReferenceImage(name=name, mime_type=reference.mime_type, data=reference.data)
        parts = self._gcs_parts(uri)
        if not parts:
            return None
        bucket_name, blob_name = parts
        # Uploaded production assets are scoped to the configured render bucket.
        if bucket_name != self.bucket_name:
            return None
        raw = self._get_storage_client().bucket(bucket_name).blob(blob_name).download_as_bytes()
        if not raw or len(raw) > 10 * 1024 * 1024:
            return None
        return OmniReferenceImage(
            name=name,
            mime_type=mime_type,
            data=base64.b64encode(raw).decode("ascii"),
        )

    async def prepare_character_references(
        self, characters: Iterable[Dict[str, Any]]
    ) -> Dict[str, OmniReferenceImage]:
        """Resolve exactly one image anchor per named character.

        The per-character image picker wins.  An uploaded asset is considered
        only when its label exactly matches the character name.  That keeps the
        cast lock deterministic and makes the UI's promise true.
        """
        resolved: Dict[str, OmniReferenceImage] = {}
        for character in characters:
            name = str(character.get("name") or "").strip()
            if not name:
                continue
            data_uri = str(character.get("reference_image_base64") or "").strip()
            if data_uri:
                reference = self._parse_data_image(data_uri)
                resolved[name] = OmniReferenceImage(name, reference.mime_type, reference.data)
                continue

            for asset in character.get("reference_asset_urls") or []:
                if not isinstance(asset, dict):
                    continue
                if str(asset.get("label") or "").strip().casefold() != name.casefold():
                    continue
                reference = await asyncio.to_thread(self._load_reference_asset, asset, name)
                if reference:
                    resolved[name] = reference
                    break
        return resolved

    async def prepare_scene_asset_references(
        self, characters: Iterable[Dict[str, Any]]
    ) -> Dict[str, OmniReferenceImage]:
        """Index every uploaded image asset by its label, for per-scene attachment.

        ``prepare_character_references`` deliberately resolves only assets whose
        label matches a cast member, because that is what a cast lock means. The
        script editor additionally lets a user attach a location plate, prop, or
        product shot to one specific scene, and those labels are not character
        names. Both paths share the same loader, so the SSRF and bucket-scoping
        rules still apply: an arbitrary remote URL is never fetched.
        """
        resolved: Dict[str, OmniReferenceImage] = {}
        for character in characters:
            for asset in character.get("reference_asset_urls") or []:
                if not isinstance(asset, dict):
                    continue
                label = str(asset.get("label") or "").strip()
                if not label or label in resolved:
                    continue
                try:
                    reference = await asyncio.to_thread(self._load_reference_asset, asset, label)
                except Exception as exc:
                    logger.warning("Could not load scene asset %r: %s", label, exc)
                    continue
                if reference:
                    resolved[label] = reference
        return resolved

    async def reserve_omni_budget(
        self,
        scene_id: str,
        *,
        characters_involved: Optional[List[str]] = None,
        # None means "the writer supplied no tension figure for this beat".
        # It is stored as None rather than coerced to 0.0, so the UI can omit the
        # value instead of displaying a confident-looking 0%.
        drama_score: Optional[float] = None,
        omni_prompt: str = "",
        duration_seconds: int = OMNI_CLIP_DURATION_SECONDS,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        seed: Optional[int] = None,
        previous_interaction_id: str = "",
        anchor_names: Optional[List[str]] = None,
        scene_asset_labels: Optional[List[str]] = None,
        generation_attempt: int = 1,
        production_id: str = "",
        scene_index: int = 0,
        expected_scene_count: int = 0,
    ) -> SceneRecord:
        """Reserve an Omni generation atomically before issuing the API call."""
        if duration_seconds != OMNI_CLIP_DURATION_SECONDS:
            raise ValueError(
                f"REVERIE's Omni continuity workflow uses {OMNI_CLIP_DURATION_SECONDS}-second clips; "
                f"got {duration_seconds}."
            )
        if aspect_ratio not in {"16:9", "9:16"}:
            raise ValueError("Omni aspect ratio must be 16:9 or 9:16.")
        involved = list(characters_involved or [])
        if len(involved) > MAX_REFERENCE_IMAGES:
            raise ValueError(
                f"An Omni shot can use at most {MAX_REFERENCE_IMAGES} image references."
            )

        # Clamp only a real figure. Coercing an absent value to 0.0 (as the
        # previous signature did) makes "no tension was scored" indistinguishable
        # from "this beat is genuinely flat".
        tension: Optional[float] = None
        if drama_score is not None:
            try:
                tension = max(0.0, min(1.0, float(drama_score)))
            except (TypeError, ValueError):
                tension = None

        scene = SceneRecord(
            scene_id=scene_id,
            characters_involved=involved,
            drama_score=tension,
            omni_prompt=omni_prompt,
            video_uri="",
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            status="queued",
            seed=seed,
            previous_interaction_id=previous_interaction_id,
            anchor_names=list(anchor_names or []),
            scene_asset_labels=list(scene_asset_labels or []),
            generation_attempt=generation_attempt,
            production_id=production_id,
            scene_index=scene_index,
            expected_scene_count=expected_scene_count,
        )
        return await self.scene_repo.reserve_omni_budget(
            scene_id, scene, daily_limit=self.daily_clip_budget
        )

    async def generate_clip(
        self,
        scene: SceneRecord,
        *,
        reference_images: Optional[List[OmniReferenceImage]] = None,
        previous_interaction_id: Optional[str] = None,
    ) -> str:
        """Create one clip and retain the interaction ID for the next shot.

        The scene remains ``rendering`` until the director accepts it.  That
        prevents the screening room from presenting an unreviewed generation as
        a finished scene.
        """
        with trace_span("omni_generate_clip", {"scene_id": scene.scene_id}):
            scene.status = "rendering"
            self.scene_repo.save(scene.scene_id, scene)
            previous_id = previous_interaction_id if previous_interaction_id is not None else scene.previous_interaction_id
            references = list(reference_images or [])[:MAX_REFERENCE_IMAGES]
            # One budget reservation authorizes one model call. Retrying inside
            # this method used to make as many as three billable Omni calls while
            # decrementing the budget only once. The Studio Engine performs a
            # bounded, separately-reserved retake instead.
            try:
                video_bytes, interaction_id, chain_used = await self._call_omni_api(
                    prompt=scene.omni_prompt,
                    aspect_ratio=scene.aspect_ratio,
                    references=references,
                    previous_interaction_id=previous_id or None,
                )
                scene.actual_duration_seconds = self._validate_clip_duration(video_bytes)
                blob_name = f"renders/{scene.scene_id}.mp4"
                blob = self._get_storage_client().bucket(self.bucket_name).blob(blob_name)
                blob.upload_from_string(video_bytes, content_type="video/mp4")
                scene.storage_uri = f"gs://{self.bucket_name}/{blob_name}"
                scene.video_uri = f"{_PUBLIC_GCS_PREFIX}{self.bucket_name}/{blob_name}"
                scene.omni_interaction_id = interaction_id
                # Only true when the renderer accepted the parent interaction.
                # The UI reads this instead of inferring a chain from a
                # non-empty parent field, which is set before the call is made.
                scene.stateful_chain_verified = bool(chain_used and previous_id)
                self.scene_repo.save(scene.scene_id, scene)
                logger.info(
                    "[Omni] Clip ready for review scene=%s interaction=%s chained=%s duration=%.2fs",
                    scene.scene_id,
                    interaction_id or "(none returned)",
                    scene.stateful_chain_verified,
                    scene.actual_duration_seconds,
                )
                return scene.video_uri
            except Exception as exc:
                scene.status = "failed"
                scene.failure_reason = str(exc)[:1000]
                self.scene_repo.save(scene.scene_id, scene)
                raise RuntimeError(f"Omni generation failed for {scene.scene_id}: {exc}") from exc

    async def _call_omni_api(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        references: List[OmniReferenceImage],
        previous_interaction_id: Optional[str],
    ) -> tuple[bytes, str, bool]:
        """Use Omni's documented stateful interactions API.

        First shot: text prompt (+ optional image references).
        Following shots: the accepted ``previous_interaction_id`` carries the
        model's prior video state forward.

        Returns ``(video_bytes, interaction_id, chain_used)``. ``chain_used`` is
        True only when the API actually accepted the parent interaction. The
        previous build silently dropped the parent while the schema and UI still
        advertised a verified stateful chain; continuity then rested entirely on
        the text prompt ledger without saying so. When the parent is rejected we
        retry once without it and report the downgrade instead of hiding it.
        """
        if not prompt.strip():
            raise ValueError("Cannot render an empty Omni prompt.")
        client = self._get_genai_client()

        # Build the input list that Omni expects.
        # Structure mirrors the user's working SDK sample:
        #   input=[{"type": "image", ...}, {"type": "text", "text": "..."}]
        # Two input shapes are built up front, because the chained attempt may be
        # rejected and the fallback must still carry the cast-lock images. Sending
        # the chained text-only payload unchained would quietly drop every subject
        # reference and break the identity anchor this pipeline exists to protect.
        def _fresh_parts() -> List[Dict[str, Any]]:
            """Self-contained input: subject references first, then the prompt."""
            if not references:
                return [{"type": "text", "text": prompt}]
            identity_lines = "\n".join(
                f"- {ref.name} is image #{index + 1}" for index, ref in enumerate(references)
            )
            tagged_prompt = (
                "Use the supplied image(s) as subject references - preserve these identities "
                "exactly, do not merge or redesign them.\n"
                f"Cast map:\n{identity_lines}\n\n{prompt}"
            )
            parts: List[Dict[str, Any]] = [
                {"type": "image", "data": ref.data, "mime_type": ref.mime_type}
                for ref in references
            ]
            parts.append({"type": "text", "text": tagged_prompt})
            return parts

        fresh_parts = _fresh_parts()
        if previous_interaction_id:
            # Continuing shot: Omni inherits visual state from the accepted prior
            # interaction, so the instruction alone is enough.
            continuation_text = (
                "Create the next distinct 10-second shot in this film. "
                "Preserve all established character identities, wardrobe, props, "
                "lighting logic, and audio identity unless this instruction explicitly "
                "changes them. Single continuous shot; no montage.\n\n" + prompt
            )
            chained_parts: List[Dict[str, Any]] = [
                {"type": "text", "text": continuation_text}
            ]
        else:
            chained_parts = fresh_parts

        def _omni_create_with_retry(model: str, **kwargs) -> tuple[Any, str]:
            """Retry on 429 with backoff until quota resets."""
            import time as _time
            for attempt in range(3):
                try:
                    return client.interactions.create(model=model, **kwargs), model
                except Exception as exc:
                    msg = str(exc)
                    is_quota = "429" in msg or "quota" in msg.lower() or "too_many_requests" in msg.lower()
                    if is_quota and attempt < 2:
                        wait = 65 * (attempt + 1)
                        logger.warning("[Omni] 429 attempt %s — waiting %ss for quota reset", attempt + 1, wait)
                        _time.sleep(wait)
                        continue
                    raise

        def _generate() -> tuple[bytes, str, bool]:
            logger.info(
                "[Omni] interactions.create model=%s references=%s aspect=%s parent=%s",
                self.omni_model_id,
                len(references),
                aspect_ratio,
                previous_interaction_id or "none",
            )
            chain_used = False
            interaction = None
            model_used = self.omni_model_id

            if previous_interaction_id:
                # Try the real stateful path first. Not every SDK build and
                # backend combination exposes it, so a rejection must degrade
                # visibly rather than being swallowed.
                try:
                    interaction, model_used = _omni_create_with_retry(
                        self.omni_model_id,
                        input=chained_parts,
                        previous_interaction_id=previous_interaction_id,
                    )
                    chain_used = True
                except TypeError as exc:
                    # The installed SDK has no such parameter.
                    logger.warning(
                        "[Omni] SDK does not accept previous_interaction_id (%s); "
                        "continuing from the prompt ledger only.",
                        exc,
                    )
                except Exception as exc:
                    # The backend rejected the parent (expired, unknown, or
                    # unsupported on this surface). Retry unchained below.
                    logger.warning(
                        "[Omni] Backend rejected parent interaction %s (%s); "
                        "continuing from the prompt ledger only.",
                        previous_interaction_id,
                        exc,
                    )

            if interaction is None:
                # Unchained fallback: use the self-contained payload so the
                # cast-lock reference images are still sent.
                interaction, model_used = _omni_create_with_retry(
                    self.omni_model_id,
                    input=fresh_parts,
                )
            if model_used != self.omni_model_id:
                logger.info("[Omni] Clip rendered with fallback model %s", model_used)

            # An absent id must stay empty: a placeholder like "unknown" would be
            # stored as this shot's interaction id and then handed to the next
            # shot as its parent, fabricating a chain link that never existed.
            interaction_id = str(getattr(interaction, "id", "") or "")
            raw = self._extract_video_bytes(client, interaction)
            return raw, interaction_id, chain_used

        return await asyncio.get_running_loop().run_in_executor(None, _generate)

    @staticmethod
    def _value(value: Any, key: str, default: Any = None) -> Any:
        """Read an SDK response field from either an object or a raw dict."""
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _extract_video_bytes(self, client: Any, interaction: Any) -> bytes:
        """Extract video bytes from an Omni interaction response.

        The SDK response shape follows the user-validated working code:
        iterate ``interaction.steps``, find a step with type == 'model_output',
        then find a part with type == 'video'. The part contains either inline
        base64 ``data`` or a ``uri`` pointing to the Files API.

        A top-level ``output_video`` field is also checked first for forward
        compatibility with future SDK shapes.
        """
        # Fast path: some SDK versions surface output_video at the top level.
        output_video = self._value(interaction, "output_video")
        if output_video:
            inline_data = self._value(output_video, "data")
            if inline_data:
                return base64.b64decode(inline_data)
            uri = self._value(output_video, "uri")
            if uri:
                return self._download_omni_file(client, str(uri))

        # Primary path: iterate steps as shown in the user's working code sample.
        # step.get('type') == 'model_output' and step.get('content') contains parts.
        steps = getattr(interaction, "steps", None)
        if steps is None:
            # Some SDK versions return steps as a dict key.
            steps = self._value(interaction, "steps") or []
        for step in steps:
            # Normalise to dict — works for both dict and SDK object steps.
            if isinstance(step, dict):
                step_data = step
            else:
                step_data = (
                    step.model_dump() if hasattr(step, "model_dump")
                    else getattr(step, "__dict__", {})
                )
            if step_data.get("type") != "model_output":
                continue
            content = step_data.get("content") or []
            for part in content:
                if not isinstance(part, dict):
                    try:
                        part = part.model_dump() if hasattr(part, "model_dump") else vars(part)
                    except Exception:
                        continue
                if part.get("type") != "video":
                    continue
                mime_type = part.get("mime_type", "video/mp4")
                video_b64 = part.get("data")
                if video_b64:
                    return base64.b64decode(video_b64)
                uri = part.get("uri")
                if uri:
                    return self._download_omni_file(client, str(uri))

        raise RuntimeError("Omni response contained no video data or retrievable URI.")

    @staticmethod
    def _validate_clip_duration(video_bytes: bytes) -> float:
        """Check the duration of the returned MP4. Returns duration in seconds.

        If ffprobe is unavailable or the clip is out of range, logs a warning
        and returns a best-effort value rather than hard-failing the render —
        Vertex Omni may return slightly shorter clips and we don't want to
        discard good video on a timing edge case.
        """
        if not video_bytes:
            raise RuntimeError("Omni returned an empty video response.")
        path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as handle:
                handle.write(video_bytes)
                path = handle.name
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            duration = float(result.stdout.strip())
        except FileNotFoundError:
            # ffprobe not installed — skip duration check, return assumed duration
            logger.warning("ffprobe not found; skipping clip duration validation.")
            return float(OMNI_CLIP_DURATION_SECONDS)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            logger.warning("Could not verify Omni MP4 duration: %s", exc)
            return float(OMNI_CLIP_DURATION_SECONDS)
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        if not MIN_ACCEPTED_CLIP_SECONDS <= duration <= MAX_ACCEPTED_CLIP_SECONDS:
            logger.warning(
                "Omni returned a %.2fs clip (accepted range %.1f–%.1fs). "
                "Keeping clip — out-of-range duration logged only.",
                duration, MIN_ACCEPTED_CLIP_SECONDS, MAX_ACCEPTED_CLIP_SECONDS,
            )
        return duration

    @staticmethod
    def _file_name_from_uri(uri: str) -> str:
        match = re.search(r"(?:^|/)files/([^/?#:]+)", uri)
        if match:
            return f"files/{match.group(1)}"
        if uri.startswith("files/"):
            return uri.split("?", 1)[0]
        raise RuntimeError(f"Could not derive an Omni Files API name from {uri!r}")

    def _download_omni_file(self, client: Any, uri: str) -> bytes:
        name = self._file_name_from_uri(uri)
        deadline = time.monotonic() + 15 * 60
        while True:
            file_info = client.files.get(name=name)
            state = getattr(file_info, "state", "")
            state_name = str(getattr(state, "name", state)).upper()
            if state_name == "ACTIVE":
                break
            if state_name == "FAILED":
                raise RuntimeError(f"Omni file {name} failed processing.")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for Omni file {name} to become ACTIVE.")
            time.sleep(5)

        try:
            downloaded = client.files.download(file=uri)
        except Exception:
            downloaded = client.files.download(file=file_info)
        if isinstance(downloaded, bytes):
            return downloaded
        if isinstance(downloaded, bytearray):
            return bytes(downloaded)
        # Some SDK versions return a response object with bytes/content.
        content = getattr(downloaded, "content", None) or getattr(downloaded, "data", None)
        if isinstance(content, bytes):
            return content
        raise RuntimeError("Omni Files API download returned an unsupported response type.")
