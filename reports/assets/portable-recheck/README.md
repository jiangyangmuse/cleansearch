# 免安装包与浏览器二次复查截图（2026-11-14 晚）

当前构建 `apps/web/dist`（19:30），日常 `127.0.0.1:8000`（fixture、api_version=2），Chromium/Playwright。

| 文件 | 场景 | 说明 |
| --- | --- | --- |
| 01-empty-home-mobile.png | 390×844 空首页 | 最近搜索/示例/快捷入口；此前为空屏 |
| 02-filter-panel-mobile.png | 390×844 筛选面板 | 面板完整落在视口内，点外部关闭 |
| 03-capability-banner.png | 模拟旧后端 health | 页头版本横幅，筛选入口禁用 |
| 04-1024-drawer.png | 1024×900 | 单列 + 工具按钮/抽屉 |
| 05-1181-three-column.png | 1181×900 | 三栏恢复 |
| 06-390-results.png | 390×844 结果页 | 首条结果 y≈547，官方入口折在强相关之后 |
