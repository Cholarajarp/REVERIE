"""REVERIE's continuity-first, agentic Gemini Omni Flash production harness."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from google.api_core.exceptions import ResourceExhausted
from vertexai.generative_models import GenerativeModel

from agents.ads_agent import AdsSpecialistAgent, is_ad_style
from agents.character_agent import CharacterAgent
from agents.cinematographer_agent import CinematographerAgent
from agents.director_agent import DirectorAgent
from core.audience_sync import audience_sync_manager
from core.logger import get_logger
from core.omni_pipeline import (
    INTER_CLIP_DELAY_SECONDS,
    MAX_REFERENCE_IMAGES,
    OMNI_CLIP_DURATION_SECONDS,
    OmniPipeline,
    OmniReferenceImage,
)
from core.video_editor import VideoEditor
from models.schema import CharacterState, WorldState

logger = get_logger(__name__)


class StudioEngine:
    """Turns an idea into an accepted chain of Omni video states.

    The pipeline enforces the product's central claim:

    ``characters remember -> writers plan -> cinematographer locks a visual
    bible -> Omni carries the accepted interaction state -> director approves
    before the editor concatenates``.

    Each phase records an artifact.  No generated clip is called part of the
    film until the Director's visual critic has accepted it.
    """

    def __init__(
        self,
        cinematographer: CinematographerAgent,
        omni: OmniPipeline,
        editor: VideoEditor,
        scene_repo: Any,
        director: Optional[DirectorAgent] = None,
    ):
        self.cinematographer = cinematographer
        self.omni = omni
        self.editor = editor
        self.scene_repo = scene_repo
        self.director = director or DirectorAgent()
        self.ads = AdsSpecialistAgent()
        self.model = GenerativeModel("gemini-3.5-flash")
        # Cumulative token count across the full production run (table-read +
        # screenwriter + director critique). Reset at the start of each render.
        self._total_tokens_burned: int = 0
        self.max_retries_per_film = max(
            0, int(os.getenv("MAX_CONTINUITY_RETAKES_PER_FILM", "4"))
        )
        self.allow_partial_films = os.getenv("ALLOW_PARTIAL_FILMS", "false").lower() == "true"
        self.require_character_references = (
            os.getenv("REQUIRE_CHARACTER_REFERENCES", "false").lower() == "true"
        )
        # How the Director's visual continuity gate behaves. The previous build
        # hard-coded an auto-approval while the UI claimed every shot was
        # director-approved, so a clip that merely rendered was presented as
        # reviewed evidence of character continuity.
        #
        #   enforce  - a shot joins the film only after the critic passes it.
        #   advisory - the critic runs and its verdict is recorded, but a clip
        #              it could not verify is kept and labelled 'unverified'.
        #   off      - no critic call at all; every shot is labelled
        #              'review_disabled'. Cheapest, and honest about it.
        #
        # Default is advisory: the critic is a multimodal call that can hit 429
        # quota mid-render, and silently failing a whole film on a quota blip is
        # worse than labelling a shot unverified. Nothing is ever labelled
        # approved without a real verdict.
        mode = os.getenv("CONTINUITY_REVIEW_MODE", "advisory").strip().lower()
        if mode not in {"enforce", "advisory", "off"}:
            logger.warning("Unknown CONTINUITY_REVIEW_MODE %r; falling back to advisory.", mode)
            mode = "advisory"
        self.review_mode = mode

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def generate_movie(
        self,
        characters: List[Dict[str, Any]],
        premise: str,
        video_duration: str = "10s",
        film_duration_minutes: int = 1,
        aspect_ratio: str = "16:9",
        visual_style: str = "cinematic",
        brand: str = "",
    ) -> str:
        """Legacy endpoint: run pre-production followed by the Omni harness."""
        result = await self.simulate_script(
            characters=characters,
            premise=premise,
            video_duration=video_duration,
            film_duration_minutes=film_duration_minutes,
            aspect_ratio=aspect_ratio,
            visual_style=visual_style,
            brand=brand,
            simulation_ticks=1,
        )
        if result.get("status") != "success" or not result.get("script"):
            raise RuntimeError(result.get("detail") or "Screenplay generation failed.")
        return await self.render_movie(result)

    async def simulate_script(
        self,
        characters: List[Dict[str, Any]],
        premise: str,
        video_duration: str = "10s",
        film_duration_minutes: int = 1,
        aspect_ratio: str = "16:9",
        visual_style: str = "cinematic",
        brand: str = "",
        simulation_ticks: int = 1,
    ) -> Dict[str, Any]:
        """Run a table read then generate an exact shot list + continuity ledger.

        ``brand`` is the client-supplied product or brand name. It is only
        meaningful for ad styles, where it is handed to the Ads Specialist as a
        hint so the brief names the real product instead of inferring one.
        """
        clean_characters = self._validate_characters(characters)
        if not clean_characters:
            return {"status": "error", "detail": "Add at least one named character."}
        if aspect_ratio not in {"16:9", "9:16"}:
            return {"status": "error", "detail": "Aspect ratio must be 16:9 or 9:16."}

        try:
            requested_clip_duration = int(str(video_duration).lower().replace("s", "").strip())
            if requested_clip_duration != OMNI_CLIP_DURATION_SECONDS:
                raise ValueError(
                    f"The Omni continuity harness renders {OMNI_CLIP_DURATION_SECONDS}-second clips. "
                    "This keeps the stateful shot plan and final edit honest."
                )
            raw = int(film_duration_minutes)
            if is_ad_style(visual_style):
                # For ads the UI sends duration in SECONDS (20 or 40).
                # Accept any value >= 10 seconds.
                if raw < 10:
                    raise ValueError("Ad duration must be at least 10 seconds.")
                target_duration_seconds = raw
            else:
                # Drama films: value is in minutes, minimum 1.
                if raw < 1:
                    raise ValueError("Film duration must be at least one minute.")
                target_duration_seconds = raw * 60
        except (TypeError, ValueError) as exc:
            return {"status": "error", "detail": str(exc)}

        total_clips = math.ceil(target_duration_seconds / OMNI_CLIP_DURATION_SECONDS)
        # Minimum 1 clip — a 20s ad = 2 clips, a 40s ad = 4 clips
        total_clips = max(1, total_clips)
        if total_clips > self.omni.daily_clip_budget:
            max_seconds = self.omni.daily_clip_budget * OMNI_CLIP_DURATION_SECONDS
            return {
                "status": "error",
                "detail": (
                    f"This production needs {total_clips} Omni clips, but only "
                    f"{self.omni.daily_clip_budget} are available today. "
                    f"Maximum runtime is {max_seconds} seconds ({max_seconds // 60} minutes)."
                ),
            }

        logger.info(
            "Starting living-film pre-production: %s scenes, %s cast members",
            total_clips,
            len(clean_characters),
        )
        character_agents: List[CharacterAgent] = []
        for character in clean_characters:
            state = CharacterState(
                name=character["name"],
                current_location=character.get("current_location", "Town Square"),
                current_goal=character.get("current_goal", premise),
                mood=character.get("mood", "neutral"),
                memory_stream=character.get("memory_stream") or [f"Starting premise: {premise}"],
                visual_description=character.get("visual_description", ""),
            )
            character_agents.append(
                CharacterAgent(state, character.get("personality_description", ""))
            )

        world_state = WorldState(
            current_time=datetime.utcnow(),
            weather="Overcast",
            active_characters=[character["name"] for character in clean_characters],
            location_populations={"Town Square": len(clean_characters)},
        )
        await self._run_table_read(character_agents, world_state, simulation_ticks)

        history_lines: List[str] = []
        for agent in character_agents:
            history_lines.append(f"=== {agent.state.name} ===")
            history_lines.extend(agent.state.memory_stream[-8:])

        production_id = self._production_id(clean_characters, premise, target_duration_seconds // 60 or 1, visual_style)

        # An advertisement is not a short drama. When the requested style is a
        # commercial, the Ads Specialist plans it against the persuasive arc and
        # runs a claim-compliance pass, instead of the drama screenwriter
        # improvising conflict that a brand cannot air.
        campaign_brief: Optional[Dict[str, Any]] = None
        planner_report: Dict[str, Any] = {"planner": "screenwriter"}
        if is_ad_style(visual_style):
            campaign_brief = await self.ads.build_campaign_brief(
                premise=premise,
                characters=clean_characters,
                total_clips=total_clips,
                clip_duration=OMNI_CLIP_DURATION_SECONDS,
                brand_hint=str(brand or "").strip(),
            )
            script, planner_report = await self.ads.generate_ad_shot_list(
                brief=campaign_brief,
                premise=premise,
                characters=clean_characters,
                history="\n".join(history_lines),
                total_clips=total_clips,
                clip_duration=OMNI_CLIP_DURATION_SECONDS,
            )
            # Ad shot lists still pass the shared validator: an ad may legitimately
            # have product-only shots with no cast, which the drama path forbids.
            normalised = [
                self._normalise_scene(
                    scene,
                    {character["name"] for character in clean_characters},
                    allow_empty_cast=True,
                )
                for scene in script
            ]
            script = [scene for scene in normalised if scene is not None]
        else:
            script = await self._generate_script_from_history(
                characters=clean_characters,
                premise=premise,
                history="\n".join(history_lines),
                total_clips=total_clips,
                clip_duration=OMNI_CLIP_DURATION_SECONDS,
            )

        if len(script) != total_clips:
            return {
                "status": "error",
                "detail": (
                    "The ads specialist could not produce a valid exact-length shot list. Please retry."
                    if campaign_brief is not None
                    else "The screenwriter could not produce a valid exact-length shot list. Please retry."
                ),
            }

        return {
            "status": "success",
            "production_id": production_id,
            "script": script,
            "campaign_brief": campaign_brief,
            "planner_report": planner_report,
            "settings": {
                "video_duration": f"{OMNI_CLIP_DURATION_SECONDS}s",
                "duration_seconds": OMNI_CLIP_DURATION_SECONDS,
                "film_duration_minutes": raw,
                "target_duration_seconds": target_duration_seconds,
                "aspect_ratio": aspect_ratio,
                "visual_style": visual_style,
                "continuity_mode": "omni_stateful_chain",
            },
            "characters": clean_characters,
        }

    async def render_movie(self, script_data: Dict[str, Any]) -> str:
        """Render a directed, stateful Omni chain and compile its accepted clips."""
        self._total_tokens_burned = 0  # reset for each new production
        script_scenes = script_data.get("script") or []
        settings = script_data.get("settings") or {}
        characters = self._validate_characters(script_data.get("characters") or [])
        if not script_scenes or not characters:
            raise ValueError("A non-empty screenplay and cast are required for rendering.")

        duration_seconds = int(settings.get("duration_seconds", OMNI_CLIP_DURATION_SECONDS))
        if duration_seconds != OMNI_CLIP_DURATION_SECONDS:
            raise ValueError(
                f"Omni continuity renders must use {OMNI_CLIP_DURATION_SECONDS}-second clips."
            )
        target_duration_seconds = int(
            settings.get("target_duration_seconds", int(settings.get("film_duration_minutes", 1)) * 60)
        )
        aspect_ratio = str(settings.get("aspect_ratio", "16:9"))
        if aspect_ratio not in {"16:9", "9:16"}:
            raise ValueError("Omni aspect ratio must be 16:9 or 9:16.")
        visual_style = str(settings.get("visual_style", "cinematic"))

        total_scenes = len(script_scenes)
        remaining_budget = await self.omni.remaining_budget()
        if total_scenes > remaining_budget:
            raise RuntimeError(
                f"This render needs {total_scenes} Omni generations but only {remaining_budget} "
                "daily reservations remain. Shorten the film or wait for quota reset."
            )
        retake_slots = min(self.max_retries_per_film, remaining_budget - total_scenes)

        # Keep the Screening Room focused on this production but DO NOT reset the
        # cost counter. The original app reset it, creating an inaccurate budget.
        try:
            await asyncio.to_thread(self.scene_repo.delete_all)
        except Exception as exc:
            logger.warning("Could not clear previous Screening Room records: %s", exc)

        references_by_character = await self.omni.prepare_character_references(characters)
        # Assets the user attached to individual shots in the script editor
        # (location plates, props, product shots). Indexed by label; a shot may
        # only reference a label that actually resolved to an image.
        scene_assets_by_label = await self.omni.prepare_scene_asset_references(characters)
        unanchored = [c["name"] for c in characters if c["name"] not in references_by_character]
        if self.require_character_references and unanchored:
            raise ValueError(
                "Character Lock is enabled; add a reference image for: " + ", ".join(unanchored)
            )
        if unanchored:
            logger.warning(
                "No explicit image anchor for %s. Omni will use the visual bible and its stateful "
                "interaction chain, but the Director marks these scenes as lower confidence.",
                ", ".join(unanchored),
            )

        self.cinematographer.video_duration = f"{duration_seconds}s"
        self.cinematographer.film_duration_minutes = max(1, math.ceil(target_duration_seconds / 60))
        self.cinematographer.aspect_ratio = aspect_ratio
        self.cinematographer.visual_style = visual_style
        from agents.cinematographer_agent import _sanitise_prompt
        self.cinematographer.set_character_visuals(
            {character["name"]: _sanitise_prompt(character.get("visual_description", "")) for character in characters}
        )

        production_id = str(script_data.get("production_id") or self._production_id(
            characters, "", max(1, target_duration_seconds // 60), visual_style
        ))
        # A screenplay hash is stable, but Firestore scene IDs must not be. Two
        # identical submissions on the same day are separate billable runs and
        # need separate review evidence instead of overwriting each other's shots.
        render_id = f"{production_id[:10]}-{uuid.uuid4().hex[:8]}"
        compiled_assets: List[Dict[str, Any]] = []
        failed_scenes: List[str] = []
        # This is the core continuity state.  It changes only after a Director
        # acceptance, so retakes never poison the following shot's visual memory.
        previous_accepted_interaction_id = ""

        allow_empty_cast = is_ad_style(visual_style)
        for scene_index, raw_scene in enumerate(script_scenes):
            scene_data = self._normalise_scene(
                raw_scene,
                {character["name"] for character in characters},
                allow_empty_cast=allow_empty_cast,
            )
            if scene_data is None:
                failed_scenes.append(f"scene {scene_index + 1}: invalid shot data")
                continue

            scene_started = time.monotonic()
            accepted, asset, retakes_used, accepted_interaction_id = await self._render_and_review_scene(
                production_id=render_id,
                scene_index=scene_index,
                total_scenes=total_scenes,
                scene_data=scene_data,
                character_references=references_by_character,
                scene_asset_references=scene_assets_by_label,
                aspect_ratio=aspect_ratio,
                previous_interaction_id=previous_accepted_interaction_id,
                retake_slots=retake_slots,
            )
            retake_slots -= retakes_used

            # Telemetry reports what actually happened. The previous build sent a
            # synthetic token count, a latency of `120 + time.time() % 50`, and a
            # drama score derived from scene position, so the dashboard was
            # animated decoration rather than observability.
            audience_sync_manager.update_metrics(
                token_burn=self._total_tokens_burned or None,
                tick_latency_ms=round((time.monotonic() - scene_started) * 1000.0, 1),
                drama_score=scene_data.get("tension"),
            )

            # Acceptance and chain state are separate concerns. A clip can be
            # accepted while the renderer returns no interaction id; requiring one
            # here would discard a good shot. Only a real id may become the next
            # shot's parent.
            if accepted and asset:
                compiled_assets.append(asset)
                if accepted_interaction_id:
                    previous_accepted_interaction_id = accepted_interaction_id
                self._apply_continuity_updates(scene_data)
            else:
                failed_scenes.append(f"scene {scene_index + 1}")

            if scene_index < total_scenes - 1 and INTER_CLIP_DELAY_SECONDS > 0:
                await asyncio.sleep(INTER_CLIP_DELAY_SECONDS)

        if failed_scenes and not self.allow_partial_films:
            raise RuntimeError(
                "Film was not compiled because the continuity gate did not approve "
                + ", ".join(failed_scenes)
                + ". Review the failed shots; REVERIE will not present a partial film as complete."
            )
        if not compiled_assets:
            raise RuntimeError("No Omni scene passed render and continuity review.")

        # The screenwriter always produces ceil(runtime / 10) scenes. FFmpeg
        # trims the end of the final accepted clip, making the advertised film
        # duration real instead of silently returning an overlong playlist.
        exact_target = min(target_duration_seconds, len(compiled_assets) * duration_seconds)
        final_movie_url = await self.editor.compile_movie(
            compiled_assets, target_duration_seconds=exact_target
        )
        logger.info("Living film compiled: %s", final_movie_url)
        return final_movie_url

    # ─────────────────────────────────────────────────────────────────────────
    # Render -> critic -> state transition
    # ─────────────────────────────────────────────────────────────────────────

    async def _render_and_review_scene(
        self,
        *,
        production_id: str,
        scene_index: int,
        total_scenes: int,
        scene_data: Dict[str, Any],
        character_references: Dict[str, OmniReferenceImage],
        scene_asset_references: Dict[str, OmniReferenceImage],
        aspect_ratio: str,
        previous_interaction_id: str,
        retake_slots: int,
    ) -> Tuple[bool, Optional[Dict[str, Any]], int, str]:
        """Try a bounded candidate branch without corrupting accepted state."""
        attempts = 2 if retake_slots > 0 else 1
        retakes_used = 0
        involved = scene_data["characters_involved"]
        references = [
            character_references[name] for name in involved if name in character_references
        ]
        # Per-scene attachments follow the cast locks so character identity keeps
        # priority in the reference list, and are capped with them so a shot with
        # several attachments cannot push a cast anchor out of the payload.
        attached_labels: List[str] = []
        for label in scene_data.get("scene_asset_labels") or []:
            reference = scene_asset_references.get(label)
            if reference is None or any(existing.name == label for existing in references):
                continue
            if len(references) >= MAX_REFERENCE_IMAGES:
                logger.warning(
                    "Scene attachment %r dropped: %s reference slots already used.",
                    label,
                    MAX_REFERENCE_IMAGES,
                )
                break
            references.append(reference)
            attached_labels.append(label)

        for attempt in range(attempts):
            # Observability is a real control loop, not a dashboard ornament:
            # check before reserving a billable generation. A throttled result
            # stops the production with zero additional Omni spend.
            health = await self.director.get_system_health()
            if str(health.get("status", "healthy")).lower() == "throttled":
                reason = str(health.get("reason") or "Grafana health gate is throttled.")
                raise RuntimeError(
                    "Rendering paused by the Grafana health gate before Omni generation: " + reason
                )

            prompt = await self.cinematographer.generate_omni_prompt(
                drama_beat=scene_data["drama_beat"],
                characters_involved=involved,
                location=scene_data["location"],
                dialogues=scene_data["dialogues"],
                continuity=scene_data.get("continuity") or {},
                critique_feedback=str(scene_data.get("last_critique") or ""),
            )
            scene_id = f"{production_id[:10]}-s{scene_index + 1:02d}-a{attempt + 1}"
            scene_record = await self.omni.reserve_omni_budget(
                scene_id,
                characters_involved=involved,
                # The writer's judgement of THIS beat, not its position in the
                # list. None when the writer gave no figure, so the Screening
                # Room omits the number instead of inventing one.
                drama_score=scene_data.get("tension"),
                omni_prompt=prompt,
                duration_seconds=OMNI_CLIP_DURATION_SECONDS,
                aspect_ratio=aspect_ratio,
                resolution="720p",
                seed=self.omni.stable_seed(production_id, scene_index, attempt),
                previous_interaction_id=previous_interaction_id,
                anchor_names=[reference.name for reference in references],
                scene_asset_labels=attached_labels,
                generation_attempt=attempt + 1,
                production_id=production_id,
                scene_index=scene_index + 1,
                expected_scene_count=total_scenes,
            )
            try:
                video_uri = await self.omni.generate_clip(
                    scene_record,
                    reference_images=references,
                    previous_interaction_id=previous_interaction_id,
                )
            except Exception as exc:
                logger.error("Omni scene %s failed: %s", scene_id, exc)
                scene_data["last_critique"] = str(exc)
                if attempt < attempts - 1:
                    retakes_used += 1
                    continue
                return False, None, retakes_used, ""

            # The continuity gate. A rendered clip is not yet part of the film:
            # what makes REVERIE's claim real is that a critic looked at it.
            accepted, verdict = await self._review_rendered_scene(
                scene_record, video_uri, scene_data
            )
            scene_record.continuity_score = verdict["continuity_score"]
            scene_record.critique = verdict["critique"][:1000]
            scene_record.review_mode = verdict["review_mode"]

            if not accepted:
                # Rejected candidates are recorded as failed so the Screening
                # Room can show why a shot did not make the film, instead of
                # the evidence disappearing.
                scene_record.status = "failed"
                scene_record.failure_reason = verdict["critique"][:1000]
                self.scene_repo.save(scene_record.scene_id, scene_record)
                logger.warning(
                    "Scene %s rejected by the continuity gate: %s", scene_id, verdict["critique"]
                )
                scene_data["last_critique"] = verdict.get("revised_prompt") or verdict["critique"]
                if attempt < attempts - 1:
                    retakes_used += 1
                    continue
                return False, None, retakes_used, ""

            scene_record.status = "critiqued"
            self.scene_repo.save(scene_record.scene_id, scene_record)
            logger.info(
                "Scene %s accepted (%s, continuity=%.2f).",
                scene_id,
                verdict["review_mode"],
                verdict["continuity_score"],
            )
            return (
                True,
                {
                    "video_uri": video_uri,
                    "storage_uri": scene_record.storage_uri,
                    "duration": scene_record.actual_duration_seconds
                    or OMNI_CLIP_DURATION_SECONDS,
                },
                retakes_used,
                # Only a real Omni interaction id may become the next shot's
                # parent. Falling back to the scene id here (as the previous
                # build did) fabricated a parent that the renderer had never
                # issued, which is what made the stateful-chain badge a lie.
                scene_record.omni_interaction_id,
            )

        return False, None, retakes_used, ""

    async def _review_rendered_scene(
        self,
        scene_record: Any,
        video_uri: str,
        scene_data: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        """Run the Director's visual gate and report how the shot was judged.

        Returns ``(accepted, verdict)``. The verdict always carries a
        ``review_mode`` so no caller can present an unreviewed clip as
        director-approved.
        """
        if self.review_mode == "off":
            return True, {
                "continuity_score": None,
                "critique": "Continuity review disabled for this run (CONTINUITY_REVIEW_MODE=off).",
                "review_mode": "review_disabled",
                "revised_prompt": "",
            }

        expected = {
            "location": scene_data.get("location"),
            "drama_beat": scene_data.get("drama_beat"),
            "characters_involved": scene_data.get("characters_involved"),
            "dialogues": scene_data.get("dialogues"),
            "continuity": scene_data.get("continuity") or {},
            "character_visual_bible": {
                name: self.cinematographer.character_visuals.get(name, "")
                for name in scene_data.get("characters_involved") or []
            },
            "reference_images_supplied": list(scene_record.anchor_names or []),
        }

        try:
            verdict = await self.director.critique_scene(scene_record, video_uri, expected)
        except Exception as exc:
            # A crashing critic is an infrastructure failure, not a verdict.
            logger.error("Continuity critic raised for %s: %s", scene_record.scene_id, exc)
            verdict = {
                "approved": False,
                "continuity_score": 0.0,
                "critique": f"Continuity review could not run: {exc}",
                "revised_prompt": "",
            }

        try:
            score = max(0.0, min(1.0, float(verdict.get("continuity_score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0
        approved = bool(verdict.get("approved"))
        critique = str(verdict.get("critique") or "").strip() or "No critique text returned."
        revised = str(verdict.get("revised_prompt") or "")

        if approved:
            return True, {
                "continuity_score": score,
                "critique": critique,
                "review_mode": "director_approved",
                "revised_prompt": revised,
            }

        if self.review_mode == "enforce":
            return False, {
                "continuity_score": score,
                "critique": critique,
                "review_mode": "unverified",
                "revised_prompt": revised,
            }

        # Advisory mode: keep the clip but never call it approved. The score is
        # left as the critic reported it so the Screening Room shows the real
        # number rather than an invented 100%.
        return True, {
            "continuity_score": score,
            "critique": f"Kept without approval (advisory review): {critique}",
            "review_mode": "unverified",
            "revised_prompt": revised,
        }

    def _apply_continuity_updates(self, scene_data: Dict[str, Any]) -> None:
        continuity = scene_data.get("continuity") or {}
        environment = str(continuity.get("environment_state") or "").strip()
        # Commit the prompt ledger only after the Director accepted this exact
        # Omni interaction. Rejected attempts must not become narrative history.
        self.cinematographer.commit_scene(
            location=scene_data.get("location"),
            drama_beat=scene_data.get("drama_beat", ""),
            environment_state=environment,
        )
        updates = continuity.get("character_state_updates") or []
        if isinstance(updates, dict):
            updates = [
                {"character_name": name, "state_note": note} for name, note in updates.items()
            ]
        for update in updates:
            if not isinstance(update, dict):
                continue
            name = str(update.get("character_name") or "").strip()
            note = str(update.get("state_note") or "").strip()
            if name and note and name in self.cinematographer.character_visuals:
                self.cinematographer.update_character_state(name, note[:300])
        if environment:
            self.cinematographer.update_environment_state(environment[:300])

    # ─────────────────────────────────────────────────────────────────────────
    # Agents and script validation
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_table_read(
        self,
        agents: List[CharacterAgent],
        world_state: WorldState,
        simulation_ticks: int,
    ) -> None:
        delay = max(0, int(os.getenv("INTER_AGENT_DELAY_SECONDS", "12")))
        ticks = max(1, min(int(simulation_ticks), 3))
        for tick in range(ticks):
            for index, agent in enumerate(agents):
                try:
                    action = await agent.tick(world_state)
                    # Extract real token usage from the character agent response.
                    # agent.tick() returns the CharacterAction; the raw Gemini
                    # response is stored on the agent as _last_response (if set).
                    try:
                        last_resp = getattr(agent, "_last_response", None)
                        if last_resp is not None:
                            self._total_tokens_burned += (
                                last_resp.usage_metadata.total_token_count or 0
                            )
                    except Exception:
                        pass
                except Exception as exc:
                    logger.warning("Table-read tick failed for %s: %s", agent.state.name, exc)
                if index < len(agents) - 1 and delay:
                    await asyncio.sleep(delay)

    async def _generate_script_from_history(
        self,
        *,
        characters: List[Dict[str, Any]],
        premise: str,
        history: str,
        total_clips: int,
        clip_duration: int,
    ) -> List[Dict[str, Any]]:
        names = [character["name"] for character in characters]
        char_list = ", ".join(names)
        prompt = f"""You are REVERIE's screenwriter and continuity supervisor.

PREMISE:
{premise}

CHARACTER MEMORY FROM THE LIVE TABLE READ:
{history}

Return ONLY a JSON array with exactly {total_clips} shots. Each shot lasts
{clip_duration} seconds and must contain:
- "location": a specific visible location
- "drama_beat": present-tense, filmable action in one continuous shot
- "characters_involved": 1 to 3 exact names from [{char_list}]
- "dialogues": zero to two {{"character_name", "line"}} objects; each line <= 12 words
- "tension": 0.0 to 1.0, how much dramatic pressure THIS shot carries. Judge the
  beat itself, not its position in the list. A quiet setup shot is genuinely low.
- "continuity": {{
    "environment_state": time/weather/light to carry forward,
    "transition_from_previous": visual connection from prior shot (empty only for shot 1),
    "character_state_updates": [{{"character_name", "state_note"}}]
  }}

Hard rules:
- Never invent characters or change a named character's face, body, hair, or core costume.
- Carry props, injuries, wardrobe changes, positions, and time of day forward.
- Write one single continuous shot per entry: no montage and no unrelated cutaway.
- Build a dramatic arc: setup -> pressure -> reversal -> climax -> consequence.
- Do not create more or fewer than {total_clips} shots.
- NEVER use real-world copyrighted character names (Spider-Man, Batman, Superman, Iron Man, etc.) in drama_beat or dialogue. Use only the character names provided above.
"""

        for attempt in range(4):
            try:
                response = await self.model.generate_content_async(
                    prompt,
                    generation_config={"response_mime_type": "application/json"},
                )
                try:
                    self._total_tokens_burned += (
                        response.usage_metadata.total_token_count or 0
                    )
                except Exception:
                    pass
                decoded = json.loads(response.text)
                if not isinstance(decoded, list) or len(decoded) != total_clips:
                    raise ValueError("The screenplay did not contain the requested exact number of shots.")
                normalised = [self._normalise_scene(scene, set(names)) for scene in decoded]
                if any(scene is None for scene in normalised):
                    raise ValueError("The screenplay contained an invalid scene or unknown character.")
                return [scene for scene in normalised if scene is not None]
            except ResourceExhausted as exc:
                if attempt == 3:
                    logger.error("Screenwriter quota exhausted: %s", exc)
                    return []
                delay = 20 * (2**attempt)
                logger.warning("Screenwriter rate limited; retrying in %ss", delay)
                await asyncio.sleep(delay)
            except Exception as exc:
                if attempt == 3:
                    logger.error("Screenwriter output failed validation: %s", exc)
                    return []
                logger.warning("Invalid screenplay attempt %s: %s", attempt + 1, exc)
        return []

    @staticmethod
    def _validate_characters(characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clean: List[Dict[str, Any]] = []
        used_names = set()
        for raw in characters:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if not name or name.casefold() in used_names:
                continue
            used_names.add(name.casefold())
            character = dict(raw)
            character["name"] = name
            memories = character.get("memory_stream") or []
            if isinstance(memories, str):
                memories = [line.strip() for line in memories.split("\n") if line.strip()]
            character["memory_stream"] = [str(m)[:500] for m in memories if str(m).strip()]
            clean.append(character)
        return clean

    @staticmethod
    def _normalise_scene(
        raw_scene: Any,
        valid_names: set[str],
        *,
        allow_empty_cast: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Validate one shot.

        ``allow_empty_cast`` exists for advertisements, where a product-only or
        pack-shot frame with nobody on screen is a legitimate shot. Dramatic
        scenes still require at least one known character, because a drama beat
        with no cast is almost always a hallucinated or truncated shot.
        """
        if not isinstance(raw_scene, dict):
            return None
        location = str(raw_scene.get("location") or "").strip()[:300]
        # Sanitise drama_beat for IP names — the screenwriter LLM can output
        # copyrighted names from the premise which Omni then blocks.
        from agents.cinematographer_agent import _sanitise_prompt
        drama_beat = _sanitise_prompt(str(raw_scene.get("drama_beat") or "").strip())[:1800]
        raw_names = raw_scene.get("characters_involved") or []
        if not isinstance(raw_names, list):
            return None
        involved: List[str] = []
        for name in raw_names:
            if isinstance(name, str) and name in valid_names and name not in involved:
                involved.append(name)
        # Three people is an intentional composition limit even though Omni can
        # accept more image references. It gives the critic a meaningful chance
        # to verify each identity rather than showing an indistinct crowd.
        if not location or not drama_beat or len(involved) > 3:
            return None
        if not involved and not allow_empty_cast:
            return None

        dialogues: List[Dict[str, str]] = []
        for line in raw_scene.get("dialogues") or []:
            if not isinstance(line, dict):
                continue
            name = str(line.get("character_name") or line.get("character") or "").strip()
            text = _sanitise_prompt(str(line.get("line") or line.get("text") or "").strip())
            if name in involved and text:
                dialogues.append({"character_name": name, "line": text[:180]})
            if len(dialogues) == 2:
                break

        continuity = raw_scene.get("continuity") or {}
        if not isinstance(continuity, dict):
            continuity = {}
        updates = continuity.get("character_state_updates") or []
        if not isinstance(updates, (list, dict)):
            updates = []

        # Planned tension for this specific beat. The previous build derived the
        # displayed "drama" figure from scene_index / total_scenes, so the last
        # shot of every film always read 100% regardless of content. An absent or
        # unparseable value stays None so the UI can omit the figure rather than
        # showing a fabricated one.
        planned_tension: Optional[float] = None
        raw_tension = raw_scene.get("tension", raw_scene.get("drama_score"))
        if raw_tension is not None:
            try:
                planned_tension = max(0.0, min(1.0, float(raw_tension)))
            except (TypeError, ValueError):
                planned_tension = None

        # Media the user attached to this specific shot in the script editor.
        # Labels only: the render path resolves them against uploaded assets, so
        # an unknown label cannot inject an arbitrary URL into a prompt.
        raw_assets = raw_scene.get("scene_asset_labels") or []
        scene_asset_labels: List[str] = []
        if isinstance(raw_assets, list):
            for label in raw_assets:
                text = str(label).strip()[:120]
                if text and text not in scene_asset_labels:
                    scene_asset_labels.append(text)

        return {
            "location": location,
            "drama_beat": drama_beat,
            "characters_involved": involved,
            "dialogues": dialogues,
            "tension": planned_tension,
            "scene_asset_labels": scene_asset_labels[:MAX_REFERENCE_IMAGES],
            "continuity": {
                "environment_state": str(continuity.get("environment_state") or "").strip()[:300],
                "transition_from_previous": str(
                    continuity.get("transition_from_previous") or ""
                ).strip()[:500],
                "character_state_updates": updates,
            },
        }

    @staticmethod
    def _production_id(
        characters: List[Dict[str, Any]], premise: str, duration_minutes: int, style: str
    ) -> str:
        identity = {
            "cast": [
                {"name": character.get("name"), "visual": character.get("visual_description", "")}
                for character in characters
            ],
            "premise": premise,
            "duration": duration_minutes,
            "style": style,
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:20]
