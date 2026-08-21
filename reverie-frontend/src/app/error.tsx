"use client";

import React, { useEffect } from "react";
import { Button } from "@astryxdesign/core";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("REVERIE Simulation Error Caught:", error);
  }, [error]);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-[var(--color-background-body)] text-white p-6 relative overflow-hidden font-mono text-center">
      {/* Background Film Grain and Red/Amber Alert Glow */}
      <span className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(232,176,75,0.1)_0,transparent_70%)] pointer-events-none" />
      
      <section className="relative z-10 max-w-lg p-8 rounded bg-[var(--color-background-surface)] border border-[var(--color-accent)]/40 shadow-[0_0_50px_rgba(232,176,75,0.2)] flex flex-col items-center gap-6">
        <header className="flex flex-col items-center gap-2">
          <span className="w-4 h-4 rounded-full bg-[var(--color-accent)] animate-ping inline-block shadow-[0_0_15px_var(--color-accent)]" />
          <h1 className="text-2xl md:text-3xl font-bold tracking-widest uppercase font-[family-name:var(--font-family-display)] text-[var(--color-accent)]">
            SIGNAL LOST // SIMULATION DISCONNECTED
          </h1>
        </header>

        <section className="text-xs text-white/70 leading-relaxed bg-black/50 p-4 rounded border border-white/10 w-full text-left font-sans">
          <p className="font-mono text-[10px] text-[var(--color-accent-secondary)] uppercase tracking-wider mb-1">
            TELEMETRY DIAGNOSTIC REPORT:
          </p>
          <p className="italic text-white/90">
            {error.message || "WebGL render pipeline or CRDT WebSocket synchronization stream encountered an unrecoverable exception."}
          </p>
          {error.digest && (
            <p className="text-[10px] font-mono text-white/40 mt-2">
              ERROR DIGEST // {error.digest}
            </p>
          )}
        </section>

        <footer className="flex flex-col sm:flex-row items-center gap-3 w-full justify-center">
          <Button
            label="Reconnect & Re-initialize"
            variant="primary"
            onClick={() => reset()}
          />
          <Button
            label="Reload Page"
            variant="ghost"
            onClick={() => window.location.reload()}
          />
        </footer>
      </section>
    </main>
  );
}
