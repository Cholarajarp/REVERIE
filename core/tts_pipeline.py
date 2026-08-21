"""
Cloud Text-to-Speech pipeline for character dialogue.

NOTE: The active REVERIE studio path (StudioEngine + OmniPipeline) does NOT
call this module. Gemini Omni Flash generates video with native character
voices and ambient audio already baked into every MP4 clip. Cloud TTS was
used by the legacy SimulationEngine path and is kept for reference only.

If you see "TTS synthesis failed" warnings in logs, those come from the
legacy /start_simulation endpoint (SimulationEngine), not from the Studio.
The Studio's /api/studio/render_movie route uses Omni for both video and
audio — no separate TTS call is made.
"""

import os
import asyncio
from typing import Optional

from core.logger import get_logger, trace_span

logger = get_logger(__name__)


class TTSPipeline:
    """Synthesizes character dialogue into audio via Google Cloud TTS."""

    def __init__(self):
        self._tts_client = None
        self._storage_client = None
        self.bucket_name = os.getenv("GCS_RENDER_BUCKET", "").strip()

    def _get_tts_client(self):
        """Lazily initialise the Cloud TTS client."""
        if self._tts_client is None:
            from google.cloud import texttospeech_v1 as texttospeech
            self._tts_client = texttospeech.TextToSpeechClient()
        return self._tts_client

    def _get_storage_client(self):
        if self._storage_client is None:
            from google.cloud import storage
            self._storage_client = storage.Client()
        return self._storage_client

    async def synthesize_dialogue(
        self,
        text: str,
        voice_id: str,
        scene_id: str,
        character_name: str,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
    ) -> str:
        """
        Synthesize character dialogue into audio.

        Args:
            text: The dialogue text to speak.
            voice_id: Google Cloud TTS voice name (e.g., "en-US-Studio-O").
            scene_id: Scene identifier for file naming.
            character_name: Character name for file naming.
            speaking_rate: Speed of speech (0.25 to 4.0, default 1.0).
            pitch: Pitch adjustment in semitones (-20.0 to 20.0, default 0.0).

        Returns:
            Signed URL to the audio file in GCS.
        """
        with trace_span("tts_synthesize", {
            "scene_id": scene_id,
            "character": character_name,
            "voice": voice_id,
            "text_length": len(text),
        }):
            if not self.bucket_name:
                raise RuntimeError("GCS_RENDER_BUCKET is required for Cloud TTS delivery.")

            try:
                audio_bytes = await self._call_tts_api(
                    text=text,
                    voice_id=voice_id,
                    speaking_rate=speaking_rate,
                    pitch=pitch,
                )

                # Upload to GCS
                safe_name = character_name.lower().replace(" ", "_")
                blob_name = f"audio/{scene_id}/{safe_name}.mp3"

                storage_client = self._get_storage_client()
                bucket = storage_client.bucket(self.bucket_name)
                blob = bucket.blob(blob_name)
                blob.upload_from_string(audio_bytes, content_type="audio/mpeg")

                # Public URL — bucket must have allUsers objectViewer IAM binding.
                # Signed URLs require a service-account key which is not available
                # on Cloud Run's Compute Engine identity; skip them entirely.
                public_url = f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"

                logger.info(
                    f"TTS synthesis complete for {character_name} in scene {scene_id}: "
                    f"{len(audio_bytes)} bytes, voice={voice_id}"
                )
                return public_url

            except Exception as e:
                logger.error(f"TTS synthesis failed for {character_name}: {e}")
                raise

    async def _call_tts_api(
        self,
        text: str,
        voice_id: str,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
    ) -> bytes:
        """
        Calls Google Cloud Text-to-Speech API.

        Returns raw MP3 audio bytes.
        """
        from google.cloud import texttospeech_v1 as texttospeech

        client = self._get_tts_client()

        # Parse language code from voice_id (e.g., "en-US-Studio-O" → "en-US")
        parts = voice_id.split("-")
        language_code = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else "en-US"

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_id,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
            pitch=pitch,
            # Use highest quality available
            effects_profile_id=["headphone-class-device"],
        )

        # Run synchronous client call in executor for async compatibility
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            ),
        )

        logger.info(f"TTS API returned {len(response.audio_content)} bytes for voice {voice_id}")
        return response.audio_content

    async def synthesize_scene_dialogue(
        self,
        dialogues: list[dict],
        scene_id: str,
    ) -> list[dict]:
        """
        Synthesize all character dialogues for a scene in parallel.

        Args:
            dialogues: List of dicts with keys: character_name, text, voice_id
            scene_id: Scene identifier.

        Returns:
            List of dicts with keys: character_name, audio_url, text
        """
        if not dialogues:
            return []

        tasks = []
        for d in dialogues:
            tasks.append(
                self.synthesize_dialogue(
                    text=d["text"],
                    voice_id=d.get("voice_id", "en-US-Studio-O"),
                    scene_id=scene_id,
                    character_name=d["character_name"],
                )
            )

        audio_urls = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for d, url in zip(dialogues, audio_urls):
            if isinstance(url, Exception):
                logger.error(f"TTS failed for {d['character_name']}: {url}")
                results.append({
                    "character_name": d["character_name"],
                    "text": d["text"],
                    "audio_url": None,
                    "error": str(url),
                })
            else:
                results.append({
                    "character_name": d["character_name"],
                    "text": d["text"],
                    "audio_url": url,
                })

        return results
