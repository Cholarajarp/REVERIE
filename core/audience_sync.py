from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pycrdt import Doc, Array, Map
import json
import asyncio
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from core.redis_broadcaster import RedisBroadcaster, REMOTE_ORIGIN

logger = logging.getLogger(__name__)

# Hard cap on a single whisper. A model can emit a paragraph, and the whole
# document is replayed to every newly connected client.
MAX_WHISPER_LENGTH = 500

# Rolling cap on whisper history.
#
# Five characters speaking across 288 ticks is ~1440 agent lines plus audience
# chatter. Every new client is sent ydoc.get_update(), which is FULL state, so an
# untrimmed array means the cold-start payload grows all day -- and so does the
# Redis snapshot. 500 keeps roughly the last 100 ticks of dialogue, which is far
# more than a live feed displays.
MAX_WHISPER_HISTORY = 500

# Id prefix for simulation-authored whispers. Used to keep agent dialogue out of
# the connect-time ACK replay: ACKs exist to settle a CLIENT's optimistic ghost,
# and no client is ever waiting on an agent's line.
AGENT_WHISPER_PREFIX = "sim-"

class AudienceSyncManager:
    def __init__(self):
        # The global Yjs document for this screening
        self.ydoc = Doc()
        # The array of whispers: [{"user": "str", "text": "str", "ts": "str"}, ...]
        self.whispers = self.ydoc.get("whispers", type=Array)
        # Live enterprise telemetry map
        self.telemetry = self.ydoc.get("telemetry", type=Map)
        # Connected clients held by THIS instance only. Under Cloud Run
        # autoscaling this is a fraction of the audience, which is exactly why
        # the broadcaster exists.
        self.active_connections: dict[WebSocket, str] = {}
        # Sliding window timestamps per user_id: user_id -> list of float timestamps
        self.user_timestamps: dict[str, list[float]] = {}
        # Lock for safe document updates
        self.lock = asyncio.Lock()
        # Injected at startup. None means single-instance mode, where the
        # process-local dict and window are already globally correct.
        self.broadcaster: Optional[RedisBroadcaster] = None
        # Set synchronously by the observer on every local mutation. Safe to read
        # immediately after a transaction block because pycrdt fires observers
        # inline, before the mutating call returns (verified).
        self._last_local_update: Optional[bytes] = None
        self.ydoc.observe(self._on_doc_change)

    def attach_broadcaster(self, broadcaster: RedisBroadcaster) -> None:
        self.broadcaster = broadcaster

    def _on_doc_change(self, event) -> None:
        """Publishes locally-originated document changes to the global stream.

        Publishing from an observer rather than from each call site means any
        future mutation is replicated automatically, and it hands us the
        INCREMENTAL update bytes. That matters: `ydoc.get_update()` returns the
        full document state, which grows monotonically, so the previous
        telemetry path re-broadcast the entire document every tick.
        """
        try:
            if event.transaction.origin() == REMOTE_ORIGIN:
                # Arrived from Redis and was already applied by the broadcaster.
                # Re-publishing it would be a pointless round trip.
                return
        except Exception:
            pass  # no origin available: treat as local

        update = bytes(event.update)
        self._last_local_update = update

        if not (self.broadcaster and self.broadcaster.enabled):
            return
        try:
            # Observers are sync, so hop onto the loop to do the network write.
            asyncio.get_running_loop().create_task(self.broadcaster.publish(update))
        except RuntimeError:
            # Mutated outside an event loop (tests, scripts). Nothing to do.
            logger.debug("Doc mutated with no running loop; update not published")

    async def _check_rate_limit_async(self, user_id: str) -> bool:
        """Rate limit check, global when Redis is available.

        The local window below is per-process, so with N instances a user could
        send 5N whispers per minute, and reconnecting through a different
        instance handed out a fresh allowance. Defer to Redis when we have it.
        """
        if self.broadcaster and self.broadcaster.enabled:
            return await self.broadcaster.check_rate_limit(user_id, limit=5, window_ms=60_000)
        return self._check_rate_limit(user_id)

    def _check_rate_limit(self, user_id: str) -> bool:
        """Sliding window rate limiter: allows max 5 whispers/updates per 60 seconds per user."""
        now = time.time()
        timestamps = self.user_timestamps.get(user_id, [])
        # Keep only timestamps within the last 60 seconds
        valid_timestamps = [ts for ts in timestamps if now - ts <= 60.0]

        if len(valid_timestamps) >= 5:
            self.user_timestamps[user_id] = valid_timestamps
            return False

        valid_timestamps.append(now)
        self.user_timestamps[user_id] = valid_timestamps
        return True

    async def deliver_remote_update(self, update: bytes) -> None:
        """Fans out an update that originated on another Cloud Run instance.

        This is the broadcaster's callback. The Doc has already been updated by
        the time we get here, so this only pushes bytes to local sockets.

        No ACK is sent: ACKs are the responsibility of the instance that received
        the whisper and still holds that client's socket.
        """
        for connection in list(self.active_connections.keys()):
            try:
                await connection.send_bytes(update)
            except Exception as e:
                logger.debug(f"Failed to deliver remote update to a client: {e}")

    async def publish_agent_dialogue(self, lines: list[tuple[str, str]], tick: int) -> int:
        """Appends character dialogue to the whisper feed so the audience can read it.

        `lines` is a list of (character_name, dialogue) pairs for one tick.

        Called from the simulation loop, which runs only on the elected leader, so
        these appends have a single writer. Every other instance receives them
        through Redis via the doc observer, then relays to its own sockets.

        Deliberately does NOT go through the rate limiter: that budget is 5/min
        per audience member, while five characters speak every tick. Agents are
        trusted publishers, not untrusted clients.

        Returns the number of lines actually published.
        """
        entries = []
        for name, dialogue in lines:
            if not isinstance(dialogue, str):
                continue
            text = dialogue.strip()
            if not text:
                continue
            entries.append({
                # Unique per (tick, character) with a random suffix. The suffix
                # matters: resuming from a checkpoint replays tick numbers, and a
                # colliding id would make the frontend merge the new whisper into
                # the old one instead of appending it.
                "id": f"sim-{tick}-{name}-{uuid.uuid4().hex[:6]}",
                "user": name,
                "text": text[:MAX_WHISPER_LENGTH],
                # ISO-8601: the frontend localises at render time, and string
                # timestamps keep ordering stable across peers.
                "ts": datetime.now(timezone.utc).isoformat(),
            })

        if not entries:
            return 0

        try:
            # One transaction for the whole tick, so five speaking characters
            # produce a single CRDT update and a single Redis publish rather
            # than five of each.
            with self.ydoc.transaction():
                for entry in entries:
                    self.whispers.append(entry)
                self._trim_whispers()

            # Local sockets need an explicit push: the observer publishes to
            # Redis for other instances, but does not deliver to this instance's
            # own clients.
            update = self._last_local_update
            if update:
                await self._broadcast_all(update)

            return len(entries)
        except Exception as e:
            logger.error(f"Could not publish agent dialogue: {e}")
            return 0

    def _trim_whispers(self) -> None:
        """Caps the whisper history to a bounded window.

        Without this the array grows for the whole run -- 288 ticks times five
        characters is ~1440 agent lines plus audience chatter -- and because every
        newly connected client is sent `ydoc.get_update()` (full state), the
        cold-start snapshot would grow all day.

        Must be called inside an existing transaction so the trim rides along with
        the append as one update.
        """
        overflow = len(self.whispers) - MAX_WHISPER_HISTORY
        if overflow > 0:
            del self.whispers[0:overflow]

    def _whisper_ids(self, client_only: bool = False) -> set[str]:
        """Collects the whisper ids currently committed to the doc.

        `client_only` excludes simulation-authored dialogue. Used for the
        connect-time ACK replay: an ACK settles a CLIENT's optimistic ghost, and
        no client is ever waiting on an agent's line, so replaying ~500 agent ids
        to every connecting viewer is pure handshake weight.
        """
        ids: set[str] = set()
        try:
            for entry in self.whispers:
                if isinstance(entry, dict):
                    whisper_id = entry.get("id")
                    if isinstance(whisper_id, str):
                        if client_only and whisper_id.startswith(AGENT_WHISPER_PREFIX):
                            continue
                        ids.add(whisper_id)
        except Exception as e:
            logger.debug(f"Could not enumerate whisper ids: {e}")
        return ids

    def _whispers_by_id(self, ids: set[str]) -> list[dict]:
        """Returns the committed whisper entries matching `ids`."""
        found = []
        try:
            for entry in self.whispers:
                if isinstance(entry, dict) and entry.get("id") in ids:
                    found.append(entry)
        except Exception as e:
            logger.debug(f"Could not look up whispers by id: {e}")
        return found

    def update_metrics(self, token_burn: Optional[int] = None,
                       tick_latency_ms: Optional[float] = None,
                       drama_score: Optional[float] = None,
                       active_connections: Optional[int] = None):
        """Updates live simulation telemetry and broadcasts to connected clients.

        Called from the simulation loop, which runs only on the elected leader,
        so these writes do not race across instances.

        Every metric is optional, and a None metric is NOT written. Callers that
        do not measure a value must omit it rather than passing a placeholder:
        the render loop previously reported a token count of
        `scene_index * 1500` and a latency of `120 + time.time() % 50`, which
        rendered as a live dashboard while measuring nothing at all. An absent
        key lets the frontend show "not measured" instead of a plausible lie.

        `active_connections` is passed in rather than read from the local dict:
        this instance only holds a fraction of the audience, so len() here would
        under-report the real figure. None means single-instance mode.
        """
        try:
            with self.ydoc.transaction():
                if token_burn is not None:
                    self.telemetry["token_burn"] = token_burn
                if tick_latency_ms is not None:
                    self.telemetry["tick_latency_ms"] = tick_latency_ms
                self.telemetry["active_connections"] = (
                    len(self.active_connections) if active_connections is None
                    else active_connections
                )
                if drama_score is not None:
                    self.telemetry["drama_score"] = drama_score

            # The observer captured the INCREMENTAL bytes for that transaction and
            # already queued the Redis publish. Previously this sent
            # ydoc.get_update(), which is the full document state and grows
            # monotonically -- so every tick re-transmitted the entire history to
            # every client, and the payload got steadily larger all day.
            update = self._last_local_update
            if update:
                asyncio.create_task(self._broadcast_all(update))
        except Exception as e:
            logger.debug(f"Could not update telemetry in pycrdt doc: {e}")

    async def _broadcast_all(self, update: bytes):
        for connection in list(self.active_connections.keys()):
            try:
                await connection.send_bytes(update)
            except Exception:
                pass

    async def connect(self, websocket: WebSocket, user_id: str = "anonymous"):
        await websocket.accept()
        self.active_connections[websocket] = user_id

        # Outer try/finally ensures cleanup always runs, even when we return early
        # because the client disconnected between accept() and the first receive().
        try:
            # Do not serve a snapshot until this instance has caught up with global
            # state. On a cold Cloud Run instance the Doc starts empty.
            if self.broadcaster:
                await self.broadcaster.wait_until_ready(timeout=10.0)

            # Presence is counted in Redis; this instance holds only a slice.
            global_total = None
            if self.broadcaster:
                global_total = await self.broadcaster.track_connection(+1)

            try:
                with self.ydoc.transaction():
                    self.telemetry["active_connections"] = (
                        len(self.active_connections) if global_total is None else global_total
                    )
            except Exception:
                pass

            # Full state snapshot. Guard: the client may have disconnected between
            # accept() and here (browser tab closed immediately).
            try:
                await websocket.send_bytes(self.ydoc.get_update())
            except Exception as e:
                logger.debug(f"Could not send initial snapshot to {user_id}: {e}")
                return  # early exit — finally block below still runs cleanup

            # Connect-time ACK. client_only: agent dialogue dominates; no client waits on it.
            known_ids = sorted(self._whisper_ids(client_only=True))
            if known_ids:
                try:
                    await websocket.send_json({"ack": known_ids})
                except Exception as e:
                    logger.debug(f"Could not send initial ACK to {user_id}: {e}")

            try:
                while True:
                    try:
                        message = await websocket.receive()
                    except RuntimeError:
                        # Starlette raises RuntimeError when receive() is called after
                        # a disconnect message was already delivered.
                        break

                    if message["type"] == "websocket.disconnect":
                        break

                    if message["type"] == "websocket.receive":
                        if "bytes" in message:
                            if not await self._check_rate_limit_async(user_id):
                                logger.warning(f"Rate limit exceeded for user {user_id}: 5 whispers per minute.")
                                try:
                                    await websocket.send_json({"error": "Rate limit exceeded: max 5 whispers per minute"})
                                except Exception:
                                    pass
                                continue

                            update = message["bytes"]
                            async with self.lock:
                                before = self._whisper_ids()
                                self.ydoc.apply_update(update)
                                committed = sorted(self._whisper_ids() - before)

                            if committed:
                                try:
                                    await websocket.send_json({"ack": committed})
                                except Exception as e:
                                    logger.debug(f"Could not ACK {user_id}: {e}")

                            await self.broadcast(update, exclude=websocket)
                            asyncio.create_task(
                                self.intercept_events(update, committed_ids=set(committed))
                            )

            except WebSocketDisconnect:
                logger.info(f"Client {user_id} disconnected from whisper feed")

        finally:
            # Runs on every exit path: normal disconnect, early return after send
            # failure, or any unhandled exception in the receive loop.
            self.active_connections.pop(websocket, None)
            self.user_timestamps.pop(user_id, None)

            cleanup_global = None
            if self.broadcaster:
                cleanup_global = await self.broadcaster.track_connection(-1)

            try:
                with self.ydoc.transaction():
                    self.telemetry["active_connections"] = (
                        len(self.active_connections) if cleanup_global is None else cleanup_global
                    )
            except Exception:
                pass

    async def broadcast(self, update: bytes, exclude: WebSocket):
        """Broadcasts CRDT binary diffs to all connected clients."""
        for connection in list(self.active_connections.keys()):
            if connection != exclude:
                try:
                    await connection.send_bytes(update)
                except Exception as e:
                    logger.error(f"Failed to broadcast to client: {e}")

    async def intercept_events(self, update: bytes, committed_ids: Optional[set[str]] = None):
        """Scans newly committed AUDIENCE whispers for keywords to inject.

        Only the elected leader acts. Every instance now applies every whisper
        (that is the point of the broadcaster), so without this guard an audience
        event would be injected once per running instance. The leader is also the
        only process running the simulation loop, so it is the only one that could
        act on the event anyway.

        `committed_ids` names exactly which whispers to examine. It replaced a
        `self.whispers[-1]` read, which became wrong once agents started writing
        to the same array for two reasons:

          - this method runs in a detached task, so a tick's dialogue can land
            between the client's write and this scan, and the client's whisper is
            then no longer last; and
          - more seriously, `[-1]` could land on an AGENT's line, so a character
            who happened to say "a letter arrives" would trigger an audience
            event. The simulation would be feeding its own commands back to
            itself, and the resulting behaviour would look inexplicable from the
            outside.

        Agent-authored ids are filtered out regardless, so simulation dialogue can
        never trigger an injection even if callers pass its ids in.
        """
        # `is_leader`, not `not leadership_lost`: the latter is also False on an
        # instance that never attempted acquisition, which would let every
        # non-leader inject the event and reintroduce the N-times bug.
        if self.broadcaster and self.broadcaster.enabled and not self.broadcaster.is_leader:
            return

        if not committed_ids:
            return

        audience_ids = {
            wid for wid in committed_ids
            if isinstance(wid, str) and not wid.startswith(AGENT_WHISPER_PREFIX)
        }
        if not audience_ids:
            return

        for whisper in self._whispers_by_id(audience_ids):
            text = str(whisper.get("text", "")).lower()
            if "introduce event" in text or "letter arrives" in text:
                logger.info(f"Audience event intercepted: {whisper.get('text')}")

# Singleton instance
audience_sync_manager = AudienceSyncManager()

async def audience_websocket_endpoint(websocket: WebSocket, user_id: str = "anonymous"):
    await audience_sync_manager.connect(websocket, user_id=user_id)
