import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import UpdateToast from "./components/UpdateToast";
import { watchServerState } from "./capabilities";
import { initPerf } from "./perf";
import { initInstallPrompt } from "./pwa";
import { registerServiceWorker } from "./swRegister";
import { watchTheme } from "./theme";
import "./styles.css";
import "./workspace.css";

// 路由级拆包：首屏只加载搜索页，其余页面按需拉取
const App = lazy(() => import("./App"));
const BookmarkPage = lazy(() => import("./BookmarkPage"));
const PageSummaryPage = lazy(() => import("./PageSummaryPage"));
const ToolsPage = lazy(() => import("./ToolsPage"));
const SettingsPage = lazy(() => import("./SettingsPage"));

// 系统主题变化、其它标签页改主题、bfcache 恢复都由这里统一收口
watchTheme();
initInstallPrompt();
initPerf();
watchServerState();
registerServiceWorker();

const container = document.getElementById("root");
if (!container) throw new Error("缺少 #root 挂载点");

const path = window.location.pathname.replace(/\/+$/, "") || "/";
const page =
  path === "/bookmarks" ? (
    <BookmarkPage />
  ) : path === "/settings" ? (
    <SettingsPage />
  ) : path === "/s" ? (
    <PageSummaryPage />
  ) : path === "/tools" ? (
    <ToolsPage />
  ) : (
    <App />
  );

createRoot(container).render(
  <StrictMode>
    <Suspense fallback={<p className="app-boot" role="status">正在加载…</p>}>
      {page}
      <UpdateToast />
    </Suspense>
  </StrictMode>,
);
