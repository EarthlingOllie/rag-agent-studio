import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // xfwd passes the browser's IP on (X-Forwarded-For); the API counts failed sign-ins per IP.
      "/api": { target: process.env.API_PROXY_TARGET ?? "http://localhost:8000", xfwd: true },
      // Uploads PUT to presigned URLs on the Studio's own origin; this forwards them to the
      // object store (RustFS) unchanged, Host header included, so the signature still matches.
      "/studio-documents": { target: process.env.OBJECT_STORE_PROXY_TARGET ?? "http://localhost:9000" },
    },
  },
});
