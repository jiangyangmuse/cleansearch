# 完工报告 · M7 缓存与交互验收优化

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-2148 |
| 开始 | 2026-11-06 21:48 |
| 结束 | 2026-11-06 21:49 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

**目标**

独立验收 M7 的搜索与单页总结缓存、键盘操作、三态主题和移动端抽屉。

**验收标准**

- 重复搜索仍能命中并生成总结。新增黑名单规则后旧缓存立即失配，更新后的引用不含被拦截结果。
- 单页总结只在实际模型输入一致时复用。请求地址及页面信息保持正确，缓存失败不阻断请求。
- 键盘操作不抢占焦点控件，主题跨页面一致，窄屏抽屉的打开、收起及焦点行为正确。

**不做**

- 本轮仅修复已有缓存、快捷键、主题和移动端交互。运行验证使用独立临时库及黑名单副本。

## 2 做了什么

1. 搜索缓存按检索后端、上游地址和当前黑名单版本分开。部分引擎失败的结果不写入缓存，命中仍登记新总结快照。
2. 单页缓存按正文、最终地址、标题、正文上限及模型配置分开，只保存模型生成文本。响应地址和元信息始终取本次抓取。
3. 两张缓存表独立限量，默认 512 条，按写入顺序淘汰。读写移到工作线程，SQLite 忙时按未命中继续，关闭时不打开缓存连接。
4. 快捷键复用现有卡片链接和收藏按钮，控件的 Enter 行为保持独立，查询切换清空选择。抽屉收起时从焦点顺序移除，Esc 还原焦点。三页都能切换主题。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/api/app/core/safety.py` | 黑名单内容指纹；读取失败保留已载入规则 |
| `apps/api/app/db/cache.py`、`apps/api/app/config.py` | 版本化键、容量、忙时降级和缓存开关 |
| `apps/api/app/routers/search.py`、`apps/api/app/routers/page.py` | 搜索隔离、快照重建、单页响应与缓存内容分离 |
| `apps/api/tests/test_cache.py` | 规则热更新、后端隔离、容量、SQLite 忙和单页缓存回归 |
| `apps/web/src/App.tsx`、`apps/web/src/components/ResultCard.tsx`、`apps/web/src/styles.css` | 快捷键选择、原生控件交互和抽屉焦点 |
| `apps/web/src/theme.ts`、`apps/web/src/BookmarkPage.tsx`、`apps/web/src/PageSummaryPage.tsx` | 主题持久化容错及三页一致入口 |
| `.env.example`、`README.md`、`docs/决策与接口变更.md` | 配置和行为说明 |
| `reports/2026-11-06-2148-m7-polish-acceptance.md`、`reports/INDEX.md` | 验收报告及登记 |

## 4 验证与证据

| 命令或操作 | 结果 | 关键输出 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `224 passed in 2.44s`，含 5 项新增回归 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 转换 41 个模块，741 ms |
| 设置独立 `DB_PATH`、黑名单副本、`CACHE_ENABLED=true`、`LLM_PROVIDER=stub` 与 `FETCH_EXTRA_CIDRS=198.18.0.0/15`，运行 `.\scripts\serve.ps1 -Provider fixture -Port 18096 -SkipBuild` | 通过 | 回环端口 18096 启动 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18096` | 通过 | 15/15，重复查询 `cached=True total=10`，摘要 SSE 161 片段，内网拦截 403 |
| 使用 `httpx` 重复 `POST /api/search` 的 `python 文档`，在临时黑名单副本追加 `fastapi.tiangolo.com` 后重复请求 | 通过 | 缓存状态 `True → False → True`，拦截 1、展示 9，刷新后两次 `sid` 不同；命中快照 SSE 正常结束，9 条引用都未包含被拦截的域名 |
| 同一临时库另启 `.\scripts\serve.ps1 -Provider fixture -Port 18097 -OllamaModel 'qwen3.5-4b-local:latest' -SkipBuild`，在两个端口分别重复 `POST /api/page/summarize` 请求 Python asyncio 文档 | 通过 | 桩与千问各自 `cached=false → true`。千问本机单次观测 15.9 秒 → 1.42 秒，生成 3 条要点。命中仍需重新抓页面，期间有一次 504，重试成功 |
| 内置浏览器桌面模式，选择固定样本，按 `j` 两次、`b`，分别对主题按钮和选中结果按 Enter | 通过 | 选中第二条，卡片显示已收藏；主题按钮的 Enter 未打开链接，选中卡片的 Enter 打开正确 asyncio 新标签；书签页显示已收藏项目 |
| 内置浏览器 390×844，执行 `s`、`Esc` 并恢复默认视口 | 通过 | 收起时不可见且无横向溢出，`s` 展开并开始总结，`Esc` 后关闭且焦点回到开关 |
| 浏览器刷新、打开书签和单页总结页；触发「上游不可用」并在搜索框输入字母 | 通过 | 三页保留深色，错误态显示 `UPSTREAM_UNAVAILABLE` / 503 和重试，输入框保留 `jb` |
| `curl.exe -sS --max-time 3 http://127.0.0.1:8888/healthz` | 真实上游未验证 | 退出码 7，连接被拒，未测真实引擎下的缓存时延 |

证据为上述终端输出、HTTP 断言和浏览器无障碍树摘要。两台临时实例均已停止。

## 5 关键决策

| 决策 | 依据 |
| --- | --- |
| 搜索继续缓存最终分档结果，按规则版本区分 | 维持命中时跳过重打分的收益，规则变更能作用到下一次查询 |
| 单页只缓存生成文本，分开计算本次页面元信息 | 即使不同入口重定向到同一正文，请求网址仍准确；更换模型、标题或输入上限会重新生成 |
| SQLite 缓存是可丢弃的数据 | 锁定或损坏时优先让业务继续；容量按最近写入控制，不为读命中增加写事务 |

## 6 遗留与风险

- 本机 SearXNG 未运行，搜索缓存验收用固定样本及受控契约用例，真实引擎收益待实测。
- 单页命中仍依赖网页可抓取。实网探针用了本机透明代理例外，耗时为本机单次观测。
- 新缓存键与旧键隔离。旧条目随过期和容量清理，书签数据未迁移。提示词或评分策略有不兼容修改时需同步更新对应缓存键版本。

## 7 交接

部署可用的 SearXNG 后，用 `scripts/verify-searxng.py` 确认可用引擎，再用相同查询比较 `meta.cached` 与端到端耗时。

- `docs/决策与接口变更.md` 记录 M7 验收修正和配置语义。
- `apps/api/tests/test_cache.py` 覆盖新缓存行为。
