"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Button, Layout, LayoutHeader, LayoutContent, HStack, VStack, Card } from "@astryxdesign/core";
import { Panel, Badge, FeaturedCard, ProgressBar, TelemetryStat, StatusDot } from "../components/ui/Layout";
import { Footer } from "../components/layout/Footer";
import { ThemeToggle } from "../components/ui/ThemeToggle";

interface LiveStats {
  simRunning: boolean;
  scenes: { scene_id: string; status: string; drama_score: number | null }[];
  tickLatency: number;
  tokenBurn: number;
}

export default function LandingPage() {
  const [liveStats, setLiveStats] = useState<LiveStats | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [health, scenesRes] = await Promise.all([
          fetch("/health").then((r) => r.json()),
          fetch("/api/scenes").then((r) => r.json()),
        ]);
        setLiveStats({
          simRunning: health.simulation_running ?? false,
          scenes: scenesRes.scenes ?? [],
          tickLatency: 0,
          tokenBurn: 0,
        });
      } catch { /* ignore */ }
    };
    fetchStats();
    const id = setInterval(fetchStats, 8000);
    return () => clearInterval(id);
  }, []);

  const readyScenes = liveStats?.scenes.filter((s) => s.status === "critiqued") ?? [];
  const failedScenes = liveStats?.scenes.filter((s) => s.status === "failed") ?? [];
  const renderingScenes = liveStats?.scenes.filter((s) => s.status === "rendering" || s.status === "queued") ?? [];

  /* Peak tension across rendered shots, or null when no shot carries a rating.
     drama_score is nullable, and Math.max() over an array containing null
     returns NaN -- which rendered as "NaN%" -- while an empty list returns
     -Infinity. Both are filtered out here so the UI shows a real figure or
     states that none was measured. */
  const scoredTensions = readyScenes
    .map((s) => s.drama_score)
    .filter((score): score is number => typeof score === "number");
  const peakTension = scoredTensions.length > 0 ? Math.max(...scoredTensions) : null;
  const peakTensionPct = peakTension === null ? null : Math.round(peakTension * 100);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.2 },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 30 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.8 } },
  };

  return (
    <Layout
      height="auto"
      header={
        <LayoutHeader
          hasDivider
          style={{
            padding: "var(--spacing-4) var(--spacing-6)",
            backgroundColor: "color-mix(in srgb, var(--color-background-surface) 85%, transparent)",
            borderColor: "var(--color-border)",
          }}
        >
          <HStack className="w-full max-w-7xl mx-auto justify-between items-center">
            <Link
              href="/"
              className="font-[family-name:var(--font-family-display)] text-2xl md:text-3xl font-bold tracking-widest transition-opacity hover:opacity-80"
              style={{ color: "var(--color-accent)" }}
            >
              REVERIE
            </Link>
            <HStack gap={4} className="items-center">
              <ThemeToggle />
              <Link href="/screening">
                <Button
                  variant="ghost"
                  label="[SCREENING]"
                  className="border font-mono text-xs cursor-pointer"
                  style={{ borderColor: "var(--color-border)", color: "var(--color-text-secondary)" }}
                />
              </Link>
              <Link href="/studio">
                <Button
                  variant="ghost"
                  label="[ENTER STUDIO]"
                  className="border font-mono text-xs cursor-pointer"
                  style={{ borderColor: "var(--color-accent)", color: "var(--color-accent)" }}
                />
              </Link>
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={0} isScrollable={false}>
          <VStack className="w-full items-center">
            {/* HERO SECTION (100vh) */}
            <section className="relative w-full min-h-[95vh] flex flex-col items-center justify-center px-4 py-16 overflow-hidden">
              {/* Background Layer with Cinematic Gradient */}
              <div
                className="absolute inset-0 bg-cover bg-center filter blur-sm transform scale-105 pointer-events-none z-0 opacity-30"
                style={{ backgroundImage: "url('https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=1920&q=80')" }}
              />
              <div
                className="absolute inset-0 pointer-events-none z-0"
                style={{
                  background: "linear-gradient(to bottom, transparent 0%, color-mix(in srgb, var(--color-background-body) 60%, transparent) 50%, var(--color-background-body) 100%)",
                }}
              />

              <motion.div
                variants={containerVariants}
                initial="hidden"
                animate="visible"
                className="relative z-10 max-w-4xl mx-auto flex flex-col items-center text-center gap-6 w-full"
              >
                <motion.div variants={itemVariants} className="flex items-center gap-3 flex-wrap justify-center">
                  <Badge label="GOOGLE CLOUD HACKATHON 2026" variant="accent" />
                  <Badge label="Gemini 3.5 Flash + Omni" variant="secondary" />
                </motion.div>

                <motion.h1
                  variants={itemVariants}
                  className="font-normal tracking-[0.12em] font-[family-name:var(--font-family-display)] leading-none"
                  style={{
                    fontSize: "clamp(3rem, 8vw, 6rem)",
                    color: "var(--color-accent)",
                    textShadow: "0 0 40px color-mix(in srgb, var(--color-accent) 40%, transparent)",
                  }}
                >
                  REVERIE
                </motion.h1>

                <motion.h2
                  variants={itemVariants}
                  className="text-2xl md:text-4xl font-light tracking-wide opacity-90 font-[family-name:var(--font-family-body)]"
                  style={{ color: "var(--color-accent)" }}
                >
                  The First Living Film.
                </motion.h2>

                <motion.p
                  variants={itemVariants}
                  className="text-base md:text-lg opacity-80 max-w-2xl font-[family-name:var(--font-family-body)] leading-relaxed"
                >
                  Five AI characters with persistent memories inhabit a photorealistic 3D town. They improvise emergent drama. A virtual Director renders it as cinema. You co-create the story in real time.
                </motion.p>

                {/* Studio Setup Gateway */}
                <motion.div variants={itemVariants} className="w-full max-w-md mt-6 flex justify-center">
                  <Link href="/studio" className="w-full">
                    <button
                      className="w-full py-4 px-6 rounded font-mono text-sm uppercase tracking-wider transition-all cursor-pointer flex items-center justify-center gap-3 border shadow-xl hover:brightness-110 active:scale-95"
                      style={{
                        backgroundColor: "color-mix(in srgb, var(--color-accent) 20%, transparent)",
                        borderColor: "var(--color-accent)",
                        color: "var(--color-accent)",
                      }}
                    >
                      <span className="font-bold text-lg tracking-widest">[ ENTER DIRECTOR STUDIO ]</span>
                    </button>
                  </Link>
                </motion.div>
              </motion.div>
            </section>

            {/* FEATURES SECTION */}
            <VStack gap={6} className="w-full max-w-7xl mx-auto py-24 px-6 items-center">
              <VStack gap={2} className="items-center text-center">
                <Badge label="CORE ARCHITECTURE" variant="accent" />
                <h2
                  className="text-3xl md:text-5xl font-bold font-[family-name:var(--font-family-display)] tracking-wide"
                  style={{ color: "var(--color-accent)" }}
                >
                  Engineered for Autonomy &amp; Scale
                </h2>
                <p className="text-sm font-mono opacity-60 max-w-xl">
                  Strictly typed, capital-efficient infrastructure delivering continuous generative drama at sub-$5 daily compute costs.
                </p>
              </VStack>

              <HStack gap={6} className="w-full flex-col md:flex-row items-stretch pt-6">
                <div className="flex-1 flex">
                  <FeaturedCard
                    badge="STANFORD ARCHITECTURE"
                    title="Autonomous Agents"
                    subtitle="Gemini 3.5 Flash"
                    description="Persistent associative memory streams, cognitive reflection loops, and dynamic spatial pathfinding drive unscripted, believable character improvisation across the town."
                  />
                </div>
                <div className="flex-1 flex">
                  <FeaturedCard
                     badge="GEMINI OMNI"
                     title="Cinematic Rendering"
                     subtitle="GEMINI 3.5 FLASH DIRECTOR"
                     description="An autonomous Director monitors tension in real time. When drama beats cross critical thresholds, it prompts Gemini Omni to generate photorealistic 16:9 cinematic video scenes up to 10 seconds long."
                   />
                </div>
                <div className="flex-1 flex">
                  <FeaturedCard
                    badge="SUB-SECOND SYNC"
                    title="Audience Co-Creation"
                    subtitle="YJS CRDT & WEBSOCKETS"
                    description="Thousands of live viewers inject narrative prompts ('whispers') directly into character subconscious layers via conflict-free replicated data types with zero database write amplification."
                  />
                </div>
              </HStack>
            </VStack>

            {/* TELEMETRY TEASER SECTION */}
            <VStack className="w-full max-w-6xl mx-auto py-16 px-6 mb-24 items-center">
              <Panel
                title="DIRECTOR'S MONITOR"
                subtitle="ENTERPRISE OBSERVABILITY & LIVE CRDT STREAM"
                action={<Badge label="LIVE TELEMETRY PREVIEW" variant="accent" />}
                className="w-full shadow-2xl"
              >
                <HStack gap={6} className="w-full flex-col md:flex-row items-stretch p-2">
                  <VStack gap={4} className="flex-1 justify-between">
                    <header
                      className="flex justify-between items-center border-b pb-2"
                      style={{ borderColor: "var(--color-border)" }}
                    >
                      <span className="font-mono text-xs font-bold" style={{ color: "var(--color-accent)" }}>
                        {liveStats?.simRunning
                          ? "SIMULATION LOOP: RUNNING"
                          : liveStats
                          ? `SIMULATION IDLE — ${liveStats.scenes.length} SCENES TOTAL`
                          : "DIRECTOR'S MONITOR"}
                      </span>
                      <StatusDot status={liveStats?.simRunning ? "active" : "idle"} />
                    </header>
                    <p className="text-sm opacity-70 font-mono text-xs leading-relaxed">
                      {readyScenes.length > 0
                        ? `${readyScenes.length} clip${readyScenes.length !== 1 ? "s" : ""} rendered${peakTensionPct !== null ? ` · peak tension: ${peakTensionPct}%` : " · no tension rating recorded"}`
                        : liveStats
                        ? "No clips rendered yet. Start a simulation in Studio to generate film."
                        : "Loading live telemetry…"}
                    </p>
                    <ProgressBar
                      value={peakTensionPct ?? 0}
                      label={
                        peakTensionPct === null
                          ? "PEAK TENSION — NOT RATED"
                          : `PEAK TENSION — ${peakTensionPct}%`
                      }
                      variant={peakTension !== null && peakTension > 0.6 ? "danger" : "accent"}
                    />
                    <HStack gap={2} className="w-full flex-col sm:flex-row items-stretch pt-2">
                      <div className="flex-1 flex">
                        <TelemetryStat label="CLIPS READY" value={readyScenes.length} unit="/" subtext={`${liveStats?.scenes.length ?? 0} Total`} />
                      </div>
                      <div className="flex-1 flex">
                        <TelemetryStat label="RENDERING" value={renderingScenes.length} unit="OMNI" subtext="In Progress" />
                      </div>
                      <div className="flex-1 flex">
                        <TelemetryStat label="FAILED" value={failedScenes.length} unit="ERR" subtext="Omni Errors" />
                      </div>
                      <div className="flex-1 flex">
                        <TelemetryStat label="ENGINE" value={liveStats?.simRunning ? "ON" : "OFF"} subtext={liveStats?.simRunning ? "Running" : "Idle"} />
                      </div>
                    </HStack>
                  </VStack>

                  <Card
                    variant="muted"
                    padding={4}
                    style={{
                      width: "100%",
                      maxWidth: "320px",
                      borderColor: "var(--color-border)",
                    }}
                  >
                    <VStack gap={3} className="w-full font-mono text-xs">
                      <span
                        className="text-[10px] opacity-60 uppercase tracking-widest border-b pb-1"
                        style={{ borderColor: "var(--color-border)" }}
                      >
                        SCENE QUEUE // LIVE FROM FIRESTORE
                      </span>
                      {liveStats && liveStats.scenes.length === 0 && (
                        <div className="text-[10px] opacity-40 py-2 text-center">No scenes yet — start a simulation</div>
                      )}
                      {(liveStats?.scenes ?? []).slice(0, 3).map((scene) => (
                        <div
                          key={scene.scene_id}
                          className="flex items-center justify-between py-1 border-b"
                          style={{ borderColor: "var(--color-border)", color: scene.status === "critiqued" ? "var(--color-accent-secondary)" : scene.status === "rendering" ? "var(--color-accent)" : "rgba(255,255,255,0.4)" }}
                        >
                          <span className="truncate max-w-[180px]">[v4] {scene.scene_id.slice(0, 12)}…mp4</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${scene.status === "rendering" ? "animate-pulse" : ""}`} style={{ borderColor: "var(--color-border)" }}>
                            {scene.status === "critiqued" ? "READY" : scene.status === "rendering" ? "RENDERING" : scene.status === "queued" ? "QUEUED" : "FAILED"}
                          </span>
                        </div>
                      ))}
                      <Link href="/screening" className="w-full mt-2">
                        <button
                          className="w-full py-2 rounded font-bold transition-all text-center cursor-pointer border hover:opacity-80"
                          style={{
                            backgroundColor: "color-mix(in srgb, var(--color-accent) 15%, transparent)",
                            borderColor: "var(--color-accent)",
                            color: "var(--color-accent)",
                          }}
                        >
                          [&rarr; Open Screening Room]
                        </button>
                      </Link>
                    </VStack>
                  </Card>
                </HStack>
              </Panel>
            </VStack>
          </VStack>
        </LayoutContent>
      }
      footer={<Footer />}
    />
  );
}
