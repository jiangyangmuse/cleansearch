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
          确认本机服务已启动（默认 http://127.0.0.1:8000）。免安装版重新双击启动程序即可；
          从源码运行的，在仓库根目录执行 {" "}<code>{"scripts\\serve.ps1"}</code>。
        </p>
        <button type="button" className="chip" onClick={() => void refreshServerState()}>重试连接</button>
      </div>
    );
  }

  return (
    <div className="server-banner" role="status" data-state="outdated">
      <p className="server-banner__title">本机服务版本过旧，部分功能已禁用</p>
      <p className="server-banner__detail">
        当前服务缺少：{state.missing.map(name => CAPABILITY_LABELS[name]).join("、")}。
        先停掉旧进程，再用新版程序重启本机服务（免安装版：关掉窗口后重新双击；源码：{" "}
        <code>{"scripts\\serve.ps1 -SkipBuild"}</code>），然后重试。
      </p>
      <button type="button" className="chip" onClick={() => void refreshServerState()}>重试连接</button>
    </div>
  );
}
