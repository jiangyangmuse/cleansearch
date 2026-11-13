import { useEffect, useState } from "react";
import { getEngines, loadEngineSettings, saveEngineSettings } from "../api";
import type { EngineInfo } from "../types";
import { ENGINE_SECTIONS } from "../engineQuery";
import type { CustomSearchEntry, EnginePreferences, EngineSettings, SearchEntryKind } from "../types";

const EMPTY: CustomSearchEntry = { code: "", label: "", kind: "engine", target: "" };
const TARGETS = {
  engine: { title: "SearXNG 引擎名称", placeholder: "例如 bilibili" },
  region: { title: "语言或地区代码", placeholder: "例如 fr-FR" },
  website: { title: "搜索网址模板", placeholder: "https://example.com/search?q={q}" },
};
const KIND: Record<SearchEntryKind, string> = { engine: "聚合引擎", region: "语言或地区", website: "网页直达" };

export default function EngineSettingsPanel() {
  const [data, setData] = useState<EngineSettings | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [filter, setFilter] = useState("");
  const [probing, setProbing] = useState(false);
  // 「刷新状态」拉一次目录，把可用/冷却/未知贴到每个引擎上
  const [probe, setProbe] = useState<Record<string, EngineInfo>>({});

  const refreshStatus = async () => {
    setProbing(true);
    setError("");
    setNotice("");
    try {
      const payload = await getEngines();
      const engines = payload.engines.filter(engine => engine.kind === "engine");
      setProbe(Object.fromEntries(engines.map(engine => [engine.code, engine])));
      const counts = engines.reduce((acc, engine) => {
        acc[engine.status] = (acc[engine.status] ?? 0) + 1;
        return acc;
      }, {} as Record<string, number>);
      setNotice(`引擎状态已刷新：可用 ${counts.ok ?? 0} · 冷却 ${counts.cooldown ?? 0} · 未知 ${counts.unknown ?? 0}`);
    } catch {
      setProbe({});
      setError("引擎状态刷新失败，稍后再试");
    } finally {
      setProbing(false);
    }
  };

  useEffect(() => {
    const request = new AbortController();
    void loadEngineSettings(request.signal).then(settings => {
      if (!request.signal.aborted) {
        setData(settings);
        setError("");
      }
    }).catch(error => {
      if (!request.signal.aborted) setError(error instanceof Error ? error.message : "引擎设置读取失败");
    });
    return () => request.abort();
  }, [reload]);

  const update = (preferences: EnginePreferences) => {
    setData(current => current && ({ ...current, preferences }));
    setDirty(true);
    setNotice("");
    setError("");
  };

  const save = async () => {
    if (!data) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const preferences = await saveEngineSettings(data.preferences);
      setData({ ...data, preferences });
      setDirty(false);
      setNotice("搜索引擎设置已保存");
    } catch (error) {
      setError(error instanceof Error ? error.message : "引擎设置保存失败");
    } finally {
      setBusy(false);
    }
  };

  const startEditing = (entry?: CustomSearchEntry) => {
    setEditing(entry?.code ?? null);
    setDraft(entry ?? EMPTY);
    setFormOpen(true);
    setError("");
  };

  const applyEntry = () => {
    if (!data) return;
    const entry = { ...draft, label: draft.label.trim(), code: draft.code.trim().toLowerCase(), target: draft.target.trim() };
    const { preferences, builtins } = data;
    const reserved = new Set(["zh", "cn", "jp", "us", "en", "ds", ...builtins.flatMap(row => [row.code, ...row.aliases])]);
    if (reserved.has(entry.code) || preferences.custom.some(row => row.code === entry.code && row.code !== editing)) {
      setError("这个后缀已经被使用");
      return;
    }
    const custom = editing ? preferences.custom.map(row => row.code === editing ? entry : row) : [...preferences.custom, entry];
    const default_engines = preferences.default_engines?.flatMap(code =>
      code !== editing ? [code] : entry.kind === "engine" ? [entry.code] : [],
    ) ?? null;
    update({ ...preferences, custom, default_engines });
    setFormOpen(false);
  };

  if (!data) {
    return <section className="settings-card" id="engine-settings" aria-labelledby="engine-settings-title">
      <h2 id="engine-settings-title">搜索引擎</h2>
      <div className="settings-row">
        <p role="status">{error || "正在读取引擎设置…"}</p>
        {error && <button type="button" className="chip" onClick={() => setReload(value => value + 1)}>重新读取</button>}
      </div>
    </section>;
  }

  const { preferences, builtins, sources } = data;
  const custom = preferences.custom.map(entry => ({
    ...entry, searx_engine: entry.target, section: "custom" as const, aliases: [],
  }));
  const defaults = builtins.filter(row => sources?.[row.searx_engine] === true).map(row => row.code);
  const defaultCount = sources === null ? null : Object.values(sources).filter(Boolean).length;
  const inheriting = preferences.default_engines === null;
  const active = preferences.default_engines ?? defaults;
  const inheritReason = "当前继承 SearXNG 默认引擎，逐项开关不可单独勾选；先打开上面的「使用自选默认引擎」";
  const rows = [...builtins.map(row => ({ ...row, kind: "engine" as const })), ...custom];
  const activeTargets = new Set(rows.filter(row => row.kind === "engine" && active.includes(row.code))
    .map(row => row.searx_engine));
  const needle = filter.trim().toLowerCase().replace(/^!/, "");
  const visibleRows = needle
    ? rows.filter(row => [row.label, row.code, row.searx_engine ?? "", ...row.aliases]
      .some(value => String(value).toLowerCase().includes(needle)))
    : rows;

  return (
    <section className="settings-card engine-settings" id="engine-settings" aria-labelledby="engine-settings-title">
      <h2 id="engine-settings-title">搜索引擎</h2>
      <div className="engine-settings__body">
        <label className="engine-settings__mode">
          <span><strong>使用自选默认引擎</strong>
            <small>普通搜索使用勾选的引擎。关闭后沿用 SearXNG 的默认设置。</small>
          </span>
          <input className="workspace-switch" type="checkbox" role="switch" checked={preferences.default_engines !== null}
            aria-label="使用自选默认引擎" disabled={busy} onChange={event =>
              update({ ...preferences, default_engines: event.target.checked ? defaults : null })} />
        </label>
        {sources === null && <p className="model-settings__hint">暂时无法读取 SearXNG 的引擎状态。</p>}
        {inheriting && (
          <p className="engine-settings__inherit" role="status">
            继承 SearXNG 默认{defaultCount !== null && `（${defaultCount} 个）`}。开启自选模式后可单独勾选引擎。
          </p>
        )}
        {preferences.default_engines?.length === 0 && <p className="model-settings__hint">普通搜索已暂停，仍可使用指定引擎的后缀。</p>}
        <div className="engine-settings__toolbar">
          <input className="engine-settings__filter" value={filter} aria-label="筛选引擎"
            placeholder="筛选引擎名称、后缀或上游名"
            onChange={event => setFilter(event.target.value)} />
          <button type="button" className="chip" disabled={probing} onClick={() => void refreshStatus()}>
            {probing ? "刷新中…" : "刷新状态"}
          </button>
          {filter ? <span className="model-settings__hint">{visibleRows.length} / {rows.length} 个入口</span> : null}
        </div>
        <p className="model-settings__hint">显示服务记录的引擎状态。可用表示最近一次请求成功，冷却表示暂停请求，未知表示暂无成功记录。</p>
        {visibleRows.length === 0 ? <p className="model-settings__hint" role="status">没有匹配「{filter.trim()}」的入口。</p> : null}
        {ENGINE_SECTIONS.map(({ section, title }) => {
          const items = visibleRows.filter(row => (row.section ?? null) === section);
          if (!items.length) return null;
          return (
            <div className="engine-settings__group" key={section ?? "unclassified"} aria-label={title ?? undefined}>
              {title && <h3>{title}</h3>}
              <ul>
                {items.map(row => {
                  // 继承上游默认时不把任一开关画成已选，避免「看起来生效」的误读。
                  const checked = !inheriting && activeTargets.has(row.searx_engine);
                  const lockedByInherit = inheriting && row.kind === "engine";
                  const unavailable = sources !== null && !Object.hasOwn(sources, row.searx_engine);
                  const customEntry = preferences.custom.find(entry => entry.code === row.code);
                  const detail = row.kind !== "engine" ? KIND[row.kind]
                    : unavailable ? "上游未加载" : customEntry ? row.searx_engine : null;
                  return (
                    <li key={row.code}>
                      <div className="engine-settings__identity">
                        <strong>{row.label}</strong> <kbd>{row.code}</kbd>
                        {detail && <small>{detail}</small>}
                        {row.kind === "engine" && probe[row.code]?.searx_engine === row.searx_engine ? (
                          <small className={`engine-settings__status engine-settings__status--${probe[row.code].status}`}>
                            {probe[row.code].status === "ok" ? "可用"
                              : probe[row.code].status === "cooldown"
                              ? `冷却 ${Math.max(1, Math.ceil(probe[row.code].remaining_seconds / 60))} 分`
                                : "未知"}
                          </small>
                        ) : null}
                      </div>
                      <div className="engine-settings__actions">
                        {row.kind === "engine" && (
                          <input className="workspace-switch" type="checkbox" role="switch"
                            aria-label={`默认搜索使用 ${row.label}`} checked={checked}
                            aria-describedby={lockedByInherit ? `engine-reason-${row.code}` : undefined}
                            disabled={busy || inheriting || (unavailable && !checked)}
                            onChange={event => update({
                              ...preferences, default_engines: event.target.checked
                                ? [...active, row.code] : active.filter(code =>
                                  rows.find(entry => entry.code === code)?.searx_engine !== row.searx_engine),
                            })} />
                        )}
                        {lockedByInherit && (
                          <span className="sr-only" id={`engine-reason-${row.code}`}>{inheritReason}</span>
                        )}
                        {customEntry && (
                          <>
                            <button type="button" className="chip" disabled={busy} onClick={() => startEditing(customEntry)}>编辑</button>
                            <button type="button" className="chip" disabled={busy} onClick={() => {
                              if (editing === row.code) setFormOpen(false);
                              update({
                                ...preferences, custom: preferences.custom.filter(entry => entry.code !== row.code),
                                default_engines: preferences.default_engines?.filter(code => code !== row.code) ?? null,
                              });
                            }}>移除</button>
                          </>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
        <div className="engine-settings__footer">
          <button type="button" className="button button--ghost" disabled={busy || preferences.custom.length >= 30}
            onClick={() => startEditing()}>添加搜索入口</button>
          <button type="button" className="button button--ghost" disabled={busy || (inheriting && !dirty)}
            onClick={() => update({ ...preferences, default_engines: null })}>恢复默认</button>
          <button type="button" className="button" disabled={busy || !dirty || formOpen}
            onClick={() => void save()}>{busy ? "保存中…" : "保存引擎设置"}</button>
        </div>
        {formOpen && (
          <form className="engine-settings__form" onSubmit={event => { event.preventDefault(); applyEntry(); }}>
            <label>入口名称<input value={draft.label} required maxLength={48}
              onChange={event => setDraft({ ...draft, label: event.target.value })} /></label>
            <label>搜索后缀<input value={draft.code} required maxLength={8} pattern="[a-z][a-z0-9]{0,7}"
              placeholder="例如 wiki2" onChange={event => setDraft({ ...draft, code: event.target.value.toLowerCase() })} /></label>
            <label>入口类型<select value={draft.kind} onChange={event => {
              setDraft({ ...draft, kind: event.target.value as SearchEntryKind, target: "" });
            }}>
              {Object.entries(KIND).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
            <label>{TARGETS[draft.kind].title}
              <input value={draft.target} required maxLength={draft.kind === "website" ? 1000 : 100}
                list={draft.kind === "engine" ? "loaded-search-engines" : undefined}
                placeholder={TARGETS[draft.kind].placeholder} onChange={event => setDraft({ ...draft, target: event.target.value })} />
            </label>
            <datalist id="loaded-search-engines">
              {Object.keys(sources ?? {}).map(name => <option value={name} key={name} />)}
            </datalist>
            <div className="engine-settings__footer">
              <button type="submit" className="button">{editing ? "应用修改" : "添加到列表"}</button>
              <button type="button" className="button button--ghost" onClick={() => { setFormOpen(false); setError(""); }}>取消</button>
            </div>
          </form>
        )}
        {dirty && <p className="model-settings__hint">保存后生效</p>}
        {notice && <p role="status">{notice}</p>}
        {error && <p role="alert" className="workspace-form-error">{error}</p>}
      </div>
    </section>
  );
}
