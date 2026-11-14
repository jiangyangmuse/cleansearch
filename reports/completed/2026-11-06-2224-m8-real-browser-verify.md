# 完工报告 · M8 真实浏览器验收：扩展与 PWA

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-2224 |
| 开始 | 2026-11-06 22:24 |
| 结束 | 2026-11-06 22:24 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | test |
| 状态 | 完成 |

## 1 任务

**目标**

补上 [M8 验收报告](../incomplete/2026-11-06-2214-m8-capture-acceptance.md) §6 留的待验项：在独立 Chromium 配置里真实加载未打包扩展，验证弹窗收藏；并用 CDP 核对 PWA 清单与安装性。

**验收标准**

- `--load-extension` 能加载 `apps/extension`，能从 service worker 拿到真实扩展 ID。
- popup 填 API 与 token 后收藏成功，书签落库。
- 后台保存函数（右键菜单路径）可独立调用成功。
- `Page.getAppManifest` 解析到含 `share_target` 的清单；`Page.getInstallabilityErrors` 结果可判读。
- 脚本可复现，全量测试与构建不回归。

**不做**

- Android 真机安装与系统分享菜单（无设备）。
- Chrome 应用商店打包/上架。

## 2 做了什么

1. 新增 `scripts/verify-extension.cjs`：持久化上下文 + `--disable-extensions-except`/`--load-extension`，从 service worker URL 取扩展 ID，驱动 popup 完成 token 设置与收藏，再调后台保存函数，最后用 CDP 读 PWA 清单与安装性错误；截图与 `installability.json` 落在 `docs/m9-evidence`。
2. 修 popup 的地址一致性：原实现把标签页地址写进 `<p>` 的 textContent，改成交互输入后「显示」与「保存」可能不一致；现在地址框是输入框、保存以输入框为准（空则回退标签页），并把 `chrome.tabs.query` 失败降级为填空而不是抛异常。
3. 给扩展补 background service worker + 右键菜单入口（`contextMenus`），既是产品通道，也让自动化能定位扩展 ID。
4. playwright 只作为 `apps/web` 的 devDependency；脚本按 `apps/web/node_modules → 仓库根 → 全局` 顺序解析，缺依赖时给出可执行提示。
5. 文档补「验证扩展」小节与 M8-D7…D9 决策。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [scripts/verify-extension.cjs](../../scripts/verify-extension.cjs) | 新增 | 真实浏览器验收脚本 |
| [apps/extension/background.js](../../apps/extension/background.js) | 新增 | 右键菜单 + 共用保存函数 |
| [apps/extension/manifest.json](../../apps/extension/manifest.json) | 修改 | `background`、`contextMenus` |
| [apps/extension/popup.html](../../apps/extension/popup.html)、[popup.js](../../apps/extension/popup.js)、[popup.css](../../apps/extension/popup.css) | 修改 | 地址输入框、保存以输入为准、权限失败降级 |
| [apps/web/package.json](../../apps/web/package.json) | 修改 | `playwright` devDependency（仅验收脚本使用） |
| [docs/m9-evidence/](../../docs/m9-evidence) | 新增 | 截图与 installability.json |
| [README.md](../../README.md)、[docs/决策与接口变更.md](../../docs/决策与接口变更.md) | 修改 | 验证命令、M8-D7…D9 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `node scripts/verify-extension.cjs http://127.0.0.1:18085` | 通过 | `ALL PASS`，7 项断言 |
| `python -m pytest apps/api -o addopts= -q` | 通过 | `239 passed` |
| `npm --prefix apps/web run build` | 通过 | 42 modules，TypeScript 通过 |
| `Page.getInstallabilityErrors` | 通过 | `[]`（无安装性错误） |

脚本实际输出：

```
扩展已加载            id=<由 service worker 推导>
popup 可打开          chrome-extension://<id>/popup.html
popup 写入书签        已收藏
书签落库              total=1（含 docs.python.org）
后台保存函数可用      {"ok": true, "message": "已收藏"}
manifest 被解析       http://127.0.0.1:18085/manifest.webmanifest（含 share_target）
安装性检查            [] 无错误
无 JS 运行时错误      ok
```

证据文件：`docs/m9-evidence/01-扩展收藏.png`、`docs/m9-evidence/installability.json`。

未验证：Android 真机 PWA 安装与系统分享；扩展在 Edge / Chrome 正式渠道的加载（本轮用 Playwright 自带 Chromium）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 用持久化上下文 + `--load-extension` | 只做 manifest 静态校验 | M8 报告明确缺「真实加载」这一项，静态校验补不上 |
| 从 service worker 取扩展 ID | 按路径哈希猜 ID | 猜出来的 ID 与实际不符时导航被 `ERR_BLOCKED_BY_CLIENT` 挡住（已踩） |
| popup 地址改为输入框且以输入为准 | 只显示不可改 | 原实现 `textContent` 与输入框混用，UI 与保存值会分叉 |
| playwright 只进 devDependencies | 塞进运行时依赖 | 浏览器自动化与产品运行无关，按需安装即可 |
| 加 background + 右键菜单 | 只留 popup | 既是产品通道（右键收藏），也让验收脚本有稳定锚点 |

## 6 遗留与风险

- Playwright Chromium 与实际 Chrome / Edge 仍有差异（扩展 API 覆盖、权限提示文案）。
- 手机端 PWA 未验证；服务默认只监听回环，手机需指向可访问部署，且要 HTTPS 才能安装。
- 验收脚本需要可见浏览器窗口，CI 里要换 `--headless=new` 或 xvfb；本轮未接 CI。
- 脚本会向所连实例写一条书签（`docs.python.org`）与一条后台测试记录，跑在正式库前需自行清理。

## 7 交接

**下一个人第一件事**

在 `http://<局域网 IP>:8000`（HTTPS 或手机可访问的地址）上装一次 PWA，从 Android 分享菜单发链接到 CleanSearch，确认落到 `/bookmarks` 且预填、未自动写库。

**相关文件**

- [M8 验收报告](../incomplete/2026-11-06-2214-m8-capture-acceptance.md)
- [验证脚本](../../scripts/verify-extension.cjs)、[扩展目录](../../apps/extension)
- [M8-D7…D9](../../docs/决策与接口变更.md)
- [真实浏览器证据](../../docs/m9-evidence)
