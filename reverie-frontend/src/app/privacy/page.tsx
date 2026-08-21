"use client";

import React from "react";
import Link from "next/link";
import { AppShell, Panel, Badge } from "../../components/ui/Layout";
import { Footer } from "../../components/layout/Footer";

export default function PrivacyPolicyPage() {
  return (
    <AppShell>
      <header className="w-full max-w-4xl mx-auto py-6 flex items-center justify-between border-b border-white/10 mb-8">
        <Link href="/" className="font-[family-name:var(--font-family-display)] text-2xl font-bold tracking-wider text-white hover:text-[var(--color-accent)] transition-colors">
          REVERIE
        </Link>
        <div className="flex items-center gap-4">
          <Badge label="HACKATHON DEMO NOTICE" variant="accent" />
          <Link href="/" className="text-xs font-mono text-white/60 hover:text-white transition-colors">
            [&larr; BACK TO HOME]
          </Link>
        </div>
      </header>

      <main className="w-full max-w-4xl mx-auto flex-1 flex flex-col gap-8 pb-16">
        <Panel title="PRIVACY NOTICE" subtitle="HACKATHON DEMO • REVIEW BEFORE PRODUCTION USE">
          <article className="flex flex-col gap-6 text-sm text-white/80 leading-relaxed font-[family-name:var(--font-family-body)]">
            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                1. Overview &amp; Commitment to Privacy
              </h2>
              <p>
                This is a hackathon demonstration, not a production privacy policy. Do not submit personal, confidential, or sensitive information in prompts, character memories, or reference media.
              </p>
            </section>

            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                2. Demo Data
              </h2>
              <p className="mb-2">
                The current demo does not provide account authentication. It may process the story prompt, cast descriptions, reference media, browser interaction data, and generated output needed to operate the session.
              </p>
              <ul className="list-disc list-inside space-y-1 pl-2 text-white/70">
                <li><strong>Reference media:</strong> Character images and uploaded assets can be stored in the configured Cloud Storage bucket to support the render.</li>
                <li><strong>Production records:</strong> Scene prompts, review results, and budget counters can be stored in Firestore so the Screening Room can show why a shot was accepted or rejected.</li>
              </ul>
            </section>

            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                3. Third-Party AI &amp; Cloud Infrastructure
              </h2>
              <p>
                REVERIE uses Google Cloud services for its app, storage, state, and Gemini planning/critique agents, plus Gemini Omni Flash for video generation. Provider processing and retention are governed by the configuration and terms of the Google services used for the deployment. This demo does not claim a zero-retention agreement or isolated VPC deployment.
              </p>
            </section>

            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                4. Cookies &amp; Telemetry Storage
              </h2>
              <p>
                The frontend may use browser storage for temporary UI/session preferences. The current demo does not rely on Firebase authentication cookies. Configure your own consent, analytics, retention, and deletion controls before any production deployment.
              </p>
            </section>

            <section>
              <h2 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] mb-2">
                5. Your Rights (GDPR / CCPA)
              </h2>
              <p>
                If you deploy REVERIE, you are responsible for implementing applicable privacy rights, retention periods, deletion workflows, legal notices, and a working privacy contact. The demo has no account-management or self-service deletion system.
              </p>
            </section>
          </article>
        </Panel>
      </main>

      <Footer />
    </AppShell>
  );
}
