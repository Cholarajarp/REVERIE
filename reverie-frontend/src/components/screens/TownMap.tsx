"use client";

import React, { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CharacterState, useSimulationStore } from "../../store/simulationStore";
import { Panel, StatusDot, Badge } from "../ui/Layout";

export interface TownMapProps {
  characters: CharacterState[];
  onSelectCharacter?: (char: CharacterState) => void;
}

interface LocationNode {
  id: string;
  name: string;
  x: number;
  y: number;
  description: string;
}

/**
 * Generates location nodes dynamically from characters' current_location values.
 * Spreads them evenly across the map area using a simple grid layout.
 */
function deriveLocations(characters: CharacterState[]): LocationNode[] {
  const uniqueLocations = Array.from(new Set(characters.map((c) => c.current_location)));
  
  // Grid positions to spread locations evenly across the map
  const positions = [
    { x: 25, y: 30 },
    { x: 75, y: 25 },
    { x: 20, y: 70 },
    { x: 70, y: 72 },
    { x: 50, y: 50 },
    { x: 40, y: 20 },
    { x: 60, y: 80 },
    { x: 85, y: 50 },
  ];

  return uniqueLocations.map((name, i) => ({
    id: `loc-${i}`,
    name,
    x: positions[i % positions.length].x,
    y: positions[i % positions.length].y,
    description: `${characters.filter((c) => c.current_location === name).length} agent(s) currently active here.`,
  }));
}

export function TownMap({ characters, onSelectCharacter }: TownMapProps) {
  const [selectedLoc, setSelectedLoc] = useState<string | null>(null);
  const worldState = useSimulationStore((state) => state.worldState);

  // Derive locations from actual character data instead of hardcoding
  const locations = useMemo(() => deriveLocations(characters), [characters]);

  const getCharactersAtLocation = (locName: string) => {
    return characters.filter((c) => c.current_location === locName);
  };

  const getEnvironmentFilters = () => {
    if (!worldState) return {};
    const weather = worldState.weather.toLowerCase();
    const isRain = weather.includes("rain") || weather.includes("drizzle");
    const isFog = weather.includes("fog") || weather.includes("cloudy");
    
    let isNight = true;
    try {
      const date = new Date(worldState.current_time);
      const hours = date.getUTCHours();
      isNight = hours < 6 || hours > 18;
    } catch {
      isNight = true;
    }

    const brightness = isNight ? (isRain ? "brightness(0.35)" : "brightness(0.5)") : "brightness(1.0)";
    const hueRotate = isRain ? "hue-rotate(15deg)" : isNight ? "hue-rotate(5deg)" : "hue-rotate(0deg)";
    const contrast = isFog ? "contrast(0.85)" : "contrast(1.1)";

    return {
      filter: `${brightness} ${hueRotate} ${contrast}`,
      transition: "filter 2s ease-in-out",
    };
  };

  // Build SVG path lines between all locations
  const pathLines = useMemo(() => {
    const lines: { x1: string; y1: string; x2: string; y2: string }[] = [];
    for (let i = 0; i < locations.length; i++) {
      for (let j = i + 1; j < locations.length; j++) {
        lines.push({
          x1: `${locations[i].x}%`,
          y1: `${locations[i].y}%`,
          x2: `${locations[j].x}%`,
          y2: `${locations[j].y}%`,
        });
      }
    }
    return lines;
  }, [locations]);

  return (
    <Panel
      title="TOWN SIMULATION MAP"
      subtitle="REAL-TIME AGENT TELEMETRY"
      action={<Badge count={characters.length} label="ACTIVE AGENTS" variant="accent" />}
      className="h-full min-h-[500px] flex flex-col relative overflow-hidden border-white/15 bg-gradient-to-b from-[var(--color-background-surface)] to-[var(--color-background-body)]"
    >
      <section
        style={getEnvironmentFilters()}
        className="relative flex-1 rounded border border-white/5 bg-black/40 overflow-hidden min-h-[400px] flex items-center justify-center p-6 transition-all duration-1000"
      >
        {/* Decorative Grid Lines */}
        <span className="absolute inset-0 bg-[linear-gradient(to_right,#1f1d1b_1px,transparent_1px),linear-gradient(to_bottom,#1f1d1b_1px,transparent_1px)] bg-[size:4rem_4rem] opacity-30 pointer-events-none z-0" />
        
        {/* SVG Roads / Paths connecting locations dynamically */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-25 z-0">
          {pathLines.map((line, i) => (
            <line
              key={i}
              x1={line.x1} y1={line.y1}
              x2={line.x2} y2={line.y2}
              stroke="var(--color-accent)"
              strokeWidth="1.5"
              strokeDasharray="6,6"
            />
          ))}
        </svg>

        {/* Dynamic Fog / Weather Overlay */}
        {worldState && worldState.weather.toLowerCase().includes("fog") && (
          <div className="absolute inset-0 bg-gradient-to-t from-white/10 via-transparent to-white/5 pointer-events-none animate-pulse duration-1000 z-0" />
        )}
        {worldState && worldState.weather.toLowerCase().includes("rain") && (
          <div className="absolute inset-0 bg-[linear-gradient(to_bottom,rgba(100,150,255,0.05)_1px,transparent_1px)] bg-[size:100%_4px] pointer-events-none z-0" />
        )}

        {/* Empty state */}
        {locations.length === 0 && (
          <div className="text-white/30 font-mono text-sm text-center z-10">
            No characters loaded. Go to <span className="text-[var(--color-accent)]">/studio</span> to configure your cast.
          </div>
        )}
        
        {/* Location Nodes */}
        {locations.map((loc) => {
          const charsHere = getCharactersAtLocation(loc.name);
          const isSelected = selectedLoc === loc.id;

          return (
            <motion.section
              key={loc.id}
              style={{ left: `${loc.x}%`, top: `${loc.y}%` }}
              className="absolute -translate-x-1/2 -translate-y-1/2 cursor-pointer group flex flex-col items-center z-10"
              onClick={() => setSelectedLoc(isSelected ? null : loc.id)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.98 }}
            >
              <section className={`w-14 h-14 rounded-full border-2 flex items-center justify-center backdrop-blur-md transition-all duration-500 shadow-xl ${
                isSelected ? "border-[var(--color-accent)] bg-[var(--color-accent)]/20 shadow-[0_0_20px_var(--color-accent)]" : "border-white/20 bg-black/70 hover:border-white/50"
              }`}>
                <span className="font-[family-name:var(--font-family-display)] text-lg text-[var(--color-accent)] font-bold">
                  {loc.name[0]}
                </span>
              </section>

              <section className="mt-2 text-center bg-black/80 px-3 py-1 rounded border border-white/10 backdrop-blur-sm shadow-md">
                <p className="text-xs font-semibold tracking-wider text-white/90 font-[family-name:var(--font-family-display)]">
                  {loc.name}
                </p>
                <section className="flex items-center justify-center gap-1 mt-0.5">
                  <StatusDot status={charsHere.length > 0 ? "active" : "idle"} />
                  <span className="text-[10px] font-mono text-white/60">{charsHere.length} AGENTS</span>
                </section>
              </section>

              {/* Character avatars clustered around location */}
              <AnimatePresence>
                {charsHere.map((char, idx) => (
                  <motion.button
                    key={char.name}
                    layoutId={`avatar-${char.name}`}
                    initial={{ opacity: 0, scale: 0 }}
                    animate={{ opacity: 1, scale: 1, x: (idx - (charsHere.length - 1) / 2) * 32, y: -42 }}
                    exit={{ opacity: 0, scale: 0 }}
                    transition={{ type: "spring", stiffness: 120, damping: 20 }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectCharacter?.(char);
                    }}
                    className="absolute top-0 w-8 h-8 rounded-full bg-[var(--color-accent-secondary)] text-black font-bold text-xs flex items-center justify-center border-2 border-black shadow-[0_0_15px_rgba(232,176,75,0.8)] hover:scale-125 transition-transform z-20 cursor-pointer"
                    title={`${char.name}: ${char.current_goal}`}
                  >
                    {char.name[0]}
                  </motion.button>
                ))}
              </AnimatePresence>
            </motion.section>
          );
        })}
      </section>

      {/* Selected Location Details Overlay */}
      <AnimatePresence>
        {selectedLoc && (
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="border-t border-white/10 pt-4 flex flex-col gap-2 bg-black/60 p-4 rounded z-30"
          >
            {(() => {
              const loc = locations.find((l) => l.id === selectedLoc);
              if (!loc) return null;
              const chars = getCharactersAtLocation(loc.name);
              return (
                <>
                  <header className="flex justify-between items-center">
                    <h3 className="text-sm font-bold font-[family-name:var(--font-family-display)] text-[var(--color-accent)] uppercase">
                      {loc.name}
                    </h3>
                    <button
                      onClick={() => setSelectedLoc(null)}
                      className="text-xs text-white/50 hover:text-white cursor-pointer"
                    >
                      [CLOSE]
                    </button>
                  </header>
                  <p className="text-xs text-white/70 italic">{loc.description}</p>
                  <section className="mt-2 flex flex-col gap-1.5">
                    <span className="text-[10px] font-mono uppercase text-white/50">Present Agents ({chars.length}):</span>
                    {chars.length === 0 ? (
                      <p className="text-xs text-white/40 italic">No characters currently in this sector.</p>
                    ) : (
                      <section className="flex flex-col gap-1 divide-y divide-white/5">
                        {chars.map((c) => (
                          <section key={c.name} className="py-1 flex items-center justify-between text-xs">
                            <span className="font-medium text-white/90">{c.name}</span>
                            <span className="text-white/60 italic truncate max-w-[200px]">{c.current_goal}</span>
                            <Badge label={c.mood} variant="secondary" />
                          </section>
                        ))}
                      </section>
                    )}
                  </section>
                </>
              );
            })()}
          </motion.section>
        )}
      </AnimatePresence>
    </Panel>
  );
}
