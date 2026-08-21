"use client";

import React from "react";
import Link from "next/link";
import { AppShell, Panel, Badge } from "../../components/ui/Layout";
import { Footer } from "../../components/layout/Footer";

export default function TermsAndConditionsPage() {
  return (
    <AppShell>
      <header className="w-full max-w-4xl mx-auto py-6 flex items-center justify-between border-b border-white/10 mb-8">
        <Link href="/" className="font-[family-name:var(--font-family-display)] text-2xl font-bold tracking-wider text-white hover:text-[var(--color-accent)] transition-colors">
          REVERIE
        </Link>
        <div className="flex items-center gap-4">
          <Badge label="HACKATHON DEMO TERMS" variant="accent" />
          <Link href="/" className="text-xs font-mono text-white/60 hover:text-white transition-colors">
            [&larr; BACK TO HOME]
          </Link>
        </div>
      </header>

      <main className="w-full max-w-4xl mx-auto flex-1 flex flex-col gap-8 pb-16">
        <Panel title="DEMO TERMS" subtitle="HACKATHON BUILD • NOT A PRODUCTION CONTRACT">
          <article className="flex flex-col gap-6 text-sm text-white/80 leading-relaxed font-[family-name:var(--font-family-body)]">
            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                1. Acceptance of Terms
              </h2>
              <p>
                By accessing this REVERIE hackathon demo, you agree to use it responsibly and not submit content you do not have the right to process. These demo terms are not a production contract or legal advice.
              </p>
            </section>

            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                2. Acceptable Use &amp; Audience Conduct
              </h2>
              <p className="mb-2">
                You may experiment with the studio and audience prompts. You agree not to:
              </p>
              <ul className="list-disc list-inside space-y-1 pl-2 text-white/70">
                <li>Inject malicious code, SQL/NoSQL injection payloads, or attempt to exploit CRDT protocol vulnerabilities.</li>
                <li>Submit prompts intended to generate illegal, abusive, harassing, or defamatory content within the simulation.</li>
                <li>Attempt to scrape, overwhelm, bypass quotas, or misuse the backend, WebSocket, or Gemini Omni rendering pipeline.</li>
              </ul>
            </section>

            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                3. AI Generation Liability &amp; Emergent Content
              </h2>
              <p>
                REVERIE is an autonomous multi-agent film system powered by Gemini planning/critic agents and Gemini Omni Flash. Outputs can be inaccurate, inconsistent, blocked, or unsuitable. <strong>Do not treat generated dialogue, images, or video as factual, safe, cleared, or production-ready without human review.</strong> Generated content does not represent the views of REVERIE or Google.
              </p>
            </section>

            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                4. API Usage Limits &amp; Budget Shield Enforcement
              </h2>
              <p>
                REVERIE reserves Omni capacity before each generation and defaults to a 24-generation UTC daily cap. The Director may pause a render through the observability gate, and rejected candidates can consume separately budgeted retakes. Deployments should add authentication and user-level rate limits before public production access.
              </p>
            </section>

            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                5. Intellectual Property Rights
              </h2>
              <p>
                All underlying software architecture, design systems (including Astryx Gothic themes), 3D town assets, and proprietary orchestration algorithms remain the exclusive property of REVERIE Studios. Users retain personal, non-commercial rights to share exported video clips of simulations they co-created, subject to attribution requirements.
              </p>
            </section>
          </article>
        </Panel>
      </main>

      <Footer />
    </AppShell>
  );
}
