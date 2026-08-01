/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    // Monaco is large and almost never changes; the Code app around it changes
    // often. Splitting them means shipping a fix to the editor UI does not make
    // every user re-download the whole editor — the Monaco chunk stays cached.
    // It is loaded lazily either way, so none of this touches first paint.
    chunkSizeWarningLimit: 3600,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("node_modules/monaco-editor")) return "monaco";
          if (id.includes("node_modules/yjs") || id.includes("node_modules/y-monaco")
              || id.includes("node_modules/y-protocols")) return "crdt";
          return undefined;
        },
      },
    },
  },
  // Component tests run against a real DOM. Server tests can't see a button
  // that never became clickable, which is exactly how a broken verification
  // screen passed an API-level check once.
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1 (not "localhost") — Windows/Node may resolve localhost to
      // IPv6 ::1 while uvicorn listens on IPv4, breaking the proxy.
      // ws: true lets /api/ws (realtime presence + live feed) tunnel through.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true, ws: true },
    },
  },
});
