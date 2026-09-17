import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:3100",
    headless: true,
    channel: process.platform === "win32" ? "msedge" : undefined,
  },
  webServer: {
    command: "node src/server.js",
    url: "http://127.0.0.1:3100/health",
    env: { PORT: "3100", HOST: "127.0.0.1", ALLOW_SERVER_KEY: "false" },
    reuseExistingServer: false,
  },
  reporter: "list",
});
