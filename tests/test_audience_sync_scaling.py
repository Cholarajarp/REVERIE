"""End-to-end WebSocket fan-out across simulated Cloud Run instances.

test_redis_broadcaster covers replication in isolation. This module covers the
wiring: whether a whisper arriving on one instance actually reaches a browser
held by a different instance, and whether the ACK that clears the frontend's
optimistic "ghost bubble" still comes from the instance holding that socket.

Fresh AudienceSyncManager instances are constructed per test rather than using
the module singleton, so each test starts from an empty document.
"""
import asyncio

import pytest
from pycrdt import Doc, Array

import core.redis_broadcaster as rb
from core.audience_sync import AudienceSyncManager


class FakeWebSocket:
    """Minimal duck-type of starlette's WebSocket for the paths connect() uses."""

    def __init__(self, name):
        self.name = name
        self.sent_bytes = []
        self.sent_json = []
        self._inbox = asyncio.Queue()

    async def accept(self):
        pass

    async def send_bytes(self, payload):
        self.sent_bytes.append(payload)

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def receive(self):
        return await self._inbox.get()

    def client_sends(self, payload):
        self._inbox.put_nowait({"type": "websocket.receive", "bytes": payload})

    def acked_ids(self):
        ids = []
        for message in self.sent_json:
            ids.extend(message.get("ack", []))
        return ids

    def errors(self):
        return [m for m in self.sent_json if "error" in m]


class Instance:
    """One Cloud Run container: an AudienceSyncManager plus its broadcaster."""

    def __init__(self, name):
        self.name = name
        self.mgr = AudienceSyncManager()
        self.b = rb.RedisBroadcaster(
            self.mgr.ydoc,
            on_remote_update=self.mgr.deliver_remote_update,
            redis_url="redis://fake",
            instance_id=name,
        )
        self.mgr.attach_broadcaster(self.b)
        self._connections = []

    async def start(self):
        await self.b.start()

    def connect_client(self, websocket, user_id):
        task = asyncio.create_task(self.mgr.connect(websocket, user_id=user_id))
        self._connections.append(task)
        return task

    async def shutdown(self):
        for task in self._connections:
            task.cancel()
        await asyncio.sleep(0.1)
        await self.b.stop()

    def whisper_ids(self):
        return [w["id"] for w in self.mgr.whispers]


def browser_update(whisper):
    """The bytes a browser sends: a whisper appended to its own local doc."""
    doc = Doc()
    doc.get("whispers", type=Array).append(whisper)
    return doc.get_update()


@pytest.fixture
async def cluster(fake_redis_server):
    a, b = Instance("inst-A"), Instance("inst-B")
    await a.start()
    await b.start()
    yield a, b
    await a.shutdown()
    await b.shutdown()


async def test_whisper_crosses_instances_to_other_clients(cluster):
    """The headline fix: half the room no longer sees half the chat."""
    a, b = cluster
    alice, bob = FakeWebSocket("alice"), FakeWebSocket("bob")
    a.connect_client(alice, "alice")
    b.connect_client(bob, "bob")
    await asyncio.sleep(0.3)

    alice.client_sends(browser_update({"id": "w1", "text": "hello", "user": "alice"}))
    await asyncio.sleep(0.6)

    assert a.whisper_ids() == ["w1"]
    assert b.whisper_ids() == ["w1"], "instance B never converged"
    # Snapshot on connect, then the relayed whisper.
    assert len(bob.sent_bytes) >= 2, "bob's browser was never sent the whisper"


async def test_only_the_holding_instance_acks(cluster):
    """ACK clears the frontend ghost bubble, so it must reach the author.

    It must NOT be sent by other instances: they do not hold that socket, and a
    stray ACK would confirm a whisper on the wrong client.
    """
    a, b = cluster
    alice, bob = FakeWebSocket("alice"), FakeWebSocket("bob")
    a.connect_client(alice, "alice")
    b.connect_client(bob, "bob")
    await asyncio.sleep(0.3)

    alice.client_sends(browser_update({"id": "w1", "text": "hi", "user": "alice"}))
    await asyncio.sleep(0.6)

    assert "w1" in alice.acked_ids(), "author never got consensus; ghost would hang at 50%"
    assert "w1" not in bob.acked_ids(), "a non-holding instance ACKed someone else's whisper"


async def test_no_echo_storm(cluster):
    """A republish loop would grow the stream without bound."""
    a, _ = cluster
    alice = FakeWebSocket("alice")
    a.connect_client(alice, "alice")
    await asyncio.sleep(0.3)

    alice.client_sends(browser_update({"id": "w1", "text": "hi", "user": "alice"}))
    await asyncio.sleep(0.8)

    depth = await a.b.redis.xlen(rb.STREAM_KEY)
    assert depth <= 4, f"stream grew to {depth} entries from a single whisper"


async def test_telemetry_payload_stays_bounded(cluster):
    """Telemetry previously re-sent the ENTIRE document every tick.

    ydoc.get_update() returns full state, which grows monotonically, so the
    per-tick frame got steadily larger all day. The observer now supplies
    incremental bytes instead.
    """
    a, _ = cluster
    alice = FakeWebSocket("alice")
    a.connect_client(alice, "alice")
    await asyncio.sleep(0.3)

    sizes = []
    for i in range(4):
        before = len(alice.sent_bytes)
        a.mgr.update_metrics(
            token_burn=1000 * (i + 1),
            tick_latency_ms=12.5,
            drama_score=0.4,
            active_connections=2,
        )
        await asyncio.sleep(0.25)
        new_frames = alice.sent_bytes[before:]
        if new_frames:
            sizes.append(len(new_frames[-1]))

    assert sizes, "no telemetry frame was delivered"
    assert sizes[-1] <= sizes[0] + 12, f"payload is growing per tick: {sizes}"


async def test_telemetry_reaches_other_instances(cluster):
    """Viewers on non-leader instances must still see live metrics."""
    a, b = cluster
    a.mgr.update_metrics(token_burn=4000, tick_latency_ms=10.0, drama_score=0.5,
                         active_connections=3)
    await asyncio.sleep(0.5)

    assert b.mgr.telemetry.get("token_burn") == 4000


async def test_rate_limit_shared_across_instances(cluster):
    """A user must not get a fresh budget per instance."""
    a, _ = cluster
    alice = FakeWebSocket("alice")
    a.connect_client(alice, "alice")
    await asyncio.sleep(0.3)

    for i in range(7):
        alice.client_sends(browser_update({"id": f"r{i}", "text": "spam", "user": "alice"}))
    await asyncio.sleep(1.3)

    committed = [x for x in a.whisper_ids() if x.startswith("r")]
    assert len(committed) == 5, f"limit is 5/min, committed {len(committed)}"
    assert len(alice.errors()) == 2, "over-limit sends were not reported to the client"


async def test_cold_instance_serves_complete_snapshot(cluster):
    """A client landing on a freshly scaled-up instance must see the full feed."""
    a, _ = cluster
    alice = FakeWebSocket("alice")
    a.connect_client(alice, "alice")
    await asyncio.sleep(0.3)

    for i in range(3):
        alice.client_sends(browser_update({"id": f"w{i}", "text": "x", "user": "alice"}))
        await asyncio.sleep(0.2)

    cold = Instance("inst-cold")
    await cold.start()
    try:
        carol = FakeWebSocket("carol")
        cold.connect_client(carol, "carol")
        await asyncio.sleep(0.4)

        assert carol.sent_bytes, "carol received no snapshot at all"
        decoded = Doc()
        whispers = decoded.get("whispers", type=Array)
        decoded.apply_update(carol.sent_bytes[0])
        assert len(whispers) == len(a.whisper_ids()) == 3
    finally:
        await cold.shutdown()


async def test_presence_is_global_and_decrements(cluster):
    """Each instance sees only its own sockets, so the count lives in Redis."""
    a, b = cluster
    alice, bob = FakeWebSocket("alice"), FakeWebSocket("bob")
    task_a = a.connect_client(alice, "alice")
    task_b = b.connect_client(bob, "bob")
    await asyncio.sleep(0.4)

    assert await a.b.get_connection_count() == 2, "local len() would report 1"

    task_a.cancel()
    task_b.cancel()
    await asyncio.sleep(0.3)

    # The finally block in connect() must run even on cancellation, or the
    # audience count drifts upward for the life of the deployment.
    assert await a.b.get_connection_count() == 0


async def test_only_leader_intercepts_audience_events(cluster):
    """Every instance now applies every whisper, so injection must be gated.

    Ungated, an audience-triggered event would fire once per running instance.
    """
    a, b = cluster
    assert await a.b.try_acquire_leadership(ttl_ms=5000) is True
    assert await b.b.try_acquire_leadership(ttl_ms=5000) is False

    logged = []

    import core.audience_sync as sync_module
    original = sync_module.logger.info
    sync_module.logger.info = lambda msg, *args, **kw: logged.append(str(msg))
    try:
        a.mgr.whispers.append({"id": "e1", "text": "introduce event: a letter arrives"})
        await asyncio.sleep(0.3)

        # committed_ids names exactly which whispers to scan, rather than reading
        # whispers[-1], which races against agent dialogue from the tick loop.
        await a.mgr.intercept_events(b"", committed_ids={"e1"})   # leader: acts
        await b.mgr.intercept_events(b"", committed_ids={"e1"})   # follower: silent
    finally:
        sync_module.logger.info = original

    intercepts = [m for m in logged if "Audience event intercepted" in m]
    assert len(intercepts) == 1, f"expected exactly one injection, got {len(intercepts)}"


async def test_agent_dialogue_cannot_trigger_audience_events(cluster):
    """A character saying "a letter arrives" must NOT inject an audience event.

    Agents and the audience now write to the same array. The old whispers[-1] read
    could land on an agent's line, so the simulation would feed its own dialogue
    back to itself as a command -- behaviour that would look inexplicable from
    the outside.
    """
    a, _ = cluster
    assert await a.b.try_acquire_leadership(ttl_ms=5000) is True

    published = await a.mgr.publish_agent_dialogue(
        [("Maya", "Wait -- a letter arrives every morning, always unsigned.")], tick=7
    )
    assert published == 1

    agent_ids = {w["id"] for w in a.mgr.whispers if w["id"].startswith("sim-")}
    assert agent_ids, "agent whisper was not committed"

    logged = []
    import core.audience_sync as sync_module
    original = sync_module.logger.info
    sync_module.logger.info = lambda msg, *args, **kw: logged.append(str(msg))
    try:
        # Even passed in explicitly, agent ids must be filtered out.
        await a.mgr.intercept_events(b"", committed_ids=agent_ids)
    finally:
        sync_module.logger.info = original

    assert [m for m in logged if "Audience event intercepted" in m] == []
