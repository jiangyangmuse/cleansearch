"""LLM 客户端：OpenAI 兼容的流式 chat/completions。

M2 只需要「按材料生成带编号引用的总结」，因此只暴露 async 流式切词接口；
异常统一转成 LLMTimeout / LLMUnavailable，由 SSE 端点转成 error 事件。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

import httpx


class LLMError(Exception):
    code = "LLM_ERROR"
    retryable = True

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMTimeout(LLMError):
    code = "LLM_TIMEOUT"


class LLMUnavailable(LLMError):
    code = "LLM_UNAVAILABLE"


class LLMBadResponse(LLMError):
    code = "LLM_BAD_RESPONSE"


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._transport = transport
        self.reasoning_effort = reasoning_effort

    async def stream(self, system: str, user: str) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "stream": True,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            # 推理片段可能持续到达，但侧栏要在期限内收到可见正文。
            async with asyncio.timeout(self.timeout) as first_text_timeout, httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
                ) as response:
                    if response.status_code != 200:
                        if response.status_code == 404:
                            raise LLMBadResponse(f"找不到模型 {self.model} 或模型接口，请检查配置")
                        raise LLMBadResponse(f"模型接口返回 HTTP {response.status_code}")
                    has_text = False
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            if not has_text:
                                raise LLMBadResponse("模型没有生成可显示的总结")
                            return
                        if not data:
                            continue
                        text = self._parse_content(data)
                        if not has_text and text.strip():
                            has_text = True
                            first_text_timeout.reschedule(None)
                        if has_text and text:
                            yield text
                    raise LLMBadResponse("模型输出中断，未收到结束信号")
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise LLMTimeout(f"等待模型响应超时（{self.timeout:g} 秒）") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"无法连接 LLM（{self.base_url}）：{exc.__class__.__name__}") from exc

    @staticmethod
    def _parse_content(data: str) -> str:
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError as exc:
            raise LLMBadResponse("模型返回的流式数据无效") from exc
        if not isinstance(chunk, dict) or "error" in chunk:
            raise LLMBadResponse("模型接口返回了错误的流式数据")
        choices = chunk.get("choices") or []
        if not choices:
            return ""
        if not isinstance(choices, list) or not isinstance(choices[0], dict):
            raise LLMBadResponse("模型返回的流式数据无效")
        delta = choices[0].get("delta")
        content = delta.get("content") if isinstance(delta, dict) else None
        return content if isinstance(content, str) else ""
