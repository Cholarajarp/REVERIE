import asyncio
import uuid
import time
from datetime import timedelta, datetime
from typing import List, Optional, Tuple

from models.schema import CharacterState, WorldState, SceneRecord
from agents.character_agent import CharacterAgent
from agents.director_agent import DirectorAgent
from agents.cinematographer_agent import CinematographerAgent
from core.omni_pipeline import OmniPipeline
from core.tts_pipeline import TTSPipeline
from repositories.world import WorldRepository
from repositories.scene import SceneRepository, BudgetExceededError
from repositories.character import CharacterRepository
from core.logger import get_logger, trace_span
from core.audience_sync import audience_sync_manager

logger = get_logger(__name__)

# Simulation leadership lease lifetime.
#
# Must comfortably exceed one tick's worst case, but stay short enough that a
# crashed leader is replaced promptly. A tick that triggers Veo can run for
# minutes, which is why the lease is renewed by a background heartbeat rather
# than once per tick -- the TTL only has to outlive the heartbeat interval
# (TTL/3), not a tick.
LEASE_TTL_MS = 30_000

# Bounds on model-authored strings written back into CharacterState.
#
# Both fields are re-injected into every subsequent prompt and checkpointed to
# Firestore, so an unbounded value would compound: a paragraph-length "mood"
# would inflate token cost for the rest of the run and bloat every checkpoint.
MAX_MOOD_LENGTH = 60
MAX_GOAL_LENGTH = 200

class SimulationEngine:
    def __init__(self, characters: List[CharacterAgent], director: DirectorAgent,
                 cinematographer: CinematographerAgent, omni: Optional[OmniPipeline] = None,
                 world_repo: WorldRepository = None, char_repo: CharacterRepository = None,
                 scene_repo: SceneRepository = None, broadcaster=None,
                 tts_pipeline: Optional[TTSPipeline] = None, veo: Optional[Any] = None, **kwargs):
        self.characters = characters
        self.director = director
        self.cinematographer = cinematographer
        self.omni = omni or veo
        self.veo = self.omni
        self.tts = tts_pipeline or TTSPipeline()
        self.world_repo = world_repo
        self.char_repo = char_repo
        self.scene_repo = scene_repo
        # Optional RedisBroadcaster. Supplies the leadership lease that keeps
        # this loop singular across Cloud Run instances. None means
        # single-instance mode, where the loop is trivially the only one.
        self.broadcaster = broadcaster
        self.is_running = False
        
        # Telemetry metrics
        self.total_tokens_burned = 0
        self.avg_tick_latency_ms = 0.0
        self.total_ticks_run = 0

    async def run_day(self, start_world_state: WorldState):
        """Runs the simulation until the film is complete or a budget/tick cap is hit.

        Tick cap: MAX_TICKS_PER_RUN (default 80) — a 1-min film needs ~6 clips,
        which typically arrive within 20-40 ticks.  Running all 288 ticks on
        every start wastes Gemini budget even after the film is done.

        Token budget: GEMINI_TOKEN_BUDGET — hard stop to protect GCP credits.
        Estimate: 3 chars × ~400 tok + director ~600 tok ≈ 1800 tok/tick.
        At 80 ticks that is ~144k tokens total (gemini-3.5-flash).

        Director skip: director only runs every DIRECTOR_INTERVAL ticks (default 3).
        Characters still act every tick for natural behaviour, but we only pay
        for a drama check one-third as often.
        """
        # Leader election happens BEFORE anything else, and a non-leader returns
        # here rather than falling into the try/finally below. That ordering is
        # load-bearing: the finally block writes {"is_running": False,
        # "tick_number": 0} to the shared checkpoint document, so a second
        # instance that entered and bailed out would erase the real leader's
        # progress and strand it mid-day.
        if self.broadcaster is not None:
            if not await self.broadcaster.try_acquire_leadership(ttl_ms=LEASE_TTL_MS):
                logger.info(
                    "Another instance holds the simulation lease. Not starting a "
                    "second loop; this instance will serve WebSockets only."
                )
                return
            # Renew on a timer rather than per tick: a tick that triggers Veo can
            # block for minutes, which would let the lease lapse mid-scene and
            # invite a second writer.
            self.broadcaster.start_leadership_heartbeat(ttl_ms=LEASE_TTL_MS)
            logger.info("Acquired simulation leadership; running the tick loop.")

        self.is_running = True
        lost_leadership = False
        world_state = start_world_state
        start_tick = 0
        # Per-run hard limits — protect GCP credits
        MAX_TICKS_PER_RUN = 80        # never run more than 80 ticks
        DIRECTOR_INTERVAL = 3         # director drama check every 3rd tick
        GEMINI_TOKEN_BUDGET = 200_000 # stop here to protect GCP credits
        # Inter-character delay (seconds) between sequential Gemini calls.
        # gemini-3.5-flash has ~60 QPM on free tier; 3 chars + director = 4 calls
        # per tick. 1.5s gap keeps us well under quota with no 429s.
        INTER_CHAR_DELAY = 1.5

        # Check for existing checkpoint after Cloud Run crash/restart
        try:
            checkpoint_doc = self.world_repo.db.collection("system_meta").document("checkpoint").get()
            if checkpoint_doc.exists:
                cp_data = checkpoint_doc.to_dict()
                if cp_data.get("is_running") and cp_data.get("tick_number", 0) < 287:
                    start_tick = cp_data.get("tick_number", 0) + 1
                    if "world_state" in cp_data and cp_data["world_state"]:
                        world_state = WorldState.model_validate(cp_data["world_state"])
                    logger.info(f"Resuming simulation from checkpoint at tick {start_tick + 1}/288")
        except Exception as e:
            logger.warning(f"Could not load checkpoint, starting new day: {e}")

        # Wire character visual descriptions into the cinematographer once,
        # before the first tick.  This is what makes all Veo clips look like
        # scenes from the same film — every prompt will reference the same
        # face, costume, and build for each character.
        character_visuals = {
            agent.state.name: agent.state.visual_description
            for agent in self.characters
            if agent.state.visual_description
        }
        self.cinematographer.set_character_visuals(character_visuals)

        # Initial save on startup
        self.world_repo.save("current_world", world_state)
        for agent in self.characters:
            self.char_repo.save(agent.state.name, agent.state)

        try:
            for tick in range(start_tick, min(288, start_tick + MAX_TICKS_PER_RUN)):
                if not self.is_running:
                    logger.info("Simulation engine stopped by user.")
                    break

                # Stop when enough clips have been generated for the film
                if getattr(self.cinematographer, "is_film_complete", False) is True:
                    logger.info(
                        f"Film complete! Generated {getattr(self.cinematographer, '_scenes_generated', '?')}/"
                        f"{getattr(self.cinematographer, 'total_clips_needed', '?')} scenes for "
                        f"{getattr(self.cinematographer, 'film_duration_minutes', '?')}-minute film. "
                        f"Stopping simulation."
                    )
                    break

                # Stop immediately if the lease lapsed. By this point another
                # instance may already have resumed from our last checkpoint, so
                # continuing would mean two writers advancing the same world and
                # double-spending on Veo.
                if self.broadcaster is not None and self.broadcaster.leadership_lost:
                    lost_leadership = True
                    logger.error(
                        f"Lost simulation leadership at tick {tick + 1}/288. Stopping "
                        f"this loop; another instance will resume from the last checkpoint."
                    )
                    break

                t0 = time.time()
                with trace_span("sim_tick", {"tick": tick + 1, "time": world_state.current_time.isoformat()}):
                    logger.info(f"--- TICK {tick + 1}/288 --- Time: {world_state.current_time.isoformat()}")
                    
                    # 1. Update world_state.current_time (+5 minutes) in memory (no Firestore read!)
                    world_state.current_time += timedelta(minutes=5)
                    
                    # 2. Update weather
                    if tick % 50 == 0:
                        world_state.weather = "Cloudy" if world_state.weather == "Sunny" else "Sunny"
                    
                    # 3. Asynchronously trigger CharacterAgent.tick() for all characters (mutating in memory!)
                    async def process_character(agent: CharacterAgent) -> Optional[Tuple[str, str]]:
                        """Runs one tick and commits its results to the character's state.

                        Returns (name, dialogue) when the character spoke, so the
                        caller can publish to the whisper feed. Returning the line
                        rather than appending to a shared list keeps ordering
                        deterministic: asyncio.gather preserves input order, while
                        append order would follow whichever model replied first.
                        """
                        try:
                            action = await agent.tick(world_state)
                            if not action:
                                return None

                            if action.get("action") == "move" and action.get("target"):
                                agent.state.current_location = action["target"]

                            # Mood writeback. Previously never persisted, so mood
                            # stayed at its seed value for the entire run: the
                            # Director's volatility axis scored a constant, and
                            # CURRENT_MOOD in each tick prompt never changed.
                            mood = action.get("mood")
                            if isinstance(mood, str) and mood.strip():
                                agent.state.mood = mood.strip()[:MAX_MOOD_LENGTH]

                            # Goal succession, and only on a genuinely completed
                            # goal. Gating on goal_status is what stops a character
                            # trading away its long-term goal because one tick was
                            # dull -- which is the drift the prompt work fixed.
                            if action.get("goal_status") == "COMPLETE":
                                next_goal = action.get("next_goal")
                                if isinstance(next_goal, str) and next_goal.strip():
                                    previous_goal = agent.state.current_goal
                                    agent.state.current_goal = next_goal.strip()[:MAX_GOAL_LENGTH]
                                    logger.info(
                                        f"{agent.state.name} completed a goal and adopted a successor",
                                        extra={
                                            "character": agent.state.name,
                                            "previous_goal": previous_goal,
                                            "new_goal": agent.state.current_goal,
                                        },
                                    )

                            # Note: No Firestore save here! We eliminate write amplification.
                            dialogue = action.get("dialogue")
                            if (action.get("action") == "talk"
                                    and isinstance(dialogue, str)
                                    and dialogue.strip()):
                                return (agent.state.name, dialogue.strip())
                            return None
                        except Exception as e:
                            logger.error(f"Error processing tick for {agent.state.name}: {e}")
                            return None

                    # Sequential character calls with delay — prevents 429 rate
                    # limit errors that occur when all characters hit Gemini
                    # simultaneously. asyncio.gather() parallelises everything
                    # into a burst; sequential + sleep spreads the load evenly.
                    spoken = []
                    for agent in self.characters:
                        result = await process_character(agent)
                        spoken.append(result)
                        if len(self.characters) > 1:
                            await asyncio.sleep(INTER_CHAR_DELAY)

                    # 3b. Publish this tick's dialogue to the whisper feed.
                    #
                    # CharacterAgent has always generated `dialogue`, but nothing
                    # consumed it: the audience could watch telemetry and video
                    # while the actual conversation was invisible.
                    dialogue_lines = [line for line in spoken if line]
                    if dialogue_lines:
                        try:
                            await audience_sync_manager.publish_agent_dialogue(
                                dialogue_lines, tick=tick + 1
                            )
                        except Exception as e:
                            # A broken feed must not stop the simulation.
                            logger.warning(f"Could not publish dialogue to whisper feed: {e}")

                    # 4. Director drama check — only every DIRECTOR_INTERVAL ticks
                    # to avoid paying for a Gemini call on every single tick.
                    char_states = [agent.state for agent in self.characters]
                    drama_score = 0.0
                    drama_beat = ""
                    try:
                        if tick % DIRECTOR_INTERVAL == 0:
                            drama_result = await self.director.detect_drama(char_states)
                            drama_score = drama_result.get("drama_score", 0.0)
                            drama_beat = drama_result.get("beat", "")
                            logger.info(f"Director evaluated drama: {drama_score:.2f} — {drama_beat}")
                        else:
                            drama_result = {"drama_score": 0.0, "involved_characters": [], "beat": ""}

                        # 5. If drama_score > 0.60: trigger scene generation
                        if drama_score > 0.60:
                            logger.info("Drama threshold exceeded. Checking system health before Veo generation.")
                            
                            # Grafana MCP Integration: Self-regulating check
                            health = await self.director.get_system_health()
                            if health.get("status") == "throttled":
                                logger.warning(f"Grafana reported throttled state: {health.get('reason')}. Skipping Veo generation to save budget.")
                            else:
                                # The Director now names the cast explicitly and its
                                # names are validated against real characters before
                                # they get here.
                                #
                                # This replaces `c.current_location in drama_beat`,
                                # which substring-matched a location name against a
                                # prose sentence -- it silently fell through to "first
                                # two characters" whenever the Director's phrasing did
                                # not happen to contain the location string.
                                involved_characters = drama_result.get("involved_characters") or []

                                if not involved_characters:
                                    # Above the filming threshold the Director is
                                    # required to name its cast, so an empty list here
                                    # means a malformed response. Filming arbitrary
                                    # characters would spend real Veo budget on a scene
                                    # unrelated to the beat, so skip this tick instead.
                                    logger.warning(
                                        f"Drama score {drama_score} exceeded threshold but the Director "
                                        f"named no characters. Skipping Veo generation for this tick."
                                    )
                                else:
                                    scene_location = drama_result.get("location")
                                    omni_prompt = await self.cinematographer.generate_omni_prompt(
                                        drama_beat, involved_characters, location=scene_location
                                    )
                                    scene_id = f"scene_{uuid.uuid4().hex[:8]}"

                                    try:
                                        scene = await self.omni.reserve_omni_budget(
                                            scene_id=scene_id,
                                            characters_involved=involved_characters,
                                            drama_score=drama_score,
                                            omni_prompt=omni_prompt,
                                            duration_seconds=10,
                                        )

                                        video_uri = await self.omni.generate_clip(scene)
                                        if video_uri:
                                            critique = await self.director.critique_scene(scene, video_uri)
                                            logger.info(f"Director critique for scene {scene_id}: {critique}")

                                            # Synthesize TTS audio for dialogue in this scene
                                            try:
                                                # Collect recent dialogue from involved characters
                                                scene_dialogues = []
                                                for agent in self.characters:
                                                    if agent.state.name in involved_characters:
                                                        # Get the character's voice_id
                                                        voice_id = getattr(agent, 'voice_id', 'en-US-Studio-O')
                                                        # Use the drama beat as dialogue context
                                                        scene_dialogues.append({
                                                            "character_name": agent.state.name,
                                                            "text": drama_beat,
                                                            "voice_id": voice_id,
                                                        })
                                                if scene_dialogues:
                                                    audio_results = await self.tts.synthesize_scene_dialogue(
                                                        dialogues=scene_dialogues,
                                                        scene_id=scene_id,
                                                    )
                                                    logger.info(f"TTS synthesized {len(audio_results)} dialogue tracks for scene {scene_id}")
                                            except Exception as tts_err:
                                                logger.warning(f"TTS synthesis failed for scene {scene_id}: {tts_err}")

                                    except BudgetExceededError as e:
                                        logger.warning(f"Skipping Veo generation: {e}")
                                
                    except Exception as e:
                        logger.error(f"Error in director/cinematographer pipeline: {e}")

                    # 6. Update telemetry + check token budget
                    tick_duration_ms = (time.time() - t0) * 1000.0
                    self.total_ticks_run += 1
                    self.avg_tick_latency_ms = ((self.avg_tick_latency_ms * (self.total_ticks_run - 1)) + tick_duration_ms) / self.total_ticks_run
                    # Estimate: each char ~400 tok; director check every 3rd tick ~600 tok
                    tick_tokens = len(self.characters) * 400
                    if tick % DIRECTOR_INTERVAL == 0:
                        tick_tokens += 600
                    self.total_tokens_burned += tick_tokens

                    if self.total_tokens_burned >= GEMINI_TOKEN_BUDGET:
                        logger.warning(
                            f"Token budget of {GEMINI_TOKEN_BUDGET:,} reached at tick {tick + 1}. "
                            f"Stopping simulation to protect GCP credits."
                        )
                        break

                    try:
                        # Audience size must come from Redis: the leader holds
                        # only its own share of the sockets, so its local count
                        # would under-report the real figure to every viewer.
                        global_viewers = None
                        if self.broadcaster is not None:
                            global_viewers = await self.broadcaster.get_connection_count()

                        audience_sync_manager.update_metrics(
                            token_burn=self.total_tokens_burned,
                            tick_latency_ms=round(self.avg_tick_latency_ms, 2),
                            drama_score=drama_score,
                            active_connections=global_viewers
                        )
                    except Exception as e:
                        logger.debug(f"Could not broadcast telemetry: {e}")

                    # 7. Checkpoint to Firestore every 10 ticks (or on tick 287) to drop DB ops by >92%
                    if (tick + 1) % 10 == 0 or tick == 287:
                        try:
                            self.world_repo.save("current_world", world_state)
                            for agent in self.characters:
                                self.char_repo.save(agent.state.name, agent.state)
                                
                            checkpoint_data = {
                                "tick_number": tick,
                                "world_state": world_state.model_dump(mode="json"),
                                "is_running": True,
                                "updated_at": datetime.utcnow().isoformat()
                            }
                            self.world_repo.db.collection("system_meta").document("checkpoint").set(checkpoint_data, merge=True)
                            logger.info(f"Saved simulation checkpoint & flushed in-memory state to Firestore at tick {tick + 1}")
                        except Exception as e:
                            logger.error(f"Failed to save simulation checkpoint: {e}")
                    
                    await asyncio.sleep(0)  # yield to event loop without blocking

        finally:
            # 8. Final save upon simulation termination.
            #
            # Skipped entirely when leadership was lost, and that exclusion is
            # the single most important safety property in this file. By the time
            # we get here another instance has likely resumed from our last
            # checkpoint, so:
            #   - writing {"is_running": False, "tick_number": 0} would erase its
            #     progress and make the next resume restart the day from tick 0;
            #   - flushing our stale in-memory world_state and character states
            #     would roll the live simulation backwards.
            # Our lease is already gone, so the new leader owns these documents.
            if lost_leadership:
                logger.warning(
                    "Skipping final checkpoint write: leadership was lost, and another "
                    "instance now owns the simulation state. Writing here would "
                    "overwrite its progress."
                )
            else:
                try:
                    self.world_repo.save("current_world", world_state)
                    for agent in self.characters:
                        self.char_repo.save(agent.state.name, agent.state)
                    self.world_repo.db.collection("system_meta").document("checkpoint").set(
                        {"is_running": False, "tick_number": 0, "updated_at": datetime.utcnow().isoformat()},
                        merge=True
                    )
                except Exception as e:
                    logger.error(f"Error during final termination save: {e}")

            # Release the lease so a replacement can start promptly rather than
            # waiting out the TTL. Also stops the heartbeat task.
            if self.broadcaster is not None:
                try:
                    await self.broadcaster.release_leadership()
                except Exception as e:
                    logger.debug(f"Could not release leadership cleanly: {e}")

            self.is_running = False
            logger.info("Simulation day completed and terminated cleanly.")
