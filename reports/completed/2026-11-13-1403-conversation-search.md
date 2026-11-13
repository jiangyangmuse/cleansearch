# 完工报告 · AI 对话搜索与独立视图

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1403 |
| 开始 | 2026-11-13 14:03 |
| 结束 | 2026-11-13 14:07 |
| 耗时 | 4 分钟 |
| 执行者 | Codex |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

在翻译下新增 AI 对话搜索。侧栏提交后进入左侧独立 AI 视图，支持多种结果与追问。日常 AI 和 ds 保留搜索页面原有呈现。

## 2 做了什么

- 增加 AI 视图和侧栏输入。提交侧栏需求自动切换，视图内可继续追问或开启新对话，切回首页再返回可查看原轮次。
- 新接口先由已配置模型拆成 1–3 个方向，再按当前引擎设置查询免费上游。每组最多五条实际网页，按方向显示查询词并跨组去重。
- 沿用 AI 检索模型与备选权限。过滤不安全结果，部分方向失败时展示其他成功结果。
- 恢复已存在的本机 Docker SearXNG 和原生 8000。保留原数据与设置。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/api/app/core/conversation_search.py`、`routers/search.py` | 需求拆分、上下文、并行检索、过滤及分组 |
| `apps/web/src/App.tsx`、`api.ts`、`components/ConversationSearch.tsx`、`workspace.css` | 侧栏、AI 视图、对话状态和响应式布局 |
| `apps/api/tests/test_conversation_search.py`、`docs/决策与接口变更.md` | 回归及接口记录 |
| [验收证据](../assets/conversation-search/) | 浏览器脚本、屏幕截图、真实上游和部署记录 |

## 4 验证与证据

| 命令 | 输出 |
| --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 退出 0，462 passed in 9.37s |
| `node --test scripts/browser-check.test.cjs scripts/engine-query.test.cjs` | 退出 0，19 项通过 |
| `npm --prefix apps/web run build` | 退出 0，60 个模块，Vite 764ms |
| `pwsh -NoProfile -File scripts/smoke.ps1 -BaseUrl http://127.0.0.1:18187` | 退出 0，16/16 |
| `node reports/assets/conversation-search/verify-browser.cjs` | 退出 0，侧栏位置、自动切换、追问上下文、ds 与日常 AI、刷新隔离、新对话、320px 验收通过 |
| `docker desktop start --detach`、`Start-Process ... 'Docker Desktop.exe'`、`docker start cs-searxng` | CLI 首次未就绪，直接启动可用。Docker 引擎 29.9.2，SearXNG 目录 263 个 |
| `scripts/serve.ps1 -Provider searxng -SkipBuild` 与保留配置重启 | 日常 API 恢复，最终进程 23740，原配置、书签、令牌和 SearXNG 校验一致 |
| `node -` 日常真实 Chromium | HTTP 200，千问把 Python 官方入门教程和中文入门视频拆为两组，每组 5 条，浏览器异常 0 |
| `python -` 隔离真实 API 追问 | HTTP 200，「视频只要哔哩哔哩，再加练习」分别查询 B 站入门视频和练习题，均返回 5 条 |
| `git -c core.safecrlf=false diff --check` | 退出 0 |

[日常真实浏览器](../assets/conversation-search/live-browser.json) · [页面截图](../assets/conversation-search/live-browser.png) · [真实追问](../assets/conversation-search/followup.json) · [重启证据](../assets/conversation-search/restart.json)。

## 5 关键决策

对话独立于 AI 检索端点，模型只生成方向与关键词。每轮最多携带六条历史需求和对应方向。会话保存在当前页面内存。模型请求失败沿用已有备选逻辑，分方向的网页查询支持部分成功。

## 6 遗留与风险

- 实测一度因 SearXNG 未启动全部报 503，恢复后成功。小模型首轮曾把追问里两个方向混成一个，补充提示后复测拆开。更复杂意图与每条网页的匹配度仍受模型和上游影响。
- 刷新页面会清空对话。隔离验收服务已停止。

## 7 交接

打开 [AI 对话搜索](http://127.0.0.1:8000/?category=conversation) 或从翻译下方提交需求。AI 检索所用模型在设置里分配。

