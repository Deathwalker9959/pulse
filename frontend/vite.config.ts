import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";
const wsProxyTarget = process.env.VITE_WS_PROXY_TARGET ?? "ws://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    hmr: {
      host: process.env.VITE_HMR_HOST ?? "localhost",
      clientPort: parseInt(process.env.VITE_HMR_CLIENT_PORT ?? "5173"),
    },
    watch: {
      usePolling: process.env.VITE_USE_POLLING === "true",
      interval: 300,
    },
    proxy: {
      "/api": apiProxyTarget,
      "/ws": {
        target: wsProxyTarget,
        ws: true
      }
    }
  }
});
