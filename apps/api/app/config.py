"""运行配置：全部从环境变量读，缺省值即本机单用户默认。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent          # apps/api/app
API_ROOT = APP_DIR.parent                          # apps/api
REPO_ROOT = API_ROOT.parent.parent                # 仓库根；容器 /app 下回退到 /

VALID_PROVIDERS = ("searxng", "fixture")


def _env(name: str, default: str | None = None) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return default
    raw = raw.strip()
    return raw or default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)) or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)) or default)
    except ValueError:
        return default


def _path(name: str, fallback: str) -> Path:
    value = _env(name, fallback) or fallback
    return Path(value).expanduser()


def _env_bool(name: str, default: bool) -> bool:
    raw = (_env(name) or "").lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # 检索后端：searxng = 真实 SearXNG；fixture = 固定样本（无需 Docker 即可验收闭环）
    provider: str
    searxng_url: str
    search_timeout: float
    max_query_len: int
    # 安全过滤：本地黑名单文件（一行一个域名或 URL）
    blocklist_path: Path
    # 总结：LLM 端点（OpenAI 兼容），未配置时用本地桩
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout: float
    llm_stub_delay: float
    # 搜索快照：供侧栏总结读取
    session_ttl: int
    session_capacity: int
    # 书签库（SQLite，WAL）
    db_path: Path
    # 正文抓取（M4）：受控入口的限额
    fetch_timeout: float
    summary_fetch_timeout: float
    fetch_max_bytes: int
    fetch_max_redirects: int
    fetch_concurrency: int
    fetch_extra_cidrs: tuple[str, ...]
    # 缓存：搜索结果 TTL 与总开关
    cache_ttl: int
    cache_enabled: bool
    # 一键添加：跨域写书签的共享 token 文件
    api_token_path: Path
    # 黑名单 feed：可刷新的纯文本源（OpenPhish 等无 key 源）
    feed_urls: tuple[str, ...]
    feed_output_path: Path
    # RDAP 域名年龄：给风险分补「新注册域名」信号
    rdap_enabled: bool
    rdap_ttl_days: int
    # 商用检索兜底：配置了 brave/serper key 且开关打开才启用
    brave_api_key: str
    serper_api_key: str
    paid_fallback: bool
    # favicon 缓存目录
    favicon_dir: Path
    # 查询扩展：off（不扩展）/ rank（只影响排序）/ rewrite（并入上游查询）
    expansion_mode: str
    # 熔断：连续失败阈值与冷却秒数
    breaker_enabled: bool
    breaker_fails: int
    breaker_cooldown: int
    # 前端构建产物目录；存在即由 FastAPI 同源托管
    web_dist: Path
    api_host: str
    api_port: int
    serve_web: bool
    # 显式允许的非回环主机名（手机/局域网访问）；回环永远允许
    allowed_hosts: tuple[str, ...] = ()
    llm_reasoning_effort: str | None = None
    cache_max_entries: int = 512


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    provider = (_env("SEARCH_PROVIDER", "searxng") or "searxng").lower()
    if provider not in VALID_PROVIDERS:
        provider = "searxng"
    dist = Path(_env("WEB_DIST", str(REPO_ROOT / "apps" / "web" / "dist")) or "")
    if not dist.is_absolute():
        dist = (REPO_ROOT / dist).resolve()
    blocklist = Path(_env("BLOCKLIST_PATH", str(API_ROOT / "fixtures" / "blocklist.txt")) or "")
    if not blocklist.is_absolute():
        blocklist = (REPO_ROOT / blocklist).resolve()
    db_path = Path(_env("DB_PATH", "data/cs.db") or "data/cs.db")
    if not db_path.is_absolute():
        db_path = (REPO_ROOT / db_path).resolve()
    llm_base_url = (_env("LLM_BASE_URL", "") or "").rstrip("/")
    llm_provider = (_env("LLM_PROVIDER", "") or "").lower()
    if llm_provider not in ("openai", "stub"):
        llm_provider = "openai" if llm_base_url else "stub"
    summary_fetch_timeout = _env_float("SUMMARY_FETCH_TIMEOUT", 4.0)
    if not 0 < summary_fetch_timeout <= 10:
        summary_fetch_timeout = 4.0
    return Settings(
        provider=provider,
        blocklist_path=blocklist,
        llm_provider=llm_provider,
        llm_base_url=llm_base_url,
        llm_api_key=_env("LLM_API_KEY", "ollama") or "ollama",
        llm_model=_env("LLM_MODEL", "qwen3:8b") or "qwen3:8b",
        llm_reasoning_effort=_env("LLM_REASONING_EFFORT"),
        llm_timeout=_env_float("LLM_TIMEOUT", 30.0),
        llm_stub_delay=_env_float("LLM_STUB_DELAY", 0.02),
        session_ttl=_env_int("SESSION_TTL", 900),
        session_capacity=_env_int("SESSION_CAPACITY", 64),
        db_path=db_path,
        fetch_timeout=_env_float("FETCH_TIMEOUT", 2.5),
        summary_fetch_timeout=summary_fetch_timeout,
        fetch_max_bytes=_env_int("FETCH_MAX_BYTES", 2_000_000),
        fetch_max_redirects=_env_int("FETCH_MAX_REDIRECTS", 3),
        fetch_concurrency=_env_int("FETCH_CONCURRENCY", 6),
        api_token_path=(lambda p: p if p.is_absolute() else (REPO_ROOT / p).resolve())(
            Path(_env("API_TOKEN_PATH", "data/api-token.txt") or "data/api-token.txt")
        ),
        cache_ttl=_env_int("CACHE_TTL", 900),
        feed_urls=tuple(
            item.strip() for item in (_env("FEED_URLS", "") or "").split(",") if item.strip()
        ),
        feed_output_path=(lambda p: p if p.is_absolute() else (REPO_ROOT / p).resolve())(
            Path(_env("FEED_OUTPUT_PATH", "data/blocklist-feeds.txt") or "data/blocklist-feeds.txt")
        ),
        rdap_enabled=_env_bool("RDAP_ENABLED", True),
        rdap_ttl_days=_env_int("RDAP_TTL_DAYS", 30),
        brave_api_key=_env("BRAVE_API_KEY", "") or "",
        serper_api_key=_env("SERPER_API_KEY", "") or "",
        paid_fallback=_env_bool("PAID_FALLBACK", True),
        favicon_dir=_path("FAVICON_DIR", "data/favicons"),
        expansion_mode=(_env("EXPANSION_MODE", "rank") or "rank").lower(),
        breaker_enabled=_env_bool("BREAKER_ENABLED", True),
        breaker_fails=_env_int("BREAKER_FAILS", 3),
        breaker_cooldown=_env_int("BREAKER_COOLDOWN", 3600),
        cache_enabled=_env_bool("CACHE_ENABLED", True),
        cache_max_entries=max(1, _env_int("CACHE_MAX_ENTRIES", 512)),
        fetch_extra_cidrs=tuple(
            item.strip()
            for item in (_env("FETCH_EXTRA_CIDRS", "") or "").split(",")
            if item.strip()
        ),
        searxng_url=(_env("SEARXNG_URL", "http://127.0.0.1:8888") or "").rstrip("/"),
        search_timeout=_env_float("SEARCH_TIMEOUT", 8.0),
        max_query_len=_env_int("MAX_QUERY_LEN", 512),
        web_dist=dist,
        api_host=_env("API_HOST", "127.0.0.1") or "127.0.0.1",
        api_port=_env_int("API_PORT", 8000),
        serve_web=_env_bool("SERVE_WEB", True),
        allowed_hosts=tuple(
            item.strip().lower() for item in (_env("ALLOWED_HOSTS", "") or "").split(",") if item.strip()
        ),
    )


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
