import { defineConfig, devices } from "@playwright/test";

const STUB_PORT = 8099;
const APP_PORT = 3100;

// 127.0.0.1 would make Next dev treat its own assets as cross-origin and refuse to serve them,
// which leaves a page that looks loaded but is dead
export const APP_URL = `http://localhost:${APP_PORT}`;
export const STUB_URL = `http://localhost:${STUB_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // the stub holds one world in memory, so tests take turns with it
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: APP_URL,
    // A failed run keeps a trace: `npx playwright show-trace <path>` replays it action by action,
    // with the DOM at each step, which beats re-running to see what happened
    trace: "retain-on-failure",
    // SLOW_MO=600 npm run test:e2e:headed — puts a pause between actions so they can be followed.
    // Playwright otherwise clicks and types far faster than anyone can watch
    launchOptions: { slowMo: Number(process.env.SLOW_MO ?? 0) },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  // The real Next server, with the Python backend swapped for the stub: the route handlers, the
  // httpOnly login cookie and the SSE pass-through are all the production ones
  webServer: [
    {
      command: `node e2e/stub-backend.mjs ${STUB_PORT}`,
      url: `${STUB_URL}/health`,
      reuseExistingServer: !process.env.CI,
      stdout: "ignore",
    },
    {
      command: `npx next dev --port ${APP_PORT}`,
      url: APP_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: "ignore",
      env: { BACKEND_URL: STUB_URL },
    },
  ],
});
