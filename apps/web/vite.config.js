import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

/**
 * Vite configuration (OWNER: D1).
 *
 * The browser talks to exactly one origin: the dev/preview server proxies `/api`
 * to FastAPI, so development needs no CORS — and the client never talks to the
 * database (spec §3, §22).
 *
 * Ports and the API target come from the environment, so **two applications built
 * from the same specification can run side by side** without editing any file:
 *
 *   BLOODLINK_API_URL        proxy target for /api   (default http://127.0.0.1:8000)
 *   BLOODLINK_WEB_PORT       dev-server port         (default 5173)
 *   BLOODLINK_PREVIEW_PORT   built-bundle port       (default 4173)
 *
 * Example — a second copy of the app next to this one:
 *
 *   BLOODLINK_WEB_PORT=5174 BLOODLINK_API_URL=http://127.0.0.1:8010 npm run dev
 */
const API_TARGET = process.env.BLOODLINK_API_URL ?? "http://127.0.0.1:8000";
const DEV_PORT = Number(process.env.BLOODLINK_WEB_PORT ?? 5173);
const PREVIEW_PORT = Number(process.env.BLOODLINK_PREVIEW_PORT ?? 4173);

const proxy = {
  "/api": {
    target: API_TARGET,
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  resolve: {
    // `@bloodlink/ui` resolves through the workspace symlink and its `exports` map
    // (see packages/ui/package.json), so subpath imports like
    // `@bloodlink/ui/styles/tokens.css` keep working.
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: DEV_PORT,
    strictPort: true,
    // Preview hosts look like https://5173-<sandbox>.e2b.app — allow them.
    allowedHosts: true,
    proxy,
  },
  preview: {
    // `npm run build && npm run preview` serves the real bundle; it needs the same
    // `/api` proxy as the dev server or the SPA would call itself.
    host: "0.0.0.0",
    port: PREVIEW_PORT,
    strictPort: true,
    allowedHosts: true,
    proxy,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
