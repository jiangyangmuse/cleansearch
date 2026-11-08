# 完工报告 · 品牌导航入口误去重复现与修复

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1138 |
| 开始 | 2026-11-08 11:38 |
| 结束 | 2026-11-08 11:44 |
| 耗时 | 7 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

用户反馈搜索 `deepseek` 有两条正确的强相关结果，但没有发现官网 `https://www.deepseek.com/` 的网页入口。核查可导致入口丢失的环节，修复误去重并验证页面可见。

验收：同名官网/聊天/参考页不互相吞并；相同 URL 变体和正文同稿去重仍正常；旧误删缓存不复用；完整回归与发布形态冒烟通过。

不做：不硬编码 DeepSeek 返回项、不推造上游没有返回的 URL、不调整打分权重、不更改并发 M19 引擎逻辑，不提交/推送 Git。

## 2 做了什么

1. 读取台账、决策与跨客户端交接，确认开工无未提交文件；本轮随后检测到并发 M19 引擎目录/回退/UI 改动，单独记录而未覆盖。
2. 原 8000/5173/8888 服务与 Docker 引擎未运行，无法直接取到用户原“两条强相关”的请求快照。本轮未把不同环境的结果冒充原现场复现。
3. 实际调用已有 Serper 查询 `deepseek`，得到 9 条公开候选。旧标题去重仅保留 7 条：`DeepSeek` 与 `deepseek-ai (DeepSeek)` 指纹相同，聊天页与维基被误合并。该批官网 `/en/` 原本已在候选中；根首页被同名参考页消掉的情况另以排序回放精确复现。
4. 入口页（根路径、语言首页、常见 index）不参与跨 URL 标题合并；不足 4 个不同词元的短标题也不作同稿证据。canonical URL 去重与正文型长标题 simhash 合并保留，安全过滤顺序保持。
5. 搜索缓存迁移到 `search-v5`，不复用旧策略保存的缺入口结果，不清空正式数据库。
6. 新增 11 个回归，覆盖输入顺序、品牌/通用短标题、长标题入口、文章同稿、URL 参数变体、来源/ID 与端到端入口保留、旧缓存隔离。
7. 真实 9 候选重放恢复为 9 条，官网 `/en/` 与聊天页均保留。隔离实际 API 冷/热查询保留官网，浏览器页面确认链接可见。

## 3 改动清单

| 路径 | 改动 |
| --- | --- |
| `apps/api/app/core/normalize.py` | 缩小标题 simhash 的适用范围，保留独立导航目的地 |
| `apps/api/app/db/cache.py` | `search-v4` → `search-v5` |
| `apps/api/tests/test_navigation_dedupe.py` | 11 项误去重及缓存回归 |
| `docs/决策与接口变更.md` | NAV-D1…D4，保留并发 M19 决策 |
| `docs/进展与欠账.md` | 本次实测边界、重启生效条件与报告入口 |
| `reports/assets/navigation-search/` | 真实候选、处理前后/冷热证据、截图、JUnit、冒烟及作用域核对 |
| 本报告与 `reports/INDEX.md` | 按协议记录、完成归档；历史行保持 |

## 4 验证与证据

| 命令原文 / 操作 | 结果与输出摘要 |
| --- | --- |
| 本机 8000/5173/8888 健康读取、`docker compose ps --format json` | 无活动 API/搜索端口；Docker daemon 管道不存在。原用户现场未复现。 |
| Serper `/search`，公开 `q=deepseek,num=10,page=1`；重放旧解析与去重 | HTTP 200，9 候选 → 7；聊天与维基被误合并，见 serper-before.json、before-stages.json。未保存请求头/密钥。 |
| `python -m pytest apps/api/tests/test_navigation_dedupe.py -q -o addopts= --tb=short`（修复前） | 1；9 failed、2 passed，端到端只剩参考页，官网/聊天被删除；旧缓存键相同 |
| 同上命令（修复后） | 0；11 passed in 0.05s |
| `python -m pytest apps/api -q --junitxml=reports/assets/navigation-search/api-tests.xml`（共享工作区初跑） | 1；346 passed、1 failed。失败是并发 M19 新增目录尚缺 360search，非本次去重逻辑；未修改该目录。 |
| `git archive --format=zip --output=data/navigation-baseline.zip HEAD`，仅覆盖本补丁 3 文件 | 0；隔离基线 5af2dafaabff87480b283c40010a7baaed84ed99，补丁哈希与当前工作区相同 |
| 隔离目录中 `python -m pytest apps/api -q -o addopts= --junitxml=D:\agent\llq\reports\assets\navigation-search\isolated-api-tests.xml` | 0；334 passed in 9.16s，无并发引擎代码混入 |
| 并发目录补齐后 `python -m pytest apps/api -q -o addopts= --junitxml=reports/assets/navigation-search/merged-api-tests.xml` | 0；当前合并工作区 347 passed in 9.07s |
| `npm --prefix apps/web run build`（最终共享版本） | 0；TypeScript 通过，43 modules，Vite 构建成功；包含并发 M19 的前端组件 |
| 保存的真实候选按当前函数重放 | 0；9 → 9，标题删除 0；官网 `/en/`、聊天与参考页都保留，见 after-stages.json |
| `18171` 独立真实 API 查询 `deepseek` 两次 | HTTP 200；6 个上游候选全部返回，filtered dup/risk 均 0；首次 cached=false、再次 true，均含官网 `/en/`。该次上游候选不含聊天页，未补造。 |
| `node reports/assets/navigation-search/verify-browser.cjs` | 0；Chrome 156 浏览器确认官网 `/en/` 链接 visible=true，见 browser.json、after-ui.png |
| 隔离基线补丁发布形态，`.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18170` | 0；16/16，保持 fixture 三档 3/6/1、URL 去重与风险过滤 |
| `python scripts/ci-smoke.py http://127.0.0.1:18170` | 0；15/15，冒烟通过 |

Python 测试 TEMP/TMP 使用工作区隔离目录。两次真实数据的候选数分别为 9 与 6，未把动态上游变化算成去重收益；9→7→9 的对照使用同一保存响应。

尝试以现有本机 SearXNG 在独立端口启动，进程退出且未成功监听，因此真实 API 验收走已配置 Serper 故障兜底（meta 如实标记 SearXNG unavailable）。未验证 SearXNG 与 Serper 同时可用时原用户的完整召回；没有将此写成通过。

## 5 关键决策

NAV-D1…D4 覆盖 M1-D7 的标题合并适用范围：标题相似不能证明独立入口相同。入口/短标题优先保留召回，URL 真重复仍合并，长标题文章规则保留。缓存升级仅影响搜索派生数据。公开 API、评分阈值与权威名单不变。

DeepSeek 官网确有网页版链接，入口属于 `chat.deepseek.com`；本轮不增加运行时品牌白名单或拼接根链接。[官网](https://www.deepseek.com/)

## 6 遗留与风险

- 本轮验证可导致该现象的误合并缺陷；用户原服务未启动，原“两条强相关”的完整上游/缓存快照未取到。
- 只保留实际召回项：若某次上游没返回某入口，聚合器不保证凭品牌补出它。单引擎官网可能仍归入“相关”，本次没有硬改强相关分数。
- 保留更多同名入口可能增加条数，属于此次修复的预期取舍。未对所有品牌/语言做系统召回评测。
- 并发 M19 改动由另一执行体处理；本轮保留其所有文件和报告，最终合并回归已通过，不据此认定其真实引擎验收范围。
- 源码已改，用户所用 API 进程需重启；Docker 运行时需重建 API 镜像。本轮未提交/推送，也未替换正式数据库或启动正式 8000 服务。

## 7 交接

以实际使用的方式重启 API（Docker 则重建 API 镜像），重新搜索 deepseek，核对官网/聊天与参考页独立显示；需要发布时按协议取得当轮提交/推送授权。其它品牌入口漏召回应保留原始上游响应，再判断是否属于过滤、去重或上游缺项。

- [当前进展](../../docs/进展与欠账.md)
- [修复前同批候选](../assets/navigation-search/before-stages.json)
- [修复后同批候选](../assets/navigation-search/after-stages.json)
- [实际冷/热响应](../assets/navigation-search/live-after.json)
- [页面截图](../assets/navigation-search/after-ui.png)
- [回归与隔离作用域](../assets/navigation-search/verification-scope.json)

本轮仅测试 data/navigation-*.db 与独立 token。临时 18170/18171 在验证后关闭；启动失败的 18888 上游进程已退出。未改动原用户书签或模型配置。
