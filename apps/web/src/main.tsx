import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import BookmarkPage from "./BookmarkPage";
import PageSummaryPage from "./PageSummaryPage";
import ToolsPage from "./ToolsPage";
import { applyTheme, readTheme } from "./theme";
import "./styles.css";

applyTheme(readTheme());

const container = document.getElementById("root");
if (!container) throw new Error("缺少 #root 挂载点");

const path = window.location.pathname.replace(/\/+$/, "") || "/";
const page =
  path === "/bookmarks" ? (
    <BookmarkPage />
  ) : path === "/s" ? (
    <PageSummaryPage />
  ) : path === "/tools" ? (
    <ToolsPage />
  ) : (
    <App />
  );

createRoot(container).render(<StrictMode>{page}</StrictMode>);