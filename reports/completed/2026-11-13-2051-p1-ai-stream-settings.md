# 完工报告 · P1 AI 流控制与设置页增强

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2051 |
| 开始 | 2026-11-13 20:51 |
| 结束 | 2026-11-13 20:52 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) `6 落地 P1 第 13、14 条：AI 工具面板收起后明确「后台生成中」并提供停止；设置页补引擎筛选/状态说明/刷新状态、模型测试连接、数据管理（库路径、清历史、导出设置）。

**验收标准**

- 收起总结面板后出现「AI 总结正在后台生成 · 查看 / 停止」，点停止后提示与流都结束。
- AI 检索进行中收起面板同样有提示，停止后提示消失。
- 引擎列表可按名称/后缀筛选，空结果给提示；「刷新状态」把可用/冷却/未知贴到引擎并汇总。
- 模型「测试连接」显示可用（N 个模型）或失败原因。
- 数据管理显示 `.db` 路径与书签数；导出下载 `cleansearch-settings.json`；清空历史写入 `[]`。
- 既有 192 项断言不回归；pytest 与前端构建通过。

**不做**

- P1 第 15 条（旧页面移动端）与 P2 全部内容。
- 不导出模型密钥：导出文件只含主题/日常 AI/引擎偏好/本机信息/历史词。

## 2 做了什么

1. **流状态上报**：`SummaryPanel` 新增 `onBusyChange`，把 `streaming` 传给 `App`；卸载时回传 false。新增 `cs:summary-stop` 事件，供面板外的停止按钮收口。
2. **后台任务条**：`App` 在结果区顶部渲染 `.background-task`（圆点 + 文案 + 查看 / 停止）；总结或 AI 检索在跑且对应面板收起时出现。停止总结派发事件，停止 AI 检索直接 abort `aiController`。
3. **后端**：`POST /api/settings/models/test` 请求 `{base_url}/models`（Bearer key、6s 超时、零 token），未知 id 404，连接/HTTP 错误返回 `ok:false`；`/api/health` 增加 `db_path`。新增 2 个用例（未知 id 与连接失败、401 映射）。
4. **设置页**：重写 `SettingsPage`，新增「数据管理」卡（库路径、书签数、版本、历史条数、导出设置、清空历史、管理书签）。
5. **引擎设置**：筛选输入 + 「刷新状态」+ 状态说明；每个引擎显示可用/冷却 N 分/未知。
6. **模型设置**：每个模型加「测试连接」按钮与结果提示。
7. **验收脚本**：新增 20 项断言（流控制 5、设置页 8，其余为随页面结构更新的选择器）。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/routers/ai_tools.py` | 修改 | `POST /api/settings/models/test` |
| `apps/api/app/schemas.py`、`apps/api/app/main.py` | 修改 | Health 暴露 `db_path` |
| `apps/api/tests/test_model_tools.py`、`test_search.py` | 修改 | 新接口与 health 字段用例 |
| `apps/web/src/components/SummaryPanel.tsx` | 修改 | `onBusyChange`、`cs:summary-stop` |
| `apps/web/src/App.tsx` | 修改 | 后台任务条、停止逻辑 |
| `apps/web/src/api.ts` | 修改 | `readHealth`、`testModelConnection` |
| `apps/web/src/SettingsPage.tsx` | 重写 | 数据管理卡 |
| `apps/web/src/components/EngineSettingsPanel.tsx` | 修改 | 筛选、刷新状态、状态标签 |
| `apps/web/src/components/ModelSettingsPanel.tsx` | 修改 | 测试连接 |
| `apps/web/src/styles.css`、`workspace.css` | 修改 | 后台任务条、设置页动作区、状态标签 |
| `scripts/audit-ui.cjs` | 修改 | 新增 20 项（共 200 项） |
| `reports/assets/ui-p1/` | 修改 | 设置页与后台任务截图、最新审计 JSON |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md` | 修改 | 新接口与交互口径 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18192 --out reports/assets/ui-p1` | 通过 | `ALL PASS (200)`：后台生成提示、停止后清空、AI 检索提示、引擎筛选 20→0、刷新状态「可用 16 · 冷却 0 · 未知 4」、模型测试「可用（3 个模型）」、`.db` 路径、导出文件名、清空历史写 `[]` |
| `npm --prefix apps/web run build` | 通过 | 70 modules，JS 336.13 kB，CSS 55.26 kB |
| `python -m pytest apps/api -q` | 通过 | 468 项（465 + 新 3），`[100%]` 无 F/E |
| 环境 | — | 验收用独立 `serve.ps1 -Provider fixture -Port 18192`，验完已停 |

**证据文件**

- 审计结果：`reports/assets/ui-p1/p0-ui-audit.json`
- 截图：`desktop-settings-data.png`（引擎状态 + 数据管理）、`desktop-background-task.png`（后台生成提示）

**未验证**

- 真实 Ollama/DeepSeek 的「测试连接」只跑了 MockTransport 与固定样本；真实网络与错误码（401/404/超时）待手工确认。
- 后台任务条在移动端抽屉关闭时的位置未单独截图；读屏朗读未实机验证。
- 导出设置里的引擎偏好来自当前服务端，若接口失败则该字段为 null（不阻塞下载）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 总结关闭面板不 abort，改为提示 | 直接 abort 流 | 用户常是“先看结果再回来看总结”，直接掐断会浪费已生成内容 |
| 停止走自定义事件 | App 直接持有 SummaryPanel ref | 组件在隐藏面板里，事件比 ref 穿透更简单，也和既有 `cs:summarize` 对称 |
| 模型测试请求 `/models` | 发一次 chat 请求 | `/models` 不耗 token、快；只看连通与鉴权，不验推理质量 |
| 导出不含密钥 | 导出完整配置 | 密钥只在服务端；导出物可能被分享，不能带凭证 |
| 刷新状态手动触发 | 每次进设置页自动请求 | 自动请求会打上游；显式点击更可控 |

## 6 遗留与风险

- 后台提示只反映 `streaming` 状态；流结束即消失，没有“已完成未读”提示。
- 模型测试每个模型一次串行请求，20 个模型时手点成本高（未做“全部测试”）。
- 引擎状态来自进程内熔断器，重启后归零；刷新结果不代表上游长期状态。
- 导出设置包含搜索历史原文，属于个人数据，已在按钮旁标注文件名，未加密。

## 7 交接

**下一个人第一件事**

P1 只剩第 15 条（旧页面移动端：书签页工具栏分行、添加表单折叠、卡片操作不挤压标题、单页总结空态示例 URL）。做完后按方案 `8 进入 P2（SW/OpenSearch/manifest/扩展/分享/性能/设计系统）。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（`6 第 13、14 条已标注完成）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P1 AI 工具流控制与设置页增强）
- 实现：`apps/api/app/routers/ai_tools.py`、`apps/web/src/SettingsPage.tsx`、`apps/web/src/App.tsx`
- 验收：`scripts/audit-ui.cjs`、`reports/assets/ui-p1/`