# CleanSearch · 干净搜索聚合器

聚合多引擎检索 + 零广告结果页 + 三档相关性分组 + 侧栏 AI 总结 + 书签启动台。
本机搜索、书签、正文增强、缓存和一键添加已交付。默认真实搜索和本机千问总结已联通，指定引擎与容器部署仍待验收。[当前进展与待办](docs/进展与欠账.md) · [完工台账](reports/INDEX.md)

## M0 做了什么

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 同源前后端 | React + TS + Vite（`apps/web`）+ FastAPI（`apps/api`），发布时 FastAPI 托管 `dist` | ✅ |
| `POST /api/search` | JSON 请求体、结果归一化、URL 去重、契约字段齐全 | ✅ |
| 最小结果列表 | 标题 / 域名面包屑 / 摘要 / 引擎标签 / 序号，原站新标签打开 | ✅ |
| 三态可区分 | 有结果 `status=ok`、零结果 `status=empty`、上游不可用 `503 + error.code` | ✅ |
| 本机启动命令 | `scripts/serve.ps1`（发布形态）、`scripts/dev.ps1`（开发形态）、`scripts/smoke.ps1`（冒烟） | ✅ |
| 固定样本 | `apps/api/fixtures/searxng_hit.json` 等，无 Docker 也能稳定验收 | ✅ |
| 自动测试 | `apps/api/tests` 覆盖三态、去重、契约、同源托管、上游响应结构、外链白名单和 Compose 端口 | ✅ |

M1 增加了后缀路由、去重、打分与三档分组、已知恶意链接拦截。M2 增加了带引用的 AI 侧栏。

已知恶意链接由本地黑名单拦截。已支持刷新 OpenPhish 类无 key feed，可疑结果经签名 `/go` 确认。GSB / URLhaus 待接入。

### 上游响应与 URL 护栏（验收后收紧）

- SearXNG 响应必须是 JSON 对象且带 `results` 列表：缺失或类型错误一律 `UPSTREAM_BAD_RESPONSE`，既不静默当成零结果，也不会冒成 HTTP 500。
- `results` 非空但没有任何一条能解析出标题 + 合法链接时，同样判坏响应。
- 结果 URL 只放行具有明确主机和合法端口的 `http`/`https`，长度 ≤ 2048。含内嵌凭证、反斜杠、控制字符或百分号编码主机的链接在结果归一化时丢弃，前端渲染前再校验。
- Compose 的 SearXNG 端口只绑回环：`127.0.0.1:8888:8080`（limiter 已关，不能对外暴露）。


## M1 做了什么（当前）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 后缀 / bang 路由 | `apps/api/app/core/query_parser.py`；`数分知识点 g` → Google，`python !b` → Bing，`天气预报 zh` → 地区 cn | ✅ |
| 解析护栏 | 单字母前导（`C g`、`x b`）、引号内、未闭合引号、非末尾短码一律保持普通查询 | ✅ |
| URL 去重加强 | canonical URL + 64 位标题 simhash（汉明距离 ≤ 3），合并引擎列表 | ✅ |
| 已知恶意链接拦截 | `apps/api/app/core/safety.py` + `fixtures/blocklist.txt`，先拦截并计入 `meta.filtered.risk`，再去重和打分 | ✅ |
| 启发式风险分 | 可疑 TLD / IP 直连 / 深层子域 / 长随机串 / IDN / 形近字符；0.35 起标记「可疑」 | ✅ |
| 打分与三档分组 | 词法（BM25 饱和 + 查询词覆盖率）、引擎共识、权威域名、时效，负向扣风险与营销特征 | ✅ |
| 前端三档渲染 | 强相关 / 相关默认展开，弱相关折叠；可疑卡片带角标与悬停理由；元信息展示路由与拦截数 | ✅ |
| 查询回归集 | `apps/api/tests/regression/m1_queries.json`，40 条查询断言解析结果 | ✅ |

M1 不做：向量语义分（需 bge-m3）、LLM 复核重排（M2 前置）、三源实时黑名单 feed 与 `/go` 中转（M4）、域名年龄（RDAP）。

### 打分口径（M1 标定）

`score = 0.50·词法 + 0.25·共识 + 0.15·权威 + 0.10·时效 − 0.15·风险 − 0.10·营销`

- 词法 = 0.5 × BM25 饱和值 + 0.5 × 查询词覆盖率（中英文都按二元组/词切分）；
- 共识：1 个引擎 0.4，2 个 0.8，≥3 个 1.0；
- 强相关 ≥ 0.55，相关 ≥ 0.30，弱相关 < 0.30；强相关允许为空，弱相关最多 5 条；
- 分数是**绝对分**，不做 minmax 归一，所以全是垃圾的查询不会凭空出现 0.9 的「强相关」。

### 黑名单

`BLOCKLIST_PATH` 默认指向 `apps/api/fixtures/blocklist.txt`（仓库内的演示规则：`evil-phish.test` 等）。
接真实数据时把该变量指向 URLhaus / OpenPhish 的导出文件即可，文件按 mtime 热加载，无需重启。


## M2 做了什么（当前）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 搜索快照 | `apps/api/app/core/session_store.py`：按 `sid` 存本次通过过滤与分档的结果源，TTL 900s、容量 64，LRU 淘汰 | ✅ |
| SSE 总结端点 | `GET /api/summarize?sid=&mode=fast`，事件 `meta → cite×N → token×M → done`，失败发 `error` | ✅ |
| 引用绑定 | `cite` 事件带 `i` 与稳定的 `result_id`；前端只渲染 cite 里出现过的编号 | ✅ |
| 侧栏 UI | 右侧 sticky 面板：生成 / 停止 / 重新生成，流式正文，点击 `[n]` 滚动并高亮对应卡片 | ✅ |
| 切换查询取消旧流 | 面板按 `sid` 重新挂载 + `AbortController`，上一轮文本不会接到新查询 | ✅ |
| 模型降级 | LLM 超时 / 不可达 → `error` 事件，保留已发引用与正文，结果列表照常可用 | ✅ |
| 离线可验收 | 未配 `LLM_BASE_URL` 时走本地抽取式桩 `stub-extractive`，结构与提示词一致 | ✅ |

M2 不做：`mode=full`（正文抓取，M4）、多轮对话、总结落库缓存、移动端抽屉（M7 打磨）。

### 接口

```
GET /api/summarize?sid=s_9f3a&mode=fast
Accept: text/event-stream

event: meta   data: {"model":"stub-extractive","sources":10,"mode":"fast","sid":"s_9f3a","query":"python 文档"}
event: cite   data: {"i":1,"result_id":"r_1","title":"...","url":"https://...","domain":"fastapi.tiangolo.com"}
event: token  data: {"t":"围绕「python 文档」，"}
event: done   data: {"ms":5763,"tokens":161,"partial":false}
event: error  data: {"code":"LLM_TIMEOUT","message":"等待模型响应超时（1 秒）","retryable":true}
```

- `sid` 不存在或过期 → `404 SESSION_NOT_FOUND`（`retryable=false`）；
- 零结果不落快照，直接 404；
- `mode` 只接受 `fast`，其它值 → `400 MODE_UNSUPPORTED`；
- `GET /api/health` 提供 `llm_provider` / `llm_model`。桩与真实模型都必须输出正文、有效引用并以 `done` 结束，冒烟才会通过。

### 接真实模型

本机 Ollama 已启动时，先用 `ollama list` 查到已安装的模型名，再启动应用。以下命令使用固定搜索样本和真实模型，打开首页后点「有结果」和「生成总结」。

```powershell
ollama list
.\scripts\serve.ps1 -Provider fixture -OllamaModel 'qwen3.5-4b-local:latest'
```

`-OllamaModel` 连接本机 `127.0.0.1:11434/v1`，默认发送 `reasoning_effort=none`，减少等待正文的时间。可在环境变量或 `.env` 里设置 `LLM_REASONING_EFFORT` 覆盖。`LLM_TIMEOUT` 限制等待首段可见正文的时间，随后也用于读取超时，默认 30 秒。

通用 OpenAI 兼容端点也可以直接通过环境变量配置。`LLM_REASONING_EFFORT` 留空时由端点决定。

```dotenv
LLM_BASE_URL=http://127.0.0.1:11434/v1   # Ollama 的 OpenAI 兼容端点
LLM_MODEL=qwen3.5-4b-local:latest
LLM_REASONING_EFFORT=none
LLM_TIMEOUT=30
```

配了 `LLM_BASE_URL` 就走真实模型（`LLM_PROVIDER` 可显式覆盖为 `openai`）；不配则用桩。
提示词在 `apps/api/app/prompts/`，与构建方案 §9.1/§9.2 一致。


## M3 做了什么（当前）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 书签存储 | `apps/api/app/db/`（SQLite WAL + FTS5，FTS5 缺失时自动降级 LIKE） | ✅ |
| 一键收藏 | 结果卡「收藏」按钮，写 `POST /api/bookmarks`，同 URL 不重复 | ✅ |
| 启动台页面 | `/bookmarks`：分组标签、标题与网址子串搜索、分页网格、添加、移组、删除、新建分组 | ✅ |
| 浏览器导入 | `POST /api/bookmarks/import`（Netscape HTML，20MB 上限） | ✅ |
| 浏览器导出 | `GET /api/bookmarks/export`（保留嵌套目录，未分组项保留在根目录） | ✅ |
| 往返一致 | 导入 → 导出 → 再导入后，URL / 标题 / 分组三者不变 | ✅ |

M3 不做：死链检测（M4）、标签 UI、拖拽排序、数字键快捷启动、Chrome 扩展与 bookmarklet（M8）。

### 重复规则（明确写死）

| 场景 | 行为 |
| --- | --- |
| 手动收藏已存在的 URL | 不新增；只补空标题、补备注、按传入的 `group_id` 改分组，返回 `deduplicated=true` |
| 导入时遇到已存在的 URL | **纯跳过**，不覆盖已有标题与分组（用户手动整理的结果优先） |
| 导入时同一文件内重复 | 第一条创建，后续跳过 |
| 分组 | 按需创建，只给真正新增的条目建，不留空分组 |

### 接口

```
GET    /api/bookmarks?q=&group=      -> { items, groups, total, fts }
POST   /api/bookmarks                -> 201 { item, deduplicated:false } / 200 { item, deduplicated:true }
PATCH  /api/bookmarks/{id}           { title?, group_id?, note?, dead? } -> 更新后的书签
DELETE /api/bookmarks/{id}           -> 204
GET    /api/groups                   -> [{ id, name, count }]
POST   /api/groups                   -> 201 { id, name }
POST   /api/bookmarks/import         multipart: file=<Netscape HTML>
GET    /api/bookmarks/export         text/html; attachment
```

本机启动时数据落在 `data/cs.db`（`DB_PATH` 可改）。移组时传 `group_id: null` 可移回「未分组」，省略该字段则保留原分组。导入导出采用 Chrome / Edge / Firefox 使用的 Netscape 书签 HTML 格式。


## M4 做了什么（当前）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 受控抓取入口 | `apps/api/app/core/fetch.py`：只连接已校验地址，逐跳复检重定向目标，总时限 2.5s、正文上限 2MB | ✅ |
| 正文提取 | `apps/api/app/core/extract.py`：trafilatura（装了就用）→ 标准库 HTMLParser 回退；过滤脚本/导航/面包屑 | ✅ |
| 正文增强 | `GET /api/summarize?mode=full`：并发抓前 5 条正文，失败保留摘要并标 `failed`/`degraded` | ✅ |
| 单页总结 | `POST /api/page/summarize` + `/s?u=<url>` 页面：一句话结论 / 要点 / 分歧 | ✅ |
| 死链检测 | `POST /api/bookmarks/check`：并发 5，只检查当前页所选书签，404/410 标记为「失效」 | ✅ |
| 侧栏交互 | 摘要完成后可增强，页脚显示抓取、降级和截断条数，引用标出素材来源 | ✅ |

M4 不做：三源实时黑名单 feed 与 `/go` 中转（需 API key，见方案 M4 安全部分）、Playwright 渲染兜底、r.jina.ai 兜底、总结结果落库缓存。

### 抓取护栏（M4 核心）

- 协议只放行 `http`/`https`；`file:`、`javascript:`、`data:`、无协议相对地址一律拒绝。
- 主机名黑名单：`localhost`、`*.local`、`metadata*`；IP 字面量直接判内网。
- 检查域名解析出的全部地址，并把连接固定到已通过检查的 IP。HTTP Host 和 TLS 证书校验仍使用原域名。
- 每次重定向都重新做上述校验，最多 3 跳。
- DNS、重定向和下载共用 2.5s 时限。正文只接收未压缩的白名单内容类型，超过 2MB 时截断并标记。死链检测只读取响应状态。

> 本机网络经透明代理把公网域名解析到 `198.18.x.x`（bench 网段），默认会被判为非公网。
> 本机可显式设置 `FETCH_EXTRA_CIDRS=198.18.0.0/15`。该例外仅用于此网段的 DNS 解析结果。默认配置拒绝这类地址。

### 接口

```
GET  /api/summarize?sid=&mode=fast|full    meta 提供 fetched / failed / truncated / degraded，cite 提供 material
POST /api/page/summarize  {"url": "https://..."}
     -> { url, final_url, title, byline, published, word_count, read_minutes,
          content_hash, extractor, truncated, summary{one_liner,bullets,key_data,caveats},
          summary_text, model }
     403 非公网 / 502 上游失败 / 504 超时 / 422 正文过短
POST /api/bookmarks/check  {"ids"?: [...], "limit"?: 20}
     -> { checked, dead, unknown, items:[{id,url,dead,status,detail}] }
```


## 打磨轮（M7）：缓存、快捷键、暗色、移动端

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 搜索缓存 | `apps/api/app/db/cache.py`，按 `qkey` 存 15 分钟，命中时元信息标「缓存」 | ✅ |
| 单页总结缓存 | 按正文与模型输入复用生成文本，页面信息取本次抓取结果 | ✅ |
| 键盘快捷键 | `/` 聚焦、`j`/`k` 选择、`Enter` 打开、`b` 收藏、`s` 总结、`Esc` 取消、`g s` 回搜索页 | ✅ |
| 暗色主题 | 自动 / 浅色 / 深色三态，`localStorage` 持久化，`data-theme` 驱动 | ✅ |
| 移动端侧栏抽屉 | <1080px 变成底部抽屉（62vh），右下角「AI 总结」开关 | ✅ |
| 错误态收敛 | 断网 / 超时 / 引擎全挂都落到统一 `ErrorState`，带重试与错误码 | ✅ |

### 缓存语义

- 搜索缓存按检索后端、查询参数和当前黑名单版本隔离。上游部分失败的结果不写入缓存；命中时 `meta.cached=true`。
- 快照：命中后按新的 `sid` 重新登记，侧栏总结照常可用；
- 单页总结仍会抓取页面。正文、最终地址、标题、长度上限和模型配置相同时复用生成文本，返回 `cached=true`。
- `CACHE_ENABLED=false` 可关闭缓存；`CACHE_TTL` 控制搜索缓存时效（默认 900 秒）。两张缓存表各保留 `CACHE_MAX_ENTRIES` 条最新写入记录（默认 512）。

### 快捷键一览

```
/      聚焦搜索框
j / k  上下选择结果（弱相关折叠时不参与）
Enter  新标签打开选中结果
b      收藏选中结果
s      生成/重新生成侧栏总结（窄屏同时展开抽屉）
Esc    取消选中、收起抽屉
g s    回搜索页
```


## 一键添加：bookmarklet / 扩展 / PWA

| 通道 | 落点 | 用法 |
| --- | --- | --- |
| Bookmarklet | `GET /api/tools/bookmarklet` + `/tools` 页面 | 把链接拖到书签栏；浏览器拦截直连时，可打开本机书签页确认 |
| Chrome / Edge 扩展 | `apps/extension/`（MV3） | `chrome://extensions` → 开发者模式 → 加载已解压的扩展，填 API 与 token |
| PWA 分享 | `apps/web/public/manifest.webmanifest` 的 `share_target` | 支持的设备安装后可分享 `url` 或含链接的 `text`，在书签页预填并确认 |

### 验证扩展（真实浏览器）

```powershell
# 首次：安装可选依赖与浏览器（仓库默认不带）
npm --prefix apps/web install
npm --prefix apps/web exec playwright install chromium

# 起一个隔离实例，再跑验收脚本（会打开可见 Chromium 加载未打包扩展）
node scripts/verify-extension.cjs http://127.0.0.1:8000
```

脚本会：加载 `apps/extension` → 打开 popup 填 token → 收藏 `docs.python.org` → 调后台保存函数 → 用 CDP 读 PWA 清单与安装性错误。
截图与 `installability.json` 写到 `docs/m9-evidence/`。

### 跨域写入与 token

bookmarklet 和扩展都在「别人的页面」里发起请求，无法用 Origin 白名单，因此统一走 token：

- token 文件：`data/api-token.txt`（`API_TOKEN_PATH` 可改），首次访问 `/api/tools/bookmarklet` 自动生成；
- 服务仅接受 `127.0.0.1`、`localhost`、`[::1]` 的 Host；Compose 的 token 和书签数据库同在 `/data` 卷。
- 跨域只允许带 `X-CS-Token` 的 `POST /api/bookmarks`，只接受 `url` 和 `title`，只返回 `deduplicated`。其余跨域请求返回 `403 CORS_FORBIDDEN`；缺少或无效 token 返回 `401 TOKEN_REQUIRED`。
- 同源书签页照常浏览、修改和删除；跨域预检只允许对添加接口发 POST。

> token 等于「谁能往你书签里写东西」，不要贴到公开地方；泄露后删掉 `data/api-token.txt` 即轮换。

### PWA 安装

安装和系统分享依赖浏览器支持。默认服务仅监听本机，安装设备须能访问对应地址；同一网络里的手机无法通过自己的 `localhost` 访问电脑上的服务。预填后须手动收藏。应用依赖在线服务。


## 真实上游、熔断与中转（本轮）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 真实 SearXNG 跑通 | `D:\agent\build\searxng`（源码 + venv + Windows shim），详情见下 | ✅ 本机实测 |
| 引擎健康与熔断 | `apps/api/app/core/breaker.py`，`engine_health` 表，实例级 + 引擎级分离 | ✅ |
| 黑名单 feed 刷新 | `apps/api/app/core/feeds.py` + `POST /api/tools/refresh-feeds` | ✅（无 key 源） |
| `/go` 风险中转 | `apps/api/app/routers/go.py`，HMAC 签名，可疑结果带 `go_url` | ✅ |
| 查询扩展（词典版） | `apps/api/app/core/expand.py`，别名词半权计入词法 | ✅ |
| 书签标签 | `bookmark_tags` + `/api/bookmarks?tag=` + 启动台标签条 | ✅ |
| 搜索分页 | 结果页「上一页 / 下一页」，空页可返回 | ✅ |
| `/tools` 入口 | 头部导航「一键添加」 | ✅ |
| git 与 CI | `.github/workflows/ci.yml`（pytest + build），仓库已 `git init` 并暂存 | ✅（初始提交留给你执行） |


### 引擎后缀（2026-11-07 实测）

| 后缀 | 引擎 | 本机可用性 |
| --- | --- | --- |
| `gc` | google cse | ✅ 稳定（10–14 条，0.6–0.7s） |
| `y` | yahoo | ✅ 稳定（6–7 条，1.2–1.3s） |
| `d` | duckduckgo | ⚠️ 间歇 CAPTCHA |
| `b` | bing | ❌ 返回空 |
| `br` | brave | ❌ 限流（too many requests） |
| `sc` | google scholar | ❌ access denied |
| `sg` | sogou | ❌ SearXNG 侧 unexpected crash |
| `w` | wikipedia | ❌ 返回空 |
| `g` | google | ❌ 默认 disabled，启用后 access denied |

`sp`（startpage）、`mj`（mojeek）保留在映射表里，但当前 SearXNG 版本没有这两个引擎，指定它们会被忽略。

### 真实验收结果（2026-11-07）

```
verify-searxng.py --engines gc y        -> 9/9 PASS（exit 0，无缓存）
    gc: 655 / 591 / 674 ms，10–13 条
    y : 1250 / 1227 / 1312 ms，6–7 条
    含 bang（!gc）、地区（jp）、护栏（C g）

measure-search-quality.py（默认多引擎，8 次）
    8/8 有结果，中位 1736 ms，最大 2623 ms，来源 google cse + yahoo
    每次都有 brave/ddg/sogou 失败（CAPTCHA / 限流 / crash）

冷热缓存（同一查询连打两次）
    asyncio 事件循环 原理: 2783 ms -> 28 ms（cached=True）
    SearXNG 元搜索 配置 : 2227 ms -> 5 ms（cached=True）

真实搜索接本机千问（qwen3.5-4b-local，reasoning=none）
    搜索 2810 ms / 17 条 / 3 引擎
    总结首字 7672 ms，总 18329 ms，176 段，10 条引用全部绑定，done.partial=false
```


### Docker Compose 验收（2026-11-08）

前提：Docker Desktop 4.98（Store/per-user 安装）。若 `docker` 不在 PATH：
`C:\Users\<你>\AppData\Local\Programs\DockerDesktop\resources\bin`（本机为 `C:\Users\HUAWEI\AppData\Local\Programs\DockerDesktop\resources\bin`）。

```powershell
cd D:\agent\llq
Copy-Item .env.example .env          # 首次
npm --prefix apps/web run build      # compose 会把 dist 挂到 /web
docker compose up -d --build
.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8000
```

实测结果：

| 项目 | 结果 |
| --- | --- |
| 镜像 | `llq-api` 242MB 构建成功；`searxng/searxng:latest` 387MB |
| 端口 | 两端点均只绑 `127.0.0.1`（8000 / 8888） |
| 固定样本 | `provider=fixture`、`web_dist=/web`，冒烟 **16/16** |
| 数据持久化 | 写入书签 → `docker compose down` → `up` → 书签与 token 均在（卷 `llq_bookmarks`） |
| 真实上游 | 切 `SEARCH_PROVIDER=searxng` 后 `provider=searxng`、上游 `http://searxng:8080`；`--engines y gc` **9/9** |
| 前端 | 容器同源页面渲染正常，10 张卡片，无 JS 错误 |

注意：容器里的 SearXNG 引擎可用性与宿主机原生实例不同——本机容器内 `duckduckgo` 可用、`google cse` 偶发超时；宿主机原生实例反之。
仓库的 `searxng/settings.yml` 已显式启用 `bing/yahoo/sogou`，保证 `compose up` 后引擎集一致。

### 本机跑真实 SearXNG（无 Docker 时）

```powershell
# 一次性准备（源码在仓库外，避免污染工程）
git clone --depth 1 https://github.com/searxng/searxng.git D:\agent\build\searxng
cd D:\agent\build\searxng
git restore --source=HEAD -- . ':(exclude)utils/templates'   # Windows 无法创建带 ":" 的文件名
python -m venv ..\searxenv
..\searxenv\Scripts\python.exe -m pip install -r requirements.txt

# Windows 兼容 shim（SearXNG 导入期需要 pwd 与 os.getuid）
# 见 D:\agent\build\shims\{pwd.py,sitecustomize.py}

$env:SEARXNG_SETTINGS_PATH='D:\agent\build\searxng-settings.yml'
$env:PYTHONPATH='D:\agent\build\shims;D:\agent\build\searxng'
..\searxenv\Scripts\python.exe -m searx.webapp
```

settings 关键项：`search.formats: [html, json]`、`server.limiter: false`、`bind_address: 127.0.0.1`。

### 本机实测（2026-11-06 23:4x）

只启用了一个能出结果的引擎（`google cse`），其余在生产环境也会遇到：

```
8/8 次成功，延迟中位 936 ms（最大 3303 ms），结果 10–15 条
失败引擎：brave(Suspended: too many requests) / duckduckgo(CAPTCHA) / wikidata(timeout)
```

这也直接验证了熔断的必要性：**引擎级全 CAPTCHA 不会被误判成实例故障**（`EnginesUnresponsive` 只记引擎级失败）。

### 熔断与 `/go` 的接口语义

- `ENGINE_UNAVAILABLE`（503）：显式指定的引擎处于冷却期，提示换引擎；
- `UPSTREAM_UNAVAILABLE`（503）：实例级熔断（连接失败 / 超时 / 坏响应累计 3 次），冷却 `BREAKER_COOLDOWN`；
- `meta.unresponsive`：本次哪些引擎没给结果（来自 SearXNG）；
- 可疑结果（0.35 ≤ risk < 0.6）多出 `go_url`，前端点击先进 `/go?u=&sig=` 确认页；签名错 → 403。

## 本机启动

### 0. 依赖

```powershell
python -m pip install -e "apps/api[dev]"
npm --prefix apps/web install
```

### 1. 没有 Docker 时：固定样本跑通闭环

```powershell
.\scripts\serve.ps1 -Provider fixture
# 打开 http://127.0.0.1:8000
```

固定样本模式下，首页提供有结果、零结果、上游不可用、恶意链接四个自检入口。也可输入 `test`、`__empty 任意词`、`__fail 任意词`、`__risky 任意词`。

### 2. 有 Docker 时：接真实 SearXNG

```powershell
Copy-Item .env.example .env
npm --prefix apps/web run build
docker compose up -d --build        # SearXNG :8888，API :8000
curl "http://127.0.0.1:8888/search?q=test&format=json"   # 先确认能拿到 JSON
```

本机只跑 API（SearXNG 在 Docker 里）：`SEARCH_PROVIDER=searxng` + `SEARXNG_URL=http://127.0.0.1:8888`，然后 `scripts\serve.ps1`。

Compose 将书签数据库保存到命名卷 `bookmarks`，重建 API 容器后仍保留。若旧版 API 容器已有书签，先下载其 `/api/bookmarks/export`，确认备份后再重建并导回。容器默认使用抽取式总结；配置 `COMPOSE_LLM_BASE_URL` 时须使用容器可访问的模型端点。本机 Ollama 可搭配本机 API 使用。

### 3. 开发形态（热更新）

```powershell
.\scripts\dev.ps1 -Provider fixture
# FastAPI :8000 （--reload，被 Vite 代理），浏览器只访问 http://127.0.0.1:5173
```

## 验收与测试

```powershell
# 单元 / 契约测试（固定样本，不依赖网络与 Docker）
python -m pytest apps/api -q

# 固定样本服务启动后：三态、路由、拦截、引用、书签与同源首页
.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8000

# 真实搜索服务启动后：选 2～3 个已启用引擎，逐条记录结果数、来源、延迟和通过率
python scripts/verify-searxng.py --base-url http://127.0.0.1:8000 --engines g b
```

浏览器闭环：输入 `test` 提交 → 结果列表出现 10 条 → 点击标题在原站打开；刷新页面（地址栏保留 `?q=test`）结果复现。

## API 契约（M0 已实现部分）

`POST /api/search`

```json
{ "q": "test", "page": 1, "region": null,
  "opts": { "safe": true, "exact": false, "summarize": false, "fixture": null } }
```

```json
{ "parsed": { "q": "test", "engine": "default", "region": null, "router": "default" },
  "groups": { "strong": [Result...], "related": [], "weak": [] },
  "meta": { "status": "ok|empty", "engines": ["google"], "unresponsive": [],
            "provider": "fixture|searxng", "cached": false, "ms": 3, "total": 10,
            "filtered": { "dup": 1, "risk": 0 }, "sid": "s_1a2b" } }
```

上游错误使用 `{"error":{"code":"...","message":"...","retryable":true}}`。不可用或超时返回 HTTP `503`，错误码为 `UPSTREAM_UNAVAILABLE` 或 `UPSTREAM_TIMEOUT`。坏响应返回 HTTP `502`，错误码为 `UPSTREAM_BAD_RESPONSE`。

其他端点：`GET /api/health`（provider / web_built / 版本）、`GET /api/docs`（OpenAPI）。

## 目录结构

```
llq/
├─ apps/api/
│  ├─ app/main.py            FastAPI 入口 + 同源托管 dist + SPA 回退
│  ├─ app/config.py          环境变量配置
│  ├─ app/schemas.py         请求 / 响应模型
│  ├─ app/routers/search.py  POST /api/search
│  ├─ app/core/searxng.py    真实 SearXNG 客户端（超时 / 连接失败 / 坏响应分类）
│  ├─ app/core/fixture_provider.py  固定样本上游（三态）
│  ├─ app/core/normalize.py  URL 规范化、展示串、去重
│  ├─ app/core/aggregator.py 选择上游 + 计时
│  ├─ fixtures/              SearXNG 形状的固定样本
│  └─ tests/                 API 契约、护栏、解析、安全、打分与缓存测试
├─ apps/web/                 React 19 + TS + Vite
│  ├─ src/App.tsx            状态机 idle/loading/ok/empty/error
│  ├─ src/api.ts             fetch 封装 + 错误码
│  └─ src/components/        SearchBar / ResultList / ResultCard / MetaBar / StatePanel
├─ searxng/settings.yml      开 json、关 limiter
├─ docker-compose.yml        可选：SearXNG + API
└─ scripts/                  serve.ps1 / dev.ps1 / smoke.ps1
```

## 设计取舍（与方案文档的差异）

见 [docs/决策与接口变更.md](docs/决策与接口变更.md)。要点：前端用 Vite 而非 Next.js；搜索端点只保留 POST；M0 结果全落 `strong`；新增 `fixture` 上游用于无 Docker 验收。

## 下一步

优先稳定真实 SearXNG 的指定引擎，再验证完整响应的冷热缓存、Compose 重建后的数据持久化。[验收条件](docs/进展与欠账.md#后续优先级)