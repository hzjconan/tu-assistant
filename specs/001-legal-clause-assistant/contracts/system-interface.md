# Contract: 系统接口与模型端点

命令行对话、网页界面、评测运行器都只通过同一个 Python 接口与系统交互。正式阶段加入检索对照组时实现同一接口即可。

## 1. Assistant 接口

```python
class Assistant(Protocol):
    def new_session(self, config: SessionConfig | None = None) -> str:
        """创建会话，返回 session_id。会话只存在于内存中。"""

    def send(self, session_id: str, message: str) -> Reply:
        """发送一条用户消息，返回本轮回复（已经过出处校验、免责提示、身份信息检查）。"""

    def export_markdown(self, session_id: str, turn_index: int | None = None) -> str:
        """返回某一轮（默认最后一轮）回复的 Markdown 文本，供保存为 .md 文件（FR-032）。"""

    def close(self, session_id: str) -> None:
        """结束会话并释放上下文（FR-009：不跨会话记忆）。"""
```

```python
@dataclass
class SessionConfig:
    max_questions_per_turn: int = 5      # FR-011，可配置
    default_article_count: int = 3       # FR-028
    max_article_count: int = 10          # FR-028

@dataclass
class Reply:
    content: str                 # 交付给用户的 Markdown
    intent: str | None           # "consult" / "article" / None（仍在确认）
    citations: list[Citation]    # 含每处引用的校验结论（data-model §1）
    question_count: int          # 本轮追问问题数
    raw_content: str | None      # 模型原始输出；仅在评测模式下返回
```

实现：

| 实现 | 说明 |
|---|---|
| `TrainedAssistant` | POC：自训模型，不检索 |
| `RetrievalAssistant` | 正式阶段：检索条款放入上下文 + 同一基座（未微调），作为对照组；POC 不实现 |

## 2. 模型端点

- 编排层通过 OpenAI 兼容的 Chat Completions 接口访问模型（POC：本机 `mlx_lm.server`；正式阶段可换 vLLM）。
- 配置项 `runtime.model_endpoint` 必须匹配白名单 `runtime.allowed_hosts`（默认 `127.0.0.1`、`localhost`），
  不匹配则拒绝启动（宪章原则 III、IV）。
- `temperature` 评测时固定为 0，交互时可配置。

## 3. 外部大模型客户端（仅离线）

- POC 只在 `synth`（数据合成）模块中使用；正式阶段 `eval`（评判模型、用户模拟器）也可使用。
- 配置项 `external_llm.base_url` / `external_llm.model` / API Key（从环境变量读取，不写入仓库）。
- 调用前校验输入只来自知识库公开文档或评测用例；编排层（运行时）代码不得导入该客户端（由测试检查）。
