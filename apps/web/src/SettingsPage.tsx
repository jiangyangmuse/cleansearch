import { useEffect, useState } from "react";
import ModelSettingsPanel from "./components/ModelSettingsPanel";
import WorkspaceHeader from "./components/WorkspaceHeader";
import { readDailyAI, saveDailyAI } from "./searchPreferences";
import { applyTheme, readTheme, type ThemeChoice } from "./theme";

const themes: { value: ThemeChoice; label: string }[] = [
  { value: "auto", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

export default function SettingsPage() {
  const [theme, setTheme] = useState(readTheme);
  const [dailyAI, setDailyAI] = useState(readDailyAI);

  useEffect(() => {
    document.title = "设置 · CleanSearch";
    const sync = () => {
      setTheme(readTheme());
      setDailyAI(readDailyAI());
    };
    window.addEventListener("cs:theme", sync);
    window.addEventListener("pageshow", sync);
    return () => {
      window.removeEventListener("cs:theme", sync);
      window.removeEventListener("pageshow", sync);
    };
  }, []);

  return (
    <div className="workspace-app">
      <WorkspaceHeader settings />
      <main className="settings-page">
        <a className="settings-page__back" href="/">← 返回搜索</a>
        <h1>设置</h1>
        <section className="settings-card" aria-labelledby="appearance">
          <h2 id="appearance">外观</h2>
          <fieldset className="settings-row">
            <legend>主题</legend>
            <div className="settings-themes">
              {themes.map(({ value, label }) => (
                <label key={value}>
                  <input type="radio" name="theme" value={value} checked={theme === value} onChange={() => {
                    setTheme(value);
                    applyTheme(value);
                  }} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </section>
        <section className="settings-card" aria-labelledby="search-settings">
          <h2 id="search-settings">搜索</h2>
          <label className="settings-row settings-row--switch">
            <span><strong>日常 AI 检索</strong>
              <small>开启后随每次搜索请求 AI 服务，可能产生 API 费用。关闭时可用 <kbd>ds</kbd> 后缀单次启用。</small>
            </span>
            <input className="workspace-switch" type="checkbox" role="switch" checked={dailyAI}
              aria-label="日常 AI 检索" onChange={(event) => {
                const enabled = event.target.checked;
                setDailyAI(enabled);
                saveDailyAI(enabled);
              }} />
          </label>
          <ModelSettingsPanel />
        </section>
      </main>
    </div>
  );
}
