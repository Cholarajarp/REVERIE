"""CachedContent lifecycle for CharacterAgent.

Two bugs are pinned here, both of which only appear over a long run:

  1. TTL expiry. The cache lives 3600s but a day is 288 ticks. The original code
     never rechecked, so once the cache died `cached_content_name` stayed set,
     _init_cache() never re-ran, and every later generate call failed into the
     fallback -- characters went inert roughly an hour in.

  2. Creation-failure retry storm. On failure `cached_content_name` stayed None,
     so _init_cache() re-ran every tick including a full CachedContent.list()
     scan: 288 wasted round trips per character per day.
"""
from datetime import datetime, timedelta, timezone
import time

import pytest
from google.api_core.exceptions import NotFound, PermissionDenied

from agents.character_agent import CharacterAgent, CACHE_MAX_FAILURES


class FakeState:
    """Stand-in for CharacterState.

    CharacterAgent is duck-typed on these five attributes, and using a plain
    object keeps these tests about cache lifecycle rather than schema validation.
    """

    def __init__(self):
        self.name = "Maya"
        self.current_location = "The Mill"
        self.current_goal = "recover the stolen ledger"
        self.mood = "guarded"
        self.memory_stream = ["saw a light moving in the mill after midnight"]


class FakeWorld:
    def __init__(self):
        self.current_time = datetime(2026, 1, 1, 3, 0, 0)
        self.weather = "Cloudy"
        self.active_characters = ["Maya", "Leo"]


@pytest.fixture
def agent():
    return CharacterAgent(FakeState(), "a watchmaker who never sleeps")


def test_creation_failure_backs_off(agent, monkeypatch):
    """A persistent failure must stop hammering the API."""
    import agents.character_agent as ca

    list_calls = []

    class FailingCache:
        @staticmethod
        def list():
            list_calls.append(1)
            return []

        @staticmethod
        def create(**kwargs):
            raise RuntimeError("429 quota exceeded for CreateCachedContent")

    monkeypatch.setattr(ca, "CachedContent", FailingCache)

    import asyncio

    async def run_ticks():
        for _ in range(40):
            agent.tick_count += 1
            if not agent.cached_content_name:
                await agent._init_cache()

    asyncio.run(run_ticks())

    # Old behaviour: 40 attempts. New: capped, then disabled entirely.
    assert len(list_calls) == CACHE_MAX_FAILURES
    assert agent.cache_disabled is True


def test_uncached_prompt_still_carries_identity_and_memories(agent):
    """Without a cache the personality text is absent from context entirely.

    If it were not re-sent inline the character would speak as a generic voice
    while still appearing to work.
    """
    prompt = agent._build_tick_prompt(FakeWorld())

    assert "YOUR IDENTITY" in prompt
    assert "a watchmaker who never sleeps" in prompt
    assert "saw a light moving in the mill after midnight" in prompt


def test_cached_prompt_omits_identity_block(agent):
    """When cached, re-sending identity would pay for tokens the cache holds."""
    agent.cached_content_name = "projects/p/locations/l/cachedContents/123"
    prompt = agent._build_tick_prompt(FakeWorld())

    assert "YOUR IDENTITY" not in prompt


def test_expired_cache_is_dropped(agent):
    agent.cached_content_name = "caches/123"
    agent.cached_memory_count = 1
    agent.cache_expires_at = time.monotonic() - 1.0

    assert agent._cache_expired() is True

    agent._drop_cache("test")
    assert agent.cached_content_name is None
    # Must reset to 0: an uncached model holds no baked memories, so the whole
    # window has to be replayed.
    assert agent.cached_memory_count == 0
    assert "YOUR IDENTITY" in agent._build_tick_prompt(FakeWorld())


def test_fresh_agent_is_not_considered_expired(agent):
    """cache_expires_at is None before any cache exists; must not report expired."""
    assert agent.cache_expires_at is None
    assert agent._cache_expired() is False


@pytest.mark.parametrize(
    "exc,expected",
    [
        (NotFound("gone"), True),
        (PermissionDenied("denied"), True),
        (RuntimeError("404 CachedContent not found"), True),
        (RuntimeError("cached_content has expired"), True),
        (ValueError("invalid temperature value"), False),
        (RuntimeError("500 internal server error"), False),
        (TimeoutError("deadline exceeded"), False),
    ],
)
def test_cache_gone_classification(exc, expected):
    """Permissive in the safe direction.

    A false positive costs one cache rebuild. A false negative wedges the
    character for the rest of the run, which is the original bug.
    """
    assert CharacterAgent._is_cache_gone(exc) is expected


def test_reused_stale_cache_uses_server_expiry(agent):
    """A cache reused from an earlier run may be nearly dead.

    Assuming a fresh full TTL there would leave us holding a handle that dies on
    the next tick, which is exactly the failure this fix targets.
    """
    class StaleHandle:
        expire_time = datetime.now(timezone.utc) + timedelta(seconds=100)

    agent._set_cache_deadline(StaleHandle())
    remaining = agent.cache_expires_at - time.monotonic()

    # 80% of the 100s actually left, not 80% of the nominal 3600s.
    assert 70 < remaining < 90


def test_missing_expire_time_falls_back_to_ttl(agent):
    """A lightweight test double may omit expire_time; preserve the TTL fallback."""
    class NoExpiry:
        pass

    agent._set_cache_deadline(NoExpiry())
    remaining = agent.cache_expires_at - time.monotonic()

    assert 2800 < remaining < 2900  # 80% of 3600s


def test_fallback_action_is_schema_complete(agent):
    """The engine reads action["action"]; a partial dict would KeyError."""
    action = agent._fallback_action("model unreachable")

    for key in ("recall", "goal_status", "repetition_check", "reflection",
                "action", "target", "reason", "dialogue", "new_memory"):
        assert key in action, f"fallback missing {key}"
    assert action["action"] == "stay"


def test_fallback_is_not_recorded_in_action_window(agent):
    """The window holds 6 entries; a system failure must not evict real dialogue."""
    agent._record_action({"action": "talk", "target": "Leo", "dialogue": "Where were you?"})
    before = list(agent.recent_actions)

    agent._fallback_action("boom")

    assert list(agent.recent_actions) == before


def test_recorded_action_keeps_dialogue_verbatim(agent):
    """Near-identical lines are the visible symptom of looping.

    The model needs the exact text to compare against, not a summary.
    """
    agent.tick_count = 12
    agent._record_action({"action": "talk", "target": "Leo", "dialogue": "Where were you last night?"})

    entry = agent.recent_actions[-1]
    assert "Where were you last night?" in entry
    assert "tick 12" in entry
    assert "Leo" in entry


def test_action_window_is_bounded(agent):
    """A 288-tick day must not grow the prompt without limit."""
    from agents.character_agent import RECENT_ACTION_WINDOW

    for i in range(50):
        agent._record_action({"action": "talk", "target": "Leo", "dialogue": f"line {i}"})

    assert len(agent.recent_actions) == RECENT_ACTION_WINDOW
    assert "line 49" in agent.recent_actions[-1]


def test_memory_delta_is_injected_not_whole_stream(agent):
    """Memories baked into the cache must not be re-sent every tick.

    Re-sending them would forfeit the point of the cache; omitting the NEW ones
    is what caused the deterministic dialogue loop.
    """
    agent.cached_content_name = "caches/123"
    agent.cached_memory_count = 1
    agent.state.memory_stream.append("Leo denied being at the mill")

    prompt = agent._build_tick_prompt(FakeWorld())

    assert "Leo denied being at the mill" in prompt
    assert "saw a light moving in the mill after midnight" not in prompt


async def test_reactive_recovery_retries_uncached(agent, monkeypatch):
    """An expired cache surfaces as a generic error mid-generate.

    The original code returned a fallback immediately, so once the cache died the
    character emitted "I am confused" for every remaining tick.
    """
    import json

    calls = {"n": 0}

    class FlakyAgent:
        async def generate_content_async(self, prompt, generation_config=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise NotFound("cachedContents/123 not found")

            class R:
                text = json.dumps({
                    "recall": "the light in the mill",
                    "goal_status": "ADVANCING",
                    "repetition_check": "NONE",
                    "reflection": "I press on.",
                    "action": "talk",
                    "target": "Leo",
                    "reason": "He was there.",
                    "dialogue": "You were at the mill.",
                    "new_memory": "Confronted Leo about the mill.",
                })
            return R()

    agent.cached_content_name = "caches/123"
    agent.cached_memory_count = 1
    agent.agent = FlakyAgent()
    monkeypatch.setattr(agent, "_build_agent", lambda: FlakyAgent())

    result = await agent.tick(FakeWorld())

    assert calls["n"] == 2, "did not retry after the cache died"
    assert result["action"] == "talk"
    assert result["dialogue"] == "You were at the mill."
    assert agent.cached_content_name is None, "dead cache handle was not released"
    # The successful retry must still form a memory.
    assert "Confronted Leo about the mill." in agent.state.memory_stream
