import { create } from 'zustand';

export interface CharacterState {
  name: string;
  current_location: string;
  current_goal: string;
  mood: string;
}

export interface SceneRecord {
  scene_id: string;
  characters_involved: string[];
  /**
   * The writer's tension rating for this beat, 0..1, or null when no rating was
   * produced. Nullable on purpose: the backend previously derived this from
   * scene position, so the displayed figure was a progress bar wearing a
   * "drama" label. Callers must not coerce null to 0 for display.
   */
  drama_score: number | null;
  veo_prompt: string;
  /** Active Gemini Omni prompt. veo_prompt remains for legacy persisted scenes. */
  omni_prompt?: string;
  video_uri: string;
  status: string;
}

export interface Whisper {
  /** Client-generated, stable across the optimistic -> confirmed transition. */
  id: string;
  user: string;
  text: string;
  ts: string;
  /** True while the whisper is an optimistic ghost awaiting CRDT consensus. */
  pending?: boolean;
  /**
   * True when consensus was never reached (dropped connection, or the server
   * rate-limited the write). Distinguishes "not yet confirmed" from "confirmed",
   * so the UI never implies a whisper landed when it did not.
   */
  failed?: boolean;
}

export interface WorldState {
  current_time: string;
  weather: string;
}

export interface TelemetryMetrics {
  tokenBurn: number;
  tickLatencyMs: number;
  activeConnections: number;
  dramaScore: number;
}

interface SimulationStore {
  worldState: WorldState | null;
  characters: CharacterState[];
  activeScene: SceneRecord | null;
  whispers: Whisper[];
  telemetry: TelemetryMetrics;
  
  setWorldState: (state: WorldState | null) => void;
  setCharacters: (chars: CharacterState[]) => void;
  setActiveScene: (scene: SceneRecord | null) => void;
  /** Append a whisper. Idempotent on `id` so CRDT replays cannot duplicate. */
  addWhisper: (whisper: Whisper) => void;
  /** Settle an optimistic ghost once consensus confirms it. */
  confirmWhisper: (id: string, confirmed?: Whisper) => void;
  /** Mark an optimistic ghost as never having reached consensus. */
  failWhisper: (id: string) => void;
  setTelemetry: (metrics: Partial<TelemetryMetrics>) => void;
}

/**
 * Rolling cap on rendered whispers, matching MAX_WHISPER_HISTORY on the server.
 *
 * Agent dialogue now lands here at roughly five lines per tick, so a long-lived
 * session accumulates well over a thousand entries — each one re-rendered by
 * WhisperFeed on every change.
 *
 * The CRDT observer only reacts to `added` events, so server-side trimming never
 * reaches this store. Capping locally keeps memory bounded without needing to
 * mirror deletions, and a feed only ever displays the recent tail anyway.
 */
const MAX_WHISPERS = 500;

/** Keeps the newest MAX_WHISPERS entries, preserving arrival order. */
function capWhispers(whispers: Whisper[]): Whisper[] {
  return whispers.length > MAX_WHISPERS
    ? whispers.slice(whispers.length - MAX_WHISPERS)
    : whispers;
}

export const useSimulationStore = create<SimulationStore>((set) => ({
  worldState: null,
  characters: [],
  activeScene: null,
  whispers: [],
  telemetry: {
    tokenBurn: 0,
    tickLatencyMs: 0,
    activeConnections: 0,
    dramaScore: 0,
  },
  
  setWorldState: (state) => set({ worldState: state }),
  setCharacters: (chars) => set({ characters: chars }),
  setActiveScene: (scene) => set({ activeScene: scene }),
  setTelemetry: (metrics) => set((state) => ({ telemetry: { ...state.telemetry, ...metrics } })),
  // Idempotent on id. The previous implementation matched on user+text, which
  // silently collapsed two identical whispers from the same agent into one.
  addWhisper: (whisper) => set((state) => {
    if (state.whispers.some((w) => w.id === whisper.id)) return state;
    return { whispers: capWhispers([...state.whispers, whisper]) };
  }),

  // Settles an optimistic ghost once consensus confirms it. If the id is not
  // present this doubles as the remote-insert path for a peer's whisper, but
  // only when the full payload is supplied — a bare ACK for an unknown id is
  // ignored rather than inventing an empty bubble.
  confirmWhisper: (id, confirmed) => set((state) => {
    const index = state.whispers.findIndex((w) => w.id === id);
    if (index === -1) {
      if (!confirmed) return state;
      // Remote-insert path: this is how agent dialogue arrives from the backend,
      // so it is the hot path now and needs the same cap.
      return {
        whispers: capWhispers([
          ...state.whispers,
          { ...confirmed, id, pending: false, failed: false },
        ]),
      };
    }
    const updated = [...state.whispers];
    updated[index] = { ...updated[index], ...confirmed, id, pending: false, failed: false };
    return { whispers: updated };
  }),

  // Consensus never arrived. Clearing `pending` stops the ghost shimmer, and
  // `failed` lets the UI say so instead of implying the write landed.
  failWhisper: (id) => set((state) => {
    const index = state.whispers.findIndex((w) => w.id === id);
    if (index === -1) return state;
    const updated = [...state.whispers];
    updated[index] = { ...updated[index], pending: false, failed: true };
    return { whispers: updated };
  }),
}));
