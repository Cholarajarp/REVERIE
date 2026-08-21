"use client";

import { Theme } from "@astryxdesign/core/theme";
import { reverieTheme } from "../../lib/reverieTheme";

export default function ClientTheme({ children }: { children: React.ReactNode }) {
  return <Theme theme={reverieTheme}>{children}</Theme>;
}
export { reverieTheme };
