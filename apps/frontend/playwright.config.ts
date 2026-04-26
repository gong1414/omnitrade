import { defineConfig, devices } from "@playwright/test";

// Some dev environments run a global HTTP proxy that returns 502 for every
// localhost port — this confuses Playwright's webServer "already used" probe.
// Forcing NO_PROXY here makes the probe talk directly to the loopback.
process.env.NO_PROXY = "localhost,127.0.0.1,::1";
process.env.no_proxy = process.env.NO_PROXY;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3030",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npx next dev --port 3030",
    url: "http://localhost:3030/dashboard",
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      NEXT_PUBLIC_API_BASE_URL: "http://localhost:8765",
      NEXT_PUBLIC_SSE_URL: "http://localhost:8765",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
