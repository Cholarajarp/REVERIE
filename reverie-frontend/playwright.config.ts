import { defineConfig, devices } from "@playwright/test";

/**
 * The suite previously had no config and no npm script, so it could not run at
 * all. `webServer` boots the Next dev server (the `build` script is stubbed to
 * an echo in this repo, so `next start` is not viable).
 *
 * No backend is running during these tests, which is deliberate: it lets us
 * assert that an un-ACKed whisper degrades to UNCONFIRMED rather than being
 * silently reported as having reached consensus.
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    // Cold Next compile is slow on first hit.
    timeout: 180_000,
  },
});
