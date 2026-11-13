# 完工报告 · 免费检索官网召回与品牌误导结果修复

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1708 |
| 开始 | 2026-11-08 17:08 |
| 结束 | 2026-11-08 17:28 |
| 耗时 | 21 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

目标：复现指定 Bing 时官方入口缺失、正常资料掉弱相关及未核验品牌首页靠前的问题，降低日常对 Serper 的依赖。
验收：免费路线可用，官网与目录来源明确、身份提示保守，正常免费检索不付费；回归/冒烟/真实页面及日常部署通过。
不做：不宣称所有未核验站点为钓鱼站，不访问这些站点做恶意检测，不重写搜索引擎索引，不提交推送或更换部署/数据。

开工读取台账最近三份、决策与共享交接。上一轮官方入口与千问已部署到原生 8000，但仅识别上游实际返回的少量入口，日常数据库/令牌保持原值。

## 2 做了什么

### 原因与复现

1. 原日常 `deepseek !b`：上游9条、official=0，平台页 https://www.deepseek.com/en/platform/ 未入表；Hugging Face 的 DeepSeek-V4 资料因复合词不命中而只有0.1，落弱相关。官网首页根本没在本批Bing候选中，排序不能补出它。
2. 直接免费 Bing 查询 `deepseek 官网` 返回多个自称官网/品牌近似域首页；没有把它们确认为恶意，也没有打开这些站点。按语言或 site: 限制的少量探测未稳定补回首页，不能据此保证同一引擎召回。
3. 默认聚合代码在免费首屏正常成功后仍调用商用源，这会持续消耗额度并掩盖免费结果的质量问题。

### 最终修复

- 默认付费改为真正故障兜底：免费成功、正常空态、部分引擎失败不调用付费；主链故障才遵守既有首屏、开关与熔断兜底。指定Bing继续无付费路由。
- 扩充DeepSeek平台/下载/官方仓库的精确路径，入口表46品牌/116条。首页、聊天等缺失角色可由表内声明补“目录直达”，origin=directory、空engine/摘要；上游入口为origin=search。只在已知品牌导航首屏补充，不扩展到教程、未知品牌或后续页。
- 目录不作为总结材料；未核验品牌首页也不作为总结来源。冷/热快照一致，无其他材料时前端禁用总结；纯目录不写搜索缓存。目录同样检查黑名单与风险，不推导未知URL。
- 首页标题命中品牌且自称官网，或主机包含品牌近似词但不匹配已核验入口时，标记brand_warning并限制分数≤0.29。显示“品牌身份未核验”；不增加恶意风险分、不自动写黑名单，普通第三方文章不受此规则泛化影响。
- 分词保留复合名同时拆出组成词，DeepSeek-V4/DeepSeek-ai正常命中deepseek；无关子串不命中。正常标题高覆盖率不再当成关键词堆砌，实际重复至少三次且占比超过一半才触发该信号。权重和绝对分档阈值不变。
- 缓存使用official-v4+完整目录摘要、engine-fallback-v3，隔离旧分档与付费混合缓存；search-v6不变，不清书签。

真实日常对照：Hugging Face条目由weak/0.1变为related/0.3543；平台页进入console搜索入口；首页由本批缺失变为明确目录直达。见 comparison.json。

## 3 改动清单

| 路径 | 内容 |
| --- | --- |
| apps/api/app/core/aggregator.py | 正常免费请求不追加付费 |
| apps/api/app/core/official.py | 目录补充、身份声明/近似域提示、核验路径、缓存目录摘要 |
| apps/api/app/core/scoring.py | 复合词与堆砌信号修正 |
| apps/api/app/schemas.py、routers/search.py | origin/directory/brand_warning，来源过滤、缓存、目录安全检查 |
| apps/api/tests/test_free_retrieval.py | 新增14项：付费计数、目录边界、身份与分词、冷热快照 |
| apps/api/tests/test_paid.py、test_cache.py | 适配真正故障兜底与缓存能力隔离，保留去重来源/熔断覆盖 |
| apps/api/tests/test_official.py、test_official_review.py、test_navigation_dedupe.py | 区分目录和搜索条目，保留原去重/引用验收 |
| apps/web/src/types.ts、App.tsx、components/OfficialPanel.tsx、ResultCard.tsx、MetaBar.tsx | 来源标签、警示、统计及无材料禁总结 |
| README.md、docs/决策与接口变更.md、docs/进展与欠账.md | FREE-D1～D6与现行计费/来源契约 |
| 本报告、reports/INDEX.md、reports/assets/bing-retrieval-review/ | 报告与原始候选、对照、浏览器、测试证据 |
| data/bing-retrieval-backup-20261108-1708/、日常原生进程 | 备份原库/令牌后592→22608；环境全部保留 |

未编辑既有breaker、engines、probe、SearXNG配置、db/cache.py、其他执行体报告或.env。前端dist为本地构建产物；原生8888和千问不重启；不改Docker卷。

## 4 验证与证据

Windows测试临时目录：`$env:TEMP=Join-Path $PWD 'data/review-temp'; $env:TMP=$env:TEMP`。隔离真实实例18177使用SearXNG8888，但PAID_FALLBACK=false且Serper/Brave key均清空、RDAP=false、stub总结；fixture18178使用原样固定样本。二者独立DB/token，未访问正式书签记录。

| 命令原文 | 真实输出摘要 |
| --- | --- |
| `POST http://127.0.0.1:8000/api/search {"q":"deepseek !b"}`（修复前） | official=0，9候选，HF=weak/0.1，平台页普通related；before-api.json |
| `GET http://127.0.0.1:8888/search?q=deepseek&engines=bing&format=json` 等少量变体 | 原始/zh-CN/导航/site限制各保存JSON；没有访问结果中的未核验主机 |
| `python -m pytest apps/api/tests/test_free_retrieval.py -q -o addopts= --tb=short`（修复前） | 7 failed/4 passed；Mock证明免费正常请求仍多一次Serper POST |
| `python -m pytest apps/api -q -o addopts= --tb=short --junitxml=reports/assets/bing-retrieval-review/api-tests.xml` | 最终 **441 passed in8.47s**，原427+新增14，退出0 |
| `npm --prefix apps/web run build` | tsc+Vite，46modules；JS268.54kB/gzip84.57kB，退出0 |
| `node --test scripts/browser-check.test.cjs scripts/engine-query.test.cjs` | 15 pass/0 fail，退出0 |
| `python reports/assets/bing-retrieval-review/serve-verify.py` | 免费硬关闭付费实例18177；最终进程19308，仅本轮隔离数据 |
| `python reports/assets/bing-retrieval-review/serve-verify.py --fixture` | 原始fixture18178；最终进程25936 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18178` | 最终16/16，三档3/6/1，缓存/引用/安全/书签/首页通过，退出0 |
| `python scripts/ci-smoke.py http://127.0.0.1:18178` | 最终15/15，退出0；控制台中文编码替换，布尔与数字可核对 |
| `node reports/assets/bing-retrieval-review/verify-free.cjs` | 付费关闭的真实Bing，6官方（3搜索/3目录）、engine=bing、缓存true、390px无溢出；最新导航查询未返回需警示候选，如实记录0 |
| 隔离18177 `POST /api/search {"q":"deepseek"}` | 免费默认74候选、6官方检索入口、0目录，无付费提供商；free-default.json |
| `python reports/assets/bing-retrieval-review/restart-native.py` | 592→22608，配置/原库/令牌/8888保留均true，缓存true；先备份，退出0 |
| `node reports/assets/bing-retrieval-review/verify-free.cjs http://127.0.0.1:8000` | 日常Bing6入口、3目录、缓存true；“deepseek 官网 !b”五条可见警示均weak；390px无溢出、无pageerror，退出0 |
| `python reports/assets/bing-retrieval-review/verify-daily.py` | 两个日常查询快照分别9和1来源，均排除目录/身份警示；原库/令牌/8888未变，qwen模型及本地端点保留，退出0 |
| `git -c core.safecrlf=false diff --check` | 退出0，无空白错误 |

第一轮完整回归有11失败（旧付费/目录契约断言、纯目录缓存及新增用例设置等），逐项修正实现或契约测试后全通过。视觉复查又发现一个不写“官网”但含品牌近似域的首页仍在related，补规则及回归后最终441通过。隔离浏览器曾因上游不再返回警示候选而失败；保存实际响应后确认是候选变化，脚本改为仅在候选出现时断言展示，不把0候选写成“警示已验证”。日常实测仍返回5条，警示与分档已实际验证。

证据：[资产目录](../assets/bing-retrieval-review/)：api-tests.xml、before-api.json、bing-*.json、comparison.json、after-api.json、isolated/daily-browser.json、*-navigation-after.json、free-default.json、before/restart/preservation.json、smoke-*.txt、isolated/daily-desktop/mobile.png。截图已人工检查。目录直达没有伪造engine，快照过滤已逐条比较；免费成功0付费调用由Mock计数证明，不凭响应估算真实账单。

### 核验来源

- [DeepSeek官网导航](https://www.deepseek.com/)、[英文平台页](https://www.deepseek.com/en/platform/)、[中文平台页](https://www.deepseek.com/platform/)：确认返回的官网产品路径与产品链接；
- [下载页](https://www.deepseek.com/download/)：指向download.deepseek.com；[研究页](https://www.deepseek.com/news/)指向deepseek-ai组织仓库；
- [SearXNG Bing适配器文档](https://docs.searxng.org/dev/engines/online/bing.html)：核对网页端适配与语言市场行为。本轮未改上游配置。

未验证：全部46品牌/116声明的当前网络可用性、未知站点是否恶意、完整全网召回、全部引擎长期可用性、模型事实质量、托管CI、正式Chrome/Android；本轮未调用Serper真实接口，也未新增模型调用。

## 5 关键决策

FREE-D1～D6已追加到决策文件。重要变化：覆盖旧默认“首屏补付费”的策略；扩展NAV-D4/OFFICIAL-D3，允许已声明且明确标来源的目录直达。搜索候选仍只用上游实际返回内容；目录不冒充召回。身份警示与恶意风险分独立，不把第三方教程/百科一律处罚。

## 6 遗留与风险

- Bing自身索引与结果排序仍会变化，局部规则无法保证清除全部仿站。目录只有46个已维护品牌，未知品牌仍依赖真实检索；近似域提示可能覆盖正常非官方品牌站，因此用“未核验”而非“钓鱼”。
- 目录地址有核验日期但不保证实时可用；没有搜索内容时只提供直达、不生成总结。当前弱相关容量仍为5，部分候选会按既有容量被截断，不算安全拦截。
- Serper/Brave仍可在已开启且免费链路真正故障时作为兜底，也保留既有显式Google/Scholar/Brave路由；未承诺完全不会发生任何付费请求。正常免费成功不再补付费。
- 保持原生DB data/review-temp/verify.db及令牌，备份位于data/bing-retrieval-backup-20261108-1708；书签三表前后摘要相同。没有合并Docker数据。
- 441测试与本轮冒烟为本地证据，未提交推送、未重跑托管CI。原Compose、全部引擎、正式浏览器/Android、模型事实质量欠账不抵扣。

## 7 交接

日常服务22608继续运行，可访问 http://127.0.0.1:8000/?q=deepseek%20!b 或搜索“deepseek 官网 !b”。首页直达标“目录直达”，相关第三方资料与弱相关身份提示分开。以后新增品牌或维护入口时保留核验来源、路径与日期，目录摘要会使缓存自然失配。

下一步日常试用，记录未覆盖的具体查询/URL再补召回与判定样本；不要以扩大Serper使用量掩盖免费质量问题，也不要仅凭域名陌生就加入黑名单。临时18177/18178验收服务关闭，日常8000/8888/千问保持运行。