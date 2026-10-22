import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built interface is served by the AAGAM server itself (src/aagam/web/static),
// so her laptop needs no Node.js. `npm run dev` proxies the API to a running `aagam serve`.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/aagam/web/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 800,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
});
