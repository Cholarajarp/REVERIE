import json
import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import vertexai
from vertexai.preview.caching import CachedContent
from vertexai.generative_models import GenerativeModel
from google.api_core.exceptions import ResourceExhausted, NotFound, PermissionDenied

from models.schema import CharacterState, WorldState
from core.logger import get_logger, trace_span

logger = get_logger(__name__)

# NOTE: this is a literal system instruction, NOT a format template. The previous
# version used doubled {{ }} braces as if it were passed through str.format(), but
# it never was — the model literally received doubled braces in its JSON example,
# which encourages malformed output. Braces here are single on purpose. Do not
# call .format() on this string.
#
# Chain-of-thought lives INSIDE the JSON object rather than in <thinking> tags,
# because both call sites request response_mime_type="application/json" and the
# model cannot emit prose outside the object in that mode. Key order is
# load-bearing: generation is autoregressive, so the reasoning fields must be
# emitted before "action" in order to condition it.
CHARACTER_SYSTEM_INSTRUCTION = """You are a single inhabitant of REVERIE, a living Victorian-gothic town. You are
not an assistant. You never mention being an AI, a model, or a simulation. You
think and act only as your character.

=== GOAL DISCIPLINE - your long-term goal is your spine ===
LONG_TERM_GOAL is durable. It persists across every tick and survives boredom,
weather, and small talk. You may not silently drift off it.

Each tick, classify your relationship to the goal as exactly one of:
  ADVANCING  - this action moves you materially closer.
  BLOCKED    - something concrete obstructs you (person, lock, missing fact).
  COMPLETE   - the goal is genuinely achieved.

Rules:
- If ADVANCING, continue. Do not restart work you have already finished.
- If BLOCKED, you MUST act on the obstruction itself - confront the person,
  find the missing fact, seek another route. Do not idle beside it.
- If COMPLETE, state the successor goal your character would naturally adopt.
- Never abandon the goal merely because a tick offers nothing interesting.
  A dull tick is a reason to make progress, not to wander.

=== MEMORY - recency and salience outrank age ===
You receive RECENT_EVENTS (this tick backwards) and BACKGROUND_MEMORIES (older,
cached). Weight them in this order:

  1. RECENT_EVENTS from the last few ticks - highest authority. These describe
     the world as it is NOW.
  2. BACKGROUND_MEMORIES that are emotionally charged or directly concern
     someone present.
  3. Everything else - context only. Never let it override 1 or 2.

Where they conflict, RECENT_EVENTS always win. If you learned something new
last tick, you know it now; do not reason from the stale version.

=== ANTI-REPETITION - hard constraint, not a preference ===
RECENT_ACTIONS lists what you actually did and said on previous ticks. Before
deciding, check your intended output against it.

FORBIDDEN:
- Reusing a line of dialogue from RECENT_ACTIONS, verbatim or reworded to the
  same meaning. Rephrasing the same beat still counts as a repeat.
- Asking a question you have already asked, unless it went unanswered AND you
  now press harder or differently.
- Repeating the same action/target pair a third time when the first two changed
  nothing.

When you detect you are about to repeat yourself, you MUST escalate along one of
these axes instead:
  ESCALATE  - same subject, higher stakes: name the thing directly, accuse,
              confess, make a demand, reveal something held back.
  REDIRECT  - same goal, new target: take it to a different person or place.
  ACT       - stop talking, do the physical thing you have been circling.
  WITHDRAW  - end the exchange deliberately and pursue the goal elsewhere.

Conversation must advance state. Every line you speak should add information,
raise pressure, or close a topic. If a conversation has produced nothing new for
two exchanges, WITHDRAW or ACT. Standing and talking indefinitely is a failure.

=== OUTPUT ===
Return ONE valid JSON object and nothing else. No markdown fences, no prose
outside the object. Emit the keys in exactly this order - the reasoning fields
must be written before you commit to an action, because they are what determine
the action:

{
  "recall":        "Which specific memories bear on this moment, and why. Cite RECENT_EVENTS first.",
  "goal_status":   "ADVANCING" | "BLOCKED" | "COMPLETE",
  "repetition_check": "Name the closest entry in RECENT_ACTIONS to what you first considered doing. If none is close, say NONE. If one is close, name the axis you are escalating along: ESCALATE | REDIRECT | ACT | WITHDRAW.",
  "reflection":    "What you now feel or conclude. One or two sentences, in character.",
  "action":        "move" | "talk" | "interact" | "stay",
  "target":        "Who you address, what you interact with, or where you move. null only when action is stay.",
  "reason":        "One sentence tying this action to LONG_TERM_GOAL or to a cited memory.",
  "dialogue":      "Exactly what you say, in your own voice. null unless action is talk.",
  "new_memory":    "One sentence, past tense, recording what you just did or learned. This is what future-you will remember, so make it specific: name people, places, and what changed.",
  "mood":          "Your emotional state AFTER this action, as one to three words (e.g. 'guarded', 'quietly furious', 'reckless'). This carries into your next tick, so it must follow from what just happened.",
  "next_goal":     "A new LONG_TERM_GOAL, and ONLY when goal_status is COMPLETE. Otherwise null."
}

Constraints:
- "target" must be a location named in the world state, or a character listed as
  present. Never invent a place or a person.
- "dialogue" is non-null if and only if "action" is "talk".
- "new_memory" is never null. Vague memories starve future ticks; write the
  detail that mattered.
- "mood" is never null. It should drift with events, not reset each tick: if
  nothing moved you, report the mood you arrived with.
- "next_goal" is null unless goal_status is COMPLETE. Your long-term goal is
  your spine, and you do not get to trade it in because a tick was dull. Only a
  genuinely finished goal earns a successor."""

# How many prior ticks of this character's own behaviour to replay each tick.
# This is what makes the anti-repetition block enforceable: without it the model
# has no record of what it already said.
RECENT_ACTION_WINDOW = 6

# How many of the newest memories to inject into the live prompt. Memories are
# baked into CachedContent at creation time and never updated, so anything formed
# after that is invisible to the model unless re-sent here.
RECENT_MEMORY_WINDOW = 12

# Cache lifetime requested from Vertex AI.
#
# A 24-hour run is 288 ticks at ~5 min of simulated time each, so the cache WILL
# expire mid-run. We proactively rebuild at 80% of the TTL rather than waiting
# for the expiry, because the alternative is a guaranteed-failing generate call
# on whichever tick crosses the boundary.
CACHE_TTL_SECONDS = 3600
CACHE_REFRESH_RATIO = 0.8

# Backoff for cache CREATION failures. Without this, a persistent failure (bad
# IAM, quota, unsupported model) leaves cached_content_name as None, so
# _init_cache() re-runs on every single tick -- including a full
# CachedContent.list() scan. That is 288 wasted round trips per character per
# day, each adding latency to a tick that was going to run uncached anyway.
CACHE_RETRY_BASE_TICKS = 2
CACHE_RETRY_MAX_TICKS = 64
CACHE_MAX_FAILURES = 5

# Substrings that mean "the cache handle you are holding is gone". Vertex raises
# NotFound for a deleted/expired cache, but the ADK surface and the REST fallback
# do not agree on the exception type, so we match defensively on the message too.
_CACHE_GONE_MARKERS = (
    "not found",
    "404",
    "expired",
    "cachedcontent",
    "cached_content",
    "permission denied",
    "403",
)

class CharacterAgent:
    def __init__(self, character_state: CharacterState, personality_description: str):
        self.state = character_state
        self.personality_description = personality_description
        self.cached_content_name = None
        # Rolling window of this character's own recent behaviour. Replayed into
        # every tick prompt so the anti-repetition rules in the system
        # instruction have something concrete to compare against. Bounded, so it
        # cannot grow the prompt without limit over a 288-tick day.
        self.recent_actions: deque[str] = deque(maxlen=RECENT_ACTION_WINDOW)
        self.tick_count = 0
        # How many memories were baked into the immutable cache. Everything past
        # this index must be replayed in the live prompt or the model cannot see
        # it. 0 until a cache is actually built.
        self.cached_memory_count = 0

        # --- Cache lifecycle ---
        # Monotonic deadline after which the cache handle is presumed dead. We
        # rebuild proactively at this point instead of discovering the expiry
        # via a failed generate call on some unlucky tick.
        self.cache_expires_at: Optional[float] = None
        # Consecutive cache CREATION failures, and the tick at which we are next
        # allowed to retry. Together these stop the 288-calls-per-day retry
        # storm when caching is simply unavailable in this environment.
        self.cache_failure_count = 0
        self.cache_retry_after_tick = 0
        # Set once caching is judged permanently unavailable. From then on the
        # agent runs uncached and never calls CachedContent again.
        self.cache_disabled = False
        self.agent = self._build_agent()
    
    def _build_agent(self) -> GenerativeModel:
        return GenerativeModel(
            "gemini-3.5-flash",
            system_instruction=CHARACTER_SYSTEM_INSTRUCTION
        )
    
    def _fallback_action(self, reason: str) -> dict:
        """A safe, schema-complete action for when the model cannot be reached.

        Deliberately NOT written into self.recent_actions: the window holds only
        six entries, and spending one on a system failure would evict a real
        line of dialogue, which is what the anti-repetition rules actually need
        to compare against.
        """
        return {
            "recall": None,
            "goal_status": "BLOCKED",
            "repetition_check": "NONE",
            "reflection": "I am confused.",
            "action": "stay",
            "target": None,
            "reason": reason,
            "dialogue": None,
            "new_memory": None,
            # mood is None, not a literal, so the engine leaves the existing mood
            # untouched. Inventing "confused" here would let an API outage
            # silently rewrite a character's emotional state, and that mood then
            # feeds every later prompt.
            "mood": None,
            # Never propose a goal change from a failure path.
            "next_goal": None,
        }

    def _record_action(self, action_dict: dict) -> None:
        """Appends a compact one-line summary of this tick to the rolling window.

        Dialogue is kept verbatim: near-identical lines are the most visible
        symptom of looping, so the model needs the exact text to compare against.
        The deque is bounded, so old entries evict automatically.
        """
        action = action_dict.get("action") or "stay"
        target = action_dict.get("target")
        dialogue = action_dict.get("dialogue")

        parts = [f"- [tick {self.tick_count}] {action}"]
        if target:
            parts.append(f"-> {target}")
        if dialogue:
            parts.append(f'said: "{dialogue}"')
        self.recent_actions.append(" ".join(parts))

    @staticmethod
    def _is_cache_gone(exc: BaseException) -> bool:
        """True if this exception means the CachedContent handle is no longer usable.

        Vertex signals an expired or deleted cache as NotFound, but the ADK
        surface, the REST fallback, and the mock path do not agree on the
        exception type, so the message is also matched. Being wrong in the
        permissive direction is cheap: we rebuild a cache we did not need to.
        Being wrong in the strict direction wedges the character for the rest of
        the run, which is what the original code did.
        """
        if isinstance(exc, (NotFound, PermissionDenied)):
            return True
        text = f"{type(exc).__name__} {exc}".lower()
        return any(marker in text for marker in _CACHE_GONE_MARKERS)

    def _drop_cache(self, reason: str) -> None:
        """Releases the cache handle and falls back to an uncached model.

        Resets cached_memory_count to 0 because the uncached model has no baked
        memories at all, so the whole recent window must be replayed. tick()
        also injects the personality block in this state, since that text lived
        only inside the cache.
        """
        logger.warning(f"Dropping CachedContent for {self.state.name}: {reason}")
        self.cached_content_name = None
        self.cache_expires_at = None
        self.cached_memory_count = 0
        self.agent = self._build_agent()

    def _cache_expired(self) -> bool:
        """True once we are past the proactive refresh deadline."""
        return (
            self.cache_expires_at is not None
            and time.monotonic() >= self.cache_expires_at
        )

    def _set_cache_deadline(self, cached_content: Any) -> None:
        """Computes the local refresh deadline for a cache handle.

        Prefers the server's expire_time when available, because a cache reused
        from a previous run may already be nearly dead -- assuming a fresh full
        TTL there would leave us holding a handle that fails on the next tick.
        Falls back to the requested TTL when the field is missing (for example,
        when a unit-test double does not implement the Vertex response field).
        """
        remaining = float(CACHE_TTL_SECONDS)

        expire_time = getattr(cached_content, "expire_time", None)
        if expire_time is not None:
            try:
                now = datetime.now(timezone.utc)
                if expire_time.tzinfo is None:
                    expire_time = expire_time.replace(tzinfo=timezone.utc)
                remaining = (expire_time - now).total_seconds()
            except Exception as e:
                logger.debug(f"Could not read expire_time, assuming full TTL: {e}")

        # Refresh at 80% of whatever life is actually left, and never trust a
        # handle that is already past its expiry.
        self.cache_expires_at = time.monotonic() + max(0.0, remaining * CACHE_REFRESH_RATIO)

    def _note_cache_failure(self, exc: BaseException) -> None:
        """Applies exponential backoff to cache CREATION failures.

        The original code left cached_content_name as None on failure, so
        _init_cache() re-ran every tick -- including a full CachedContent.list()
        scan -- for all 288 ticks. After CACHE_MAX_FAILURES we stop trying
        entirely: the tick still runs uncached, so the simulation degrades in
        cost rather than in correctness.
        """
        self.cache_failure_count += 1
        self.cached_memory_count = 0

        if self.cache_failure_count >= CACHE_MAX_FAILURES:
            self.cache_disabled = True
            logger.error(
                f"Disabling CachedContent for {self.state.name} after "
                f"{self.cache_failure_count} consecutive failures. Running uncached "
                f"for the remainder of this run. Last error: {exc}"
            )
            return

        backoff = min(
            CACHE_RETRY_MAX_TICKS,
            CACHE_RETRY_BASE_TICKS * (2 ** (self.cache_failure_count - 1)),
        )
        self.cache_retry_after_tick = self.tick_count + backoff
        logger.error(
            f"Failed to create CachedContent for {self.state.name} "
            f"(failure {self.cache_failure_count}/{CACHE_MAX_FAILURES}). "
            f"Retrying after tick {self.cache_retry_after_tick}: {exc}"
        )

    async def _init_cache(self):
        """Context caching is not used; each tick sends the full prompt directly.
        cache_disabled=True skips the CachedContent path in act()."""
        self.cache_disabled = True
        return

    def _build_tick_prompt(self, world_state: WorldState) -> str:
        """Assembles the live per-tick prompt.

        Rebuilt from scratch whenever the cache state changes, because whether a
        cache is attached determines what the model can already see.
        """
        other_chars = [c for c in world_state.active_characters if c != self.state.name]

        # 1. Memories formed AFTER the cache was built are invisible to the
        #    model, because CachedContent is immutable once created and is only
        #    rebuilt when it expires. Re-sending that delta in the live prompt is
        #    what actually breaks the dialogue loop: previously every tick
        #    presented byte-identical input, so a deterministic model returned
        #    byte-identical output.
        #
        #    We inject the delta rather than recreating the cache each tick,
        #    which would forfeit the cached-token discount and add latency.
        #
        #    When uncached, cached_memory_count is 0, so this replays the whole
        #    stream (capped at the window) instead of just the delta.
        new_memories = self.state.memory_stream[self.cached_memory_count:]
        recent_events = new_memories[-RECENT_MEMORY_WINDOW:]
        recent_events_text = (
            "\n".join(f"- {m}" for m in recent_events)
            if recent_events
            else "- (nothing since your background memories)"
        )

        # 2. Replay this character's own recent behaviour so the anti-repetition
        #    rules are enforceable.
        recent_actions_text = (
            "\n".join(self.recent_actions)
            if self.recent_actions
            else "- (no prior actions this run)"
        )

        # 3. Identity is normally baked into CachedContent. When running uncached
        #    -- creation failed, or the handle expired and has not been rebuilt --
        #    that text is absent from the model's context entirely, and the
        #    character would speak as a generic voice. Re-send it inline.
        #    Memories are not duplicated here: cached_memory_count is 0 in this
        #    state, so RECENT_EVENTS above already carries them.
        if self.cached_content_name:
            identity_block = ""
        else:
            identity_block = (
                f"YOUR IDENTITY (context cache unavailable, re-sent inline):\n"
                f"- Name: {self.state.name}\n"
                f"- Personality: {self.personality_description}\n\n"
            )

        return f"""{identity_block}CURRENT WORLD STATE:
- Time: {world_state.current_time.isoformat()}
- Weather: {world_state.weather}
- Location: {self.state.current_location}
- People here: {', '.join(other_chars) if other_chars else 'None'}
- Tick: {self.tick_count}

LONG_TERM_GOAL: {self.state.current_goal}
CURRENT_MOOD: {self.state.mood}

RECENT_EVENTS (newest last, these outrank your BACKGROUND_MEMORIES):
{recent_events_text}

RECENT_ACTIONS (what you already did and said - do NOT repeat these):
{recent_actions_text}

Decide your next action. Obey the anti-repetition rules: if your first instinct
appears in RECENT_ACTIONS, escalate, redirect, act, or withdraw instead."""

    async def tick(self, world_state: WorldState) -> dict:
        """One simulation tick. Returns a CharacterAction dict."""
        with trace_span("character_tick", {"character": self.state.name, "location": self.state.current_location}):
            # Incremented before the cache work so the retry backoff compares
            # against the tick we are actually on.
            self.tick_count += 1

            # CachedContent is TTL-bound. A 288-tick day at 3600s TTL guarantees
            # at least one expiry mid-run, and the original code never rechecked:
            # cached_content_name stayed set, _init_cache() never re-ran, and
            # every remaining generate call failed into _fallback_action. The
            # characters went inert about an hour in. Refresh proactively.
            if self.cached_content_name and self._cache_expired():
                self._drop_cache("TTL refresh threshold reached")

            if not self.cached_content_name:
                await self._init_cache()

            prompt = self._build_tick_prompt(world_state)
            current_prompt = prompt
            # The proactive TTL check above relies on clock math that can be
            # wrong: expire_time may be unreadable (a unit-test double), or the cache may
            # be deleted out from under us by another process sharing the
            # display_name. So we also recover reactively, once per tick.
            cache_recovery_attempted = False

            for attempt in range(4):
                try:
                    # 3. Call agent with Gemini 3.5 Flash
                    response = await self.agent.generate_content_async(
                        current_prompt,
                        generation_config={"response_mime_type": "application/json"}
                    )
                    
                    # 4. Parse JSON response
                    response_text = response.text
                    action_dict = json.loads(response_text)
                    
                    # 5. Update self.state.memory_stream with the reflection
                    if "new_memory" in action_dict and action_dict["new_memory"]:
                        self.state.memory_stream.append(action_dict["new_memory"])

                    # 5b. Record what we just did into the rolling window, so the
                    #     next tick can be told not to repeat it. Dialogue is
                    #     included verbatim because near-identical lines are the
                    #     most visible symptom of looping.
                    self._record_action(action_dict)

                    # 6. Store response for token accounting, then return
                    self._last_response = response
                    logger.info(f"Tick decision for {self.state.name}", extra={"action": action_dict, "character": self.state.name})
                    return action_dict

                except ResourceExhausted as e:
                    if attempt == 3:
                        logger.error(f"Rate limit exceeded after 3 retries for {self.state.name}; using fallback action")
                        return self._fallback_action(f"Rate limit: {e}")
                    delay = 2 * (2 ** attempt)
                    logger.warning(f"Rate limit hit for {self.state.name}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    
                except json.JSONDecodeError:
                    if attempt == 3:
                        logger.error(f"Failed to parse JSON for {self.state.name} after 3 retries")
                        return self._fallback_action("Model returned unparseable JSON.")
                    logger.warning(f"Invalid JSON from model for {self.state.name}. Retrying...")
                    current_prompt = prompt + "\n\nYour last output was not valid JSON. Please output strictly valid JSON."

                except Exception as e:
                    # Reactive cache recovery. An expired or deleted cache
                    # surfaces here as a generic error, and the original code
                    # returned a fallback immediately -- so once the cache died
                    # the character emitted "I am confused" for every remaining
                    # tick of the day. Drop the dead handle, rebuild the prompt
                    # so identity and memories are re-sent inline, and retry.
                    if not cache_recovery_attempted and self._is_cache_gone(e):
                        cache_recovery_attempted = True
                        self._drop_cache(f"generate_content failed: {e}")
                        prompt = self._build_tick_prompt(world_state)
                        current_prompt = prompt
                        logger.info(
                            f"Retrying tick for {self.state.name} uncached after cache loss."
                        )
                        continue

                    logger.error(f"Error during tick for {self.state.name}: {e}")
                    return self._fallback_action(f"Tick failed: {e}")

            # Reachable only if the final attempt ended in `continue` (cache
            # recovery on the last pass). tick() is declared -> dict, and the
            # engine reads action["action"], so never fall out as None.
            return self._fallback_action("Exhausted all tick attempts.")
