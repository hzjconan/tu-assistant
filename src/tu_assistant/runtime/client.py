"""运行时模型客户端：OpenAI 兼容 Chat Completions（T024）。

启动时校验端点主机在 allowed_hosts 白名单内，否则拒绝启动
（宪章原则 III、IV：运行时不得调用外部服务）。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


class EndpointNotAllowedError(RuntimeError):
    pass


def check_endpoint_allowed(endpoint: str, allowed_hosts: list[str]) -> None:
    host = urlparse(endpoint).hostname or ""
    if host not in allowed_hosts:
        raise EndpointNotAllowedError(
            f"模型端点 {endpoint} 的主机 {host!r} 不在白名单 {allowed_hosts} 内。"
            "运行时只允许连接本机模型服务（宪章原则 III、IV）。"
        )


@dataclass
class ChatResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ModelClient:
    """OpenAI 兼容端点的薄封装；只发请求，不含任何业务逻辑。"""

    def __init__(
        self,
        endpoint: str,
        allowed_hosts: list[str],
        model: str = "default",
        timeout_s: float = 300.0,
    ) -> None:
        check_endpoint_allowed(endpoint, allowed_hosts)
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._timeout = timeout_s
        self._client = None

    def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """调用 /chat/completions。messages 为 OpenAI 格式。"""
        resp = self._get_client().post(
            f"{self.endpoint}/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        return ChatResponse(
            content=data["choices"][0]["message"]["content"],
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
