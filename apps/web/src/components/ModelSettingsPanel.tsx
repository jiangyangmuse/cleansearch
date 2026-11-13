import { useEffect, useRef, useState } from "react";
import { ApiError, loadModelSettings, saveModelSettings, testModelConnection,
  type ModelEntry, type ModelFeature, type ModelSettings } from "../api";

const FEATURES: { id: ModelFeature; label: string }[] = [
  { id: "search", label: "AI 检索" },
  { id: "summary", label: "AI 总结" },
  { id: "translate", label: "翻译" },
];

function newModel(): ModelEntry {
  return { id: crypto.randomUUID(), label: "", base_url: "", model: "", features: [] };
}

function parseImport(text: string): ModelEntry[] {
  const data: unknown = JSON.parse(text);
  if (!Array.isArray(data) || !data.length) throw new Error("请填写包含至少一个模型的 JSON 数组");
  return data.map(item => {
    if (!item || typeof item !== "object" ||
        ![item.label, item.base_url, item.model].every(value => typeof value === "string" && value.trim()) ||
        (item.api_key !== undefined && typeof item.api_key !== "string") ||
        (item.features !== undefined && (!Array.isArray(item.features) ||
          item.features.some((value: string) => !FEATURES.some(feature => feature.id === value))))) {
      throw new Error("每个模型需要 label、base_url 和 model，features 可填 search、summary、translate");
    }
    return { ...newModel(), label: item.label, base_url: item.base_url, model: item.model,
      api_key: item.api_key, features: item.features ?? [] };
  });
}

export default function ModelSettingsPanel() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [saved, setSaved] = useState<ModelSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [importText, setImportText] = useState("");
  const [reload, setReload] = useState(0);
  // 每个模型的连通性测试结果：只请求 /models，不耗 token
  const [tests, setTests] = useState<Record<string, { state: "testing" | "ok" | "fail"; text: string }>>({});
  const testRequests = useRef(new Map<string, AbortController>());

  const invalidateTest = (id: string) => {
    testRequests.current.get(id)?.abort();
    testRequests.current.delete(id);
    setTests(current => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  };

  const testConnection = async (model: ModelEntry) => {
    if (!saved || testRequests.current.has(model.id)) return;
    const request = new AbortController();
    testRequests.current.set(model.id, request);
    setTests(current => ({ ...current, [model.id]: { state: "testing", text: "测试中…" } }));
    try {
      const result = await testModelConnection(model.id, saved.revision, request.signal);
      if (request.signal.aborted) return;
      const available = result.models === undefined ? "可用" : `可用（${result.models} 个模型）`;
      setTests(current => ({
        ...current,
        [model.id]: result.ok
          ? { state: "ok", text: result.model_listed === false ? `${available}，列表未列出所填模型` : available }
          : { state: "fail", text: result.message ?? "连接失败" },
      }));
    } catch (caught) {
      if (request.signal.aborted) return;
      setTests(current => ({
        ...current,
        [model.id]: { state: "fail", text: caught instanceof ApiError ? caught.message : "测试失败" },
      }));
    } finally {
      if (testRequests.current.get(model.id) === request) testRequests.current.delete(model.id);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    const requests = testRequests.current;
    void loadModelSettings(controller.signal).then(value => {
      if (!controller.signal.aborted) {
        setSaved(value);
        setSettings(value);
      }
    }).catch(error => {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "模型配置加载失败");
    });
    return () => {
      controller.abort();
      requests.forEach(request => request.abort());
      requests.clear();
    };
  }, [reload]);

  const update = (id: string, patch: Partial<ModelEntry>) => {
    if ("base_url" in patch || "model" in patch || "api_key" in patch) invalidateTest(id);
    setNotice("");
    setSettings(current => current && ({
      ...current, models: current.models.map(model => model.id === id ? { ...model, ...patch } : model),
    }));
  };

  const remove = (id: string) => {
    if (!settings) return;
    invalidateTest(id);
    const assignments = { ...settings.assignments };
    for (const { id: feature } of FEATURES) {
      const route = assignments[feature];
      if (route) assignments[feature] = {
        primary: route.primary === id ? null : route.primary,
        fallback: route.fallback === id ? null : route.fallback,
      };
    }
    setSettings({ ...settings, models: settings.models.filter(model => model.id !== id), assignments });
    setNotice("");
  };

  const save = async () => {
    if (!settings || busy) return;
    setBusy(true);
    setNotice("");
    setError("");
    try {
      testRequests.current.forEach(request => request.abort());
      testRequests.current.clear();
      setTests({});
      const next = await saveModelSettings(settings);
      setSaved(next);
      setSettings(next);
      setNotice("模型配置已保存");
    } catch (error) {
      setError(error instanceof ApiError ? error.message : "模型配置保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="model-settings">
      <summary>模型填写 <i className="ws-icon ws-icon--chevron" aria-hidden="true" /></summary>
      {!settings ? (
        <div className="model-settings__content">
          <p role="status">{error || "正在读取模型配置…"}</p>
          {error && <button type="button" className="chip" onClick={() => setReload(value => value + 1)}>重新加载</button>}
        </div>
      ) : (
        <form className="model-settings__content" onSubmit={event => { event.preventDefault(); void save(); }}>
          <p className="model-settings__hint">支持 OpenAI 兼容接口和本地 Ollama。模型权限逐项开启，密钥保存于本机服务端。</p>
          <fieldset disabled={busy} className="model-settings__editor">
            <div className="model-settings__toolbar">
              <h3>已导入模型</h3>
              <button className="button button--ghost" type="button" disabled={settings.models.length >= 20}
                onClick={() => { setSettings({ ...settings, models: [...settings.models, newModel()] }); setNotice(""); }}>
                添加模型
              </button>
            </div>
            {settings.models.map((model, index) => {
              const persisted = saved?.models.find(item => item.id === model.id);
              const needsSave = !persisted || model.base_url !== persisted.base_url ||
                model.model !== persisted.model || model.api_key !== undefined;
              const test = tests[model.id];
              return (
              <fieldset className="model-entry" key={model.id}>
                <legend>模型 {index + 1}</legend>
                <div className="model-entry__tools">
                  <button type="button" className="chip" disabled={needsSave || test?.state === "testing"}
                    onClick={() => void testConnection(model)}>
                    {test?.state === "testing" ? "测试中…" : "测试连接"}
                  </button>
                  <button type="button" className="model-entry__remove" onClick={() => remove(model.id)}>移除</button>
                </div>
                {needsSave && <p className="model-settings__hint">保存模型的连接设置后可测试。</p>}
                <p className={test ? `model-entry__test model-entry__test--${test.state}` : "sr-only"} role="status">
                  {test?.text}
                </p>
                <div className="model-entry__fields">
                  <label>显示名称<input value={model.label} required maxLength={80}
                    placeholder="例如 本地千问" onChange={event => update(model.id, { label: event.target.value })} /></label>
                  <label>模型名称<input value={model.model} required maxLength={150}
                    placeholder="例如 qwen3.5-4b-local:latest" onChange={event => update(model.id, { model: event.target.value })} /></label>
                  <label>API 基址<input type="url" value={model.base_url} required maxLength={400}
                    placeholder="http://127.0.0.1:11434/v1" onChange={event => update(model.id, { base_url: event.target.value })} /></label>
                  <label>API 密钥<input type="password" autoComplete="new-password" maxLength={4096}
                    value={model.api_key ?? ""} placeholder={model.has_key ? "已填写，留空保留" : "本地模型可留空"}
                    onChange={event => update(model.id, { api_key: event.target.value || undefined })} /></label>
                </div>
                {model.has_key && (
                  <label className="model-entry__permission"><input type="checkbox" checked={model.api_key === ""}
                    onChange={event => update(model.id, { api_key: event.target.checked ? "" : undefined })} />移除已保存的密钥</label>
                )}
                <fieldset className="model-entry__permissions">
                  <legend>允许用于</legend>
                  {FEATURES.map(({ id, label }) => (
                    <label className="model-entry__permission" key={id}>
                      <input type="checkbox" checked={model.features.includes(id)} onChange={event =>
                        update(model.id, { features: event.target.checked
                          ? [...model.features, id] : model.features.filter(feature => feature !== id) })} />{label}
                    </label>
                  ))}
                </fieldset>
              </fieldset>
              );
            })}
            <details className="model-settings__import">
              <summary>批量导入 JSON</summary>
              <textarea aria-label="模型 JSON" value={importText} maxLength={100000} rows={4}
                placeholder={'[{"label":"本地千问","base_url":"http://127.0.0.1:11434/v1","model":"qwen3.5-4b-local:latest","features":["search"]}]'}
                onChange={event => setImportText(event.target.value)} />
              <button type="button" className="button button--ghost" disabled={!importText.trim()} onClick={() => {
                try {
                  const models = [...settings.models, ...parseImport(importText)];
                  if (models.length > 20) throw new Error("最多可保存 20 个模型");
                  setSettings({ ...settings, models });
                  setImportText("");
                  setError("");
                  setNotice("已导入到表单，保存后生效");
                } catch (error) {
                  setError(error instanceof SyntaxError ? "模型 JSON 格式无效" : (error as Error).message);
                }
              }}>导入模型</button>
            </details>
            <h3>功能分配</h3>
            {FEATURES.map(({ id, label }) => {
              const assignment = settings.assignments[id] ?? { primary: null, fallback: null };
              return (
                <fieldset className="model-entry model-route" key={id}>
                  <legend>{label}</legend>
                  {(["primary", "fallback"] as const).map(role => (
                    <label key={role}>{role === "primary" ? "默认模型" : "备选模型"}
                      <select aria-label={`${label} ${role === "primary" ? "默认模型" : "备选模型"}`}
                        value={assignment[role] ?? ""} onChange={event => {
                          setNotice("");
                          setSettings({ ...settings, assignments: {
                            ...settings.assignments, [id]: { ...assignment, [role]: event.target.value || null },
                          } });
                        }}>
                        <option value="">{role === "primary" ? "系统配置" : "无备选"}</option>
                        {settings.models.map((model, index) => (
                          <option key={model.id} value={model.id} disabled={
                            assignment[role === "primary" ? "fallback" : "primary"] === model.id
                          }>{model.label || `模型 ${index + 1}`}{model.features.includes(id) ? "" : "（未开启）"}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                </fieldset>
              );
            })}
          </fieldset>
          <div className="model-settings__footer">
            <button className="button" type="submit" disabled={busy}>{busy ? "保存中…" : "保存模型配置"}</button>
            {notice && <span role="status">{notice}</span>}
            {error && <span role="alert" className="workspace-form-error">{error}</span>}
          </div>
        </form>
      )}
    </details>
  );
}
