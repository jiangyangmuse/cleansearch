import { useEffect } from "react";
import type { CSSProperties, ReactNode } from "react";
import WorkspaceHeader, { type ShellPage } from "./WorkspaceHeader";
import type { HistoryEntry } from "../searchHistory";

interface Props {
  children: ReactNode;
  current?: ShellPage;
  /** 整页标题；给了就写到 document.title，搜索页自己按查询维护。 */
  title?: string;
  /** 与正文共用的最大宽度，保证品牌与正文左边缘对齐。 */
  maxWidth?: number;
  onHistorySearch?: (entry: HistoryEntry) => void;
}

/**
 * 五个页面共用的外壳：跳转链接 + 品牌/导航 + 正文槽位。
 * 头部与正文共用 --shell-max 与 --shell-pad，所以两者左边缘一致。
 */
export default function AppShell({ children, current, title, maxWidth, onHistorySearch }: Props) {
  useEffect(() => {
    if (title) document.title = title;
  }, [title]);

  const style = maxWidth ? ({ "--shell-max": `${maxWidth}px` } as CSSProperties) : undefined;

  return (
    <div className="workspace-app" style={style}>
      <a className="skip-link" href="#main">跳到主要内容</a>
      <WorkspaceHeader current={current} onHistorySearch={onHistorySearch} />
      {children}
    </div>
  );
}
