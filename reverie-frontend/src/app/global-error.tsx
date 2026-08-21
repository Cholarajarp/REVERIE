"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global error caught:", error);
  }, [error]);

  return (
    <html lang="en" className="dark" style={{ backgroundColor: "#0a0908" }}>
      <body className="min-h-screen flex flex-col items-center justify-center text-white bg-[var(--color-background-body)] p-6 font-mono text-center">
        <h2 className="text-xl font-bold text-[var(--color-accent)] mb-2">SYSTEM CRITICAL ERROR // REVERIE ENGINE HALTED</h2>
        <p className="text-xs text-white/70 mb-6 max-w-md">{error.message || "An unexpected error occurred in the simulation runtime."}</p>
        <button
          onClick={() => reset()}
          className="bg-[var(--color-accent)]/20 border border-[var(--color-accent)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-black font-semibold uppercase tracking-wider px-6 py-2.5 rounded text-xs transition-all duration-300"
        >
          [REBOOT SIMULATION ENGINE]
        </button>
      </body>
    </html>
  );
}
