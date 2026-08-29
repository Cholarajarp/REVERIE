"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";

interface Scene {
  scene_id: string;
  video_uri: string;
  status: string;
  /** Writer's tension rating, or null when the beat carried no rating. */
  drama_score: number | null;
  characters_involved: string[];
  veo_prompt: string;
  omni_prompt?: string;
  continuity_score?: number | null;
  critique?: string;
  failure_reason?: string;
  anchor_names?: string[];
  previous_interaction_id?: string;
  omni_interaction_id?: string;
  generation_attempt?: number;
  scene_index?: number;
  expected_scene_count?: number;
  actual_duration_seconds?: number | null;
  /** How this shot was accepted. Never assume approval from status alone. */
  review_mode?: "director_approved" | "unverified" | "review_disabled";
  /** True only when the renderer accepted the parent interaction. */
  stateful_chain_verified?: boolean;
  scene_asset_labels?: string[];
  aspect_ratio?: string;
}

/** A scene can only be played when it has been accepted AND has a video. */
const isPlayable = (s: Scene | null | undefined): boolean =>
  !!s && s.status === "critiqued" && !!s.video_uri;

const REVIEW_BADGE: Record<string, { label: string; color: string; title: string }> = {
  director_approved: {
    label: "DIRECTOR APPROVED",
    color: "#4ade80",
    title: "The visual critic watched this clip and passed it.",
  },
  unverified: {
    label: "UNVERIFIED",
    color: "#facc15",
    title:
      "This clip rendered but no approving critic verdict was obtained. It is in the film, but it is not review evidence.",
  },
  review_disabled: {
    label: "REVIEW OFF",
    color: "rgba(255,255,255,0.45)",
    title: "Continuity review was disabled for this run (CONTINUITY_REVIEW_MODE=off).",
  },
};

const apiBase =
  typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? ""
    : "http://localhost:8000";

const STATUS_COLOR: Record<string, string> = {
  critiqued: "#4ade80",
  rendering: "#facc15",
  queued:    "#60a5fa",
  failed:    "#f87171",
};

const STATUS_LABEL: Record<string, string> = {
  critiqued: "READY",
  rendering: "RENDERING…",
  queued:    "QUEUED",
  failed:    "FAILED",
};

export default function ScreeningPage() {
  const [scenes, setScenes]           = useState<Scene[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isLoading, setIsLoading]     = useState(true);
  const [isPlaying, setIsPlaying]     = useState(false);
  const [autoPlay, setAutoPlay]       = useState(false);
  const [lastFetch, setLastFetch]     = useState<Date | null>(null);
  const [renderRunning, setRenderRunning] = useState(false);
  const [scenesTotal, setScenesTotal] = useState(0);
  const [generationAttempts, setGenerationAttempts] = useState(0);
  // Approved vs merely-rendered are tracked separately so the UI can state which
  // it is showing instead of calling every finished clip director-approved.
  const [scenesApproved, setScenesApproved] = useState(0);
  const [scenesUnverified, setScenesUnverified] = useState(0);
  const [reviewMode, setReviewMode] = useState<string>("advisory");
  const [aspectRatio, setAspectRatio] = useState<string>("16:9");

  // Read production aspect ratio from studio session
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("reverie_settings");
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.aspectRatio) setAspectRatio(parsed.aspectRatio);
      }
    } catch {}
  }, []);

  // Action button states
  const [isStopping, setIsStopping]   = useState(false);
  const [isClearing, setIsClearing]   = useState(false);
  const [clearMsg, setClearMsg]       = useState("");

  const videoRef = useRef<HTMLVideoElement>(null);

  /* ── fetch scenes + render status together ── */
  const fetchScenes = useCallback(async () => {
    try {
      const [scenesRes, statusRes] = await Promise.all([
        fetch(`${apiBase}/api/scenes`).then((r) => r.json()),
        fetch(`${apiBase}/api/studio/render_status`).then((r) => r.json()),
      ]);
      setScenes(scenesRes.scenes ?? []);
      setRenderRunning(statusRes.rendering_running ?? false);
      if ((statusRes.scenes_total ?? 0) > 0) setScenesTotal(statusRes.scenes_total);
      setGenerationAttempts(statusRes.generation_attempts ?? 0);
      setScenesApproved(statusRes.scenes_approved ?? 0);
      setScenesUnverified(statusRes.scenes_unverified ?? 0);
      setReviewMode(statusRes.review_mode ?? "advisory");
      setLastFetch(new Date());
    } catch {
      // keep previous state on error
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchScenes();
    const timer = setInterval(fetchScenes, 6_000);
    return () => clearInterval(timer);
  }, [fetchScenes]);

  /* ── stop render ── */
  const handleStop = async () => {
    setIsStopping(true);
    try {
      await fetch(`${apiBase}/stop_simulation`, { method: "POST" });
      setRenderRunning(false);
    } catch { /* ignore */ }
    finally { setIsStopping(false); }
  };

  /* ── clear all scenes ── */
  const handleClear = async () => {
    if (!confirm("Clear ALL scenes from the screening room? This cannot be undone.")) return;
    setIsClearing(true);
    setClearMsg("");
    try {
      const res  = await fetch(`${apiBase}/api/studio/clear_scenes`, { method: "POST" });
      const data = await res.json();
      if (data.status === "cleared") {
        setScenes([]);
        setCurrentIndex(0);
        setIsPlaying(false);
        setAutoPlay(false);
        setClearMsg("✓ Cleared");
      } else {
        setClearMsg("Error: " + (data.detail ?? "unknown"));
      }
    } catch {
      setClearMsg("Error connecting to backend");
    } finally {
      setIsClearing(false);
      setTimeout(() => setClearMsg(""), 3000);
    }
  };

  const readyScenes  = scenes.filter(isPlayable);
  // Total clips: use render_status count when available (accurate during active render)
  const totalClips = Math.max(scenesTotal, scenes.length, readyScenes.length);
  const renderPct  = totalClips > 0 ? Math.min(100, Math.round((readyScenes.length / totalClips) * 100)) : 0;
  const currentScene = scenes[currentIndex] ?? null;
  const shotNumber = currentScene?.scene_index || currentIndex + 1;
  const continuityPct = currentScene?.continuity_score == null
    ? null
    : Math.round(currentScene.continuity_score * 100);

  /* ── playable-scene navigation ──
     Every jump is expressed as "the next index that can actually play".
     The old version searched only forward from currentIndex for autoplay and
     let PREV/NEXT land on queued or failed shots, so the chain silently
     stalled on the first gap and single clips looked unplayable. */
  const nextPlayableIndex = useCallback(
    (from: number, direction: 1 | -1): number => {
      for (let i = from; i >= 0 && i < scenes.length; i += direction) {
        if (isPlayable(scenes[i])) return i;
      }
      return -1;
    },
    [scenes]
  );

  const goToPlayable = useCallback(
    (from: number, direction: 1 | -1) => {
      const target = nextPlayableIndex(from, direction);
      if (target !== -1) setCurrentIndex(target);
    },
    [nextPlayableIndex]
  );

  const advance = useCallback(() => {
    const target = nextPlayableIndex(currentIndex + 1, 1);
    if (target !== -1) {
      setCurrentIndex(target);
      return;
    }
    // End of the accepted playlist.
    setAutoPlay(false);
    setIsPlaying(false);
  }, [currentIndex, nextPlayableIndex]);

  const handleVideoEnd = () => {
    if (autoPlay) advance();
    else setIsPlaying(false);
  };

  /* A clip whose file will not load must not freeze the whole screening.
     Without this the autoplay chain waits forever on an ended event that a
     failed <video> never fires. */
  const handleVideoError = () => {
    if (autoPlay) advance();
    else setIsPlaying(false);
  };

  const playAll = () => {
    const first = nextPlayableIndex(0, 1);
    if (first === -1) return;
    setCurrentIndex(first);
    setAutoPlay(true);
    setIsPlaying(true);
  };

  const playCurrent = () => {
    if (!isPlayable(currentScene)) return;
    setAutoPlay(false);
    setIsPlaying(true);
    videoRef.current?.play().catch(() => {});
  };

  /* Start playback when the element is genuinely ready.
     AnimatePresence remounts the <video> on every scene change, so calling
     play() from an effect keyed on the index raced the remount and hit a stale
     or null ref -- which is why clips would not play one after another. The
     element now reports its own readiness instead. */
  const handleCanPlay = () => {
    if (isPlaying || autoPlay) videoRef.current?.play().catch(() => {});
  };

  const prevPlayable = nextPlayableIndex(currentIndex - 1, -1);
  const nextPlayable = nextPlayableIndex(currentIndex + 1, 1);

  /* ════════════════════════════════════════════════════
     RENDER
     ════════════════════════════════════════════════════ */
  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: "linear-gradient(180deg,#080808 0%,#0f0f0f 100%)", color: "#e0e0e0", fontFamily: "'JetBrains Mono','SF Mono',monospace", overflow: "hidden" }}>

      {/* ── Header ── */}
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 28px", borderBottom: "1px solid rgba(255,255,255,0.08)", gap: "12px", flexWrap: "wrap" }}>
        <Link href="/" style={{ color: "rgba(255,255,255,0.4)", textDecoration: "none", fontSize: "11px", letterSpacing: "0.1em", textTransform: "uppercase" }}>
          ← HOME
        </Link>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "2px" }}>
          <h1 style={{ fontSize: "13px", letterSpacing: "0.3em", textTransform: "uppercase", color: "rgba(255,255,255,0.7)", margin: 0 }}>
            SCREENING ROOM
          </h1>
          {/* "APPROVED SHOTS" was applied to every clip that finished rendering.
              Approved and unverified are now counted and labelled separately. */}
          <span style={{ fontSize: "9px", color: "rgba(255,255,255,0.25)", letterSpacing: "0.15em" }}>
            {readyScenes.length}/{totalClips || "?"} SHOTS IN FILM · GEMINI OMNI
            {scenesApproved > 0 && ` · ${scenesApproved} APPROVED`}
            {scenesUnverified > 0 && ` · ${scenesUnverified} UNVERIFIED`}
            {reviewMode === "off" && " · REVIEW OFF"}
            {generationAttempts > totalClips && ` · ${generationAttempts} ATTEMPTS`}
            {lastFetch && ` · ${lastFetch.toLocaleTimeString()}`}
          </span>
        </div>

        {/* Controls cluster */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          {/* Stop render */}
          {renderRunning && (
            <button
              onClick={handleStop}
              disabled={isStopping}
              style={{
                padding: "6px 14px",
                background: isStopping ? "rgba(248,113,113,0.1)" : "rgba(248,113,113,0.15)",
                border: "1px solid rgba(248,113,113,0.5)",
                borderRadius: "4px",
                color: isStopping ? "rgba(248,113,113,0.4)" : "#f87171",
                cursor: isStopping ? "default" : "pointer",
                fontSize: "10px",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                fontFamily: "inherit",
              }}
            >
              {isStopping ? "⏳ STOPPING…" : "⏹ STOP RENDER"}
            </button>
          )}

          {/* Clear scenes */}
          <button
            onClick={handleClear}
            disabled={isClearing || scenes.length === 0}
            title="Delete all scenes from Firestore and start fresh"
            style={{
              padding: "6px 14px",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.15)",
              borderRadius: "4px",
              color: isClearing || scenes.length === 0 ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.55)",
              cursor: isClearing || scenes.length === 0 ? "default" : "pointer",
              fontSize: "10px",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              fontFamily: "inherit",
            }}
          >
            {isClearing ? "⏳ CLEARING…" : clearMsg || "🗑 CLEAR ALL SCENES"}
          </button>

          {/* Format aspect ratio toggle */}
          <button
            onClick={() => setAspectRatio((prev) => (prev === "9:16" ? "16:9" : "9:16"))}
            title="Toggle between 9:16 vertical and 16:9 widescreen view"
            style={{
              padding: "6px 12px",
              background: (currentScene?.aspect_ratio || aspectRatio) === "9:16" ? "rgba(124,92,216,0.2)" : "rgba(255,255,255,0.04)",
              border: (currentScene?.aspect_ratio || aspectRatio) === "9:16" ? "1px solid rgba(124,92,216,0.6)" : "1px solid rgba(255,255,255,0.15)",
              borderRadius: "4px",
              color: (currentScene?.aspect_ratio || aspectRatio) === "9:16" ? "#b9a5f0" : "rgba(255,255,255,0.6)",
              cursor: "pointer",
              fontSize: "10px",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              fontFamily: "inherit",
            }}
          >
            {(currentScene?.aspect_ratio || aspectRatio) === "9:16" ? "📱 9:16 VERTICAL" : "🖥️ 16:9 WIDESCREEN"}
          </button>

          <Link href="/studio" style={{ padding: "6px 14px", background: "rgba(201,165,90,0.12)", border: "1px solid rgba(201,165,90,0.35)", borderRadius: "4px", color: "#c9a55a", textDecoration: "none", fontSize: "10px", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            ▶ NEW FILM
          </Link>

          <Link href="/dashboard" style={{ color: "rgba(255,255,255,0.4)", textDecoration: "none", fontSize: "11px", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            DASHBOARD →
          </Link>
        </div>
      </header>

      {/* ── Render progress banner ── */}
      {renderRunning && (
        <div style={{ background: "rgba(250,204,21,0.08)", borderBottom: "1px solid rgba(250,204,21,0.2)", padding: "8px 28px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px", fontSize: "10px", color: "#facc15", letterSpacing: "0.12em" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#facc15", animation: "pulse 1.5s infinite", display: "inline-block" }} />
            {/* This banner used to claim that only director-approved shots reach
                the film, which was untrue: every rendered clip was auto-approved.
                It now states the gate that is actually configured. */}
            {reviewMode === "enforce"
              ? "GEMINI OMNI RENDERING — SHOTS MUST PASS THE CONTINUITY GATE TO ENTER THE FILM"
              : reviewMode === "off"
              ? "GEMINI OMNI RENDERING — CONTINUITY REVIEW IS DISABLED FOR THIS RUN"
              : "GEMINI OMNI RENDERING — SHOTS ARE REVIEWED; UNVERIFIED ONES ARE KEPT AND LABELLED"}
          </div>
          <span style={{ color: "#c9a55a", fontWeight: 700 }}>
            {readyScenes.length}{totalClips > 0 ? `/${totalClips}` : ""} CLIPS READY · {renderPct}%
          </span>
        </div>
      )}

      {/* ── Render progress bar (only during active render) ── */}
      {renderRunning && totalClips > 0 && (
        <div style={{ padding: "0 28px 0", background: "rgba(0,0,0,0.4)", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
          <div style={{ width: "100%", height: "3px", background: "rgba(255,255,255,0.06)", borderRadius: "2px", overflow: "hidden" }}>
            <div style={{ height: "100%", borderRadius: "2px", background: "linear-gradient(90deg, #7c5cd8, #c9a55a)", transition: "width 0.8s ease", width: `${renderPct}%` }} />
          </div>
        </div>
      )}

      <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>

        {/* ── Main Viewport ── */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "20px 24px", gap: "16px" }}>
          {isLoading ? (
            <div style={{ textAlign: "center", opacity: 0.4 }}>
              <div style={{ width: "28px", height: "28px", border: "2px solid rgba(255,255,255,0.15)", borderTopColor: "#c9a55a", borderRadius: "50%", animation: "spin 1s linear infinite", margin: "0 auto 12px" }} />
              <p style={{ fontSize: "11px", letterSpacing: "0.12em" }}>LOADING SCENES…</p>
            </div>
          ) : scenes.length === 0 ? (
            <div style={{ textAlign: "center", opacity: 0.4 }}>
              <p style={{ fontSize: "40px", marginBottom: "14px", lineHeight: 1 }}>🎬</p>
              {renderRunning ? (
                <>
                  <p style={{ fontSize: "13px", letterSpacing: "0.12em", textTransform: "uppercase", color: "#facc15" }}>Gemini Omni is rendering your film…</p>
                  <p style={{ fontSize: "11px", marginTop: "8px", color: "rgba(255,255,255,0.3)" }}>
                    First clips will appear here in 1–3 minutes. This page refreshes automatically.
                  </p>
                  <div style={{ width: "28px", height: "28px", border: "2px solid rgba(255,255,255,0.1)", borderTopColor: "#facc15", borderRadius: "50%", animation: "spin 1.2s linear infinite", margin: "24px auto 0" }} />
                </>
              ) : (
                <>
                  <p style={{ fontSize: "13px", letterSpacing: "0.12em", textTransform: "uppercase" }}>No scenes yet</p>
                  <p style={{ fontSize: "11px", marginTop: "8px", color: "rgba(255,255,255,0.3)" }}>
                    Start a simulation in the Studio to generate film clips
                  </p>
                  <Link href="/studio" style={{ display: "inline-block", marginTop: "16px", padding: "8px 20px", border: "1px solid rgba(201,165,90,0.4)", borderRadius: "4px", color: "#c9a55a", textDecoration: "none", fontSize: "11px", letterSpacing: "0.12em" }}>
                    → OPEN STUDIO
                  </Link>
                </>
              )}
            </div>
          ) : (
            <>
              {/* ── Video Player ── */}
              {(() => {
                const effectiveAspect = currentScene?.aspect_ratio || aspectRatio || "16:9";
                const isVertical = effectiveAspect === "9:16";
                return (
                  <div
                    style={{
                      width: "100%",
                      maxWidth: isVertical ? "420px" : "960px",
                      aspectRatio: isVertical ? "9/16" : "16/9",
                      maxHeight: isVertical ? "calc(100vh - 230px)" : "calc(100vh - 240px)",
                      background: "#000",
                      borderRadius: "6px",
                      overflow: "hidden",
                      position: "relative",
                      boxShadow: "0 0 60px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.06)",
                      flexShrink: 0,
                    }}
                  >
                    <AnimatePresence mode="wait">
                      <motion.div key={currentScene?.scene_id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }} style={{ width: "100%", height: "100%" }}>
                        {isPlayable(currentScene) ? (
                          <video
                            ref={videoRef}
                            src={currentScene!.video_uri}
                            controls
                            playsInline
                            preload="auto"
                            onEnded={handleVideoEnd}
                            onError={handleVideoError}
                            onCanPlay={handleCanPlay}
                            onPlay={() => setIsPlaying(true)}
                            onPause={() => setIsPlaying(false)}
                            style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }}
                          />
                        ) : currentScene?.status === "rendering" ? (
                          <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "12px" }}>
                            <div style={{ width: "32px", height: "32px", border: "2px solid rgba(255,255,255,0.15)", borderTopColor: "#facc15", borderRadius: "50%", animation: "spin 1.2s linear infinite" }} />
                            <p style={{ fontSize: "11px", color: "#facc15", letterSpacing: "0.12em" }}>OMNI RENDERING…</p>
                            <p style={{ fontSize: "9px", color: "rgba(255,255,255,0.25)", maxWidth: "320px", textAlign: "center", lineHeight: 1.5 }}>{(currentScene.omni_prompt || currentScene.veo_prompt)?.substring(0, 120)}…</p>
                          </div>
                        ) : currentScene?.status === "queued" ? (
                          <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "10px" }}>
                            <p style={{ fontSize: "11px", color: "#60a5fa", letterSpacing: "0.12em" }}>⏳ QUEUED FOR RENDERING</p>
                            <p style={{ fontSize: "9px", color: "rgba(255,255,255,0.25)", maxWidth: "320px", textAlign: "center", lineHeight: 1.5 }}>{(currentScene.omni_prompt || currentScene.veo_prompt)?.substring(0, 120)}…</p>
                          </div>
                        ) : (
                          <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "10px" }}>
                            <p style={{ fontSize: "32px" }}>⚠️</p>
                            <p style={{ fontSize: "11px", color: "#f87171", letterSpacing: "0.12em" }}>OMNI GENERATION FAILED</p>
                            <p style={{ fontSize: "9px", color: "rgba(255,255,255,0.3)", maxWidth: "280px", textAlign: "center", lineHeight: 1.5 }}>
                              {currentScene?.failure_reason || currentScene?.critique || "This candidate was rejected before it could enter the film."}
                            </p>
                          </div>
                        )}
                      </motion.div>
                    </AnimatePresence>

                    {/* Scene overlay */}
                    {currentScene && (
                      <div style={{ position: "absolute", bottom: "44px", left: "14px", right: "14px", display: "flex", justifyContent: "space-between", alignItems: "flex-end", pointerEvents: "none" }}>
                        <div>
                          <div style={{ fontSize: "9px", letterSpacing: "0.15em", color: "rgba(255,255,255,0.5)", textTransform: "uppercase", textShadow: "0 1px 4px rgba(0,0,0,0.9)" }}>
                            SHOT {shotNumber} OF {totalClips || "?"}
                          </div>
                          <div style={{ fontSize: "9px", color: "rgba(255,255,255,0.35)", marginTop: "3px", textShadow: "0 1px 4px rgba(0,0,0,0.9)" }}>
                            {currentScene.characters_involved?.join(" · ")}
                          </div>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "3px" }}>
                          <span style={{ fontSize: "9px", color: STATUS_COLOR[currentScene.status] ?? "#fff", textShadow: "0 1px 4px rgba(0,0,0,0.9)" }}>
                            ● {STATUS_LABEL[currentScene.status] ?? currentScene.status.toUpperCase()}
                          </span>
                          {currentScene.drama_score != null && (
                            <span style={{ fontSize: "9px", color: "#c9a55a", textShadow: "0 1px 4px rgba(0,0,0,0.9)" }}>
                              TENSION {(currentScene.drama_score * 100).toFixed(0)}%
                            </span>
                          )}
                          {continuityPct !== null && (
                            <span
                              title="Continuity score reported by the visual critic."
                              style={{ fontSize: "9px", color: currentScene.review_mode === "director_approved" ? "#4ade80" : "#facc15", textShadow: "0 1px 4px rgba(0,0,0,0.9)" }}
                            >
                              CONTINUITY {continuityPct}%
                            </span>
                          )}
                          {(() => {
                            const badge = REVIEW_BADGE[currentScene.review_mode ?? "unverified"];
                            return badge ? (
                              <span title={badge.title} style={{ fontSize: "9px", color: badge.color, textShadow: "0 1px 4px rgba(0,0,0,0.9)" }}>
                                {badge.label}
                              </span>
                            ) : null;
                          })()}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* ── Playback Controls ── */}
              <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", justifyContent: "center" }}>
                {/* PREV/NEXT step between PLAYABLE shots. They previously stepped
                    by raw index, so a queued or failed candidate in the middle of
                    the timeline stopped playback with no way to continue. */}
                <button
                  onClick={() => goToPlayable(currentIndex - 1, -1)}
                  disabled={prevPlayable === -1}
                  title={prevPlayable === -1 ? "No earlier playable shot" : "Previous playable shot"}
                  style={{ padding: "7px 14px", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px", color: prevPlayable === -1 ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.6)", cursor: prevPlayable === -1 ? "default" : "pointer", fontSize: "10px", letterSpacing: "0.1em", textTransform: "uppercase", fontFamily: "inherit" }}
                >
                  ◀ PREV
                </button>

                {/* Play just the selected shot. Reviewing one clip on its own was
                    impossible before: the only play control started the whole reel. */}
                <button
                  onClick={playCurrent}
                  disabled={!isPlayable(currentScene)}
                  title={isPlayable(currentScene) ? "Play only this shot" : "This shot has no playable video"}
                  style={{ padding: "7px 14px", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.14)", borderRadius: "4px", color: isPlayable(currentScene) ? "rgba(255,255,255,0.75)" : "rgba(255,255,255,0.2)", cursor: isPlayable(currentScene) ? "pointer" : "default", fontSize: "10px", letterSpacing: "0.1em", textTransform: "uppercase", fontFamily: "inherit" }}
                >
                  ▶ PLAY SHOT
                </button>

                <button
                  onClick={playAll}
                  disabled={readyScenes.length === 0}
                  style={{ padding: "9px 22px", background: readyScenes.length === 0 ? "rgba(201,165,90,0.3)" : "linear-gradient(135deg,#c9a55a,#a8863a)", border: "none", borderRadius: "4px", color: readyScenes.length === 0 ? "rgba(0,0,0,0.4)" : "#000", cursor: readyScenes.length === 0 ? "default" : "pointer", fontSize: "11px", fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", fontFamily: "inherit" }}
                >
                  {autoPlay ? "■ STOP REEL" : `▶ PLAY FILM (${readyScenes.length} CLIPS)`}
                </button>

                <button
                  onClick={() => goToPlayable(currentIndex + 1, 1)}
                  disabled={nextPlayable === -1}
                  title={nextPlayable === -1 ? "No later playable shot" : "Next playable shot"}
                  style={{ padding: "7px 14px", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px", color: nextPlayable === -1 ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.6)", cursor: nextPlayable === -1 ? "default" : "pointer", fontSize: "10px", letterSpacing: "0.1em", textTransform: "uppercase", fontFamily: "inherit" }}
                >
                  NEXT ▶
                </button>

                <button
                  onClick={fetchScenes}
                  style={{ padding: "7px 14px", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "4px", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: "10px", letterSpacing: "0.1em", textTransform: "uppercase", fontFamily: "inherit" }}
                >
                  ↻ REFRESH
                </button>
              </div>
              {currentScene && (
                <div style={{ width: "100%", maxWidth: "960px", display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "center", fontSize: "9px", color: "rgba(255,255,255,0.42)", letterSpacing: "0.06em" }}>
                  <span style={{ color: currentScene.anchor_names?.length ? "#c9a55a" : "rgba(255,255,255,0.35)" }}>
                    {currentScene.anchor_names?.length ? `CAST LOCK: ${currentScene.anchor_names.join(", ")}` : "CAST LOCK: VISUAL BIBLE"}
                  </span>
                  <span>•</span>
                  {/* Reads the renderer's own confirmation. Previously this printed
                      "STATEFUL PARENT: VERIFIED" whenever previous_interaction_id was
                      non-empty -- but that field is written before the API call, and
                      the call did not send it, so the badge was never evidence. */}
                  {!currentScene.previous_interaction_id ? (
                    <span title="First shot of the film; it has no parent to branch from.">
                      STATEFUL CHAIN: ROOT SHOT
                    </span>
                  ) : currentScene.stateful_chain_verified ? (
                    <span style={{ color: "#4ade80" }} title="The renderer accepted the previous accepted shot as this shot's parent interaction.">
                      STATEFUL PARENT: VERIFIED
                    </span>
                  ) : (
                    <span style={{ color: "#facc15" }} title="The parent interaction was not accepted by the renderer. Continuity for this shot came from the prompt ledger (character bible and carried-forward state) instead.">
                      CONTINUITY: PROMPT LEDGER ONLY
                    </span>
                  )}
                  {currentScene.scene_asset_labels?.length ? (
                    <><span>•</span><span style={{ color: "#7c5cd8" }} title="Media you attached to this specific shot.">
                      SHOT ASSETS: {currentScene.scene_asset_labels.join(", ")}
                    </span></>
                  ) : null}
                  {currentScene.actual_duration_seconds != null && <><span>•</span><span title="Duration measured from the returned MP4 with ffprobe.">{currentScene.actual_duration_seconds.toFixed(2)}s MEASURED</span></>}
                  {currentScene.critique && <><span>•</span><span title={currentScene.critique}>DIRECTOR: {currentScene.critique.slice(0, 110)}</span></>}
                </div>
              )}
            </>
          )}
        </div>

        {/* ── Scene Sidebar ── */}
        <div style={{ width: "300px", borderLeft: "1px solid rgba(255,255,255,0.07)", overflowY: "auto", padding: "14px", flexShrink: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
            <h2 style={{ fontSize: "9px", letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(255,255,255,0.35)", margin: 0 }}>
              SHOT REVIEW TIMELINE ({scenes.length} ATTEMPTS)
            </h2>
            <div style={{ display: "flex", gap: "8px", fontSize: "8px", color: "rgba(255,255,255,0.25)" }}>
              <span style={{ color: STATUS_COLOR.critiqued }}>●</span> {scenes.filter(s => s.status === "critiqued").length} READY
              &nbsp;<span style={{ color: STATUS_COLOR.failed }}>●</span> {scenes.filter(s => s.status === "failed").length} FAILED
            </div>
          </div>

          {scenes.length === 0 && !isLoading && (
            <div style={{ textAlign: "center", padding: "28px 12px", color: "rgba(255,255,255,0.2)", fontSize: "10px", lineHeight: 1.6 }}>
              No scenes yet. Start a new film in the Studio.
            </div>
          )}

          {scenes.map((scene, idx) => (
            <motion.button
              key={scene.scene_id}
              onClick={() => { setCurrentIndex(idx); setAutoPlay(false); }}
              whileHover={{ x: 3 }}
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "10px 11px", marginBottom: "6px",
                background: idx === currentIndex ? "rgba(201,165,90,0.10)" : "rgba(255,255,255,0.02)",
                border: idx === currentIndex ? "1px solid rgba(201,165,90,0.3)" : "1px solid rgba(255,255,255,0.05)",
                borderLeft: `3px solid ${STATUS_COLOR[scene.status] ?? "rgba(255,255,255,0.1)"}`,
                borderRadius: "5px", cursor: "pointer",
                fontFamily: "inherit", color: "inherit",
                transition: "all 0.15s",
                opacity: scene.status === "failed" ? 0.55 : 1,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "3px" }}>
                <span style={{ fontSize: "10px", fontWeight: 600, color: idx === currentIndex ? "#c9a55a" : "rgba(255,255,255,0.65)" }}>
                  SHOT {scene.scene_index || idx + 1}{(scene.generation_attempt ?? 1) > 1 ? ` · RETAKE ${scene.generation_attempt}` : ""}
                </span>
                <span style={{ fontSize: "8px", padding: "1px 5px", background: "rgba(255,255,255,0.05)", borderRadius: "3px", color: STATUS_COLOR[scene.status] ?? "rgba(255,255,255,0.3)" }}>
                  {STATUS_LABEL[scene.status] ?? scene.status.toUpperCase()}
                </span>
              </div>
              <div style={{ fontSize: "9px", color: "rgba(255,255,255,0.35)", marginBottom: "3px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {scene.characters_involved?.join(", ") || "Unknown cast"}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontSize: "8px", color: "rgba(255,255,255,0.2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                  {(scene.omni_prompt || scene.veo_prompt)?.substring(0, 50) ?? ""}…
                </div>
                {/* Show a continuity score when one exists, else the writer's
                    tension rating, else nothing. The old expression fell back to
                    `(drama_score ?? 0) * 100`, printing "0%" for unscored shots. */}
                <span
                  style={{
                    fontSize: "8px",
                    marginLeft: "6px",
                    flexShrink: 0,
                    color: scene.continuity_score != null
                      ? (scene.review_mode === "director_approved" ? "#4ade80" : "#facc15")
                      : "#c9a55a",
                  }}
                  title={scene.continuity_score != null ? "Continuity score from the visual critic" : "Writer's tension rating for this beat"}
                >
                  {scene.continuity_score != null
                    ? `C${Math.round(scene.continuity_score * 100)}`
                    : scene.drama_score != null
                    ? `T${Math.round(scene.drama_score * 100)}`
                    : ""}
                </span>
              </div>
            </motion.button>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes spin  { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
      `}</style>
    </div>
  );
}
