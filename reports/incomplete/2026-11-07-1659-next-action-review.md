# 完工报告 · DSH 后续验收复核与证据补强

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1659 |
| 开始 | 2026-11-07 16:59 |
| 结束 | 2026-11-07 17:15 |
| 耗时 | 17 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 部分完成 |

## 1 任务

复核 DSH“远端 CI、Chrome/Android 验收与样本扩大”的交付，修复可复现问题并对齐真实验收边界。

验收标准：自动检查不能假通过；RDAP 并发与风险规则一致；检索分母和总结证据可追溯；完成、未验与外部条件分别记录。原下一步的托管 CI、真机、新站对照及事实质检尚未收口，因此整体标为部分完成。

不做：不提交/推送 Git、不更换 remote、不改默认模型或风险权重，不将模拟或结构检查写成真机或事实质量通过。

## 2 做了什么

1. 确认 origin 为本地 bare 仓库，GitHub 连接可见仓库未匹配本项目。保留 DSH 的历史本地 act 记录，不认定已完成托管 CI。
2. 重写浏览器验收的关键检查：安装性错误会失败；唯一 URL 与精确标题/URL 落库核对；自动清理本轮记录；保存浏览器版本及检查数量。截图前清空 token 输入框。manifest 显式 enctype 消除解析警告。
3. 复现 RDAP 三请求并发峰值 12，改为同应用 store/事件循环共享上限 4；预算仍含排队，缓存不排网络队列，取消释放许可。修复同域零风险结果被连带加分。
4. 检索脚本同时统计全量、扩展子集与非扩展对照，计入未命中 MRR10；旧请求状态缺失保留未知，新跑失败留在分母并保存中间结果。
5. 校准脚本支持任意数量样本、出处及核验时间、离线汇总和新站数量门槛。复核 30 个参考后确认无新注册正常对照，不能认定新站零误报。
6. 新增可重放的总结采集/结构判断器，完成六主题 fast/full 共 12 次实际采集。补材料类型与限定语提示；三主题相同材料重放仍有事实待改写，未宣称准确率修复。
7. 将浏览器判断器负例测试纳入 CI，补 API 回归；同步 README、进度、决策 M17 和台账更正，保留历史报告及其状态行。

## 3 改动清单

| 路径 | 改动 |
| --- | --- |
| `apps/api/app/core/rdap.py`、`apps/api/tests/test_rdap.py` | 共享并发、零风险边界与 3 项回归 |
| `apps/api/app/core/summarize.py`、`apps/api/app/prompts/summary_system.txt` | 材料类型及事实限定语 |
| `apps/api/tests/test_eval_tools.py` | 5 项分母、截断 SSE、引用、未知/旧站控制回归 |
| `scripts/browser-check.cjs`、`scripts/browser-check.test.cjs` | 共享检查/清理/JSON 与安装性负例 |
| `scripts/verify-extension.cjs`、`scripts/verify-android.cjs` | 精确保存、检查失败、环境标注和隔离数据清理 |
| `scripts/eval-expansion.py`、`scripts/eval-rdap.py`、`scripts/eval-summary.py` | 聚合、门槛、采集与离线重验 |
| `apps/web/public/manifest.webmanifest`、`.github/workflows/ci.yml` | 显式 enctype、判断器测试步骤 |
| `README.md`、`docs/进展与欠账.md`、`docs/决策与接口变更.md`、`reports/INDEX.md` | 真实进度、证据边界与 M17 |
| `reports/assets/next-action-review/` | JSON、JUnit、冒烟日志、人工审读、复现实验及核对脚本 |
| 本报告 | 原目标整体部分完成，留根目录继续跟踪 |

## 4 验证与证据

所有网络/浏览器验证均经授权测试环境执行；Python 临时目录使用工作区 `data/review-temp`。初次受限环境出现 Temp 写入权限错误及套接字限制，已改用隔离目录与允许访问本机服务的执行环境，未伪记通过。

| 命令原文 / 操作 | 退出码与真实输出摘要 |
| --- | --- |
| `git remote -v`、`git log -4 --oneline --decorate` | 0；origin 为本地 bare，HEAD 为 af774b3；本轮未 commit/push |
| GitHub `list_repositories(page_size=100,page_offset=0)` | 可访问仓库 1 个，无 CleanSearch/llq 匹配；未找到目标项目的托管运行证据 |
| `python -m pytest apps/api/tests/test_rdap.py -q -o addopts= --tb=short`（共享限额修复前） | 1；`1 failed, 14 passed`，峰值 `12 <= 4` 断言失败 |
| `python -m pytest apps/api -q`（工作区 Temp） | 0；完整 API 回归通过；默认双重 quiet 不输出总数 |
| `python -m pytest apps/api -q -o addopts= --junitxml=reports/assets/next-action-review/api-tests.xml` | 0；最终修改后 `323 passed in 8.22s` |
| `npm --prefix apps/web run build` | 0；TypeScript 通过、42 modules、生产构建成功 |
| `node --test scripts/browser-check.test.cjs` | 0；1 项测试，覆盖非空安装错误、缺证据、空清单及解析错误负例 |
| `CS_CHROME_PATH` 指向已有 CfT 157、`CS_HEADLESS=true`，`node scripts/verify-extension.cjs http://127.0.0.1:18160 reports/assets/next-action-review/browser` | 0；10/10；popup、后台保存、精确落库、清单/安装性、清理及 JS 错误检查 |
| `node scripts/verify-android.cjs http://127.0.0.1:18160 reports/assets/next-action-review/browser` | 0；18/18；三种分享输入、危险 URL 拒绝、触屏新建、安装性及清理；仅桌面模拟 |
| `python scripts/eval-expansion.py --aggregate docs/m10-evidence/p2-expansion-40.json --json-out reports/assets/next-action-review/retrieval-40.json` | 0；全量 Top10 20/40、20/40、23/40；子集 6/12、6/12、9/12；MRR10 0.3761/0.3629/0.4148；旧请求状态未知 |
| `python scripts/eval-rdap.py --aggregate docs/m10-evidence/p3-rdap-sample.json --require-fresh-references 5 --json-out reports/assets/next-action-review/rdap-controls.json` | 2（预期不达标）；30 个参考、26 个年龄可得、4 未知；新站对照 0/5，新站误报率 null |
| `python reports/assets/next-action-review/probe-rdap.py` | 0；MockTransport 三批 × 8；峰值 4、启动 4、结束在途 0，耗时 4046/4016/4029 ms；不跨 worker |
| 下列六主题 `eval-summary.py` 命令 | 0；fast/full 各 6/6 结构通过；首段中位 7612.5/24135.5 ms，总中位 20655/36905.5 ms，full 取得 15/30、partial 6/6 |
| `python scripts/eval-summary.py --reassess reports/assets/next-action-review/summary-12.json --json-out reports/assets/next-action-review/summary-12-reassessed.json` | 0；正文、引用绑定/编号、meta/done 与计数重验仍 12/12 |
| `python reports/assets/next-action-review/probe-prompt.py` | 0；三次相同材料的本机千问重放，编号有效；人工仍发现 Rust/HTTP2 需改写，不等同事实通过 |
| 最终源码重启后 `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18160` | 0；16/16，日志 smoke-powershell.txt |
| `python scripts/ci-smoke.py http://127.0.0.1:18160` | 0；15/15，日志 smoke-python.txt |
| `git diff --check` | 0；无空白错误，仅已有 LF/CRLF 策略提示 |
| `python reports/assets/next-action-review/verify.py` | 0；92 个相对链接/锚点、36 份报告台账一致；35 份历史报告内容及历史状态行保持；本轮文件和证据未检出已配置凭据 |
| `.\scripts\close-report.ps1 -Path reports/2026-11-07-1659-next-action-review.md -Status 部分完成`、`python reports/assets/next-action-review/verify.py --final` | 均 0；结构 PASS，首行为本轮部分完成报告，保留根目录；自动核对 errors=[] |

实际六主题采集命令（关闭搜索缓存、扩展 off，真实 SearXNG/已配置 Serper + 本机千问）：

```powershell
python scripts/eval-summary.py --base-url http://127.0.0.1:18161 --query 'asyncio 事件循环 原理' --query 'Rust 所有权 借用' --query 'HTTP/2 多路复用' --query '量子计算 入门' --query '分布式 一致性' --query 'Python GIL 并发' --modes fast full --json-out reports/assets/next-action-review/summary-12.json
```

结构采集在提示词补强前进行；补强后用相同材料另做三例重放，未把旧输出改写成新结果。首段为总结请求口径，搜索另计；冷热未控制。原始输出、提示词重放与人工审读分别保存。

未验证：GitHub 托管、正式 Chrome 手动加载/原生书签互迁、Android 真机安装/系统分享、新注册正常域名误报率、跨 worker/真实 RDAP 限流、全量事实准确率。缺口见 §6，建议按 §7 执行。

## 5 关键决策

见决策 M17：保留 30 天/0.15 及默认模型；新增共享并发只在同应用事件循环生效；结构与事实两个口径分别验收。模拟、本地远端或老站样本不替代原验收条件。未改公开 API。

## 6 遗留与风险

- 托管 CI 需明确目标仓库、Actions 权限、当轮提交/推送授权及相同 SHA 的成功运行链接。本轮只验证当前工作区，不重跑 DSH 所称干净 clone 的 act。
- 正式 Chrome 开发者模式、原生浏览器管理器往返及 Android 真机仍需目标环境；CfT/Pixel 证据不能代替。
- 新增 30 个域名仍为老站，需至少 5 个有出处并人工核验的 <30 天正常对照；当前门槛故意保持未过。
- 本机 full 首段中位 24.14s，六次均部分抓取。未完成冷/热或成本对照，不能把原因直接归为冷启动或 CPU，也未擅自改默认模型。
- 三例事实审读仍有两例需改写；提示词未证明整体准确率提升。下一轮需一手来源、逐事实标注、重复/盲评，不把引用合法等同正确。
- 限额不跨 worker，真实服务限速与配额还需观察。40 条弱域名标签也不能代替完整检索相关性评测。

## 7 交接

优先固定一手材料建立 Rust/HTTP2 等误导反例与逐事实标注，同时补有出处的新站对照；取得目标仓库与真实设备后再完成托管 CI/正式浏览器/Android。当前原目标仍部分完成。

- [进度与验收条件](../../docs/进展与欠账.md)
- [内容人工审读](../assets/next-action-review/manual-quality.md)
- [自动验收重验](../assets/next-action-review/summary-12-reassessed.json)
- [新站门槛](../assets/next-action-review/rdap-controls.json)
- [本轮核对证据](../assets/next-action-review/validation.json)

隔离服务仅使用 `data/next-review-*.db` 与独立 token。正式服务本轮前后书签数均为 2；临时测试书签已清理为 0，见 cleanup.json。本轮端口 18160/18161 已确认停止；原 8000 健康、Ollama 返回 200。
