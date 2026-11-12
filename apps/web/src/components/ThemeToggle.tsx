import { useEffect, useState } from "react";
import { applyTheme, nextTheme, readTheme, THEME_LABEL } from "../theme";
import type { ThemeChoice } from "../theme";

export default function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(() => readTheme());

  useEffect(() => {
    const sync = () => setChoice(readTheme());
    window.addEventListener("cs:theme", sync);
    window.addEventListener("pageshow", sync);
    return () => {
      window.removeEventListener("cs:theme", sync);
      window.removeEventListener("pageshow", sync);
    };
  }, []);

  useEffect(() => {
    applyTheme(choice);
    if (choice !== "auto") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("auto");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [choice]);

  return (
    <button
      className="header__link theme-toggle"
      type="button"
      title={THEME_LABEL[choice]}
      aria-label={THEME_LABEL[choice]}
      onClick={() => {
        const next = nextTheme(choice);
        applyTheme(next);
        setChoice(next);
      }}
    >
      {choice === "auto" ? "自动" : choice === "light" ? "浅色" : "深色"}
    </button>
  );
}
