"""Replication invariants for RedisBroadcaster.

These tests exist because the whole Cloud Run design rests on two pycrdt
properties that are easy to assume and expensive to get wrong:

  - applying a duplicate update is a no-op AND does not re-fire observers,
    so echo cannot loop;
  - concurrent updates converge regardless of apply order, so a lagging
    reader is still correct.

Each test simulates separate Cloud Run instances sharing one Redis.
"""
import asyncio

import pytest
from pycrdt import Doc, Array

import core.redis_broadcaster as rb


class Instance:
    """One Cloud Run container: a Doc, a broadcaster, and its local clients."""

    def __init__(self, name):
        self.name = name
        self.doc = Doc()
        self.arr = self.doc.get("whispers", type=Array)
        self.delivered = []   # bytes pushed to this instance's websockets
        self.published = []   # bytes this instance sent to Redis
        self.b = rb.RedisBroadcaster(
            self.doc,
            on_remote_update=self._deliver,
            redis_url="redis://fake",
            instance_id=name,
        )
        self.doc.observe(self._on_change)

    def _on_change(self, event):
        if event.transaction.origin() == rb.REMOTE_ORIGIN:
            return  # arrived from Redis; republishing would be a pointless hop
        update = bytes(event.update)
        self.published.append(update)
        asyncio.get_running_loop().create_task(self.b.publish(update))

    async def _deliver(self, update):
        self.delivered.append(update)

    def ids(self):
        return [w["id"] for w in self.arr]


@pytest.fixture
async def two_instances(fake_redis_server):
    a, b = Instance("inst-A"), Instance("inst-B")
    await a.b.start()
    await b.b.start()
    yield a, b
    await a.b.stop()
    await b.b.stop()


async def test_update_reaches_other_instance(two_instances):
    """The core fix: a whisper on A must reach clients held by B."""
    a, b = two_instances
    a.arr.append({"id": "w1", "text": "hello"})
    await asyncio.sleep(0.5)

    assert b.ids() == ["w1"], "B never converged on A's whisper"
    assert len(b.delivered) == 1, "B did not forward the update to its own clients"


async def test_remote_updates_are_not_republished(two_instances):
    """Echo suppression. Without it, A and B would trade the same bytes forever."""
    a, b = two_instances
    a.arr.append({"id": "w1"})
    await asyncio.sleep(0.5)

    assert b.published == [], "B republished an update that came from Redis"


async def test_bidirectional_convergence(two_instances):
    a, b = two_instances
    a.arr.append({"id": "from-a"})
    b.arr.append({"id": "from-b"})
    await asyncio.sleep(0.6)

    assert sorted(a.ids()) == sorted(b.ids()) == ["from-a", "from-b"]


async def test_cold_instance_hydrates_full_history(two_instances):
    """A scaled-up instance must not start with an empty feed."""
    a, _ = two_instances
    for i in range(3):
        a.arr.append({"id": f"w{i}"})
    await asyncio.sleep(0.5)

    cold = Instance("inst-cold")
    await cold.b.start()
    try:
        assert sorted(cold.ids()) == ["w0", "w1", "w2"]
        assert await cold.b.wait_until_ready(timeout=2.0) is True
    finally:
        await cold.b.stop()


async def test_rate_limit_is_global(two_instances):
    """Per-process windows allowed limit*N sends, and reset on reconnect."""
    a, b = two_instances
    results = [await a.b.check_rate_limit("u1", limit=5, window_ms=60_000) for _ in range(7)]
    assert results == [True] * 5 + [False] * 2

    # Same user arriving via a different instance must NOT get a fresh budget.
    assert await b.b.check_rate_limit("u1", limit=5, window_ms=60_000) is False
async def test_leader_election_is_exclusive(two_instances):
    """Guards against N instances each running the 288-tick loop."""
    a, b = two_instances
    third = Instance("inst-C")
    await third.b.start()
    try:
        claims = [
            await a.b.try_acquire_leadership(ttl_ms=5000),
            await b.b.try_acquire_leadership(ttl_ms=5000),
            await third.b.try_acquire_leadership(ttl_ms=5000),
        ]
        assert claims.count(True) == 1, f"expected exactly one leader, got {claims}"

        leader = [i for i, c in zip((a, b, third), claims) if c][0]
        assert leader.b.is_leader is True
        assert await leader.b.renew_leadership(5000) is True

        others = [i for i, c in zip((a, b, third), claims) if not c]
        for other in others:
            assert other.b.is_leader is False
            assert await other.b.renew_leadership(5000) is False

        await leader.b.release_leadership()
        assert await others[0].b.try_acquire_leadership(5000) is True
    finally:
        await third.b.stop()


async def test_is_leader_false_before_acquiring(two_instances):
    """`not leadership_lost` is NOT a leadership check.

    leadership_lost starts False on an instance that never tried to acquire, so
    gating work on it would let every non-leader act.
    """
    a, _ = two_instances
    assert a.b.leadership_lost is False
    assert a.b.is_leader is False


async def test_heartbeat_detects_stolen_lease(two_instances):
    """A stalled leader must notice, or two instances write the same checkpoint."""
    a, b = two_instances
    assert await a.b.try_acquire_leadership(ttl_ms=1200) is True
    a.b.start_leadership_heartbeat(ttl_ms=1200)
    assert a.b.leadership_lost is False

    # Simulate the lease lapsing and another instance taking over.
    await a.b.redis.delete(rb.LEADER_LOCK_KEY)
    await b.b.try_acquire_leadership(ttl_ms=9000)

    # Heartbeat interval is max(1.0, ttl/3) == 1.0s here; wait past one beat.
    await asyncio.sleep(1.8)
    assert a.b.leadership_lost is True
    assert a.b.is_leader is False


async def test_compaction_bounds_hydration(two_instances, monkeypatch):
    """Without compaction, cold-start replay grows with deployment uptime."""
    monkeypatch.setattr(rb, "COMPACT_THRESHOLD", 10)
    a, _ = two_instances

    for i in range(14):
        a.arr.append({"id": f"c{i}"})
    await asyncio.sleep(1.5)

    snapshot = await a.b.redis.get(rb.SNAPSHOT_KEY)
    assert snapshot is not None, "stream exceeded threshold but was never compacted"

    cold = Instance("inst-post-compact")
    await cold.b.start()
    try:
        # Full history still recoverable from snapshot plus the remaining tail.
        assert len(cold.ids()) == 14
    finally:
        await cold.b.stop()


async def test_presence_counts_across_instances(two_instances):
    a, b = two_instances
    assert await a.b.track_connection(+1) == 1
    assert await b.b.track_connection(+1) == 2
    assert await a.b.get_connection_count() == 2

    await a.b.track_connection(-1)
    await b.b.track_connection(-1)
    assert await a.b.get_connection_count() == 0


async def test_presence_never_goes_negative(two_instances):
    """Crashed instances cannot run their decrement, so the counter can drift."""
    a, _ = two_instances
    assert await a.b.track_connection(-5) == 0


async def test_disabled_without_redis_url(monkeypatch):
    """No REDIS_URL must degrade to single-instance, not crash at startup."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    doc = Doc()

    async def noop(_):
        pass

    bc = rb.RedisBroadcaster(doc, on_remote_update=noop, redis_url="")
    assert bc.enabled is False
    await bc.start()                                   # no-op, must not raise
    await bc.publish(b"anything")                      # no-op, must not raise
    assert await bc.check_rate_limit("u") is True       # falls back to local window
    assert await bc.try_acquire_leadership() is True    # trivially the leader
    assert await bc.track_connection(+1) is None        # signals "use local count"
    await bc.stop()
