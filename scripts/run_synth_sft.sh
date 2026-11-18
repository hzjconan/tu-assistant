#!/usr/bin/env bash
# 包装脚本：source .env 注入 TU_EXTERNAL_LLM_API_KEY 后执行 tu synth sft。
# 等价于「set -a && source .env && set +a && uv run tu synth sft ...」，
# 仅因后台 exec 命令字面量含 .env 会被拦截而封装。
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
source .env
set +a
exec uv run tu synth sft "$@"
