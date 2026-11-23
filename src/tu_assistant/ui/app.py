"""Gradio 本地演示界面与纯 Python 会话控制器（T069、quickstart V6）。

合规与安全边界：
- 严禁导入 openai 或 tu_assistant.synth.*（持续通过 test_runtime_isolation.py）；
- 默认且仅允许监听 127.0.0.1，强制 share=False；
- 导入 gradio 前关闭遥测（GRADIO_ANALYTICS_ENABLED=False），使用系统字体零外链；
- 会话上下文仅驻留内存：点击「新会话」立即释放，关闭或刷新页面后最迟约 1 小时由框架回收
  （STATE_TTL_WHEN_CLOSED=3600），退出进程时全部清理。
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from ..chat.assistant import Assistant, SessionConfig

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

if TYPE_CHECKING:
    import gradio as gr

ALLOWED_UI_HOSTS: frozenset[str] = frozenset({"127.0.0.1"})

UI_CSS = """
.gradio-container {
    max-width: 960px !important;
    margin: 0 auto !important;
}
.tu-header-banner {
    border-bottom: 1px solid var(--border-color-primary);
    padding-bottom: 8px;
    margin-bottom: 6px;
}
.tu-status-bar {
    font-size: 0.92rem;
    color: var(--body-text-color-subdued);
}
"""


def validate_ui_host(host: str) -> str:
    """校验 UI 监听地址，严格仅允许 127.0.0.1（FR-033、T069）。"""
    if not isinstance(host, str) or host not in ALLOWED_UI_HOSTS:
        raise ValueError(
            f"演示界面仅允许监听 127.0.0.1，拒绝绑定非本机地址：{host!r}"
        )
    return host


@dataclass
class UISessionState:
    """单个浏览器标签页对应的内存会话状态（经 gr.State 隔离）。"""

    session_id: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    export_path: Path | None = None
    turn_count: int = 0


class ChatUIController:
    """不依赖 Gradio 组件类型的纯 Python UI 控制器。

    只通过 Assistant 协议交互，负责：
    - 多轮对话与空输入拦截
    - 会话懒创建、新会话重置与标签页关闭清理（FR-009）
    - 最新一轮回复导出为独立临时目录中的 UTF-8 Markdown 文件（FR-032）
    - 线程安全互斥锁与模型断连/超时友好中文兜底提示
    """

    def __init__(
        self,
        assistant: Assistant,
        session_config: SessionConfig | None = None,
        *,
        kb_version: str | None = None,
        model_endpoint: str | None = None,
        export_dir: Path | None = None,
    ) -> None:
        self._assistant = assistant
        self._session_config = session_config or SessionConfig()
        self._kb_version = kb_version
        self._model_endpoint = model_endpoint
        self._lock = threading.Lock()
        self._active_sessions: dict[str, Path | None] = {}

        if export_dir is not None:
            self._tmp_dir: tempfile.TemporaryDirectory[str] | None = None
            self._export_dir = Path(export_dir)
            self._export_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._tmp_dir = tempfile.TemporaryDirectory(prefix="tu-assistant-ui-")
            self._export_dir = Path(self._tmp_dir.name)

    @property
    def export_dir(self) -> Path:
        return self._export_dir

    @property
    def kb_version(self) -> str | None:
        return self._kb_version

    @property
    def model_endpoint(self) -> str | None:
        return self._model_endpoint

    @property
    def session_config(self) -> SessionConfig:
        return self._session_config

    def _safe_unlink(self, path: Path | None) -> None:
        if path is None:
            return
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)

    def _format_error_status(self, exc: Exception) -> str:
        endpoint_hint = self._model_endpoint or "http://127.0.0.1:8080/v1"
        if isinstance(exc, httpx.ConnectError):
            return (
                f"**无法连接本地模型服务**（`{endpoint_hint}`）。"
                "请先在另一终端启动模型服务（例如 `uv run tu serve model --exp <exp_id>`），"
                "待就绪后直接重试发送。"
            )
        if isinstance(exc, httpx.TimeoutException):
            return (
                f"**本地模型服务响应超时**（`{endpoint_hint}`）。"
                "7B 模型生成较长回复可能需要 30–60 秒，请确认服务正常运行后重试。"
            )
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code if exc.response is not None else "未知"
            return (
                f"**本地模型服务返回异常状态（HTTP {code}）**。"
                "请检查 `tu serve model` 终端日志后重试。"
            )
        if isinstance(exc, sqlite3.Error):
            return (
                f"**本地知识库读取失败**（{type(exc).__name__}: {exc}）。"
                "请检查知识库文件状态后重试。"
            )
        return (
            f"**请求处理失败**：{type(exc).__name__}: {exc}。"
            "请检查本地模型服务状态后重试。"
        )

    def _write_export_locked(self, state: UISessionState) -> Path | None:
        if state.session_id is None:
            return None
        md = self._assistant.export_markdown(state.session_id)
        if not md:
            self._safe_unlink(state.export_path)
            state.export_path = None
            self._active_sessions[state.session_id] = None
            return None

        old_path = state.export_path
        turn_no = max(state.turn_count, 1)
        new_path = self._export_dir / f"tu-reply-{state.session_id}-turn{turn_no}.md"
        new_path.write_text(md, encoding="utf-8")
        if old_path is not None and old_path != new_path:
            self._safe_unlink(old_path)
        state.export_path = new_path
        self._active_sessions[state.session_id] = new_path
        return new_path

    def _cleanup_session_locked(self, state: UISessionState | None) -> None:
        if state is None:
            return
        sid = state.session_id
        path = state.export_path
        if sid is not None and sid in self._active_sessions:
            tracked_path = self._active_sessions.pop(sid)
            if tracked_path is not None and tracked_path != path:
                self._safe_unlink(tracked_path)
            with contextlib.suppress(Exception):
                self._assistant.close(sid)
        self._safe_unlink(path)
        state.session_id = None
        state.export_path = None

    def send_message(
        self,
        state: UISessionState | None,
        message: str,
    ) -> tuple[UISessionState, list[dict[str, str]], str, str | None, str]:
        """处理一次用户发送，返回 (state, chatbot_history, textbox_val, export_file, status_md)。"""
        with self._lock:
            cur = state if state is not None else UISessionState()
            existing_export = (
                str(cur.export_path)
                if cur.export_path is not None and cur.export_path.is_file()
                else None
            )
            user_text = (message or "").strip()
            if not user_text:
                return (
                    cur,
                    [dict(m) for m in cur.history],
                    "",
                    existing_export,
                    "请输入问题或需求后再发送。",
                )

            if cur.session_id is None:
                cur.session_id = self._assistant.new_session(self._session_config)
                self._active_sessions[cur.session_id] = None

            try:
                reply = self._assistant.send(cur.session_id, user_text)
            except (
                httpx.HTTPError,
                sqlite3.Error,
                RuntimeError,
                OSError,
                ValueError,
                KeyError,
                IndexError,
            ) as exc:
                return (
                    cur,
                    [dict(m) for m in cur.history],
                    message,
                    existing_export,
                    self._format_error_status(exc),
                )

            cur.history.append({"role": "user", "content": user_text})
            cur.history.append({"role": "assistant", "content": reply.content})
            cur.turn_count += 1
            export_path = self._write_export_locked(cur)
            export_str = str(export_path) if export_path is not None else None
            status_md = (
                f"已完成第 {cur.turn_count} 轮回复。"
                "点击「保存当前回复为 Markdown」可下载本轮回复。"
                if export_str is not None
                else f"已完成第 {cur.turn_count} 轮回复。"
            )
            return (
                cur,
                [dict(m) for m in cur.history],
                "",
                export_str,
                status_md,
            )

    def export_current_reply(
        self,
        state: UISessionState | None,
    ) -> tuple[UISessionState, Path | None, str]:
        """导出当前会话最新一轮助手回复到隔离临时目录中的 .md 文件。"""
        with self._lock:
            cur = state if state is not None else UISessionState()
            if cur.session_id is None or cur.turn_count == 0:
                return cur, None, "当前会话暂无可保存的回复。"
            path = self._write_export_locked(cur)
            if path is None:
                return cur, None, "当前会话暂无可保存的回复。"
            return cur, path, f"已准备 Markdown 导出文件：`{path.name}`。"

    def reset_session(
        self,
        state: UISessionState | None,
    ) -> tuple[UISessionState, list[dict[str, str]], str, None, str]:
        """释放当前会话并开启全新空白会话（FR-009）。"""
        with self._lock:
            self._cleanup_session_locked(state)
            return (
                UISessionState(),
                [],
                "",
                None,
                "已开启新会话（上一会话上下文已从内存释放）。",
            )

    def cleanup_session(self, state: UISessionState | None) -> None:
        """供 gr.State(delete_callback=...) 在会话过期回收时调用。

        Gradio 的 _delete_state 在 asyncio 事件循环线程同步触发本回调，因此不得阻塞等锁：
        若拿不到互斥锁（如另一标签页正在生成回复），交由守护线程异步清理。
        """
        if state is None:
            return
        if self._lock.acquire(blocking=False):
            try:
                self._cleanup_session_locked(state)
            finally:
                self._lock.release()
            return

        def _deferred_cleanup() -> None:
            with self._lock:
                self._cleanup_session_locked(state)

        threading.Thread(
            target=_deferred_cleanup,
            name="tu-ui-cleanup",
            daemon=True,
        ).start()

    def cleanup_all(self) -> None:
        """进程退出时释放全部残留会话并销毁临时导出目录。"""
        with self._lock:
            sids = list(self._active_sessions.items())
            self._active_sessions.clear()
            for sid, path in sids:
                with contextlib.suppress(Exception):
                    self._assistant.close(sid)
                self._safe_unlink(path)
            if self._tmp_dir is not None:
                with contextlib.suppress(OSError):
                    self._tmp_dir.cleanup()
                self._tmp_dir = None


def build_ui_theme() -> Any:
    """构造零外部字体请求的本机系统字体 Gradio 主题。"""
    import gradio as gr

    return gr.themes.Soft(
        font=[gr.themes.Font("system-ui"), "sans-serif"],
        font_mono=[gr.themes.Font("ui-monospace"), "monospace"],
    )


def create_ui_app(controller: ChatUIController) -> gr.Blocks:
    """装配 Gradio 6 本地演示界面（零遥测、单并发队列、状态按标签页隔离）。"""
    import gradio as gr

    scfg = controller.session_config
    kb_label = controller.kb_version or "未指定"
    endpoint_label = controller.model_endpoint or "本地模型端点"
    header_md = (
        "## 工会法律条款智能助手（POC 本地演示）\n"
        f"知识库：`{kb_label}` ｜ 模型端点：`{endpoint_label}` ｜ "
        f"追问上限：{scfg.max_questions_per_turn} ｜ "
        f"默认文章篇数：{scfg.default_article_count}（上限 {scfg.max_article_count}）\n\n"
        "> 会话仅保存在本机内存中：点击「新会话」立即释放，"
        "关闭或刷新页面后最迟约 1 小时由框架回收，退出进程时全部清理；"
        "回答仅供参考，不构成法律意见。"
    )

    with gr.Blocks(
        title="工会法律条款智能助手（POC 演示）",
        analytics_enabled=False,
        delete_cache=(600, 7200),
    ) as demo:
        state = gr.State(value=None, delete_callback=controller.cleanup_session)

        gr.Markdown(header_md, elem_classes=["tu-header-banner"])

        chatbot = gr.Chatbot(
            label="对话记录",
            height=520,
            render_markdown=True,
            buttons=["copy"],
            autoscroll=True,
            placeholder=(
                "请输入工会法律咨询问题或普法文章需求，例如：我们单位领导不让搞工会"
            ),
        )

        with gr.Row():
            msg_box = gr.Textbox(
                lines=2,
                max_lines=6,
                show_label=False,
                placeholder="输入消息，按 Enter 发送（Shift+Enter 换行）",
                scale=8,
            )
            send_btn = gr.Button("发送", variant="primary", scale=1)

        with gr.Row():
            new_btn = gr.Button("新会话", variant="secondary", scale=1)
            download_btn = gr.DownloadButton(
                "保存当前回复为 Markdown",
                variant="secondary",
                interactive=False,
                scale=2,
            )
            status_md = gr.Markdown(
                "就绪。请输入问题开始对话。",
                elem_classes=["tu-status-bar"],
            )

        def _on_send(
            cur_state: UISessionState | None,
            message: str,
        ) -> tuple[UISessionState, list[dict[str, str]], str, Any, str]:
            new_state, history, cleared_input, export_file, status = (
                controller.send_message(cur_state, message)
            )
            dl_update = gr.update(
                value=export_file,
                interactive=bool(export_file),
            )
            return new_state, history, cleared_input, dl_update, status

        def _on_reset(
            cur_state: UISessionState | None,
        ) -> tuple[UISessionState, list[dict[str, str]], str, Any, str]:
            new_state, history, cleared_input, _export_file, status = (
                controller.reset_session(cur_state)
            )
            dl_update = gr.update(value=None, interactive=False)
            return new_state, history, cleared_input, dl_update, status

        msg_box.submit(
            _on_send,
            inputs=[state, msg_box],
            outputs=[state, chatbot, msg_box, download_btn, status_md],
        )
        send_btn.click(
            _on_send,
            inputs=[state, msg_box],
            outputs=[state, chatbot, msg_box, download_btn, status_md],
        )
        new_btn.click(
            _on_reset,
            inputs=[state],
            outputs=[state, chatbot, msg_box, download_btn, status_md],
        )

    demo.queue(default_concurrency_limit=1)
    return demo


def launch_ui(
    demo: gr.Blocks,
    *,
    host: str = "127.0.0.1",
    port: int = 7860,
    inbrowser: bool = False,
) -> Any:
    """以安全本地参数启动 Gradio 演示界面（严禁公网共享与外链静态资源）。"""
    safe_host = validate_ui_host(host)
    return demo.launch(
        server_name=safe_host,
        server_port=port,
        share=False,
        inbrowser=inbrowser,
        footer_links=[],
        theme=build_ui_theme(),
        css=UI_CSS,
    )
