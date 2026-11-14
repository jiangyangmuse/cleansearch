# 完工报告 · P2：检索与正文质量评估与实现

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1108 |
| 开始 | 2026-11-07 11:08 |
| 结束 | 2026-11-07 11:08 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

1) 用有标注的真实查询评估词典扩展的收益；2) 补可选正文提取器、JS 页面验证、原文锚点与 key_data；3) 在语义分 / LLM 重排 / 商用兜底之间给出有数据支撑的取舍。

**验收标准**

- 标注集与评估脚本可复现，输出 baseline/rank/rewrite 三组指标。
- trafilatura 与标准库在真实页面上有对比数据，容器内实际生效。
- 单页总结返回 key_data 与 anchors，并在真实页面验证非空。
- SPA 页面的行为有实证记录。
- 三项技术路线各有一句结论 + 依据。

**不做**

- 接入 Brave/Serper（无 key）、引入 embedding 服务、Playwright 渲染兜底。

## 2 做了什么

1. 建 18 条标注查询（query + 期望域名，含常见中文来源），写 scripts/eval-expansion.py：同一候选集下对比 baseline / rank / rewrite 三种条件。
2. 评估结果：Top10 命中 6/12 → 8/12 → 9/12，强相关 1/12 → 1/12 → 2/12，首个命中位次 1.33 → 3.62 → 3.67。
3. 据此把扩展做成三态 EXPANSION_MODE（off/rank/rewrite），默认 rank；rewrite 会把前两个别名并入上游查询。
4. 安装 trafilatura（可选依赖 [content]），写对比脚本：docs.python.org 2174 vs 2236 字、MDN 1698 vs 1487 字、纯 JS 页面 0 vs 0 字。
5. Dockerfile 改为 pip install ".[content]"，容器内 extractor=trafilatura 已确认。
6. 单页总结新增 key_data（从原文抽数字+单位，最多 8 条）与 anchors（段落序号+首句，最多 5 条）；前端加「关键数据」「原文锚点」两段。
7. 发现并修复：单页总结 2.5s 超时导致 MDN 504，改为单页专用 10s 预算；MDN 实测 7396 字、key_data=5（604800 秒等）、anchors=5。
8. SPA 验证：web.telegram.org/k/ 两种提取器都 0 字，接口返回 422「正文过短或需要登录」。
9. 技术路线取舍写入 README 与决策 M12-D1…D6。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [apps/api/app/core/expand.py](../../apps/api/app/core/expand.py) | 修改 | 新增 upstream_query 与 MODES |
| [apps/api/app/config.py](../../apps/api/app/config.py) | 修改 | EXPANSION_MODE |
| [apps/api/app/routers/search.py](../../apps/api/app/routers/search.py) | 修改 | 按模式决定别名与上游查询 |
| [apps/api/app/routers/page.py](../../apps/api/app/routers/page.py) | 修改 | key_data、anchors、单页 10s 抓取预算 |
| [apps/api/pyproject.toml](../../apps/api/pyproject.toml)、[apps/api/Dockerfile](../../apps/api/Dockerfile) | 修改 | 可选依赖 [content] 与镜像安装 |
| [apps/api/tests/test_content.py](../../apps/api/tests/test_content.py) | 修改 | key_data/anchors 用例；固定 trafilatura 用例走回退 |
| [apps/api/tests/regression/p2_labeled_queries.json](../../apps/api/tests/regression/p2_labeled_queries.json) | 新增 | 18 条标注查询 |
| [scripts/eval-expansion.py](../../scripts/eval-expansion.py) | 新增 | 三种条件对比评估 |
| [apps/web/src/PageSummaryPage.tsx](../../apps/web/src/PageSummaryPage.tsx)、[api.ts](../../apps/web/src/api.ts)、[styles.css](../../apps/web/src/styles.css) | 修改 | 关键数据与锚点渲染 |
| [README.md](../../README.md)、[docs/决策与接口变更.md](../../docs/决策与接口变更.md)、[docs/进展与欠账.md](../../docs/进展与欠账.md) | 修改 | P2 数据、决策 M12、状态 |
| 本报告与 [INDEX.md](../INDEX.md) | 新增/更新 | 登记 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| python scripts/eval-expansion.py --base-url http://127.0.0.1:8000 | 通过 | baseline 6/12、rank 8/12、rewrite 9/12；强相关 1/1/2；位次 1.33/3.62/3.67 |
| 提取器对比脚本（docs/m10-evidence/p2-extractors.json） | 通过 | asyncio 2174 vs 2236；MDN 1698 vs 1487；telegram 0 vs 0 |
| docker compose exec api python -c 'import trafilatura' | 通过 | 2.3.1；page summarize 返回 extractor=trafilatura |
| POST /api/page/summarize（MDN 缓存页） | 通过 | 7396 字、key_data=5、anchors=5（604800 秒等） |
| POST /api/page/summarize（web.telegram.org） | 预期失败 | 422「正文过短或需要登录」 |
| python -m pytest apps/api -q -o addopts= | 通过 | 270 passed |
| npm --prefix apps/web run build | 通过 | 42 modules |

未验证：语义分与 LLM 重排（本轮结论是暂不引入）；商用兜底（无 key）；更多标注查询（当前 18 条，样本偏小）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 扩展默认用 rank，rewrite 可选 | 直接默认 rewrite | rewrite 多一次上游请求、位次从 1.33 掉到 3.67；默认不该牺牲响应速度 |
| 语义分/LLM 重排暂不引入 | 先上 embedding/重排 | 无本地向量服务；千问首字 6.8–10.9s，重排会拖到 10s+ |
| 商用兜底排最前 | 继续调排序 | 真实查询每次 2–3 个引擎失败，可用性才是当前瓶颈 |
| key_data 从原文抽 | 让模型输出 JSON | 模型会编数字；原文抽取可核对 |
| 单页总结 10s、full 保持短超时 | 全局调大 | 单页是用户主动等待；full 是首屏预算 |

## 6 遗留与风险

- 标注集只有 18 条，且「期望域名」是人工挑的宽口径，结论只能看趋势。
- rewrite 依赖上游对长查询的处理，不同引擎表现可能不同，未做多引擎对比。
- key_data 是启发式正则，英文单位（seconds/percent）没覆盖，中文页面更有效。
- anchors 只是段落序号，不跳转；要做 DOM 锚点需要保存并渲染原文。
- SPA 页面仍返回 422；Playwright 兜底未做（会显著增加镜像与延迟）。
- 语义分/重排/兜底都只是「暂不引入」，不是永远不做。

## 7 交接

**下一个人第一件事**

拿到 Brave 或 Serper key 后接商用兜底，用同一套 18 条标注集复测 Top10 命中与延迟，对比「兜底 + 现有排序」与「rewrite 扩展」的收益差。

**相关文件**

- [README P2 章节](../../README.md)
- [决策 M12-D1…D6](../../docs/决策与接口变更.md)
- [评估脚本](../../scripts/eval-expansion.py)、[标注集](../../apps/api/tests/regression/p2_labeled_queries.json)
- [提取器对比数据](../../docs/m10-evidence/p2-extractors.json)

---

> 注：头部「耗时」由 `close-report.ps1` 按报告起草时间计算；本轮实际约 40 分钟。
