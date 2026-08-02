/// <reference types="vitest" />
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

/* Stamped into the bundle so a running copy can say which build it is. The
   update prompt shows it, which is the difference between "it says there is an
   update" and being able to point at the version you are now on. UTC keeps it
   comparable with the Render deploy log. */
const BUILD_ID = new Date().toISOString().slice(0, 16).replace("T", " ") + "Z";

/* public/sw.js is copied to dist verbatim, so on its own it is byte-identical
   between deploys — and a browser only notices a new service worker when the
   bytes change. A deploy could therefore replace every hashed chunk while the
   worker sat there unaware, which is precisely the case the update prompt
   exists to catch. Stamping the build id in after the copy makes the file
   differ every time. */
function stampServiceWorker(buildId: string): Plugin {
  let outDir = "dist";
  return {
    name: "stamp-service-worker",
    apply: "build",
    configResolved(cfg) { outDir = cfg.build.outDir; },
    closeBundle() {
      const sw = resolve(outDir, "sw.js");
      if (!existsSync(sw)) throw new Error(`stamp-service-worker: ${sw} not found`);
      const src = readFileSync(sw, "utf8");
      if (!src.includes("__SW_BUILD__")) {
        throw new Error("stamp-service-worker: placeholder __SW_BUILD__ missing from sw.js");
      }
      writeFileSync(sw, src.replaceAll("__SW_BUILD__", buildId));
    },
  };
}

export default defineConfig({
  plugins: [react(), stampServiceWorker(BUILD_ID)],
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
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
