import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发时 Vite 代理 /api 到 FastAPI，浏览器视角仍是同源；发布时由 FastAPI 同源托管 dist。
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
