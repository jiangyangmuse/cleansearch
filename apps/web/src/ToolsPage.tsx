import { useEffect, useRef, useState } from "react";
import ThemeToggle from "./components/ThemeToggle";

interface BookmarkletPayload {
  api: string;
  token: string;
  code: string;
  hint: string;
}

export default function ToolsPage() {
  const [payload, setPayload] = useState<BookmarkletPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const dragRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/tools/bookmarklet", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        setPayload((await response.json()) as BookmarkletPayload);
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setError(caught instanceof Error ? caught.message : "读取失败");
      });
    return () => controller.abort();
  }, []);

  // React 会拦截 javascript: 协议的 href，只能在挂载后直接写 DOM 属性
  useEffect(() => {
    if (payload && dragRef.current) {
      dragRef.current.setAttribute("href", payload.code);
    }
  }, [payload]);

  const copy = async () => {
    if (!payload) return;
    try {
      await navigator.clipboard.writeText(payload.code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("浏览器拒绝了剪贴板写入，请手动复制");
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true" />
          <span className="brand__name">CleanSearch</span>
          <span className="brand__tag">一键添加</span>
        </div>
        <span className="header__links">
          <ThemeToggle />
          <a className="header__link header__link--active" href="/bookmarks">
            书签启动台
          </a>
          <a className="header__link header__link--active" href="/">
            返回搜索
          </a>
        </span>
      </header>

      <main className="main">
        <h1 className="tools__title">把 CleanSearch 带到任意页面</h1>
        <p className="tools__lead">
          用书签栏、浏览器扩展或系统分享收集链接。书签栏和扩展需要本地 token。
        </p>

        {error ? <p className="bm-message bm-message--error">{error}</p> : null}

        <section className="tools__card">
          <h2>1 · Bookmarklet</h2>
          <p>把下面的链接拖到书签栏，在普通网页点一下即可收藏。若浏览器拦截连接，可打开本机书签页确认保存。</p>
          {payload ? (
            <a ref={dragRef} className="bookmarklet" href="#" title="拖到书签栏">
              收藏到 CleanSearch
            </a>
          ) : !error ? (
            <p className="state__hint">读取中…</p>
          ) : null}
          {payload ? (
            <>
              <button className="button button--ghost" type="button" onClick={() => void copy()}>
                {copied ? "已复制" : "复制代码"}
              </button>
              <pre className="state__cmd">{payload.code}</pre>
            </>
          ) : null}
        </section>

        <section className="tools__card">
          <h2>2 · 浏览器扩展（Chrome / Edge）</h2>
          <ol className="tools__steps">
            <li>打开 <code>chrome://extensions</code>，开启右上角「开发者模式」</li>
            <li>「加载已解压的扩展程序」→ 选择仓库里的 <code>apps/extension</code></li>
            <li>点扩展图标 →「连接设置」→ 填入 API 地址与下面的 token</li>
          </ol>
        </section>

        <section className="tools__card">
          <h2>3 · PWA 分享</h2>
          <p>
            在支持 Web Share Target 且能访问本机服务的设备上安装后，可从系统分享菜单把链接和标题预填到书签页。请确认后保存。
          </p>
        </section>

        {payload ? (
          <section className="tools__card">
            <h2>本地 token</h2>
            <p>此 token 仅用于添加书签。请只填到自己的扩展连接设置中。</p>
            <pre className="state__cmd">{payload.token}</pre>
            <p className="state__hint">API 地址：{payload.api}</p>
          </section>
        ) : null}
      </main>

      <footer className="footer">CleanSearch · 三条通道都只写本机 SQLite，不上传任何内容</footer>
    </div>
  );
}
