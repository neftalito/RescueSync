import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  workers: 1,
  use: { baseURL: "http://127.0.0.1:5184", trace: "retain-on-failure" },
  projects: [
    { name: "escritorio", use: { viewport: { width: 1280, height: 900 } } },
    { name: "movil", use: { viewport: { width: 320, height: 780 } } },
  ],
  webServer: {
    command: "npm run dev -- --mode e2e --host 127.0.0.1 --port 5184",
    url: "http://127.0.0.1:5184",
    reuseExistingServer: true,
  },
});
