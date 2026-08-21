"""Cross-instance state fan-out for REVERIE on Cloud Run.

WHY THIS EXISTS
---------------
Cloud Run is stateless and horizontally autoscaled. Three consequences break the
current single-process design:

  1. WebSocket fan-out fractures. `AudienceSyncManager.active_connections` is a
     process-local dict, so a whisper delivered to instance A is invisible to
     audience members held by instance B. Half the room sees half the chat.

  2. The CRDT document fractures. Each instance holds its own `pycrdt.Doc`, so
     the "shared" document silently forks into N divergent documents.

  3. The simulation loop multiplies. `/start_simulation` schedules a 288-tick
     BackgroundTask on whichever instance received the POST. Under autoscaling,
     N instances each run a full day -- multiplying Vertex AI and Veo spend by N
     and racing N writers onto one Firestore checkpoint document.

This module makes the pycrdt document global by routing every update through a
Redis Stream that all instances read, and provides the leader lock that keeps
the simulation loop singular.

WHY REDIS STREAMS RATHER THAN PUB/SUB
-------------------------------------
Cloud Pub/Sub is a fine transport but solves only one of the three problems.
Specifically, a *shared* Pub/Sub subscription load-balances: exactly one
subscriber receives each message, which is the opposite of fan-out. Getting
broadcast semantics requires one subscription per instance, created on startup
and deleted on shutdown -- and Cloud Run SIGKILLs instances 10s after SIGTERM,
so subscriptions leak, retain messages for days, and accrue cost until a janitor
reaps them.

Beyond transport we also need:
  - A snapshot for hydration. A cold instance's Doc is empty, and a newly
    connected client must receive the whole conversation. Pub/Sub cannot replay
    to a subscription that did not exist when the message was published.
  - A shared rate limiter. The in-memory sliding window allows 5 whispers per
    minute *per instance*, so the real limit is 5N.
  - A leader lock for problem 3.

Redis Streams give ordered durable replay (hydration), and the same Redis gives
atomic Lua evaluation (rate limit) and SET NX PX (leader lock). One dependency
instead of three, and Memorystore sits in the same VPC so RTT is sub-millisecond.

CORRECTNESS NOTES
-----------------
This design leans on two pycrdt properties, both verified experimentally against
pycrdt 0.14.2 rather than assumed:

  - Applying the same update twice is a no-op AND does not re-fire observers.
    That is what makes echo suppression safe: a duplicate cannot loop.
  - Applying two concurrent updates in opposite orders converges to identical
    state. Stream ordering is therefore a convenience, not a requirement, so a
    reader that falls behind or replays is still correct.

Together these mean "every instance applies every update from a shared log"
needs no coordination on the hot path.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Awaitable, Callable, Optional

from pycrdt import Doc

from core.logger import get_logger

logger = get_logger(__name__)

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:  # local dev without the dependency installed
    aioredis = None
    REDIS_AVAILABLE = False


# --- Redis keyspace -------------------------------------------------------
STREAM_KEY = "reverie:doc:updates"
SNAPSHOT_KEY = "reverie:doc:snapshot"
SNAPSHOT_CURSOR_KEY = "reverie:doc:snapshot_cursor"
COMPACT_LOCK_KEY = "reverie:lock:compact"
LEADER_LOCK_KEY = "reverie:lock:simulation_leader"
RATE_KEY_PREFIX = "reverie:rate:"
PRESENCE_KEY = "reverie:presence:count"

# Stream field names, as bytes because the payload itself is binary.
FIELD_UPDATE = b"u"
FIELD_ORIGIN = b"o"

# Transaction origin marking "this arrived from Redis, do not re-publish it".
#
# Deliberately a plain int. pycrdt passes non-int origins through Python's
# built-in hash(), which is randomized per process for str and bytes, so a
# string origin does NOT compare equal across instances -- or even across
# restarts of the same instance. Verified: int origins round-trip exactly,
# str/bytes origins come back as unstable hashes.
REMOTE_ORIGIN = 0x2E4E51E

# Cap the stream so an unattended deployment cannot grow it without bound.
# 288 ticks of telemetry plus audience chatter fits comfortably.
STREAM_MAXLEN = 10_000

# Compact once the stream exceeds this length. Bounds cold-start hydration cost,
# which would otherwise grow linearly with deployment uptime.
COMPACT_THRESHOLD = 500

# Prune, count, and insert must not interleave with another instance's, so the
# sliding window is evaluated server-side as one atomic script.
_SLIDING_WINDOW_LUA = """
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
if redis.call('ZCARD', KEYS[1]) >= limit then
  return 0
end
redis.call('ZADD', KEYS[1], now, member)
redis.call('PEXPIRE', KEYS[1], window)
return 1
"""
class RedisBroadcaster:
    """Replicates one pycrdt Doc across every Cloud Run instance.

    Usage:
        b = RedisBroadcaster(doc, on_remote_update=manager.deliver_to_local_clients)
        await b.start()     # hydrate from Redis, then tail the stream
        await b.publish(update_bytes)
        await b.stop()

    The broadcaster owns replication only. It never touches WebSockets: it hands
    freshly-applied bytes to `on_remote_update` and lets the caller decide who to
    deliver them to. Connection management stays in one place, and this class
    stays testable without a socket.
    """

    def __init__(
        self,
        doc: Doc,
        on_remote_update: Callable[[bytes], Awaitable[None]],
        redis_url: Optional[str] = None,
        instance_id: Optional[str] = None,
    ):
        self.doc = doc
        self.on_remote_update = on_remote_update
        self.redis_url = redis_url or os.getenv("REDIS_URL", "")
        # Must be unique per process, not per revision: CLOUD_RUN_EXECUTION is
        # shared by all instances of a Job, so a random suffix is always added.
        self.instance_id = instance_id or f"{os.getenv('K_REVISION', 'local')}-{uuid.uuid4().hex[:8]}"

        self.redis: Optional["aioredis.Redis"] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._cursor = "0-0"
        self._running = False
        self._rate_script = None
        self._hydrated = asyncio.Event()

        # Leadership lease state. The heartbeat renews on a timer rather than
        # per-tick, because a Veo-generating tick can outlive the lease.
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._leadership_lost = asyncio.Event()
        # Positive "I currently hold the lock" flag. Distinct from
        # `not leadership_lost`, which is also False on an instance that never
        # tried to acquire -- so callers gating work on leadership need this.
        self._is_leader = False

        # Degraded mode: no REDIS_URL, or the library is not installed. The app
        # still serves a single instance correctly, so local development and a
        # plain `docker run` keep working without a Redis dependency.
        self.enabled = bool(self.redis_url) and REDIS_AVAILABLE
        if not self.enabled:
            reason = "REDIS_URL not set" if REDIS_AVAILABLE else "redis package not installed"
            logger.warning(
                f"RedisBroadcaster disabled ({reason}). Running single-instance: state "
                f"will NOT be shared across Cloud Run instances. Either set REDIS_URL or "
                f"pin --max-instances=1, otherwise the audience fractures under autoscaling."
            )
            self._hydrated.set()

    # --- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        if not self.enabled:
            return

        self.redis = aioredis.from_url(
            self.redis_url,
            decode_responses=False,  # update payloads are binary
            socket_keepalive=True,
            health_check_interval=30,
        )
        await self.redis.ping()
        self._rate_script = self.redis.register_script(_SLIDING_WINDOW_LUA)

        await self._hydrate()

        self._running = True
        self._reader_task = asyncio.create_task(self._reader_loop())
        logger.info(
            "RedisBroadcaster started",
            extra={"instance_id": self.instance_id, "cursor": self._cursor},
        )

    async def stop(self) -> None:
        """Shuts down cleanly. Cloud Run allows ~10s after SIGTERM.

        Releases leadership first so a replacement instance can pick up the
        simulation immediately instead of waiting out the lease TTL.
        """
        self._running = False
        await self.release_leadership()
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self.redis:
            await self.redis.aclose()
            self.redis = None
        logger.info("RedisBroadcaster stopped")

    async def wait_until_ready(self, timeout: float = 10.0) -> bool:
        """Blocks until the local Doc reflects global state.

        Call this before sending a client its first snapshot. Without it, a
        client connecting to a cold instance receives an empty document, then
        watches the entire backlog pop in once hydration lands. It converges
        either way, but it looks broken.
        """
        try:
            await asyncio.wait_for(self._hydrated.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            logger.error(f"Hydration timed out after {timeout}s; serving possibly-stale doc")
            return False

    # --- hydration --------------------------------------------------------

    async def _hydrate(self) -> None:
        """Rebuilds local Doc state from snapshot plus stream tail.

        Two phases because the stream is trimmed: the snapshot holds everything
        older than the trim horizon, the stream holds everything since. The
        cursor stored beside the snapshot stitches them. Overlap is harmless
        anyway, since re-applying a known update is a verified no-op.
        """
        try:
            snapshot, cursor = await self.redis.mget(SNAPSHOT_KEY, SNAPSHOT_CURSOR_KEY)

            if snapshot:
                # origin=REMOTE_ORIGIN so the local observer does not mistake
                # hydration for a local edit and republish the whole history.
                with self.doc.transaction(origin=REMOTE_ORIGIN):
                    self.doc.apply_update(snapshot)
                self._cursor = cursor.decode() if cursor else "0-0"
                logger.info(f"Applied snapshot ({len(snapshot)}B) at cursor {self._cursor}")

            # Exclusive range so the snapshot's own cursor entry is not
            # re-applied. Requires Redis >= 6.2 (Memorystore default is 7.x).
            start = f"({self._cursor}" if snapshot and self._cursor != "0-0" else "-"
            entries = await self.redis.xrange(STREAM_KEY, min=start)

            applied = 0
            for entry_id, fields in entries:
                update = fields.get(FIELD_UPDATE)
                if update:
                    with self.doc.transaction(origin=REMOTE_ORIGIN):
                        self.doc.apply_update(update)
                    applied += 1
                self._cursor = entry_id.decode()

            logger.info(
                f"Hydration complete: replayed {applied} stream entries",
                extra={"instance_id": self.instance_id, "cursor": self._cursor},
            )
        except Exception as e:
            # Serving a stale doc beats refusing connections. CRDT convergence
            # means a missed update is repaired by the next one that arrives.
            logger.error(f"Hydration failed, continuing with local state: {e}")
        finally:
            self._hydrated.set()

    # --- publish / receive ------------------------------------------------

    async def publish(self, update: bytes) -> None:
        """Appends a locally-produced update to the global stream.

        Best-effort by design: the caller has already applied the update to its
        own Doc and answered its own client, so a Redis hiccup must not fail the
        user's request. Once XADD returns, the update is durable and every other
        instance will see it.
        """
        if not self.enabled or not self.redis:
            return
        try:
            await self.redis.xadd(
                STREAM_KEY,
                {FIELD_UPDATE: update, FIELD_ORIGIN: self.instance_id.encode()},
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )
        except Exception as e:
            logger.error(f"Failed to publish update to Redis stream: {e}")

    async def _reader_loop(self) -> None:
        """Tails the stream and applies everything other instances wrote.

        XREAD BLOCK is a long poll, so cross-instance latency is push-like
        rather than a polling interval, without spinning the CPU.
        """
        backoff = 1.0
        while self._running:
            try:
                response = await self.redis.xread(
                    {STREAM_KEY: self._cursor}, block=5000, count=100
                )
                backoff = 1.0
                if not response:
                    continue  # block timeout, nothing published

                for _stream_key, entries in response:
                    for entry_id, fields in entries:
                        self._cursor = entry_id.decode()
                        origin = fields.get(FIELD_ORIGIN, b"").decode()
                        update = fields.get(FIELD_UPDATE)
                        if not update:
                            continue

                        # Skip our own writes. Re-applying them is already a
                        # verified no-op, but forwarding them again would hand
                        # every local client a second copy of bytes it just got.
                        if origin == self.instance_id:
                            continue

                        with self.doc.transaction(origin=REMOTE_ORIGIN):
                            self.doc.apply_update(update)

                        await self.on_remote_update(update)

                await self._maybe_compact()

            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Memorystore failover takes seconds. Back off instead of spinning.
                logger.error(f"Stream reader error (retrying in {backoff}s): {e}")
                await asyncio.sleep(backoff)
                backoff = min(30.0, backoff * 2)
    # --- compaction -------------------------------------------------------

    async def _maybe_compact(self) -> None:
        """Collapses the stream into a single snapshot, under a global lock.

        Without this, cold-start hydration cost grows linearly with deployment
        uptime: a new instance would replay every update ever sent. The lock
        ensures exactly one instance pays the CPU cost, and its short TTL means a
        crashed holder cannot block compaction permanently.
        """
        try:
            if await self.redis.xlen(STREAM_KEY) < COMPACT_THRESHOLD:
                return

            got_lock = await self.redis.set(
                COMPACT_LOCK_KEY, self.instance_id, nx=True, px=30_000
            )
            if not got_lock:
                return

            try:
                # The local Doc already contains every entry up to _cursor, so
                # its own full state IS the compacted snapshot. No merge needed.
                snapshot = self.doc.get_update()
                cursor = self._cursor

                pipe = self.redis.pipeline()
                pipe.set(SNAPSHOT_KEY, snapshot)
                pipe.set(SNAPSHOT_CURSOR_KEY, cursor)
                await pipe.execute()

                # Trim only after the snapshot is durable. A crash between the
                # two leaves a merely-larger stream, never a gap.
                await self.redis.xtrim(STREAM_KEY, minid=cursor, approximate=False)
                logger.info(f"Compacted stream into {len(snapshot)}B snapshot at {cursor}")
            finally:
                # Release only if the lock is still ours, so an expired lease
                # cannot be deleted out from under its new owner.
                if (await self.redis.get(COMPACT_LOCK_KEY)) == self.instance_id.encode():
                    await self.redis.delete(COMPACT_LOCK_KEY)
        except Exception as e:
            logger.error(f"Compaction failed (harmless, will retry): {e}")

    # --- shared rate limiting --------------------------------------------

    async def check_rate_limit(self, user_id: str, limit: int = 5, window_ms: int = 60_000) -> bool:
        """Global sliding-window limiter, atomic across all instances.

        Replaces the per-process dict in AudienceSyncManager, which allowed
        limit*N whispers per minute because each instance tracked its own
        window -- and a client reconnecting through a different instance got a
        fresh allowance.
        """
        if not self.enabled or not self._rate_script:
            return True  # caller falls back to its local window
        try:
            allowed = await self._rate_script(
                keys=[f"{RATE_KEY_PREFIX}{user_id}"],
                args=[int(time.time() * 1000), window_ms, limit, uuid.uuid4().hex],
            )
            return bool(allowed)
        except Exception as e:
            # Fail open: a Redis outage should not silence the whole audience.
            logger.error(f"Rate limit check failed, allowing request: {e}")
            return True

    # --- global presence count -------------------------------------------

    async def track_connection(self, delta: int) -> Optional[int]:
        """Adjusts the global connection count and returns the new total.

        Needed because each instance knows only its own sockets. If every
        instance wrote len(self.active_connections) into the shared telemetry
        Map, they would overwrite each other and the displayed audience size
        would flap between per-instance counts instead of summing to the real
        total.

        Returns None when Redis is unavailable, meaning "use your local count".
        """
        if not self.enabled or not self.redis:
            return None
        try:
            total = await self.redis.incrby(PRESENCE_KEY, delta)
            # A crashed instance cannot run its own decrement, so the counter can
            # drift upward over a long deployment. Clamp the floor and let the
            # TTL below expire the key entirely once the room is empty.
            if total < 0:
                await self.redis.set(PRESENCE_KEY, 0)
                total = 0
            # Refreshed on every change, so an idle-to-zero deployment discards
            # the key rather than leaving stale drift behind forever.
            await self.redis.expire(PRESENCE_KEY, 86_400)
            return int(total)
        except Exception as e:
            logger.error(f"Presence tracking failed: {e}")
            return None

    async def get_connection_count(self) -> Optional[int]:
        """Reads the global connection count without changing it.

        Returns None when unavailable, meaning "fall back to the local count".
        """
        if not self.enabled or not self.redis:
            return None
        try:
            raw = await self.redis.get(PRESENCE_KEY)
            return int(raw) if raw is not None else 0
        except Exception as e:
            logger.debug(f"Could not read presence count: {e}")
            return None

    # --- simulation leader election --------------------------------------

    async def try_acquire_leadership(self, ttl_ms: int = 30_000) -> bool:
        """Attempts to become the single global simulation writer.

        This is what stops N instances from each running the 288-tick loop.
        Without it, autoscaling multiplies Vertex AI and Veo spend by the
        instance count and races N writers onto one Firestore checkpoint.
        """
        if not self.enabled or not self.redis:
            self._leadership_lost.clear()
            self._is_leader = True  # single instance is trivially the leader
            return True
        try:
            acquired = bool(
                await self.redis.set(LEADER_LOCK_KEY, self.instance_id, nx=True, px=ttl_ms)
            )
            if acquired:
                # Clear here rather than only in start_leadership_heartbeat, so a
                # caller that re-acquires after a previous loss does not see a
                # stale True and immediately abort its own loop.
                self._leadership_lost.clear()
            self._is_leader = acquired
            return acquired
        except Exception as e:
            # Fail CLOSED, unlike the rate limiter. If we cannot prove we are
            # alone, declining to run costs nothing; running anyway risks paying
            # for a duplicate day of Veo generation.
            logger.error(f"Leadership acquisition failed, declining to lead: {e}")
            return False

    async def renew_leadership(self, ttl_ms: int = 30_000) -> bool:
        """Extends the lease. Returns False if leadership was lost.

        The lease must outlive one tick, and the caller MUST stop its loop when
        this returns False. Otherwise an instance that stalled long enough to
        lose its lease would resume as a second concurrent writer.
        """
        if not self.enabled or not self.redis:
            return True
        try:
            current = await self.redis.get(LEADER_LOCK_KEY)
            if current != self.instance_id.encode():
                logger.warning("Lost simulation leadership; another instance now holds the lock")
                self._is_leader = False
                return False
            await self.redis.pexpire(LEADER_LOCK_KEY, ttl_ms)
            return True
        except Exception as e:
            # Fail closed for the same reason as acquisition.
            logger.error(f"Leadership renewal failed, relinquishing: {e}")
            self._is_leader = False
            return False

    async def release_leadership(self) -> None:
        """Hands the lock back so another instance can take over promptly."""
        self._leadership_lost.set()
        self._is_leader = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if not self.enabled or not self.redis:
            return
        try:
            if (await self.redis.get(LEADER_LOCK_KEY)) == self.instance_id.encode():
                await self.redis.delete(LEADER_LOCK_KEY)
                logger.info("Released simulation leadership")
        except Exception as e:
            logger.debug(f"Leadership release failed (lease will expire): {e}")

    def start_leadership_heartbeat(self, ttl_ms: int = 30_000) -> None:
        """Renews the lease on a timer, independent of tick progress.

        Renewing once per tick looks simpler but is wrong here: a tick that
        triggers Veo can block for minutes, the lease would lapse mid-scene, a
        second instance would take over, and both would then write checkpoints.
        A separate task renews at one third of the TTL, so lease liveness tracks
        process health rather than tick duration.
        """
        self._leadership_lost.clear()
        if self._heartbeat_task and not self._heartbeat_task.done():
            return

        interval = max(1.0, (ttl_ms / 1000.0) / 3.0)

        async def _beat() -> None:
            try:
                while True:
                    await asyncio.sleep(interval)
                    if not await self.renew_leadership(ttl_ms):
                        # Signal, do not raise: the simulation loop polls this
                        # and needs to shut down in an orderly way.
                        self._leadership_lost.set()
                        return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Leadership heartbeat crashed, relinquishing: {e}")
                self._leadership_lost.set()

        self._heartbeat_task = asyncio.create_task(_beat())

    @property
    def leadership_lost(self) -> bool:
        """True once a lease we HELD could not be renewed.

        The simulation loop checks this each tick and stops when it flips, which
        is what prevents two instances writing the same Firestore checkpoint.

        Not the inverse of `is_leader`: this stays False on an instance that
        never attempted acquisition. Gate work on `is_leader` instead.
        """
        return self._leadership_lost.is_set()

    @property
    def is_leader(self) -> bool:
        """True only while this instance positively holds the lock."""
        return self._is_leader and not self._leadership_lost.is_set()
