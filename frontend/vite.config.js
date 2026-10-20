import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ mode }) => ({
  cacheDir: mode === "e2e" ? ".cache/vite-e2e" : undefined,
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
  },
}));
