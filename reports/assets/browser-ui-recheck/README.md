# 浏览器与 UI 复查截图（2026-11-13 晚）

当前构建 `apps/web/dist`（22:38）隔离实例 `http://127.0.0.1:18400`（真实 SearXNG + 临时数据库），Chromium/Playwright。

| 文件 | 场景 | 说明 |
| --- | --- | --- |
| 01-filter-popover-desktop.png | 1440×900，筛选面板打开并选中“一周内” | 面板 420×339，覆盖官方入口与分页；点外部/Esc 都不关，只有再点“筛选”才关 |
| 02-filter-popover-mobile.png | 390×844，筛选面板打开 | 面板从 x=96 展开 358px，右侧超出视口；点外部不关 |
| 03-mobile-first-screen.png | 390×844 首屏 | 第一条自然结果 y=766，仅露出标题顶部；官方入口 3 条占主要空间 |
| 04-desktop-901.png | 901×900 | 仍是三栏，主列 478px；统计/卡片折行 |
| 05-desktop-1024.png | 1024×900 | 仍是三栏，主列 601px；与方案“900–1179 两栏”不一致 |
| 06-mobile-home.png | 390×844 空首页 | 只有搜索框和选项，无最近搜索/示例入口 |
| 07-offline-settings.png | 断网后打开 /settings | 离线壳能加载，但引擎设置出现英文 “Failed to fetch”，没有全局离线提示 |
| 08-mobile-drawer.png | 390×844 工具抽屉 | 抽屉效果正常，打开后结果区 top 保持 243 |
