"""Leadership gating for SimulationEngine.run_day.

The property under test is the most consequential one in this change: a Cloud Run
instance that is NOT the simulation leader must write nothing to Firestore.

run_day's `finally` block writes {"is_running": False, "tick_number": 0} to a
single shared checkpoint document. If a second instance entered run_day and then
bailed out, that write would erase the real leader's progress and make the next
resume restart the day from tick 0. It would also flush the second instance's
stale in-memory world and character states, rolling the live simulation backwards.
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from core.simulation_engine import SimulationEngine
from models.schema import WorldState


class FakeBroadcaster:
    """Leadership surface only. Nothing here touches Redis."""

    enabled = True

    def __init__(self, can_lead=True):
        self.can_lead = can_lead
        self._lost = False
        self._is_leader = False
        self.heartbeat_started = False
        self.released = False

    async def try_acquire_leadership(self, ttl_ms=0):
        self._is_leader = self.can_lead
        return self.can_lead

    def start_leadership_heartbeat(self, ttl_ms=0):
        self.heartbeat_started = True

    async def release_leadership(self):
        self.released = True
        self._is_leader = False

    async def get_connection_count(self):
        return 7

    @property
    def leadership_lost(self):
        return self._lost

    @property
    def is_leader(self):
        return self._is_leader and not self._lost


class Recorder:
    """Captures Firestore writes instead of performing them."""

    def __init__(self):
        self.checkpoints = []
        self.world_saves = []
        self.character_saves = []


def make_engine(broadcaster):
    rec = Recorder()

    checkpoint_doc = MagicMock()
    checkpoint_doc.exists = False

    db = MagicMock()
    doc_ref = db.collection.return_value.document.return_value
    doc_ref.get.return_value = checkpoint_doc
    doc_ref.set = lambda data, **kwargs: rec.checkpoints.append(data)

    world_repo = MagicMock()
    world_repo.db = db
    world_repo.save = lambda key, value: rec.world_saves.append(key)

    char_repo = MagicMock()
    char_repo.save = lambda name, state: rec.character_saves.append(name)

    director = MagicMock()

    async def quiet_town(states):
        return {"drama_score": 0.0, "beat": "", "involved_characters": []}

    director.detect_drama = quiet_town

    engine = SimulationEngine(
        characters=[],
        director=director,
        cinematographer=MagicMock(),
        veo=MagicMock(),
        world_repo=world_repo,
        char_repo=char_repo,
        scene_repo=MagicMock(),
        broadcaster=broadcaster,
    )
    return engine, rec


def a_world():
    return WorldState(
        current_time=datetime(2026, 1, 1, 6, 0, 0),
        weather="Sunny",
        active_characters=["Maya"],
        location_populations={"Park": 1},
    )


async def test_non_leader_runs_nothing_and_writes_nothing():
    """The core safety property."""
    bc = FakeBroadcaster(can_lead=False)
    engine, rec = make_engine(bc)

    await engine.run_day(a_world())

    assert rec.checkpoints == [], "a non-leader wrote a checkpoint"
    assert rec.world_saves == [], "a non-leader flushed stale world state"
    assert rec.character_saves == [], "a non-leader flushed stale character state"
    assert engine.is_running is False
    assert bc.heartbeat_started is False


async def test_leader_runs_and_releases_lease():
    bc = FakeBroadcaster(can_lead=True)
    engine, rec = make_engine(bc)

    engine.is_running = True

    import asyncio

    async def stop_after_a_tick():
        await asyncio.sleep(0.05)
        engine.is_running = False

    asyncio.create_task(stop_after_a_tick())
    await engine.run_day(a_world())

    assert bc.heartbeat_started is True, "lease is not being renewed"
    assert bc.released is True, "lease was not released, blocking takeover for the TTL"
    assert rec.checkpoints, "leader never wrote a checkpoint"
    assert rec.checkpoints[-1]["is_running"] is False


async def test_lost_lease_stops_loop_without_clobbering_checkpoint():
    """After losing the lease, another instance owns the state documents."""
    import asyncio

    bc = FakeBroadcaster(can_lead=True)
    engine, rec = make_engine(bc)

    async def steal_the_lease():
        await asyncio.sleep(0)
        bc._lost = True

    asyncio.create_task(steal_the_lease())
    await engine.run_day(a_world())

    destructive = [
        c for c in rec.checkpoints
        if c.get("is_running") is False and c.get("tick_number") == 0
    ]
    assert destructive == [], "the reset write would restart the new leader's day at tick 0"
    assert bc.released is True


async def test_single_instance_mode_still_runs():
    """No broadcaster means no Redis; the loop must work exactly as before."""
    import asyncio

    engine, rec = make_engine(None)
    engine.is_running = True

    async def stop_after_a_tick():
        await asyncio.sleep(0.05)
        engine.is_running = False

    asyncio.create_task(stop_after_a_tick())
    await engine.run_day(a_world())

    assert rec.checkpoints, "single-instance run wrote no checkpoint"


async def test_telemetry_reports_global_audience_not_local():
    """The leader holds only its share of the sockets.

    Publishing its local count would under-report the audience to every viewer.
    """
    import asyncio

    import core.simulation_engine as se

    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)

    bc = FakeBroadcaster(can_lead=True)
    engine, _ = make_engine(bc)

    original = se.audience_sync_manager.update_metrics
    se.audience_sync_manager.update_metrics = capture
    try:
        engine.is_running = True

        async def stop_after_a_tick():
            await asyncio.sleep(0.05)
            engine.is_running = False

        asyncio.create_task(stop_after_a_tick())
        await engine.run_day(a_world())
    finally:
        se.audience_sync_manager.update_metrics = original

    # 7 comes from FakeBroadcaster.get_connection_count, not len(local sockets).
    assert seen.get("active_connections") == 7
