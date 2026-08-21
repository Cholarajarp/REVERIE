"use client";

import React, { useRef, useEffect } from "react";
import { ChatMessageList, ChatMessage, TextInput, Button, Text } from "@astryxdesign/core";
import { Whisper } from "../../store/simulationStore";
import { Panel, Badge } from "../ui/Layout";

export interface WhisperFeedProps {
  whispers: Whisper[];
  onSendWhisper?: (text: string) => void;
}

/**
 * Whispers store `ts` as an ISO string so ordering and timezones stay correct
 * across peers; display is localised here at render time. Seed/mock data still
 * carries pre-formatted clock strings, so fall back to showing those as-is.
 */
function formatTimestamp(ts: string): string {
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return ts;
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function WhisperFeed({ whispers, onSendWhisper }: WhisperFeedProps) {
  const [input, setInput] = React.useState("");
  const feedEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [whispers]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    onSendWhisper?.(input.trim());
    setInput("");
  };

  return (
    <Panel
      title="WHISPER FEED"
      subtitle="REAL-TIME AGENT DIALOGUE & TELEMETRY"
      action={<Badge count={whispers.length} label="MESSAGES" variant="secondary" />}
      className="h-full flex flex-col max-h-[600px]"
    >
      <section className="flex-1 overflow-y-auto pr-1 flex flex-col">
        <ChatMessageList
          emptyState={
            <p className="text-white/40 italic text-center py-10 font-[family-name:var(--font-family-body)]">
              Listening for agent transmissions... The town is quiet.
            </p>
          }
        >
          {whispers.map((w) => (
            <ChatMessage
              // Stable id, so settling a ghost updates in place instead of
              // remounting the bubble and restarting its transition.
              key={w.id}
              sender={w.user === "Divine Architect" ? "user" : "assistant"}
              name={<span className="font-bold text-accent font-heading text-sm">{w.user}</span>}
              metadata={
                <span className="text-2xs text-secondary">
                  {formatTimestamp(w.ts)}
                  {w.pending ? " · AWAITING CONSENSUS" : ""}
                  {w.failed ? " · UNCONFIRMED — RETRYING" : ""}
                </span>
              }
              // Ghost bubbles: optimistic whispers render at half opacity and
              // fade up once the CRDT confirms them.
              className={`transition-opacity duration-300 ${w.pending ? "opacity-50" : "opacity-100"}`}
              aria-busy={w.pending ? true : undefined}
            >
              <Text size="sm" color="primary">
                {w.text}
              </Text>
            </ChatMessage>
          ))}
        </ChatMessageList>
        <div ref={feedEndRef} />
      </section>

      <form onSubmit={handleSubmit} className="pt-3 border-t border-white/10 flex gap-2 items-end">
        <div className="flex-1">
          <TextInput
            label="Whisper transmission input"
            isLabelHidden
            value={input}
            onChange={(val) => setInput(val)}
            placeholder="Inject divine suggestion or whisper..."
          />
        </div>
        <Button
          type="submit"
          label="Whisper"
          variant="primary"
        />
      </form>
    </Panel>
  );
}
