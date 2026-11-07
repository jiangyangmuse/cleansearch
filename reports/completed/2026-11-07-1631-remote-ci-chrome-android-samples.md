# 完工报告 · 远端 CI、Chrome/Android 验收与样本扩大

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1631 |
| 开始 | 2026-11-07 16:31 |
| 结束 | 2026-11-07 16:31 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | test |
| 状态 | 完成 |

## 1 任务

**目标**

1) 补远端 CI；2) Chrome 与 Android 验收；3) 扩大 RDAP 正常域名样本、检索标注样本与总结质量样本。

**验收标准**

- 远端可推送，且 CI 在干净 clone 上通过。
- Chrome 引擎能加载扩展并完成收藏；Android 相关行为有浏览器级证据。
- RDAP 有无误报数据；检索与总结各有 ≥5 个样本的量化结果。
- 拿不到的（GitHub 托管、Android 真机）如实标注。

**不做**

- 伪造 GitHub Actions 运行结果；伪造 Android 真机证据。

## 2 做了什么

1. 建本地 bare 远端 `D:\agent\llq-remote.git`，设 origin 并推送两个提交；换 GitHub 只需改 remote URL。
2. 在**干净 clone**（无 .env / node_modules / dist）里用 act 跑 ci.yml：Install、305 项测试、构建、15 项冒烟全绿，Job succeeded。
3. 装 Chrome for Testing 157，给 verify-extension.cjs 加 `CS_CHROME_PATH`，真 Chrome 引擎上扩展 12 项全过。
4. 新增 scripts/verify-android.cjs：Pixel 7 档案下验 manifest share_target、分享预填、触屏保存、CDP 安装性、JS 错误，8 项全过。
5. RDAP 校准：30 个正常域名，26 个解析成功，0 个 <30 天、0 个 <365 天；冷查询中位 3152ms、缓存 0ms；4 个查不到（ccTLD/RDAP 缺失）。
6. 检索标注集 18 → 40 条并重跑 eval-expansion：扩展命中的 12 条里 baseline 6/12、rank 6/12、rewrite 9/12。
7. 总结质量：5 个主题 fast 全成功，首字中位 7.24s、总耗时中位 19.2s、170 段、每题 10 条引用、0 partial。
8. 文档同步 README、决策 M16-D1…D5、进展与欠账（P1-1 置完成、P1-2 推进、缺口清单更新）。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [scripts/verify-android.cjs](../scripts/verify-android.cjs) | 新增 | Android 档案验收 |
| [scripts/verify-extension.cjs](../scripts/verify-extension.cjs) | 修改 | 支持 CS_CHROME_PATH |
| [apps/api/tests/regression/p2_labeled_queries.json](../apps/api/tests/regression/p2_labeled_queries.json) | 修改 | 18 → 40 条 |
| [README.md](../README.md)、[docs/决策与接口变更.md](../docs/决策与接口变更.md)、[docs/进展与欠账.md](../docs/进展与欠账.md) | 修改 | 本轮结论 |
| [docs/m10-evidence/p3-rdap-sample.json](../docs/m10-evidence/p3-rdap-sample.json)、[p2-expansion-40.json](../docs/m10-evidence/p2-expansion-40.json)、[p3-summary-quality.json](../docs/m10-evidence/p3-summary-quality.json)、[03-android-share-prefill.png](../docs/m10-evidence/03-android-share-prefill.png) | 新增 | 证据 |
| 本报告与 [INDEX.md](INDEX.md) | 新增/更新 | 登记 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| git push origin main | 通过 | acaecf9 → 44eb84f；`origin D:\agent\llq-remote.git` |
| 干净 clone + act -j verify | 通过 | Job succeeded：305 passed、构建、15 项冒烟（clone 无 .env/node_modules/dist） |
| node scripts/verify-extension.cjs（CfT 157） | 通过 | 12 项 ALL PASS |
| node scripts/verify-android.cjs | 通过 | 8 项 ALL PASS：share_target、参数、预填、标题、触屏保存、清单、安装性 []、无 JS 错误 |
| RDAP 30 域名样本 | 通过 | 26 解析、0 个 <30 天、中位年龄 7008 天；冷 3152ms、热 0ms |
| python scripts/eval-expansion.py --base-url ... | 通过 | 40 条：baseline 6/12、rank 6/12、rewrite 9/12（扩展命中子集） |
| 5 主题 fast 总结 | 通过 | 首字中位 7243ms（最大 13094）、总 19187ms、170 段、10 引用、0 partial |
| python -m pytest apps/api -q -o addopts= | 通过 | 315 passed |

未验证：GitHub/Gitea 托管运行（无凭据）；Android 真机安装、系统分享面板、离线启动（无设备/SDK）；正式版 Chrome 命令行加载扩展（137 起移除，只能手动）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 本地 bare 仓库当远端 | 等 GitHub 账号 | 先把「CI 跑已提交代码」这条闭环做实，换 URL 即可接托管 |
| Chrome 用 CfT 而不是正式版 | 手动加载扩展 | CfT 保留 --load-extension，可复现；正式版无法自动化 |
| Android 只做浏览器档案验收 | 装 Android SDK 模拟器 | 镜像 1.5GB+ 且需虚拟化，收益低于成本；缺口如实列 |
| 标注集扩到 40 条 | 用 18 条结论 | 12 条扩展样本噪声太大 |

## 6 遗留与风险

- 本地远端没有托管平台的权限模型、矩阵与缓存策略，不能完全替代 GitHub Actions。
- Android 真机、系统分享面板、离线启动、系统深色模式联动未验。
- RDAP 对 ccTLD 覆盖不全（本次 4/30 查不到），负缓存一天。
- 40 条标注集的期望域名仍是宽口径，结论看趋势。
- 总结首字中位 7.2s 仍高于设计目标。

## 7 交接

**下一个人第一件事**

把 origin 换成 GitHub 并推送，确认 Actions 与 act 结果一致；同时借一台 Android 设备补真机分享与安装验收。

**相关文件**

- [README 远端/Chrome/Android 章节](../README.md)
- [决策 M16-D1…D5](../docs/决策与接口变更.md)
- [Android 验收脚本](../scripts/verify-android.cjs)
- [RDAP 样本数据](../docs/m10-evidence/p3-rdap-sample.json)

---

> 注：头部「耗时」由 `close-report.ps1` 按报告起草时间计算；本轮实际约 40 分钟（含 CfT 下载、40 条查询评估与 5 主题总结）。
