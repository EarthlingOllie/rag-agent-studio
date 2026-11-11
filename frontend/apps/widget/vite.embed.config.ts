import { defineConfig } from "vite";

/** The Embed Snippet's loader: one small classic script, `dist/embed.js`, with no globals. */
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: false,
    lib: { entry: "src/loader.ts", formats: ["iife"], name: "ragAgentStudioEmbed", fileName: () => "embed.js" },
  },
});
