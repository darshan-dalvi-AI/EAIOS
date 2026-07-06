import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
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
