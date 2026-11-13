export type ThemeChoice = "auto" | "light" | "dark";

const STORAGE_KEY = "cs-theme";
const QUERY = "(prefers-color-scheme: dark)";
/** 与 --surface 对齐：地址栏/系统 UI 才不会和页面顶部撞色 */
const THEME_COLOR: Record<"light" | "dark", string> = { light: "#ffffff", dark: "#1b2320" };

export function readTheme(): ThemeChoice {
  const current = document.documentElement.dataset.themeChoice;
  return current === "light" || current === "dark" || current === "auto" ? current : "auto";
}

function readStoredTheme(): ThemeChoice {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === "light" || saved === "dark" || saved === "auto" ? saved : "auto";
  } catch {
    return readTheme();
  }
}

export function resolveTheme(choice: ThemeChoice): "light" | "dark" {
  if (choice !== "auto") return choice;
  return window.matchMedia(QUERY).matches ? "dark" : "light";
}

function syncThemeColor(resolved: "light" | "dark"): void {
  const color = THEME_COLOR[resolved];
  let meta = document.querySelector<HTMLMetaElement>("meta[name=theme-color]");
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.append(meta);
  }
  if (meta.content !== color) meta.content = color;
}

function renderTheme(choice: ThemeChoice): void {
  const previous = document.documentElement.dataset.themeChoice;
  const resolved = resolveTheme(choice);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeChoice = choice;
  const scheme = document.querySelector<HTMLMetaElement>('meta[name="color-scheme"]');
  if (scheme && scheme.content !== resolved) scheme.content = resolved;
  syncThemeColor(resolved);
  if (choice !== previous) window.dispatchEvent(new Event("cs:theme"));
}

export function applyTheme(choice: ThemeChoice): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // 存储受限时仍允许在当前页面切换主题。
  }
  renderTheme(choice);
}

export function watchTheme(): void {
  renderTheme(readStoredTheme());
  window.matchMedia(QUERY).addEventListener("change", () => {
    if (readTheme() === "auto") renderTheme("auto");
  });
  window.addEventListener("storage", event => {
    if (event.key === STORAGE_KEY || event.key === null) renderTheme(readStoredTheme());
  });
  window.addEventListener("pageshow", event => {
    if (event.persisted) renderTheme(readStoredTheme());
  });
}

export function nextTheme(choice: ThemeChoice): ThemeChoice {
  return choice === "auto" ? "light" : choice === "light" ? "dark" : "auto";
}

export const THEME_LABEL: Record<ThemeChoice, string> = {
  auto: "主题：跟随系统",
  light: "主题：浅色",
  dark: "主题：深色",
};
