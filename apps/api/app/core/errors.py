"""上游错误分类。前端据此区分「有结果 / 零结果 / 上游不可用」三种状态。"""

from __future__ import annotations


class SearchError(Exception):
    code = "SEARCH_ERROR"
    http_status = 502
    retryable = True

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UpstreamUnavailable(SearchError):
    code = "UPSTREAM_UNAVAILABLE"
    http_status = 503
    retryable = True
    engines: list[str] = []


class UpstreamTimeout(SearchError):
    code = "UPSTREAM_TIMEOUT"
    http_status = 503
    retryable = True


class EnginesUnresponsive(UpstreamUnavailable):
    """SearXNG 可达、但本次所有引擎都没给结果（CAPTCHA / 超时 / 限流）。

    这是数据面问题，不能算成「上游实例故障」，否则会误开实例级熔断。
    """

    def __init__(self, message: str, engines: list[str] | None = None):
        super().__init__(message)
        self.engines = engines or []


class EngineUnavailable(EnginesUnresponsive):
    code = "ENGINE_UNAVAILABLE"


class UpstreamBadResponse(SearchError):
    code = "UPSTREAM_BAD_RESPONSE"
    http_status = 502
    retryable = True
