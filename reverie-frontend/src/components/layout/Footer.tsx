"use client";

import React from "react";
import Link from "next/link";

export function Footer() {
  return (
    <footer
      className="w-full py-8 px-6 md:px-12 border-t font-mono text-xs flex flex-col md:flex-row items-center justify-between gap-4 z-10 relative"
      style={{
        backgroundColor: "var(--color-background-body)",
        borderColor: "var(--color-border)",
        color: "var(--color-accent)",
      }}
    >
      <section className="flex items-center gap-2">
        <span className="font-[family-name:var(--font-family-display)] text-sm font-bold tracking-widest">
          REVERIE
        </span>
        <span className="opacity-40">|</span>
        <span className="opacity-70">&copy; 2026 REVERIE Studios. All rights reserved.</span>
      </section>

      <nav className="flex items-center gap-6 opacity-80">
        <Link
          href="/privacy"
          className="hover:opacity-100 transition-opacity underline-offset-4 hover:underline"
        >
          Privacy Policy
        </Link>
        <Link
          href="/terms"
          className="hover:opacity-100 transition-opacity underline-offset-4 hover:underline"
        >
          Terms &amp; Conditions
        </Link>
      </nav>
    </footer>
  );
}
