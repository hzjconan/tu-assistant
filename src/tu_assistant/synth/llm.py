"""外部大模型客户端（T029）——只允许在 synth 模块使用。

- API Key 只从环境变量 TU_EXTERNAL_LLM_API_KEY 读取；
- 调用前调用方必须声明输入来源；只允许知识库公开文档与合成模板，
  断言阻止把用户对话等内容发给外部服务（宪章原则 III）；
- 每次调用记录提供方、模型、提示词版本、种子（清单可复现）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

ALLOWED_INPUT_SOURCES = {"kb_clause", "kb_document", "eval_case", "synthetic_template"}


class ExternalInputNotAllowedError(RuntimeError):
    pass


@dataclass
class LLMUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ExternalLLM:
    """OpenAI 兼容的外部大模型客户端（仅离线合成用）。"""

    base_url: str
    model: str
    prompt_version: str = "v1"
    seed: int = 42
    timeout_s: float = 120.0
    usage: LLMUsage = field(default_factory=LLMUsage)

    def __post_init__(self) -> None:
        from ..config import external_api_key

        self._key = external_api_key()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.base_url, api_key=self._key, timeout=self.timeout_s
            )
        return self._client

    def chat(
        self,
        messages: list[dict],
        *,
        input_source: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        if input_source not in ALLOWED_INPUT_SOURCES:
            raise ExternalInputNotAllowedError(
                f"input_source={input_source!r} 不允许发往外部服务。"
                f"只允许 {sorted(ALLOWED_INPUT_SOURCES)}（宪章原则 III）。"
            )
        resp = self._get_client().chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=self.seed if self.seed is not None else None,
        )
        u = resp.usage
        self.usage.calls += 1
        self.usage.prompt_tokens += getattr(u, "prompt_tokens", 0) or 0
        self.usage.completion_tokens += getattr(u, "completion_tokens", 0) or 0
        return resp.choices[0].message.content or ""

    def meta(self) -> dict:
        """写入产物清单的生成器信息。"""
        return {
            "provider_base_url": self.base_url,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "seed": self.seed,
            "usage": {
                "calls": self.usage.calls,
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
            },
        }


def from_config(cfg: dict) -> ExternalLLM:
    ext = cfg["external_llm"]
    return ExternalLLM(
        base_url=ext["base_url"],
        model=ext["model"],
        prompt_version=cfg.get("prompt_version", "v1"),
        seed=cfg.get("seed", 42),
        timeout_s=ext.get("timeout_s", 120),
    )
