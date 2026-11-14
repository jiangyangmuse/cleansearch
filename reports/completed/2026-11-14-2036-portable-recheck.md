# 完工报告 · 免安装包与浏览器二次复查

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261114-2036 |
| 开始 | 2026-11-14 20:36 |
| 结束 | 2026-11-14 20:37 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | research |
| 状态 | 完成 |

## 1 任务

**目标**

复查当前已交付的浏览器/UI 与免安装分发包：确认上一轮 R-01…R-12 已修复、当前构建可回归，找出新出现的打包分发问题，并把下一轮方案写可执行。

**验收标准**

- 在隔离实例复跑 pytest、静态检查、fixture 315 项审计与真实筛选 9/9。
- 独立复测筛选状态/浮层、移动首屏、1180 断点、能力横幅、焦点/安装/离线。
- 检查免安装包的启动器、说明、SearXNG 配置与数据边界，找出可复现的问题。
- 产出按 P1/P2/P3 排序、含文件落点与验收口径的方案。
- 不修改 `apps/`、`data/`、`dist/`、`dist-portable/`。

**不做**

- 不改产品代码、不重打包、不重启 8000、不提交 git。
- Android/iOS 真机、NVDA/VoiceOver、正式 Chrome 手动加载扩展仍缺设备。
- 不重新评估搜索排序、正文质量或付费兜底。

## 2 做了什么

1. 读 `reports/INDEX.md` 最近条目、2026-11-14 决策、`reports/incomplete/2026-11-14-0044` 与 `completed/2026-11-14-1939` 打包报告。
2. 对当前 8000（fixture，api_version=2）做独立浏览器复测：筛选回退/外部点击/Esc、390/320/640/641/768/1024/1180/1181 布局、空首页、快捷键焦点、安装按钮、离线横幅、模拟旧后端能力缺失。
3. 启动隔离实例 `18421`（fixture，临时 DB）跑 `audit-ui.cjs --test-bookmark-writes` 与 `18420`（真实 SearXNG，临时 DB）跑 `verify-filters.cjs`；再跑 pytest 与 node 静态检查。
4. 检查 `packaging/launcher.py`、`packaging/searxng/*`、`scripts/build-portable.ps1`、包内 `说明.txt` 和 README §5/§6，核对监听地址、ALLOWED_HOSTS、镜像/密钥、包内数据与文档声明。
5. 截取 6 张当前界面证据到 `reports/assets/portable-recheck/`，把结论与下一轮方案追加到 `docs/浏览器与UI复查与完善方案.md` §8。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `docs/浏览器与UI复查与完善方案.md` | 修改 | 追加 §8 二次复查：基线、R-13…R-18、打包/文档建议 |
| `reports/completed/2026-11-14-2036-portable-recheck.md` | 新增 | 本报告（验收后已移至 completed） |
| `reports/assets/portable-recheck/*.png` | 新增 | 6 张二次复查截图与索引 |
| `reports/INDEX.md` | 修改 | 按流程登记本报告一行 |
| `apps/**`、`data/**`、`dist/**`、`dist-portable/**` | 未改 | 用户要求不动现有产物 |

## 4 验证与证据

| 命令/动作 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o addopts=` | 通过 | `489 passed in 10.06s` |
| `node --test scripts/{extension,css-audit,engine-query,url-state}.test.cjs` | 通过 | 35/35，含 7 项 URL 契约 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18421 --test-bookmark-writes` | 通过 | `ALL PASS (315)` |
| `node scripts/verify-filters.cjs http://127.0.0.1:18420` | 通过 | `ALL PASS (9)`：站点、时间、语言、严格/关闭去重 |
| 8000 `/api/health` | 通过 | fixture、api_version=2、五项能力全 true、db_path 存在 |
| 筛选一周→后退 | 通过 | 回到无筛选 URL，badge/note 清空，请求带 `time_range:null`，结果回到 base |
| 筛选外部点击/Esc | 通过 | 原生 popover 关闭，焦点回「筛选」 |
| 390 首条结果 | 通过 | y≈547；官方入口默认 2 条、折在强相关之后 |
| 1024/1180/1181/1440 | 通过 | 1024/1180 抽屉，1181/1440 三栏；无横向溢出 |
| 模拟旧 health | 通过 | 页头版本横幅，筛选按钮禁用 |
| 空首页快捷键焦点 | 通过 | 打开前聚焦 main，关闭回 main；结果页回「全部快捷键」 |
| 安装按钮 | 通过 | `disabled=true`，title 提示浏览器菜单 |
| 包内 `launcher.py` | 发现 R-13 | 第 65 行设置 `API_HOST`，第 91 行 uvicorn 仍硬编码 `127.0.0.1` |
| 包内 `说明.txt` | 发现 R-13/R-16 | 第 20 行称 `ALLOWED_HOSTS` 可让手机访问；第 5 行称中文路径可用（未验证） |
| 包内 SearXNG | 发现 R-14 | `image: searxng/searxng:latest`、`SEARXNG_SECRET` 固定字符串 |
| `ServerBanner` 文案 | 发现 R-15 | 离线/过旧都指向 `\\scripts\\serve.ps1`，包内不存在 |

**截图**：`01-empty-home-mobile.png`、`02-filter-panel-mobile.png`、`03-capability-banner.png`、`04-1024-drawer.png`、`05-1181-three-column.png`、`06-390-results.png`。

**来源**：[`packaging/launcher.py`](../../packaging/launcher.py)、[`packaging/searxng/docker-compose.yml`](../../packaging/searxng/docker-compose.yml)、[`dist-portable/CleanSearch/说明.txt`](../../dist-portable/CleanSearch/说明.txt)、[MDN Popover API](https://developer.mozilla.org/en-US/docs/Web/API/Popover_API)、[PyInstaller onedir](https://pyinstaller.org/en/stable/usage.html#bundling-to-one-folder)。

**未验证**

- Android/iOS 真机安装/系统分享、NVDA/VoiceOver 朗读；真实 Google/CSE 某些时段 503。
- 免安装包在 Win10、老 CPU、中文/非 ASCII 路径下的运行；包内 `API_HOST` 改动未实测（本轮只读代码）。
- 包内 SearXNG 镜像升级后的兼容性。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 先确认 UI 基线再谈打包 | 直接找包 bug | 上一轮 R-01…R-12 是否真的修复决定下一轮优先级；315/9 项复跑通过后，UI 不再占 P0 |
| 把 R-13 定为 P1 打包问题 | 当作文档小错 | 用户按包内说明设置手机访问会直接失败；监听地址与 Host 放行是两件事 |
| 不建议本轮改代码 | 顺手修 launcher | 用户明确“不要动现在的产物”；且需要重新打包/验证，不宜只改一行 |
| 包内镜像固定 tag/digest | 继续 latest | 分发包要可复现；latest 会在未来某次拉取时改变行为 |
| 包内诊断文案分构建 | 统一写 serve.ps1 | 免安装用户没有 scripts/，照做会失败 |

## 6 遗留与风险

- R-13 未修：包内手机访问仍不可用；README §6 与 `说明.txt` 仍有误导。
- R-14 未修：镜像/密钥可复现性与共享密钥；当前只绑回环，风险有限但分发前应处理。
- R-15 未修：包内异常提示仍指向仓库脚本；离线/过旧时用户会看到不可执行命令。
- R-16 文档口径：中文路径、审计数字、支持范围尚未统一。
- R-17/R-18 为低优先：旧服务横幅无重试、首屏浏览器可能早于服务。
- 真机/读屏、Google/CSE 上游仍是既有人工缺口。
- 工作区干净，本轮只新增 docs/report/assets，未改产品。

## 7 交接

**下一个人第一件事**

先决定免安装包的局域网范围：若支持，修 `packaging/launcher.py` 使用 `API_HOST`、新增局域网启动 bat，并改 `说明.txt`/README；若只支持同机，删掉 `ALLOWED_HOSTS` 手机说明。随后处理 R-14/R-15 与打包验证。

**相关文件**

- 方案：[docs/浏览器与UI复查与完善方案.md](../../docs/浏览器与UI复查与完善方案.md) §8
- 截图：`reports/assets/portable-recheck/`
- 打包：`packaging/launcher.py`、`scripts/build-portable.ps1`、`packaging/searxng/*`、`dist-portable/CleanSearch/说明.txt`
- 验收：`scripts/audit-ui.cjs`、`scripts/verify-filters.cjs`、`scripts/url-state.test.cjs`
