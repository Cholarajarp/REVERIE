"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { Theme } from "@astryxdesign/core/theme";
import { REVERIE_THEMES, ReverieThemeKey } from "../../lib/reverieTheme";

interface ThemeContextType {
  themeKey: ReverieThemeKey;
  setThemeKey: (key: ReverieThemeKey) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  themeKey: "dark",
  setThemeKey: () => {},
});

export const useReverieTheme = () => useContext(ThemeContext);

export function ReverieThemeProvider({ children }: { children: React.ReactNode }) {
  const [themeKey, setThemeState] = useState<ReverieThemeKey>("dark");

  useEffect(() => {
    const saved = localStorage.getItem("reverie_theme_pref") as ReverieThemeKey;
    if (saved && REVERIE_THEMES[saved]) {
      setThemeState(saved);
    }
  }, []);

  const setThemeKey = (key: ReverieThemeKey) => {
    setThemeState(key);
    if (typeof window !== "undefined") {
      localStorage.setItem("reverie_theme_pref", key);
    }
  };

  const activeTheme = REVERIE_THEMES[themeKey] || REVERIE_THEMES.dark;

  return (
    <ThemeContext.Provider value={{ themeKey, setThemeKey }}>
      <Theme theme={activeTheme}>
        <div
          data-theme={themeKey}
          className="min-h-screen w-full transition-colors duration-500 relative"
          style={{ backgroundColor: "var(--color-background-body)" }}
        >
          {children}
        </div>
      </Theme>
    </ThemeContext.Provider>
  );
}
