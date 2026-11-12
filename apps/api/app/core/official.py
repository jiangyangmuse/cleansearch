"""品牌官方入口表与识别（OFFICIAL）。

设计约束（见 docs/决策与接口变更.md · 官方入口表）：

- 只认「精确主机 + 允许路径」；共享托管域名必须带组织/路径前缀，不整域认证；
- 搜索条目只标记实际候选；缺失角色可显示已声明的目录直达，不冒充搜索来源；
- 目录直达不作为总结材料，入口表负责「身份」，不保证「可访问性」；
- 品牌别名按完整词元匹配；未知品牌返回 None，保持普通结果；
- 教程 / 新闻 / 对比类查询不置顶官方入口，避免把导航意图强加成教程意图；
- 同一角色最多一条（表格顺序即优先级），语言首页与首页视为同一角色。

入口表是人工维护的真源。`verified` 只表示最后一次人工/脚本核验日期，
不保证域名永久有效；`source` 记录核验时使用的官方页面。
"""

from __future__ import annotations

import re
import unicodedata
import hashlib
import json
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from app.schemas import OfficialLink, OfficialSection, Result
from app.core.normalize import is_renderable_url, display_url

ROLE_ORDER = (
    "home",
    "chat",
    "docs",
    "console",
    "download",
    "account",
    "code",
    "status",
    "support",
)
ROLE_LABELS = {
    "home": "官网",
    "chat": "聊天 / 产品",
    "docs": "文档",
    "console": "控制台",
    "download": "下载",
    "account": "账户",
    "code": "代码仓库",
    "status": "状态",
    "support": "支持",
}


@dataclass(frozen=True, slots=True)
class OfficialSite:
    role: str
    label: str
    host: str
    path: str = "/"
    source: str = ""
    verified: str = ""


@dataclass(frozen=True, slots=True)
class BrandEntry:
    key: str
    name: str
    aliases: tuple[str, ...]
    sites: tuple[OfficialSite, ...]
    source: str = ""
    verified: str = ""
    # 允许的跳转主机（登录页 / 地区站）：只给核验脚本用，不参与结果匹配
    extra_hosts: tuple[str, ...] = ()
    note: str = ""


def _site(role: str, label: str, host: str, path: str = "/") -> OfficialSite:
    return OfficialSite(role=role, label=label, host=host, path=path)


def _brand(
    key: str,
    name: str,
    aliases: tuple[str, ...],
    *sites: tuple[str, str, str, str],
    source: str = "",
    verified: str = "",
    note: str = "",
    extra_hosts: tuple[str, ...] = (),
) -> BrandEntry:
    return BrandEntry(
        key=key,
        name=name,
        aliases=aliases,
        sites=tuple(_site(*site) for site in sites),
        source=source,
        verified=verified,
        note=note,
        extra_hosts=extra_hosts,
    )


# 核验日期：脚本 scripts/verify-official.py 会逐条重测并写入资产。
VERIFIED = "2026-11-08"

BRANDS: tuple[BrandEntry, ...] = (
    _brand(
        "arknights", "明日方舟", ("明日方舟", "arknights"),
        ("home", "中国大陆官网", "ak.hypergryph.com", "/"),
        source="https://ak.hypergryph.com/",
        verified="2026-11-12",
    ),
    _brand(
        "nexon", "Nexon", ("nexon", "넥슨"),
        ("home", "全球官网", "www.nexon.com", "/main/en"),
        ("home", "韩国官网", "www.nexon.com", "/Home/Game"),
        ("home", "官网", "www.nexon.com", "/"),
        source="https://www.nexon.com/main/en",
        verified="2026-11-12",
    ),
    _brand(
        "deepseek", "DeepSeek", ("deepseek", "深度求索"),
        ("home", "官网", "www.deepseek.com", "/"),
        ("chat", "聊天", "chat.deepseek.com", "/"),
        ("docs", "API 文档", "api-docs.deepseek.com", "/"),
        ("console", "开放平台", "platform.deepseek.com", "/"),
        ("console", "开放平台介绍", "www.deepseek.com", "/platform"),
        ("console", "开放平台介绍", "www.deepseek.com", "/en/platform"),
        ("download", "应用下载", "download.deepseek.com", "/"),
        ("code", "官方仓库", "github.com", "/deepseek-ai"),
        source="https://www.deepseek.com/",
    ),
    _brand(
        "openai", "OpenAI", ("openai", "chatgpt", "gpt"),
        ("home", "官网", "openai.com", "/"),
        ("chat", "聊天", "chatgpt.com", "/"),
        ("console", "控制台", "platform.openai.com", "/"),
        ("docs", "文档", "developers.openai.com", "/"),
        source="https://openai.com/",
    ),
    _brand(
        "anthropic", "Anthropic", ("anthropic", "claude"),
        ("home", "官网", "www.anthropic.com", "/"),
        ("chat", "聊天", "claude.ai", "/"),
        ("docs", "文档", "platform.claude.com", "/docs"),
        ("console", "控制台", "platform.claude.com", "/"),
        source="https://www.anthropic.com/",
    ),
    _brand(
        "google", "Google", ("google", "谷歌"),
        ("home", "官网", "www.google.com", "/"),
        ("chat", "Gemini", "gemini.google.com", "/"),
        ("console", "云控制台", "console.cloud.google.com", "/"),
        ("docs", "开发者文档", "developers.google.com", "/"),
        source="https://www.google.com/",
        extra_hosts=("www.google.com.hk", "accounts.google.com"),
    ),
    _brand(
        "microsoft", "Microsoft", ("microsoft", "微软"),
        ("home", "官网", "www.microsoft.com", "/"),
        ("docs", "文档", "learn.microsoft.com", "/"),
        ("console", "Azure 门户", "portal.azure.com", "/"),
        source="https://www.microsoft.com/",
    ),
    _brand(
        "github", "GitHub", ("github",),
        ("home", "官网", "github.com", "/"),
        ("docs", "文档", "docs.github.com", "/"),
        source="https://github.com/",
    ),
    _brand(
        "apple", "Apple", ("apple", "苹果"),
        ("home", "官网", "www.apple.com", "/"),
        ("docs", "开发者", "developer.apple.com", "/"),
        ("support", "支持", "support.apple.com", "/"),
        source="https://www.apple.com/",
    ),
    _brand(
        "nvidia", "NVIDIA", ("nvidia", "英伟达"),
        ("home", "官网", "www.nvidia.com", "/"),
        ("docs", "开发者文档", "developer.nvidia.com", "/"),
        source="https://www.nvidia.com/",
    ),
    _brand(
        "aws", "AWS", ("aws", "亚马逊云"),
        ("home", "官网", "aws.amazon.com", "/"),
        ("console", "控制台", "console.aws.amazon.com", "/"),
        ("docs", "文档", "docs.aws.amazon.com", "/"),
        source="https://aws.amazon.com/",
    ),
    _brand(
        "cloudflare", "Cloudflare", ("cloudflare",),
        ("home", "官网", "www.cloudflare.com", "/"),
        ("console", "控制台", "dash.cloudflare.com", "/"),
        ("docs", "文档", "developers.cloudflare.com", "/"),
        source="https://www.cloudflare.com/",
    ),
    _brand(
        "vercel", "Vercel", ("vercel",),
        ("home", "官网", "vercel.com", "/"),
        ("docs", "文档", "vercel.com", "/docs"),
        source="https://vercel.com/",
    ),
    _brand(
        "stripe", "Stripe", ("stripe",),
        ("home", "官网", "stripe.com", "/"),
        ("console", "控制台", "dashboard.stripe.com", "/"),
        ("docs", "文档", "docs.stripe.com", "/"),
        source="https://stripe.com/",
    ),
    _brand(
        "python", "Python", ("python",),
        ("home", "官网", "www.python.org", "/"),
        ("docs", "文档", "docs.python.org", "/"),
        ("code", "官方仓库", "github.com", "/python"),
        source="https://www.python.org/",
    ),
    _brand(
        "nodejs", "Node.js", ("nodejs", "node.js"),
        ("home", "官网", "nodejs.org", "/"),
        ("docs", "文档", "nodejs.org", "/api"),
        source="https://nodejs.org/",
    ),
    _brand(
        "rust", "Rust", ("rust",),
        ("home", "官网", "rust-lang.org", "/"),
        ("docs", "文档", "doc.rust-lang.org", "/"),
        ("code", "官方仓库", "github.com", "/rust-lang"),
        source="https://www.rust-lang.org/",
    ),
    _brand(
        "docker", "Docker", ("docker",),
        ("home", "官网", "www.docker.com", "/"),
        ("docs", "文档", "docs.docker.com", "/"),
        ("console", "Hub", "hub.docker.com", "/"),
        source="https://www.docker.com/",
    ),
    _brand(
        "mozilla", "Mozilla", ("mozilla", "firefox", "火狐"),
        ("home", "官网", "www.mozilla.org", "/"),
        ("docs", "MDN 文档", "developer.mozilla.org", "/"),
        ("code", "官方仓库", "github.com", "/mozilla"),
        source="https://www.mozilla.org/",
    ),
    _brand(
        "npm", "npm", ("npm",),
        ("home", "官网", "www.npmjs.com", "/"),
        ("docs", "文档", "docs.npmjs.com", "/"),
        source="https://www.npmjs.com/",
    ),
    _brand(
        "react", "React", ("react", "reactjs"),
        ("home", "官网", "react.dev", "/"),
        source="https://react.dev/",
    ),
    _brand(
        "vue", "Vue.js", ("vue", "vuejs", "vue.js"),
        ("home", "官网", "vuejs.org", "/"),
        source="https://vuejs.org/",
    ),
    _brand(
        "vite", "Vite", ("vite", "vitejs"),
        ("home", "官网", "vite.dev", "/"),
        ("docs", "文档", "vite.dev", "/guide"),
        source="https://vite.dev/",
    ),
    _brand(
        "tailwind", "Tailwind CSS", ("tailwind", "tailwindcss"),
        ("home", "官网", "tailwindcss.com", "/"),
        ("docs", "文档", "tailwindcss.com", "/docs"),
        source="https://tailwindcss.com/",
    ),
    _brand(
        "huggingface", "Hugging Face", ("huggingface",),
        ("home", "官网", "huggingface.co", "/"),
        ("docs", "文档", "huggingface.co", "/docs"),
        source="https://huggingface.co/",
    ),
    _brand(
        "figma", "Figma", ("figma",),
        ("home", "官网", "www.figma.com", "/"),
        ("docs", "帮助中心", "help.figma.com", "/"),
        source="https://www.figma.com/",
    ),
    _brand(
        "slack", "Slack", ("slack",),
        ("home", "官网", "slack.com", "/"),
        ("docs", "API 文档", "docs.slack.dev", "/"),
        source="https://slack.com/",
    ),
    _brand(
        "telegram", "Telegram", ("telegram",),
        ("home", "官网", "telegram.org", "/"),
        ("chat", "网页版", "web.telegram.org", "/"),
        ("docs", "API 文档", "core.telegram.org", "/"),
        source="https://telegram.org/",
    ),
    _brand(
        "discord", "Discord", ("discord",),
        ("home", "官网", "discord.com", "/"),
        ("docs", "开发者文档", "discord.com", "/developers"),
        source="https://discord.com/",
    ),
    _brand(
        "wikipedia", "Wikipedia", ("wikipedia", "维基百科"),
        ("home", "官网", "www.wikipedia.org", "/"),
        source="https://www.wikipedia.org/",
    ),
    _brand(
        "youtube", "YouTube", ("youtube",),
        ("home", "官网", "www.youtube.com", "/"),
        ("console", "创作中心", "studio.youtube.com", "/"),
        ("docs", "API 文档", "developers.google.com", "/youtube"),
        source="https://www.youtube.com/",
        extra_hosts=("accounts.google.com",),
    ),
    _brand(
        "aliyun", "阿里云", ("aliyun", "阿里云"),
        ("home", "官网", "www.aliyun.com", "/"),
        ("console", "控制台", "console.aliyun.com", "/"),
        ("docs", "文档", "help.aliyun.com", "/"),
        source="https://www.aliyun.com/",
        extra_hosts=("account.aliyun.com",),
    ),
    _brand(
        "tencent", "腾讯", ("tencent", "腾讯"),
        ("home", "官网", "www.tencent.com", "/"),
        ("chat", "腾讯云", "cloud.tencent.com", "/"),
        ("console", "控制台", "console.cloud.tencent.com", "/"),
        source="https://www.tencent.com/",
    ),
    _brand(
        "baidu", "百度", ("baidu", "百度"),
        ("home", "官网", "www.baidu.com", "/"),
        ("chat", "文心一言", "wenxin.baidu.com", "/"),
        ("console", "智能云控制台", "console.bce.baidu.com", "/"),
        source="https://www.baidu.com/",
    ),
    _brand(
        "doubao", "豆包 / 火山引擎", ("豆包", "doubao", "火山引擎", "volcengine"),
        ("home", "火山引擎", "www.volcengine.com", "/"),
        ("chat", "豆包", "www.doubao.com", "/"),
        ("console", "控制台", "console.volcengine.com", "/"),
        ("docs", "文档", "docs.volcengine.com", "/"),
        source="https://www.volcengine.com/",
    ),
    _brand(
        "kimi", "Kimi", ("kimi", "月之暗面", "moonshot"),
        ("home", "官网", "www.moonshot.cn", "/"),
        ("chat", "聊天", "www.kimi.com", "/"),
        ("console", "开放平台", "platform.kimi.com", "/"),
        source="https://www.moonshot.cn/",
    ),
    _brand(
        "zhipu", "智谱 AI", ("智谱", "zhipu", "chatglm", "bigmodel"),
        ("home", "官网", "www.zhipuai.cn", "/"),
        ("chat", "ChatGLM", "chatglm.cn", "/"),
        ("console", "开放平台", "open.bigmodel.cn", "/"),
        source="https://www.zhipuai.cn/",
    ),
    _brand(
        "qwen", "通义千问", ("通义", "qwen", "千问"),
        ("chat", "聊天", "qianwen.aliyun.com", "/"),
        ("docs", "百炼文档", "help.aliyun.com", "/zh/model-studio"),
        source="https://tongyi.aliyun.com/",
    ),
    _brand(
        "feishu", "飞书", ("飞书", "feishu", "lark"),
        ("home", "官网", "www.feishu.cn", "/"),
        ("docs", "开放平台文档", "open.feishu.cn", "/document"),
        ("console", "开发者后台", "open.feishu.cn", "/app"),
        source="https://www.feishu.cn/",
    ),
    _brand(
        "dingtalk", "钉钉", ("钉钉", "dingtalk"),
        ("home", "官网", "www.dingtalk.com", "/"),
        ("docs", "开放平台文档", "open.dingtalk.com", "/"),
        source="https://www.dingtalk.com/",
    ),
    _brand(
        "wechat", "微信", ("微信", "wechat", "weixin"),
        ("home", "官网", "weixin.qq.com", "/"),
        ("console", "公众平台", "mp.weixin.qq.com", "/"),
        source="https://weixin.qq.com/",
    ),
    _brand(
        "zhihu", "知乎", ("知乎", "zhihu"),
        ("home", "官网", "www.zhihu.com", "/"),
        source="https://www.zhihu.com/",
    ),
    _brand(
        "taobao", "淘宝", ("淘宝", "taobao"),
        ("home", "官网", "www.taobao.com", "/"),
        source="https://www.taobao.com/",
    ),
    _brand(
        "bilibili", "哔哩哔哩", ("bilibili", "哔哩哔哩"),
        ("home", "官网", "www.bilibili.com", "/"),
        source="https://www.bilibili.com/",
    ),
    _brand(
        "xiaohongshu", "小红书", ("小红书", "xiaohongshu"),
        ("home", "官网", "www.xiaohongshu.com", "/"),
        source="https://www.xiaohongshu.com/",
    ),
    _brand(
        "jetbrains", "JetBrains", ("jetbrains",),
        ("home", "官网", "www.jetbrains.com", "/"),
        ("docs", "文档", "www.jetbrains.com", "/help"),
        source="https://www.jetbrains.com/",
    ),
    _brand(
        "vscode", "Visual Studio Code", ("vscode",),
        ("home", "官网", "code.visualstudio.com", "/"),
        ("docs", "文档", "code.visualstudio.com", "/docs"),
        source="https://code.visualstudio.com/",
    ),
    _brand(
        "android", "Android", ("android", "安卓"),
        ("home", "官网", "www.android.com", "/"),
        ("docs", "开发者文档", "developer.android.com", "/"),
        source="https://www.android.com/",
    ),
)


# ---------- 查询侧：品牌识别 ----------

LATIN_TOKEN = re.compile(r"[a-z0-9]+(?:[._+-][a-z0-9]+)*")
CJK_RUN = re.compile(r"[一-鿿]+")

CJK_INTENT = re.compile(
    r"(教程|入门|怎么|如何|安装|配置|报错|异常|新闻|发布|评测|测评|对比|排名|排行|价格|报价|多少钱|招聘)",
)
LATIN_INTENT = frozenset(
    {
        "tutorial", "tutorials", "guide", "guides", "news", "review", "reviews",
        "pricing", "price", "compare", "versus", "vs", "jobs", "career", "howto",
        "install", "setup", "error", "errors",
    }
)


def normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip().lower()


def query_tokens(query: str) -> tuple[list[str], list[str]]:
    lowered = normalise(query)
    latin = LATIN_TOKEN.findall(lowered)
    cjk = CJK_RUN.findall(lowered)
    return latin, cjk


def has_research_intent(query: str) -> bool:
    """教程 / 新闻 / 对比类查询：官方入口仍然相关，但不该占据导航位。"""
    lowered = normalise(query)
    if CJK_INTENT.search(lowered):
        return True
    latin, _ = query_tokens(lowered)
    return bool(LATIN_INTENT.intersection(latin))


def brand_for_query(query: str) -> BrandEntry | None:
    """只有单一品牌及导航词组成的查询才展示入口，内容/歧义查询保留普通排序。"""
    if not query or has_research_intent(query):
        return None
    lowered = normalise(query)
    matches: list[tuple[BrandEntry, str]] = []
    for brand in BRANDS:
        remainder = lowered
        matched = False
        for alias in sorted(brand.aliases, key=len, reverse=True):
            key = normalise(alias)
            if not key:
                continue
            if LATIN_TOKEN.fullmatch(key):
                pattern = rf"(?<![a-z0-9._+-]){re.escape(key)}(?![a-z0-9._+-])"
            else:
                pattern = re.escape(key)
            remainder, count = re.subn(pattern, " ", remainder)
            matched = matched or count > 0
        if matched:
            matches.append((brand, remainder))
    if len(matches) != 1:
        return None
    brand, remainder = matches[0]
    latin, cjk = query_tokens(remainder)
    if any(token not in NAVIGATION_WORDS for token in latin):
        return None
    if any(NAVIGATION_CJK.sub("", run) for run in cjk):
        return None
    return brand


NAVIGATION_WORDS = frozenset(
    "official site website homepage home chat chatbot api docs documentation console dashboard "
    "login signin log in sign download downloads account platform developer developers portal "
    "web desktop client".split()
)
NAVIGATION_CJK = re.compile(
    "官方网站|官方文档|开放平台|开发者平台|公众平台|网页版|桌面版|客户端|"
    "官网|首页|登录|登陆|文档|控制台|下载|入口|聊天|平台|官方|账户|账号|网站"
)


def catalog_revision() -> str:
    """目录或身份策略变更自动隔离缓存，不复用已撤销/变更的官方标签。"""
    payload = json.dumps([asdict(brand) for brand in BRANDS], ensure_ascii=False, sort_keys=True)
    return "official-v4:" + hashlib.sha256(payload.encode()).hexdigest()[:20]


# ---------- 结果侧：入口匹配 ----------

LOCALE_LANDING = re.compile(r"^/(?:[a-z]{2}(?:[-_][a-z]{2})?|index\.html?|home|index)$", re.IGNORECASE)


def _norm_path(path: str) -> str:
    raw = (path or "/").strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    if len(raw) > 1:
        raw = raw.rstrip("/") or "/"
    return raw


def path_matches(spec_path: str, url_path: str) -> bool:
    """入口路径语义："/" 只认首页与语言首页；其他路径按目录边界前缀匹配。"""
    spec = _norm_path(spec_path)
    actual = _norm_path(url_path)
    if spec == "/":
        return actual == "/" or bool(LOCALE_LANDING.fullmatch(actual))
    return actual == spec or actual.startswith(spec + "/")


def _site_for(brand: BrandEntry, url: str) -> OfficialSite | None:
    if not is_renderable_url(url):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.port not in (None, 443):
            return None
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host:
        return None
    path = parts.path or "/"
    # 浏览器/服务端可能把这些路径解析到组织边界之外；不为歧义地址认证。
    if "%" in path or "//" in path or any(part in (".", "..") for part in path.split("/")):
        return None
    best: OfficialSite | None = None
    for site in brand.sites:
        # 精确主机：brand.com.example.org、evil-brand.com 一律不匹配
        if site.host.lower() != host or not path_matches(site.path, path):
            continue
        if best is None or len(site.path) > len(best.path):
            best = site
    return best


def collect_official(
    brand: BrandEntry, results: list[Result]
) -> tuple[OfficialSection | None, list[Result]]:
    """从上游返回的候选里挑出官方入口；同角色只取一条，表格顺序即优先级。

    返回 (官方入口区, 已被收进入口区的结果)。没有命中时返回 (None, [])，
    调用方保持普通结果不动。
    """
    links: list[OfficialLink] = []
    used: list[Result] = []
    seen_roles: set[str] = set()
    for site in brand.sites:
        if site.role in seen_roles:
            continue
        match = next(
            (
                item
                for item in results
                if item not in used and _site_for(brand, item.url) is site
            ),
            None,
        )
        if match is None:
            continue
        seen_roles.add(site.role)
        used.append(match)
        links.append(
            OfficialLink(
                **match.model_dump(),
                role=site.role,
                label=site.label or ROLE_LABELS.get(site.role, site.role),
                host=site.host,
                source=site.source or brand.source,
                verified=site.verified or brand.verified or VERIFIED,
            )
        )
    if not links:
        return None, []
    links.sort(key=lambda link: ROLE_ORDER.index(link.role) if link.role in ROLE_ORDER else len(ROLE_ORDER))
    section = OfficialSection(key=brand.key, brand=brand.name, entries=links)
    return section, used


def directory_links(brand: BrandEntry, section: OfficialSection | None) -> list[OfficialLink]:
    """缺失角色使用已核验目录地址，不发额外网络请求、不生成内容或引擎来源。"""
    roles = {entry.role for entry in section.entries} if section else set()
    urls = {entry.url for entry in section.entries} if section else set()
    links = []
    for site in brand.sites:
        if site.role in roles:
            continue
        url = f"https://{site.host}{site.path}"
        if url in urls or _site_for(brand, url) is not site:
            continue
        roles.add(site.role)
        urls.add(url)
        links.append(OfficialLink(
            id="d_" + hashlib.sha256(url.encode()).hexdigest()[:16], url=url,
            display_url=display_url(url), title=f"{brand.name} · {site.label}",
            role=site.role, label=site.label, host=site.host,
            source=site.source or brand.source, verified=site.verified or brand.verified or VERIFIED,
            origin="directory",
        ))
    return links


def unverified_home_claim(brand: BrandEntry, result: Result) -> str | None:
    """提示导航中的自称官网或品牌近似域首页，不把未认证等同恶意。"""
    try:
        parts = urlsplit(result.url)
    except ValueError:
        return None
    if not path_matches("/", parts.path):
        return None
    for site in brand.sites:
        if parts.hostname == site.host and (site.path == "/" or path_matches(site.path, parts.path)):
            return None
    title = normalise(result.title)
    if not any(
        re.search(rf"(?<![a-z0-9]){re.escape(normalise(alias))}(?![a-z0-9])", title)
        if LATIN_TOKEN.fullmatch(normalise(alias)) else normalise(alias) in title
        for alias in brand.aliases
    ):
        return None
    claims_official = bool(re.search(r"官网|官方网站|official\s+(?:site|website|homepage)", title))
    folded_host = re.sub(r"[^a-z0-9]", "", (parts.hostname or "").lower())
    brand_domain = any(
        LATIN_TOKEN.fullmatch(normalise(alias)) and
        re.sub(r"[^a-z0-9]", "", normalise(alias)) in folded_host
        for alias in brand.aliases
    )
    if not claims_official and not brand_domain:
        return None
    signal = "自称官网" if claims_official else "品牌近似域名"
    return f"{signal}，未匹配 {brand.name} 已核验入口"


def table_snapshot() -> list[dict]:
    """给核验脚本与测试用的只读快照。"""
    rows: list[dict] = []
    for brand in BRANDS:
        for site in brand.sites:
            rows.append(
                {
                    "brand": brand.key,
                    "name": brand.name,
                    "role": site.role,
                    "label": site.label,
                    "host": site.host,
                    "path": site.path,
                    "source": site.source or brand.source,
                    "verified": site.verified or brand.verified or VERIFIED,
                    "allowed_hosts": sorted({s.host.lower() for s in brand.sites} | {h.lower() for h in brand.extra_hosts}),
                }
            )
    return rows
