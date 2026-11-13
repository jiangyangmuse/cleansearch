import { useEffect, useRef, useState } from "react";
import EngineSettingsPanel from "./components/EngineSettingsPanel";
import ModelSettingsPanel from "./components/ModelSettingsPanel";
import AppShell from "./components/AppShell";
import { loadEngineSettings, readHealth, type HealthInfo } from "./api";
import { readDailyAI, saveDailyAI } from "./searchPreferences";
import { clearSearchHistory, HISTORY_CHANGED, HISTORY_KEY, readSearchHistory } from "./searchHistory";
import { applyTheme, readTheme, type ThemeChoice } from "./theme";
import { canInstall, INSTALLABLE, isStandalone, promptInstall } from "./pwa";

const themes: { value: ThemeChoice; label: string }[] = [
  { value: "auto", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

export default function SettingsPage() {
  const [theme, setTheme] = useState(readTheme);
  const [dailyAI, setDailyAI] = useState(readDailyAI);
  const [historyCount, setHistoryCount] = useState(() => readSearchHistory().length);
  const [info, setInfo] = useState<HealthInfo | null>(null);
  const [infoError, setInfoError] = useState("");
  const [notice, setNotice] = useState("");
  const [installable, setInstallable] = useState(canInstall);
  const [standalone, setStandalone] = useState(isStandalone);
  const [installing, setInstalling] = useState(false);
  const [installNotice, setInstallNotice] = useState("");
  const [includeHistory, setIncludeHistory] = useState(false);
  const [exporting, setExporting] = useState(false);
  const exportRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const sync = () => {
      setTheme(readTheme());
      setDailyAI(readDailyAI());
      setHistoryCount(readSearchHistory().length);
    };
    let controller: AbortController | undefined;
    const refreshInfo = () => {
      controller?.abort();
      const request = new AbortController();
      controller = request;
      void readHealth(request.signal).then(value => {
        if (!request.signal.aborted) {
          setInfo(value);
          setInfoError("");
        }
      }).catch(() => {
        if (!request.signal.aborted) {
          setInfo(null);
          setInfoError("读取本机数据信息失败");
        }
      });
    };
    const onPageShow = (event: PageTransitionEvent) => {
      sync();
      if (event.persisted) refreshInfo();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === HISTORY_KEY || event.key === null) sync();
    };
    const syncInstall = () => {
      setInstallable(canInstall());
      setStandalone(isStandalone());
    };
    refreshInfo();
    window.addEventListener("cs:theme", sync);
    window.addEventListener(INSTALLABLE, syncInstall);
    syncInstall();
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("storage", onStorage);
    window.addEventListener(HISTORY_CHANGED, sync);
    return () => {
      controller?.abort();
      exportRequest.current?.abort();
      window.removeEventListener("cs:theme", sync);
      window.removeEventListener(INSTALLABLE, syncInstall);
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(HISTORY_CHANGED, sync);
    };
  }, []);

  const exportSettings = async () => {
    if (exportRequest.current) return;
    const request = new AbortController();
    exportRequest.current = request;
    setExporting(true);
    setNotice("正在准备导出…");
    try {
      const { preferences } = await loadEngineSettings(request.signal);
      if (request.signal.aborted) return;
      const payload = {
        exported_at: new Date().toISOString(),
        theme: readTheme(),
        daily_ai: readDailyAI(),
        engine_preferences: {
          default_engines: preferences.default_engines,
          custom: preferences.custom.map(({ code, label, kind, target }) => ({
            code, label, kind, ...(kind !== "website" && { target }),
          })),
        },
        local: { bookmarks: info?.bookmarks ?? null, version: info?.version ?? null },
        ...(includeHistory && { search_history: readSearchHistory() }),
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "cleansearch-settings.json";
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("已导出 cleansearch-settings.json");
    } catch {
      if (!request.signal.aborted) setNotice("导出失败，无法读取已保存的引擎设置，请重试");
    } finally {
      exportRequest.current = null;
      if (!request.signal.aborted) setExporting(false);
    }
  };

  const clearHistory = () => {
    if (clearSearchHistory()) {
      setHistoryCount(0);
      setNotice("已清空本浏览器的搜索历史");
    } else {
      setNotice("清空失败，浏览器未允许写入本地存储");
    }
  };

  return (
    <AppShell current="settings" title="设置 · CleanSearch" maxWidth={880}>
      <main id="main" tabIndex={-1} className="settings-page">
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
        <EngineSettingsPanel />
        <section className="settings-card" aria-labelledby="install-settings">
          <h2 id="install-settings">安装与离线</h2>
          <div className="settings-row">
            <p className="settings-data__path">
              <strong>{standalone ? "已在独立窗口运行" : "把 CleanSearch 装到桌面 / 主屏幕"}</strong>
            </p>
            <p className="model-settings__hint">
              支持系统分享的浏览器可把链接送进书签页。应用外壳可离线打开，搜索、总结和保存书签需要本机服务。
            </p>
            <div className="settings-actions">
              <button type="button" className="button" aria-disabled={!installable || standalone || installing}
                onClick={async () => {
                  if (!installable || standalone || installing) return;
                  setInstalling(true);
                  const outcome = await promptInstall();
                  setInstallNotice(outcome === "accepted" ? "已确认安装"
                    : outcome === "dismissed" ? "安装已取消"
                    : outcome === "failed" ? "安装未完成，可从浏览器菜单重试" : "浏览器未提供安装入口");
                  setInstalling(false);
                  setInstallable(canInstall());
                }}>
                {installing ? "等待浏览器确认…" : standalone ? "已安装" : installable ? "安装到桌面" : "浏览器未提供安装入口"}
              </button>
            </div>
            {!installable && !standalone ? (
              <p className="model-settings__hint">
                也可用地址栏右侧的安装图标，或浏览器菜单里的「安装 CleanSearch」。
              </p>
            ) : null}
            <p className={installNotice ? undefined : "sr-only"} role="status">{installNotice}</p>
          </div>
        </section>
        <section className="settings-card" aria-labelledby="data-settings">
          <h2 id="data-settings">数据管理</h2>
          <div className="settings-row">
            <p className="settings-data__path">
              <strong>本机数据库</strong> <code>{info?.db_path || (info ? "路径不可用" : infoError || "读取中…")}</code>
            </p>
            <p className="model-settings__hint">
              书签 {info?.bookmarks ?? "—"} 条 · 版本 {info?.version ?? "—"} · 搜索历史 {historyCount} 条（只存在当前浏览器）
            </p>
            <label><input type="checkbox" checked={includeHistory} disabled={exporting}
              onChange={event => setIncludeHistory(event.target.checked)} /> 在导出文件中包含搜索历史</label>
            <p className="model-settings__hint">导出为设置清单，省略密钥、数据库路径和自定义直达网址模板。</p>
            <div className="settings-actions">
              <button type="button" className="button button--ghost" disabled={exporting}
                onClick={() => void exportSettings()}>{exporting ? "导出中…" : "导出设置"}</button>
              <button type="button" className="button button--ghost" disabled={historyCount === 0}
                onClick={clearHistory}>清空搜索历史</button>
              <a className="button button--ghost" href="/bookmarks">管理书签</a>
            </div>
            <p className={notice ? undefined : "sr-only"} role="status">{notice}</p>
          </div>
        </section>
      </main>
    </AppShell>
  );
}
