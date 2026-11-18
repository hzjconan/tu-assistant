"""E002 步骤 1：发往 mlx_lm.server 的 model 字段必须为 "default_model"。

mlx_lm.server 仅当请求 model == "default_model" 时才挂 --adapter-path 指定的
adapter；写具体基座模型名会被路由到不带 adapter 的基座模型。
"""

import json

from tu_assistant.cli import _model_name
from tu_assistant.runtime.client import ModelClient

ALLOWED = ["127.0.0.1", "localhost"]


def test_model_name_reads_default_model(tmp_path):
    """current.json 的 model 为 default_model 时，_model_name 返回 default_model。"""
    serve = tmp_path / "serve"
    serve.mkdir()
    (serve / "current.json").write_text(
        json.dumps(
            {
                "model": "default_model",
                "base_model": "mlx-community/Qwen2.5-7B-Instruct-4bit",
                "exp": "exp-x",
                "endpoint": "http://127.0.0.1:8080/v1",
            }
        ),
        encoding="utf-8",
    )
    assert _model_name({}, str(tmp_path)) == "default_model"


def test_model_name_explicit_config_overrides(tmp_path):
    """runtime.model_name 显式配置成别的值时仍按配置走（用于调试基座）。"""
    cfg = {"runtime": {"model_name": "mlx-community/Qwen2.5-7B-Instruct-4bit"}}
    assert (
        _model_name(cfg, str(tmp_path))
        == "mlx-community/Qwen2.5-7B-Instruct-4bit"
    )


def test_model_client_default_is_default_model():
    client = ModelClient("http://127.0.0.1:8080/v1", ALLOWED)
    assert client.model == "default_model"


def test_model_client_request_body_model(monkeypatch):
    """默认请求体里 model == "default_model"（mock httpx）。"""
    client = ModelClient("http://127.0.0.1:8080/v1", ALLOWED)
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

    monkeypatch.setattr("httpx.Client", FakeClient)
    client.chat([{"role": "user", "content": "hi"}])
    assert captured["json"]["model"] == "default_model"
