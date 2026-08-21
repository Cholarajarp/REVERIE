"use client";

import { defineTheme, DefinedTheme } from "@astryxdesign/core/theme";

export type ReverieThemeKey = "dark" | "light" | "matcha";

export const reverieDarkTheme = defineTheme({
  name: "reverie-dark",
  tokens: {
    "--color-background-body": "#0a0908",
    "--color-background-surface": "#1a1816",
    "--color-accent": "#e8b04b",
    "--color-accent-secondary": "#4a9ba8",
    "--color-border": "rgba(255, 255, 255, 0.12)",
    "--elevation-small": "0 2px 4px rgba(0, 0, 0, 0.4)",
    "--elevation-medium": "0 8px 16px rgba(0, 0, 0, 0.6)",
    "--elevation-large": "0 20px 40px rgba(0, 0, 0, 0.8)",
    "--radius-container": "4px",
    "--font-family-display": '"EB Garamond", Georgia, serif',
    "--font-family-body": '"Inter", system-ui, sans-serif',
  } as any,
});

export const reverieLightTheme = defineTheme({
  name: "reverie-light",
  tokens: {
    "--color-background-body": "#f8f6f0",
    "--color-background-surface": "#ffffff",
    "--color-accent": "#b87d14",
    "--color-accent-secondary": "#1b6e7d",
    "--color-border": "rgba(0, 0, 0, 0.12)",
    "--elevation-small": "0 2px 4px rgba(0, 0, 0, 0.06)",
    "--elevation-medium": "0 8px 16px rgba(0, 0, 0, 0.08)",
    "--elevation-large": "0 20px 40px rgba(0, 0, 0, 0.12)",
    "--radius-container": "4px",
    "--font-family-display": '"EB Garamond", Georgia, serif',
    "--font-family-body": '"Inter", system-ui, sans-serif',
  } as any,
});

export const reverieMatchaTheme = defineTheme({
  name: "reverie-matcha",
  tokens: {
    "--color-background-body": "#0d1712",
    "--color-background-surface": "#16261f",
    "--color-accent": "#78c28e",
    "--color-accent-secondary": "#52b8c5",
    "--color-border": "rgba(120, 194, 142, 0.2)",
    "--elevation-small": "0 2px 4px rgba(0, 0, 0, 0.5)",
    "--elevation-medium": "0 8px 16px rgba(0, 0, 0, 0.7)",
    "--elevation-large": "0 20px 40px rgba(0, 0, 0, 0.9)",
    "--radius-container": "4px",
    "--font-family-display": '"EB Garamond", Georgia, serif',
    "--font-family-body": '"Inter", system-ui, sans-serif',
  } as any,
});

export const REVERIE_THEMES: Record<ReverieThemeKey, DefinedTheme> = {
  dark: reverieDarkTheme,
  light: reverieLightTheme,
  matcha: reverieMatchaTheme,
};

export const reverieTheme = reverieDarkTheme;
