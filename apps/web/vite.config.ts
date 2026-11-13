import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// 开发时 Vite 代理 /api 到 FastAPI，浏览器视角仍是同源；发布时由 FastAPI 同源托管 dist。
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

/**
 * 构建结束后把 apps/web/sw.js 编译成 dist/sw.js：注入构建版本、完整壳资源表与首页哈希。
 * 壳表包含全部 JS/CSS 分包，未访问过的路由（如离线打开 /settings）也能拿到完整应用。
 */
function serviceWorker(): Plugin {
  const shell = ["offline.html", "manifest.webmanifest", "favicon.svg", "icon-192.png", "icon-512.png", "icon-maskable-512.png"];
  return {
    name: "cleansearch-service-worker",
    apply: "build",
    generateBundle: {
      order: "post",
      handler(_options, bundle) {
        const template = readFileSync(new URL("./sw.js", import.meta.url), "utf8");
        const index = bundle["index.html"];
        if (index?.type !== "asset") throw new Error("缺少 Service Worker 预缓存所需的 index.html");
        const outputs = Object.keys(bundle).sort();
        const hash = createHash("sha256").update(template);
        for (const name of outputs) {
          const item = bundle[name];
          hash.update(name).update(item.type === "asset" ? item.source : item.code);
        }
        for (const name of shell) hash.update(name).update(readFileSync(new URL(`./public/${name}`, import.meta.url)));
        const source = template
          .replace('"__CS_BUILD__"', JSON.stringify(hash.digest("hex").slice(0, 20)))
          .replace('"__CS_PRECACHE__"', JSON.stringify([...outputs, ...shell].map(name => `/${name}`)))
          .replace('"__CS_INDEX_HASH__"', JSON.stringify(createHash("sha256").update(index.source).digest("hex")));
        if (/__CS_(?:BUILD|PRECACHE|INDEX_HASH)__/.test(source)) throw new Error("sw.js 占位符未全部替换");
        this.emitFile({ type: "asset", fileName: "sw.js", source });
      },
    },
  };
}

export default defineConfig({
  plugins: [react(), serviceWorker()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
      "/opensearch.xml": { target: apiTarget, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
