import type { Metadata } from "next";
// Astryx reset/core CSS is imported inside globals.css so it lands in the
// correct @layer relative to Tailwind's utilities. Importing it here too
// would load it outside that layer order.
import "./globals.css";
import { ReverieThemeProvider } from "../components/ui/ThemeProvider";

export const metadata: Metadata = {
  title: "REVERIE | The First Living Film",
  description: "Autonomous Agentic Simulation System & Living Film powered by Gemini 3.5 Flash & Gemini Omni",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col m-0 p-0 font-[family-name:var(--font-family-body)]">
        <ReverieThemeProvider>
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              width: "100vw",
              height: "100vh",
              backgroundImage: "url(/noise.svg)",
              opacity: 0.08,
              mixBlendMode: "overlay",
              pointerEvents: "none",
              zIndex: 9999,
            }}
          />
          {children}
        </ReverieThemeProvider>
      </body>
    </html>
  );
}
