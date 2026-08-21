"use client";

import React from "react";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core";
import { useReverieTheme } from "./ThemeProvider";
import { ReverieThemeKey } from "../../lib/reverieTheme";

export function ThemeToggle() {
  const { themeKey, setThemeKey } = useReverieTheme();

  return (
    <div className="flex items-center">
      <SegmentedControl
        value={themeKey}
        onChange={(val) => setThemeKey(val as ReverieThemeKey)}
        label="Theme Selection"
        size="sm"
      >
        <SegmentedControlItem value="dark" label="🌙 Dark" />
        <SegmentedControlItem value="light" label="☀️ Light" />
        <SegmentedControlItem value="matcha" label="🍵 Matcha" />
      </SegmentedControl>
    </div>
  );
}
