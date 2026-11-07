export type ThemeChoice = "auto" | "light" | "dark";

const STORAGE_KEY = "cs-theme";
const QUERY = "(prefers-color-scheme: dark)";

export function readTheme(): ThemeChoice {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === "light" || saved === "dark" || saved === "auto" ? saved : "auto";
  } catch {
    return "auto";
  }
}

export function resolveTheme(choice: ThemeChoice): "light" | "dark" {
  if (choice !== "auto") return choice;
  return window.matchMedia(QUERY).matches ? "dark" : "light";
}

export function applyTheme(choice: ThemeChoice): void {
  document.documentElement.dataset.theme = resolveTheme(choice);
  document.documentElement.dataset.themeChoice = choice;
  try {
    window.localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // 存储受限时仍允许在当前页面切换主题。
  }
}

export function nextTheme(choice: ThemeChoice): ThemeChoice {
  return choice === "auto" ? "light" : choice === "light" ? "dark" : "auto";
}

export const THEME_LABEL: Record<ThemeChoice, string> = {
  auto: "主题：跟随系统",
  light: "主题：浅色",
  dark: "主题：深色",
};
