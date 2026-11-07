# CleanSearch 收藏（Chrome / Edge 扩展）

最小 MV3 扩展：当前页一键收藏到本地 CleanSearch。

## 安装

1. 启动 API（默认 `http://127.0.0.1:8000`）；
2. 浏览器打开 `chrome://extensions`，开启「开发者模式」；
3. 「加载已解压的扩展程序」→ 选本目录 `apps/extension`；
4. 点扩展图标 → 展开「连接设置」，填入本机 HTTP API 地址（`127.0.0.1` 或 `localhost`）与 `/tools` 页面显示的 token。点击「保存设置」供下次使用。

## 说明

- `X-CS-Token` 只允许添加链接。重复收藏会提示已存在，保留旧书签；
- 书签只写到本机 SQLite，扩展不联网、不上报；
- 图标未提供，用浏览器默认占位。
