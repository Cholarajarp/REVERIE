"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useSimulationStore } from "../../store/simulationStore";
import { useSimulationState } from "../../hooks/useSimulationState";
import { AppShell, Panel, StatusDot, Badge, ProgressBar, TelemetryStat } from "../../components/ui/Layout";
import { TownMap } from "../../components/screens/TownMap";
import { WhisperFeed } from "../../components/screens/WhisperFeed";
import { Footer } from "../../components/layout/Footer";
import type { SyncStatus } from "../../hooks/useSimulationState";

const SYNC_STATUS_LABEL: Record<SyncStatus, string> = {
  connected: "ONLINE",
  connecting: "HANDSHAKING",
  offline: "RECONNECTING",
  unauthorized: "AUTH REQUIRED",
};

const apiBase =
  typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? ""
    : "http://localhost:8000";

export default function DashboardPage() {
  const {
    worldState,
    characters,
    whispers,
    telemetry,
    setCharacters,
  } = useSimulationStore();

  const [activeTab, setActiveTab] = useState<"map" | "feed">("map");
  const [isStopping, setIsStopping] = useState(false);
  const [simRunning, setSimRunning] = useState<boolean | null>(null);
  const [scenesReady, setScenesReady] = useState(0);
  const [scenesTotal, setScenesTotal] = useState<number | null>(null); // from render_status

  const { sendWhisper, syncStatus } = useSimulationState({});

  // Poll health to know if simulation is running
  useEffect(() => {
    const poll = async () => {
      try {
        const r = await fetch(`${apiBase}/health`);
        const data = await r.json();
        const running = data.simulation_running ?? false;
        setSimRunning(running);
      } catch {
        // ignore
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  // Poll scene count for film progress — also pull render_status for total count
  // so the bar shows N/M even when sessionStorage is unavailable (e.g. first visit).
  useEffect(() => {
    const poll = async () => {
      try {
        const [scenesRes, statusRes] = await Promise.all([
          fetch(`${apiBase}/api/scenes`).then((r) => r.json()),
          fetch(`${apiBase}/api/studio/render_status`).then((r) => r.json()),
        ]);
        const ready = (scenesRes.scenes ?? []).filter(
          (s: { status: string; video_uri: string }) =>
            s.status === "critiqued" && s.video_uri
        ).length;
        setScenesReady(ready);
        // scenes_total from render_status is the authoritative count while a render is active
        if (statusRes.scenes_total > 0) {
          setScenesTotal(statusRes.scenes_total);
        }
      } catch {
        // ignore
      }
    };
    poll();
    const id = setInterval(poll, 8000);
    return () => clearInterval(id);
  }, []);

  // Hydrate characters from sessionStorage
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("reverie_characters");
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setCharacters(parsed);
        }
      }
    } catch {
      // sessionStorage unavailable
    }
  }, [setCharacters]);

  const handleSendWhisper = (text: string) => {
    sendWhisper(text, "Director");
  };

  const handleStop = useCallback(async () => {
    setIsStopping(true);
    try {
      const r = await fetch(`${apiBase}/stop_simulation`, { method: "POST" });
      await r.json();
      setSimRunning(false);
    } catch {
      // ignore
    } finally {
      setIsStopping(false);
    }
  }, []);

  // drama_score from backend is 0.0–1.0; display as 0–100
  const dramaPercent = Math.round((telemetry?.dramaScore ?? 0) * 100);

  // Film progress: prefer scenesTotal from render_status (accurate during render),
  // fall back to sessionStorage settings, then a sensible default.
  const filmSettings = (() => {
    try {
      const s = typeof window !== "undefined" ? sessionStorage.getItem("reverie_settings") : null;
      return s ? JSON.parse(s) : null;
    } catch { return null; }
  })();
  const filmDuration = filmSettings?.filmDuration ?? 1;
  const clipSecs = parseInt((filmSettings?.videoDuration ?? "10s").replace("s", ""), 10) || 10;
  /* Prefer the explicit second count. `filmDuration` carries minutes for a film
     but seconds for an ad, so reading it as minutes inflated an ad's clip target
     sixtyfold and left the progress bar stuck near zero. The ternary keeps older
     sessionStorage payloads, written before targetSeconds existed, working. */
  const targetSeconds =
    typeof filmSettings?.targetSeconds === "number"
      ? filmSettings.targetSeconds
      : filmSettings?.isAd
        ? filmDuration
        : filmDuration * 60;
  const sessionTotalClips = Math.max(1, Math.ceil(targetSeconds / clipSecs));
  // If render_status says there are more scenes than sessionStorage thinks, use that value.
  const totalClipsNeeded = Math.max(sessionTotalClips, scenesTotal ?? 0, scenesReady);
  const filmProgressPct = totalClipsNeeded > 0 ? Math.min(100, Math.round((scenesReady / totalClipsNeeded) * 100)) : 0;

  return (
    <AppShell
      header={
        <section className="w-full flex flex-col md:flex-row items-center justify-between gap-4">
          <section className="flex items-center gap-4">
            <StatusDot
              status={
                syncStatus === "connected"
                  ? "active"
                  : syncStatus === "connecting"
                    ? "idle"
                    : "alert"
              }
            />
            <span className="font-mono text-xs tracking-widest uppercase text-secondary">
              {`ENGINE STATUS: ${SYNC_STATUS_LABEL[syncStatus]} // LIVE CRDT WEBSOCKET`}
            </span>
          </section>

          <section className="flex items-center gap-6 text-xs font-mono">
            {worldState && (
              <>
                <span className="text-white/60">TIME: <strong className="text-white">{worldState.current_time}</strong></span>
                <span className="text-white/60">WEATHER: <strong className="text-[var(--color-accent-secondary)]">{worldState.weather}</strong></span>
              </>
            )}
            <div className="flex items-center gap-2 pl-4 border-l border-white/10">
              <Badge label="DIRECTOR" variant="accent" />
              <Link
                href="/"
                className="text-white/50 hover:text-white transition-colors underline underline-offset-4"
              >
                [EXIT TO HOME]
              </Link>
            </div>
          </section>
        </section>
      }
    >
      {/* Centered Display Header */}
      <section className="flex flex-col items-center justify-center py-8 gap-2 text-center">
        <h1
          className="text-5xl md:text-7xl tracking-widest font-normal drop-shadow-[0_0_35px_rgba(232,176,75,0.3)] transition-all duration-700 hover:drop-shadow-[0_0_50px_rgba(232,176,75,0.6)]"
          style={{ color: "var(--color-accent)", fontFamily: "var(--font-family-display)" }}
        >
          REVERIE
        </h1>
        <p className="text-xs md:text-sm font-mono tracking-[0.3em] text-white/50 uppercase">
          Autonomous Film Generation // Gemini Omni · Live Telemetry
        </p>
      </section>

      {/* Navigation + Controls */}
      <section className="flex flex-col md:flex-row items-center justify-between border-b border-white/10 pb-4 gap-4">
        <section className="flex gap-2">
          <button
            onClick={() => setActiveTab("map")}
            className={`px-4 py-2 rounded text-xs font-mono uppercase tracking-wider transition-all cursor-pointer ${
              activeTab === "map"
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)] border border-[var(--color-accent)] font-bold shadow-[0_0_15px_rgba(232,176,75,0.2)]"
                : "bg-white/5 text-white/60 hover:text-white border border-transparent"
            }`}
          >
            [01] Town Map ({characters.length} Agents)
          </button>
          <button
            onClick={() => setActiveTab("feed")}
            className={`px-4 py-2 rounded text-xs font-mono uppercase tracking-wider transition-all cursor-pointer ${
              activeTab === "feed"
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)] border border-[var(--color-accent)] font-bold shadow-[0_0_15px_rgba(232,176,75,0.2)]"
                : "bg-white/5 text-white/60 hover:text-white border border-transparent"
            }`}
          >
            [02] Whisper Feed ({whispers.length} Transmissions)
          </button>
        </section>

        <section className="flex gap-3 items-center">
          <Link
            href="/screening"
            className="bg-[var(--color-accent-secondary)]/20 border border-[var(--color-accent-secondary)] text-[var(--color-accent-secondary)] hover:bg-[var(--color-accent-secondary)] hover:text-black font-semibold text-xs px-4 py-2 rounded transition-all duration-300 font-[family-name:var(--font-family-display)] uppercase tracking-wider shadow-lg cursor-pointer"
          >
            ▶ SCREENING ROOM
          </Link>

          {simRunning !== false && (
            <button
              onClick={handleStop}
              disabled={isStopping}
              className={`border text-xs px-4 py-2 rounded font-mono uppercase tracking-wider transition-all cursor-pointer ${
                isStopping
                  ? "border-red-500/30 text-red-500/40"
                  : "border-red-500 text-red-400 hover:bg-red-500 hover:text-black"
              }`}
            >
              {isStopping ? "⏳ STOPPING..." : "⏹ STOP SIMULATION"}
            </button>
          )}
          {/* NEW SIMULATION link — always visible so user can always restart */}
          <Link
            href="/studio"
            className="border border-white/20 text-white/50 hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] text-xs px-4 py-2 rounded font-mono uppercase tracking-wider transition-all cursor-pointer"
          >
            ▶ NEW SIMULATION
          </Link>
        </section>
      </section>

      {/* Film Progress Bar */}
      <section className="mt-4 mb-2">
        <div className="flex items-center justify-between mb-1 text-[10px] font-mono text-white/50 uppercase tracking-wider">
          <span>
            🎬 Film Progress —{" "}
            {simRunning === null
              ? "Connecting…"
              : scenesReady === 0 && totalClipsNeeded === 0
              ? <span className="text-white/30">No render active · <Link href="/studio" className="underline text-[var(--color-accent)]">Start in Studio →</Link></span>
              : `${scenesReady}/${totalClipsNeeded} clips rendered`}
          </span>
          {totalClipsNeeded > 0 && <span className="text-[var(--color-accent)]">{filmProgressPct}%</span>}
        </div>
        <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden border border-white/10">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${filmProgressPct}%`,
              background: filmProgressPct >= 100
                ? "var(--color-accent)"
                : "linear-gradient(90deg, var(--color-accent-secondary), var(--color-accent))",
            }}
          />
        </div>
        {simRunning && totalClipsNeeded > 0 && filmProgressPct < 100 && (
          <p className="text-[10px] font-mono text-yellow-400/70 mt-1">
            ⏳ Rendering in progress — <Link href="/screening" className="underline text-[var(--color-accent)]">watch clips live in Screening Room →</Link>
          </p>
        )}
        {filmProgressPct >= 100 && (
          <p className="text-[10px] font-mono text-[var(--color-accent)] mt-1">
            ✅ Film complete! <Link href="/screening" className="underline">Watch in Screening Room →</Link>
          </p>
        )}
      </section>

      {/* Main Content Area */}
      <section className="flex-1 min-h-[550px] grid grid-cols-1 lg:grid-cols-3 gap-6 mb-12 mt-4">
        <section className="lg:col-span-2 flex flex-col h-full">
          {activeTab === "map" ? (
            <TownMap characters={characters} />
          ) : (
            <WhisperFeed whispers={whispers} onSendWhisper={handleSendWhisper} />
          )}
        </section>

        <section className="flex flex-col gap-6">
          <Panel title="ACTIVE AGENTS" subtitle="BEHAVIORAL TELEMETRY" className="flex-1">
            <section className="flex flex-col gap-3 overflow-y-auto max-h-[300px] pr-1">
              {characters.length === 0 && (
                <p className="text-xs font-mono text-white/30 text-center py-4">
                  Agents appear here once the simulation starts.<br />
                  Start a sim from the <Link href="/studio" className="underline text-[var(--color-accent)]">Studio</Link>.
                </p>
              )}
              {characters.map((c) => (
                <article
                  key={c.name}
                  className="p-3 rounded bg-black/40 border border-white/5 flex flex-col gap-1.5 hover:border-white/20 transition-all shadow-inner"
                >
                  <header className="flex items-center justify-between">
                    <span className="font-bold text-sm text-[var(--color-accent)] font-[family-name:var(--font-family-display)]">
                      {c.name}
                    </span>
                    <StatusDot status={simRunning ? "active" : "idle"} />
                  </header>
                  <p className="text-xs text-white/80 italic font-serif">&ldquo;{c.current_goal}&rdquo;</p>
                  <footer className="flex items-center justify-between text-[10px] font-mono text-white/50 pt-1 border-t border-white/5">
                    <span>LOC: {c.current_location}</span>
                    <Badge label={c.mood} variant="default" />
                  </footer>
                </article>
              ))}
            </section>
          </Panel>

          <Panel title="LIVE ENTERPRISE TELEMETRY" subtitle="REAL-TIME SYSTEM OBSERVABILITY" className="h-auto">
            <section className="flex flex-col gap-3">
              <ProgressBar
                value={dramaPercent}
                label={`LIVE DRAMA SCORE — ${dramaPercent}% (SCENE TRIGGER THRESHOLD: 60%)`}
                variant={dramaPercent > 60 ? "danger" : "accent"}
              />
              <section className="grid grid-cols-2 gap-2">
                <TelemetryStat
                  label="TOKEN BURN"
                  value={telemetry?.tokenBurn ? telemetry.tokenBurn.toLocaleString() : "—"}
                  unit={telemetry?.tokenBurn ? "TKN" : undefined}
                  subtext="Est. Vertex AI Spend"
                />
                <TelemetryStat
                  label="SCENE TIME"
                  value={(() => {
                    const ms = telemetry?.tickLatencyMs;
                    if (!ms) return "—";
                    if (ms >= 60_000) return (ms / 1000).toFixed(1);
                    return Math.round(ms).toLocaleString();
                  })()}
                  unit={(() => {
                    const ms = telemetry?.tickLatencyMs;
                    if (!ms) return undefined;
                    return ms >= 60_000 ? "S" : "MS";
                  })()}
                  subtext="Last Render Duration"
                />
                <TelemetryStat
                  label="ACTIVE CLIENTS"
                  value={telemetry?.activeConnections || 1}
                  unit="USERS"
                  subtext="CRDT WebSocket"
                />
                <TelemetryStat
                  label="BUDGET SHIELD"
                  value="ACTIVE"
                  subtext="<$5 Cap Enforced"
                />
              </section>
            </section>
          </Panel>
        </section>
      </section>

      <Footer />
    </AppShell>
  );
}
