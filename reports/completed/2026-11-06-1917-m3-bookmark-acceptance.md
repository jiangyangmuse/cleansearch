# 完工报告 · M3 书签启动台验收与优化

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-1917 |
| 开始 | 2026-11-06 19:17 |
| 结束 | 2026-11-06 19:18 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

**目标**

验收 M3 一键收藏、分组、搜索和 Netscape HTML 互迁，修复影响大量导入和目录保留的问题。

**验收标准**

- 导入、导出、再导入后保留 URL、标题、嵌套路径和根目录书签。重复导入仍跳过。
- 超过首屏的书签可以翻页，中文标题和网址可用子串查找，旧库分组保留。
- 全量 API 测试、前端构建、固定样本冒烟和浏览器关键操作通过。

**不做**

- 本轮范围为 M3，使用独立临时数据库和合成书签。

## 2 做了什么

1. 导入保存完整目录路径并区分同名子目录。启动台显示路径，导出恢复嵌套目录，未分组书签留在根目录。给旧库自动补列，保留原书签和分组。
2. 单次导入只提交一笔 SQLite 事务，写入失败时书签和分组一起回滚。将书签 I/O 放入工作线程。修复带标签收藏重复获取锁的问题。
3. 列表新增分页和匹配总数，补充中文标题和网址的字面子串匹配。搜索与翻页取消过时请求，筛选空态明确提示没有匹配项。
4. 导入支持空书签文件，限制读取大小并拒绝无效编码与格式。冒烟以只读方式检查分页上限。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/api/app/core/netscape.py` | 保存完整目录路径，导出嵌套目录和根书签 |
| `apps/api/app/db/schema.sql`、`apps/api/app/db/repo.py` | 旧库补列、批量事务、带标签保存、总数和子串查询 |
| `apps/api/app/routers/bookmarks.py` | 分页参数、导入边界校验、书签 I/O 在工作线程执行 |
| `apps/web/src/BookmarkPage.tsx`、`api.ts`、`styles.css` | 书签分页、搜索状态与导入反馈 |
| `apps/api/tests/test_bookmarks.py`、`scripts/smoke.ps1` | 旧库、嵌套、分页、标签和回滚回归，以及只读冒烟 |
| `README.md`、`docs/决策与接口变更.md` | 行为及接口变更 |
| `reports/2026-11-06-1917-m3-bookmark-acceptance.md`、`reports/INDEX.md` | 本次验收与台账 |

## 4 验证与证据

| 命令或操作 | 结果 | 关键输出 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `169 passed in 0.85s`。覆盖旧库迁移、同名子目录、根目录、分页、标签和部分失败回滚 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 转换 38 个模块，761 ms |
| `DB_PATH` 指向独立临时数据库，`LLM_PROVIDER=stub`，运行 `.\scripts\serve.ps1 -Provider fixture -Port 18092 -SkipBuild` | 通过 | 回环端口 18092 的隔离服务启动 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18092` | 通过 | 13/13，书签 `total=53 returned=1 groups=2 fts=True`，HTML 导出 5325 字节 |
| PowerShell 将 Python 探针通过 `@'…'@ \| python -` 执行，对 `BookmarkRepo.import_netscape` 使用同一批 2,500 条合成数据 | 通过 | 修改前 1408 ms、同名目录合并、子串无结果、根目录往返后进组，标签线程 1 秒后仍阻塞。最终版 92 ms，两个目录分开、子串命中、根目录仍未分组、最后一条可分页取得、标签写入不阻塞 |
| 同一 Python 探针在独立库导入 20,000 条并调用 `export_netscape()` | 通过 | 导入 809 ms，`created=20000`、末页总数 20000、导出链接数 20000。计时为本机合成样本单次观测 |
| `httpx` 探针上传合成 Chromium 结构到 `POST /api/bookmarks/import`，读取 `GET /api/bookmarks?limit=48&offset=48` 和 `GET /api/bookmarks/export`，导出再导入空库 | 通过 | 首次 53 新增、2 分组；重导 53 跳过、0 新增；两页 48/5，总数 53 且 ID 无交集；53 条的 URL、标题、目录路径往返一致 |
| 内置浏览器打开隔离实例，进入书签页、翻到下一页、搜「分析」，再从搜索结果收藏并删除一条 | 通过 | 第二页显示 49–53 条；子串只命中「数据分析手册」；收藏后总数 54、删除后恢复 53 |

证据记录为终端输出和浏览器无障碍树摘要。验收实例已停止。格式依据使用 Chromium 的嵌套目录与根目录测试样本结构，未读取实际用户书签。[Chromium 导入测试](https://chromium.googlesource.com/chromium/src/+/05e041164f5f27e92d2358dea1e4dfadb5ea2df5/components/user_data_importer/content/stable_portability_data_importer_unittest.cc)

## 5 关键决策

| 决策 | 依据 |
| --- | --- |
| 保留现有扁平分组界面，独立保存浏览器目录路径 | 可以区分同名子目录并导出原层级，同时兼容旧分组 ID 和原有 API 结构 |
| 分页保留默认每页上限 200，`total` 返回匹配总数 | 兼容已有默认请求，页面可到达全部匹配结果 |
| 导入与标签保存各自使用一次写事务 | 去掉逐条提交开销，保证失败回滚、重复操作不会留下半份数据 |

## 6 遗留与风险

- 本轮通过 Chromium 格式的合成书签往返，未在 Chrome 或 Edge 的原生书签管理器里做双向导入导出。
- 已被旧版导入合并的父目录无法从旧库推回。补列会原样保留旧分组，重新导入仍按现有重复跳过规则执行。
- 空目录没有对应书签时依照原约定不建分组。导入保持 20 MB 上限，请求在导入完成后才返回。

## 7 交接

在项目根目录运行 `.\scripts\serve.ps1 -Provider fixture`，进入 `/bookmarks` 即可使用分页和子串搜索。需要验证原生书签管理器兼容性时，用独立浏览器配置准备包含同名子目录及根书签的测试文件，再通过启动台导入、导出和回灌。

- `docs/决策与接口变更.md` 的「M3 验收修正」记录分页及路径语义。
- `apps/api/tests/test_bookmarks.py` 包含目录往返、旧库迁移和批量事务回归。
