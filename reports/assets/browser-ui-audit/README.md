# 浏览器与 UI 审计截图

2026-11-13，Chromium（Playwright 1.64），本机 `http://127.0.0.1:8000`，真实 SearXNG 模式。

| 文件 | 场景 | 说明 |
| --- | --- | --- |
| 01-desktop-idle.png | 1440×900 首页 | 空态；无最近搜索/示例 |
| 02-desktop-results.png | 1440×900 结果页 | 统计条、官方入口、分页、三档结果 |
| 03-desktop-engine-menu.png | 引擎菜单展开 | 16 个非大陆引擎落在“中国大陆可直连”标题下；菜单遮挡结果 |
| 04-desktop-summary-rail.png | 右栏打开 AI 总结 | 网页总结 + AI 总结挤在 268px 面板内 |
| 05-desktop-dark.png | 深色主题 | 对比度合格；与浅色布局一致 |
| 06-desktop-901.png | 901px 宽 | 三栏主列仅 478px，统计/官方入口/卡片元信息折行 |
| 07-desktop-1920.png | 1920px 宽 | 主列与右栏之间约 199px 空隙，右栏脱节 |
| 08-mobile-idle.png | 390×844 首页 | 头部两行 92px；书签快捷栏与工具按钮占位 |
| 09-mobile-first-screen.png | 390×844 结果页首屏 | 首屏无自然结果；第一条结果在 y=1017 |
| 10-mobile-summary-push.png | 390×844 打开 AI 总结 | 结果区被推下 421px |
| 11-mobile-engine-menu.png | 390×844 引擎菜单 | 菜单遮挡统计；点外部不关闭 |
| 12-mobile-bookmarks.png | 390×844 书签页 | 旧 header 链接竖排；品牌与正文错位 |
| 13-mobile-tools.png | 390×844 工具页 | bookmarklet 代码横向溢出 |
| 14-settings-engines.png | 1440 设置页 | 引擎分组误标；20 个禁用开关仍显示为开启 |
| 15-error-state.png | 1440 断网错误 | “上游不可用” + curl/环境变量命令 |
| 16-mobile-320.png | 320px 结果页 | 无横向溢出；工具按钮换行 |
| 17-loading-state.png | 1440 搜索中 | 结果区被一行 spinner 取代，页面塌陷 |
