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
    },
  },
});
