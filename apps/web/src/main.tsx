import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import BookmarkPage from "./BookmarkPage";
import PageSummaryPage from "./PageSummaryPage";
import ToolsPage from "./ToolsPage";
import SettingsPage from "./SettingsPage";
import { applyTheme, readTheme } from "./theme";
import "./styles.css";
import "./workspace.css";

applyTheme(readTheme());

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

createRoot(container).render(<StrictMode>{page}</StrictMode>);
