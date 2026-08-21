"""Mood/goal writeback and dialogue publishing.

Before this wiring, three agent outputs were generated and then discarded:

  - `mood` was never persisted, so it stayed at its seed value for the whole run.
    The Director's volatility axis therefore scored a constant, and CURRENT_MOOD
    in each tick prompt never changed.
  - a completed goal had no successor, so the character kept pursuing something
    already finished.
  - `dialogue` reached nothing. The audience saw telemetry and video while the
    actual conversation was invisible.
"""
import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import core.simulation_engine as se
from core.simulation_engine import SimulationEngine, MAX_MOOD_LENGTH, MAX_GOAL_LENGTH
from core.audience_sync import AudienceSyncManager, MAX_WHISPER_LENGTH
from models.schema import CharacterState, WorldState


class ScriptedAgent:
    """Duck-type of CharacterAgent returning a fixed action dict."""

    def __init__(self, name, action, *, goal="find the ledger", mood="calm", delay=0.0):
        self.state = CharacterState(
            name=name,
            current_location="The Mill",
            current_goal=goal,
            mood=mood,
            memory_stream=[],
        )
        self._action = action
        self._delay = delay
        self.tick_calls = 0

    async def tick(self, world_state):
        self.tick_calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._action


def build_engine(agents, published):
    """Engine with Firestore and the whisper feed stubbed out."""
    checkpoint = MagicMock()
    checkpoint.exists = False

    db = MagicMock()
    doc_ref = db.collection.return_value.document.return_value
    doc_ref.get.return_value = checkpoint
    doc_ref.set = lambda data, **kwargs: None

    world_repo = MagicMock()
    world_repo.db = db
    world_repo.save = lambda key, value: None

    director = MagicMock()

    async def quiet_town(states):
        return {"drama_score": 0.0, "beat": "", "involved_characters": []}

    director.detect_drama = quiet_town

    engine = SimulationEngine(
        characters=agents,
        director=director,
        cinematographer=MagicMock(),
        veo=MagicMock(),
        world_repo=world_repo,
        char_repo=MagicMock(),
        scene_repo=MagicMock(),
        broadcaster=None,
    )
    return engine


async def run_one_tick(engine):
    """Runs exactly one tick, then stops the loop."""
    engine.is_running = True

    async def stop():
        await asyncio.sleep(0.05)
        engine.is_running = False

    asyncio.create_task(stop())
    await engine.run_day(
        WorldState(
            current_time=datetime(2026, 1, 1, 6, 0, 0),
            weather="Sunny",
            active_characters=["Maya", "Leo"],
            location_populations={"The Mill": 2},
        )
    )


@pytest.fixture
def captured(monkeypatch):
    """Captures what the engine sends to the whisper feed."""
    calls = []

    async def fake_publish(lines, tick):
        calls.append({"lines": list(lines), "tick": tick})
        return len(lines)

    monkeypatch.setattr(
        se.audience_sync_manager, "publish_agent_dialogue", fake_publish
    )
    return calls


# --- mood -------------------------------------------------------------------

async def test_mood_is_persisted(captured):
    agent = ScriptedAgent("Maya", {
        "action": "talk", "target": "Leo", "dialogue": "You lied to me.",
        "goal_status": "ADVANCING", "mood": "quietly furious", "next_goal": None,
    }, mood="calm")

    await run_one_tick(build_engine([agent], captured))

    assert agent.state.mood == "quietly furious"


async def test_missing_mood_leaves_existing_value(captured):
    """A model omission must not blank out emotional state."""
    agent = ScriptedAgent("Maya", {
        "action": "stay", "target": None, "dialogue": None,
        "goal_status": "ADVANCING", "next_goal": None,
    }, mood="guarded")

    await run_one_tick(build_engine([agent], captured))

    assert agent.state.mood == "guarded"


async def test_null_mood_from_fallback_leaves_existing_value(captured):
    """_fallback_action returns mood=None on purpose.

    An API outage must not silently rewrite a character's emotional state, since
    that mood then feeds every later prompt.
    """
    agent = ScriptedAgent("Maya", {
        "action": "stay", "target": None, "dialogue": None,
        "goal_status": "BLOCKED", "mood": None, "next_goal": None,
    }, mood="hopeful")

    await run_one_tick(build_engine([agent], captured))

    assert agent.state.mood == "hopeful"


async def test_blank_mood_is_ignored(captured):
    agent = ScriptedAgent("Maya", {
        "action": "stay", "target": None, "dialogue": None,
        "goal_status": "ADVANCING", "mood": "   ", "next_goal": None,
    }, mood="wary")

    await run_one_tick(build_engine([agent], captured))

    assert agent.state.mood == "wary"


async def test_overlong_mood_is_truncated(captured):
    """Mood is re-injected into every prompt and checkpointed, so it is bounded."""
    agent = ScriptedAgent("Maya", {
        "action": "stay", "target": None, "dialogue": None,
        "goal_status": "ADVANCING", "mood": "brooding " * 40, "next_goal": None,
    })

    await run_one_tick(build_engine([agent], captured))

    assert len(agent.state.mood) <= MAX_MOOD_LENGTH


# --- goal succession --------------------------------------------------------

async def test_completed_goal_adopts_successor(captured):
    agent = ScriptedAgent("Maya", {
        "action": "stay", "target": None, "dialogue": None,
        "goal_status": "COMPLETE", "mood": "settled",
        "next_goal": "find out who sent the letter",
    }, goal="recover the stolen ledger")

    await run_one_tick(build_engine([agent], captured))

    assert agent.state.current_goal == "find out who sent the letter"


@pytest.mark.parametrize("status", ["ADVANCING", "BLOCKED"])
async def test_goal_is_not_replaced_while_unfinished(captured, status):
    """The long-term goal is the character's spine.

    A dull tick must not let it trade the goal away -- that is exactly the drift
    the prompt work was meant to stop.
    """
    agent = ScriptedAgent("Maya", {
        "action": "stay", "target": None, "dialogue": None,
        "goal_status": status, "mood": "restless",
        "next_goal": "take up gardening instead",
    }, goal="recover the stolen ledger")

    await run_one_tick(build_engine([agent], captured))

    assert agent.state.current_goal == "recover the stolen ledger"


async def test_complete_without_successor_keeps_goal(captured):
    """Better a stale goal than an empty one; an empty goal breaks the prompt."""
    agent = ScriptedAgent("Maya", {
        "action": "stay", "target": None, "dialogue": None,
        "goal_status": "COMPLETE", "mood": "spent", "next_goal": None,
    }, goal="recover the stolen ledger")

    await run_one_tick(build_engine([agent], captured))

    assert agent.state.current_goal == "recover the stolen ledger"


async def test_overlong_goal_is_truncated(captured):
    agent = ScriptedAgent("Maya", {
        "action": "stay", "target": None, "dialogue": None,
        "goal_status": "COMPLETE", "mood": "ok",
        "next_goal": "x" * 900,
    })

    await run_one_tick(build_engine([agent], captured))

    assert len(agent.state.current_goal) <= MAX_GOAL_LENGTH


# --- dialogue reaching the feed --------------------------------------------

async def test_dialogue_is_published(captured):
    agent = ScriptedAgent("Maya", {
        "action": "talk", "target": "Leo", "dialogue": "You were at the mill.",
        "goal_status": "ADVANCING", "mood": "sharp", "next_goal": None,
    })

    await run_one_tick(build_engine([agent], captured))

    assert captured, "dialogue never reached the whisper feed"
    assert captured[0]["lines"] == [("Maya", "You were at the mill.")]
    assert captured[0]["tick"] == 1


async def test_non_talk_actions_publish_nothing(captured):
    """`dialogue` is only meaningful when the character actually speaks."""
    agent = ScriptedAgent("Maya", {
        "action": "move", "target": "Park", "dialogue": "stray text",
        "goal_status": "ADVANCING", "mood": "hurried", "next_goal": None,
    })

    await run_one_tick(build_engine([agent], captured))

    assert captured == []
    assert agent.state.current_location == "Park"


async def test_blank_dialogue_publishes_nothing(captured):
    agent = ScriptedAgent("Maya", {
        "action": "talk", "target": "Leo", "dialogue": "   ",
        "goal_status": "ADVANCING", "mood": "quiet", "next_goal": None,
    })

    await run_one_tick(build_engine([agent], captured))

    assert captured == []


async def test_dialogue_order_follows_cast_not_model_latency(captured):
    """Ordering must be deterministic.

    asyncio.gather preserves input order, so a slow first responder still appears
    first. Appending to a shared list would have ordered by reply speed instead,
    making the transcript non-reproducible.
    """
    slow = ScriptedAgent("Maya", {
        "action": "talk", "target": "Leo", "dialogue": "First.",
        "goal_status": "ADVANCING", "mood": "a", "next_goal": None,
    }, delay=0.15)
    fast = ScriptedAgent("Leo", {
        "action": "talk", "target": "Maya", "dialogue": "Second.",
        "goal_status": "ADVANCING", "mood": "b", "next_goal": None,
    }, delay=0.0)

    await run_one_tick(build_engine([slow, fast], captured))

    assert captured[0]["lines"] == [("Maya", "First."), ("Leo", "Second.")]


async def test_one_agent_failing_does_not_silence_the_others(captured):
    class Broken(ScriptedAgent):
        async def tick(self, world_state):
            raise RuntimeError("model exploded")

    broken = Broken("Zara", {})
    healthy = ScriptedAgent("Leo", {
        "action": "talk", "target": "Maya", "dialogue": "Still here.",
        "goal_status": "ADVANCING", "mood": "steady", "next_goal": None,
    })

    await run_one_tick(build_engine([broken, healthy], captured))

    assert captured[0]["lines"] == [("Leo", "Still here.")]


async def test_feed_failure_does_not_stop_the_simulation(monkeypatch):
    """A broken whisper feed must not take down the tick loop."""
    async def boom(lines, tick):
        raise RuntimeError("redis down")

    monkeypatch.setattr(se.audience_sync_manager, "publish_agent_dialogue", boom)

    agent = ScriptedAgent("Maya", {
        "action": "talk", "target": "Leo", "dialogue": "Anyone there?",
        "goal_status": "ADVANCING", "mood": "tense", "next_goal": None,
    })
    engine = build_engine([agent], [])

    await run_one_tick(engine)   # must not raise

    assert agent.tick_calls == 1
    assert agent.state.mood == "tense", "writeback ran despite the feed failing"


# --- publish_agent_dialogue itself -----------------------------------------

@pytest.fixture
def manager():
    return AudienceSyncManager()


async def test_publish_commits_expected_shape(manager):
    count = await manager.publish_agent_dialogue([("Maya", "The mill was lit.")], tick=4)

    assert count == 1
    entry = manager.whispers[0]
    assert entry["user"] == "Maya"
    assert entry["text"] == "The mill was lit."
    assert entry["id"].startswith("sim-4-Maya-")
    # ISO-8601, because the frontend localises at render time and would otherwise
    # print a raw timestamp.
    assert "T" in entry["ts"]


async def test_publish_is_one_transaction_per_tick(manager):
    """Five speaking characters should cost one CRDT update, not five."""
    updates = []
    manager.ydoc.observe(lambda e: updates.append(bytes(e.update)))

    await manager.publish_agent_dialogue(
        [("Maya", "One."), ("Leo", "Two."), ("Zara", "Three.")], tick=9
    )

    assert len(updates) == 1
    assert len(manager.whispers) == 3


async def test_publish_ids_are_unique_across_replayed_ticks(manager):
    """Resuming from a checkpoint replays tick numbers.

    A colliding id would make the frontend merge the new line into the old bubble
    instead of appending it.
    """
    await manager.publish_agent_dialogue([("Maya", "Again.")], tick=5)
    await manager.publish_agent_dialogue([("Maya", "Again.")], tick=5)

    ids = [w["id"] for w in manager.whispers]
    assert len(ids) == len(set(ids)) == 2


async def test_publish_skips_empty_and_non_string(manager):
    count = await manager.publish_agent_dialogue(
        [("Maya", ""), ("Leo", "   "), ("Zara", None), ("Tom", "Real line.")], tick=2
    )

    assert count == 1
    assert [w["user"] for w in manager.whispers] == ["Tom"]


async def test_publish_truncates_long_dialogue(manager):
    await manager.publish_agent_dialogue([("Maya", "z" * 5000)], tick=1)

    assert len(manager.whispers[0]["text"]) == MAX_WHISPER_LENGTH


async def test_history_is_trimmed(manager, monkeypatch):
    """Every new client is sent full document state.

    Untrimmed, ~1440 agent lines per day would inflate the cold-start snapshot
    and the Redis snapshot along with it.
    """
    import core.audience_sync as sync_module
    monkeypatch.setattr(sync_module, "MAX_WHISPER_HISTORY", 10)

    for tick in range(8):
        await manager.publish_agent_dialogue(
            [("Maya", f"line {tick}a"), ("Leo", f"line {tick}b")], tick=tick
        )

    assert len(manager.whispers) == 10
    # Trimming drops the oldest, so the newest must survive.
    assert manager.whispers[-1]["text"] == "line 7b"


async def test_agent_ids_excluded_from_ack_replay(manager):
    """ACKs settle a client's optimistic ghost.

    No client waits on an agent's line, so replaying ~500 agent ids to every
    connecting viewer is pure handshake weight.
    """
    await manager.publish_agent_dialogue([("Maya", "Agent line.")], tick=1)
    manager.whispers.append({"id": "client-abc", "user": "Viewer", "text": "hi", "ts": "x"})

    assert manager._whisper_ids(client_only=True) == {"client-abc"}
    assert len(manager._whisper_ids()) == 2
