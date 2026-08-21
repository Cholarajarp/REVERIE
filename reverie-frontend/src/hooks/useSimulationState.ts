"use client";

/**
 * useSimulationState — Zustand (optimistic UI) <-> Yjs (CRDT consensus) bridge.
 *
 * TRANSPORT
 * ---------
 * This deliberately does NOT use `y-websocket`. The Python backend
 * (core/audience_sync.py) speaks *bare* pycrdt updates: `ydoc.get_update()` /
 * `apply_update()` over raw binary frames. `y-websocket` speaks y-protocols —
 * a varuint message-type prefix plus a sync step1/step2 handshake — which the
 * backend never reads or writes, so every frame would misparse. The adapter
 * below matches the backend byte-for-byte. Swap back to WebsocketProvider once
 * the backend wraps its frames in y-protocols.
 *
 * CONSENSUS
 * ---------
 * `Y.Array.push` applies locally and synchronously, so a local write is never
 * "pending" inside the CRDT itself. Confirmation must come from the network.
 *
 * For a PEER's whisper that is a remote-origin transaction. For the author's
 * own whisper it cannot be: echoing the author's update bytes back is a no-op
 * in Yjs (re-applying an update the doc already contains produces no event),
 * so the ghost would hang forever. The backend therefore sends an explicit
 * `{"ack": [id, ...]}` frame naming the ids it committed — see the ACK block
 * in core/audience_sync.py.
 *
 * If no ACK arrives within `ghostTimeoutMs` the whisper is marked `failed`,
 * never silently confirmed. That state is recoverable: on reconnect `onopen`
 * resends full doc state, the server re-applies and ACKs it, and the flag clears.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as Y from "yjs";
import { useSimulationStore, type Whisper } from "../store/simulationStore";

/** Marks a Yjs transaction as having arrived off the wire rather than from us. */
const REMOTE_ORIGIN = Symbol("reverie/remote");

export type SyncStatus = "connecting" | "connected" | "offline" | "unauthorized";

export interface UseSimulationStateOptions {
  /** Absolute ws:// or wss:// URL. Defaults to NEXT_PUBLIC_REVERIE_WS_URL. */
  url?: string;
  /** Firebase ID token; the backend closes unauthenticated sockets with 1008. */
  token?: string | null;
  /**
   * How long an optimistic ghost waits for remote confirmation before being
   * settled anyway. Guards against the sender-exclusion issue above.
   */
  ghostTimeoutMs?: number;
}

export interface UseSimulationStateResult {
  syncStatus: SyncStatus;
  /** True once a server snapshot has been applied to the local doc. */
  isHydrated: boolean;
  /** Last transport or server error, e.g. the rate-limit rejection. */
  lastError: string | null;
  /** Optimistically append a whisper, then reconcile against consensus. */
  sendWhisper: (text: string, user: string) => void;
}

function resolveUrl(explicit?: string): string | null {
  const raw = explicit ?? process.env.NEXT_PUBLIC_REVERIE_WS_URL;
  if (raw) return raw;
  if (typeof window === "undefined") return null;
  // Same-origin fallback relies on the /ws/:path* rewrite in next.config.ts
  // proxying the upgrade, which is not guaranteed. Prefer the env var.
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/whispers`;
}

function makeId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `w_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export function useSimulationState(
  options: UseSimulationStateOptions = {},
): UseSimulationStateResult {
  const { url, token, ghostTimeoutMs = 4000 } = options;

  const [syncStatus, setSyncStatus] = useState<SyncStatus>("connecting");
  const [isHydrated, setIsHydrated] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  // One doc per hook instance, stable across renders.
  const doc = useMemo(() => new Y.Doc(), []);
  const socketRef = useRef<WebSocket | null>(null);
  const ghostTimersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const isTornDownRef = useRef(false);

  // Select actions individually so the effect does not resubscribe whenever an
  // unrelated slice of the store changes.
  const addWhisper = useSimulationStore((s) => s.addWhisper);
  const confirmWhisper = useSimulationStore((s) => s.confirmWhisper);
  const failWhisper = useSimulationStore((s) => s.failWhisper);
  const setTelemetry = useSimulationStore((s) => s.setTelemetry);

  useEffect(() => {
    isTornDownRef.current = false;
    const target = resolveUrl(url);
    if (!target) {
      setSyncStatus("offline");
      return;
    }

    // Bind the timer map once so cleanup operates on the same instance this
    // effect populated, rather than reading the ref after a possible swap.
    const ghostTimers = ghostTimersRef.current;

    const whispers = doc.getArray<Whisper>("whispers");
    const telemetry = doc.getMap<unknown>("telemetry");

    // ---- CRDT -> Zustand -------------------------------------------------
    const onWhispers = (event: Y.YArrayEvent<Whisper>, tx: Y.Transaction) => {
      // Local pushes are already in the store as ghosts; ignore them here.
      if (tx.origin !== REMOTE_ORIGIN) return;

      event.changes.added.forEach((item) => {
        (item.content.getContent() as Whisper[]).forEach((value) => {
          if (!value || typeof value !== "object") return;
          const id = value.id ?? makeId();
          // Settles our own ghost, or inserts a peer's whisper. Both paths are
          // idempotent on id, so a re-delivered update cannot duplicate.
          confirmWhisper(id, { ...value, id, pending: false });
          const timer = ghostTimers.get(id);
          if (timer) {
            clearTimeout(timer);
            ghostTimers.delete(id);
          }
        });
      });
    };

    const onTelemetry = () => {
      const next: Record<string, number> = {};
      const read = (key: string) => Number(telemetry.get(key));
      if (telemetry.has("token_burn")) next.tokenBurn = read("token_burn");
      if (telemetry.has("tick_latency_ms")) next.tickLatencyMs = read("tick_latency_ms");
      if (telemetry.has("active_connections")) next.activeConnections = read("active_connections");
      if (telemetry.has("drama_score")) next.dramaScore = read("drama_score");
      if (Object.keys(next).length > 0) setTelemetry(next);
    };

    whispers.observe(onWhispers);
    telemetry.observe(onTelemetry);

    // ---- Local doc changes -> wire ---------------------------------------
    const onLocalUpdate = (update: Uint8Array, origin: unknown) => {
      if (origin === REMOTE_ORIGIN) return; // never echo remote work back
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(update);
      }
    };
    doc.on("update", onLocalUpdate);

    // ---- Transport, with capped exponential backoff -----------------------
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    const scheduleReconnect = () => {
      if (isTornDownRef.current) return;
      const delay = Math.min(30000, 1000 * 2 ** attempt);
      attempt += 1;
      reconnectTimer = setTimeout(() => connect(target), delay);
    };

    function connect(base: string) {
      if (isTornDownRef.current) return;
      const endpoint = token
        ? `${base}?token=${encodeURIComponent(token)}`
        : base;

      let socket: WebSocket;
      try {
        socket = new WebSocket(endpoint);
      } catch {
        setSyncStatus("offline");
        scheduleReconnect();
        return;
      }

      socket.binaryType = "arraybuffer";
      socketRef.current = socket;
      setSyncStatus("connecting");

      socket.onopen = () => {
        attempt = 0;
        setSyncStatus("connected");
        setLastError(null);
        // Hand the server our full state so anything queued offline merges in.
        socket.send(Y.encodeStateAsUpdate(doc));
      };

      socket.onmessage = (event: MessageEvent) => {
        if (typeof event.data === "string") {
          // JSON text frames carry consensus ACKs plus auth/rate-limit errors.
          let parsed: { error?: string; ack?: string[] } | null = null;
          try {
            parsed = JSON.parse(event.data) as { error?: string; ack?: string[] };
          } catch {
            setLastError(event.data);
            return;
          }

          // Authoritative consensus signal: these ids are committed server-side.
          if (Array.isArray(parsed.ack)) {
            parsed.ack.forEach((id) => {
              if (typeof id !== "string") return;
              confirmWhisper(id);
              const timer = ghostTimers.get(id);
              if (timer) {
                clearTimeout(timer);
                ghostTimers.delete(id);
              }
            });
          }

          if (parsed.error) {
            setLastError(parsed.error);
            // A rejected write (rate limit, auth) never reached consensus, so
            // every outstanding ghost from it is dead. Fail them now rather
            // than letting them sit until the timeout.
            ghostTimers.forEach((timer, id) => {
              clearTimeout(timer);
              failWhisper(id);
            });
            ghostTimers.clear();
          }
          return;
        }
        const bytes = new Uint8Array(event.data as ArrayBuffer);
        if (bytes.byteLength === 0) return;
        try {
          Y.applyUpdate(doc, bytes, REMOTE_ORIGIN);
          setIsHydrated(true);
        } catch (err) {
          setLastError(err instanceof Error ? err.message : "Malformed CRDT update");
        }
      };

      socket.onclose = (event: CloseEvent) => {
        socketRef.current = null;
        if (isTornDownRef.current) return;
        // 1008 is the backend's explicit auth rejection; retrying is pointless.
        if (event.code === 1008) {
          setSyncStatus("unauthorized");
          setLastError(event.reason || "Unauthorized");
          return;
        }
        setSyncStatus("offline");
        scheduleReconnect();
      };

      socket.onerror = () => setLastError("WebSocket transport error");
    }

    connect(target);

    return () => {
      isTornDownRef.current = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ghostTimers.forEach(clearTimeout);
      ghostTimers.clear();
      doc.off("update", onLocalUpdate);
      whispers.unobserve(onWhispers);
      telemetry.unobserve(onTelemetry);
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        socket.onclose = null; // suppress the reconnect path on intentional close
        socket.close();
      }
      doc.destroy();
    };
  }, [doc, url, token, addWhisper, confirmWhisper, failWhisper, setTelemetry]);

  const sendWhisper = useCallback(
    (text: string, user: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      const whisper: Whisper = {
        id: makeId(),
        user,
        text: trimmed,
        ts: new Date().toISOString(),
        pending: true,
      };

      // 1. Optimistic ghost renders immediately at 50% opacity.
      addWhisper(whisper);

      // 2. Local CRDT write; the doc "update" handler ships it to the wire.
      doc.getArray<Whisper>("whispers").push([whisper]);

      // 3. If no ACK arrives in time, mark the ghost unconfirmed — never
      //    silently "confirmed". This is recoverable: on reconnect `onopen`
      //    resends full doc state, the server re-applies it and ACKs, and
      //    confirmWhisper clears the failed flag.
      const timer = setTimeout(() => {
        ghostTimersRef.current.delete(whisper.id);
        failWhisper(whisper.id);
      }, ghostTimeoutMs);
      ghostTimersRef.current.set(whisper.id, timer);
    },
    [doc, addWhisper, failWhisper, ghostTimeoutMs],
  );

  return { syncStatus, isHydrated, lastError, sendWhisper };
}
