"""T028: 运行时隔离测试（quickstart V7）。

1. 端点白名单校验；
2. 静态检查：运行时代码（chat/runtime/ui/eval）不得导入外部大模型客户端
   （openai / synth.llm）——外部客户端只允许出现在 synth 模块。
"""

import ast
from pathlib import Path

import pytest

from tu_assistant.runtime.client import (
    EndpointNotAllowedError,
    ModelClient,
    check_endpoint_allowed,
)

ALLOWED = ["127.0.0.1", "localhost"]
FORBIDDEN_IMPORTS = {"openai", "tu_assistant.synth", "tu_assistant.synth.llm"}
RUNTIME_PACKAGES = ["chat", "runtime", "ui", "eval"]


class TestWhitelist:
    def test_allowed(self):
        for ep in ("http://127.0.0.1:8080/v1", "http://localhost:9000"):
            check_endpoint_allowed(ep, ALLOWED)
            ModelClient(ep, ALLOWED)

    def test_rejected(self):
        for ep in ("http://192.168.1.10:8080", "https://api.deepseek.com", "http://0.0.0.0"):
            with pytest.raises(EndpointNotAllowedError):
                check_endpoint_allowed(ep, ALLOWED)
            with pytest.raises(EndpointNotAllowedError):
                ModelClient(ep, ALLOWED)


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


class TestNoExternalClientInRuntime:
    def test_runtime_packages_clean(self):
        src = Path(__file__).parent.parent.parent / "src" / "tu_assistant"
        violations = []
        for pkg in RUNTIME_PACKAGES:
            for py in (src / pkg).rglob("*.py"):
                imports = _imports_of(py)
                for imp in imports:
                    if imp in FORBIDDEN_IMPORTS or imp.startswith("tu_assistant.synth"):
                        violations.append(f"{py.relative_to(src)}: {imp}")
        assert not violations, f"运行时模块导入了外部客户端：{violations}"
