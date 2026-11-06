import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The widget app the shell loads, built to `dist/widget/assets/widget.js` (no hash: the API's
 * shell names it). `vite.embed.config.ts` builds the loader, `dist/embed.js`, beside it. Locally,
 * `vite preview` serves `dist` and the Studio's dev server proxies `/embed.js` and
 * `/widget/assets` here, so the widget shares the API's origin as it does behind CloudFront
 * (ADR-0011).
 */
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rolldownOptions: {
      input: "src/main.tsx",
      output: {
        entryFileNames: "widget/assets/widget.js",
        chunkFileNames: "widget/assets/[name]-[hash].js",
        assetFileNames: "widget/assets/[name]-[hash][extname]",
      },
    },
  },
  preview: { port: 5174 },
});
