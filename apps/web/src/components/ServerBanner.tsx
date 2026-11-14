import { CAPABILITY_LABELS, refreshServerState, useServerState } from "../capabilities";

/**
 * 混版（新 dist + 旧 API）时的全局提示。
 * 旧服务缺接口会表现为 404/405 或参数被静默忽略，必须说出来而不是静默降级。
 */
export default function ServerBanner() {
  const state = useServerState();
  if (state.kind === "loading" || state.kind === "ok") return null;

  if (state.kind === "offline") {
    return (
      <div className="server-banner" role="status" data-state="offline">
        <p className="server-banner__title">连不上本机服务</p>
        <p className="server-banner__detail">
          确认 FastAPI 已启动（默认 http://127.0.0.1:8000），或在本机执行
          {" "}<code>{".\\scripts\\serve.ps1 -Provider searxng"}</code>。
        </p>
        <button type="button" className="chip" onClick={refreshServerState}>重试连接</button>
      </div>
    );
  }

  return (
    <div className="server-banner" role="status" data-state="outdated">
      <p className="server-banner__title">本机服务版本过旧，部分功能已禁用</p>
      <p className="server-banner__detail">
        当前服务缺少：{state.missing.map(name => CAPABILITY_LABELS[name]).join("、")}。
        先停掉旧进程，再执行 {" "}
        <code>{".\\scripts\\serve.ps1 -Provider searxng -SkipBuild"}</code>，然后刷新本页。
      </p>
    </div>
  );
}
